# coding: utf-8

import shutil
import logging
import pathlib
import markdown_to_json

from fastapi import FastAPI
from pydantic import BaseModel


from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, get_response_synthesizer
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
import ollama


logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


llm = Ollama(base_url="https://skynet.av.it.pt/ollama/", 
model="llama3.2:3b", 
request_timeout=1000, 
client=ollama.Client(host='https://skynet.av.it.pt/ollama/',
headers={'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjNiMGU3NWIwLWE4MDctNDIxYS1hYzc2LTk4YjE2YTI3NDA2YyJ9.B66iig8M8sgCl9q0fcflld9JqOZ-gg_jJoZXeaFO3Uk'}))

ollama_embedding = OllamaEmbedding(
model_name="llama3.2:3b",
request_timeout=1000,
base_url="https://skynet.av.it.pt/ollama/",
client_kwargs= {"headers" : {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjNiMGU3NWIwLWE4MDctNDIxYS1hYzc2LTk4YjE2YTI3NDA2YyJ9.B66iig8M8sgCl9q0fcflld9JqOZ-gg_jJoZXeaFO3Uk'}}        
)

text_splitter = SentenceSplitter(chunk_size=2048)

Settings.llm = llm
Settings.embed_model = ollama_embedding
Settings.transformations = [text_splitter]


class Data(BaseModel):
    course: str
    year: int
    observations: list


app = FastAPI()


@app.get('/')
async def root():
    with open('README.md') as f:
        txt = f.read()
        rv = markdown_to_json.dictify(txt)
    return rv


@app.post('/report')
async def report(data: Data):
    logger.info(f'Generate Report for {data.course} {data.year}')
    # Setup necessary folders
    logger.info('Setup necessary folders')
    ptxt = pathlib.Path('/tmp/text')
    ptxt.mkdir(parents=True, exist_ok=True)
    
    # Setup the documents to index
    logger.info('Setup the documents to index')
    course = data.course.lower().replace(' ', '_')
    for i in range(len(data.observations)):
        filepath = ptxt / f'{course}_{data.year}_{i}'
        with filepath.open('w', encoding ='utf-8') as f:
            f.write(f'Disciplina: {data.course}\n')
            f.write(f'Ano: {data.year}\n')
            f.write('Observações:\n')
            f.write(f'{data.observations[i]}')

    # Create the Vector Store
    logger.info('Create the Vector Store')
    documents = SimpleDirectoryReader(ptxt).load_data()
    index = VectorStoreIndex.from_documents(documents)
    
    # Query the LLM to build the report
    logger.info('Query the LLM to build the report')
    retriever = VectorIndexRetriever(index=index, similarity_top_k=len(data.observations))
    response_synthesizer = get_response_synthesizer(response_mode='compact')
    query_engine = RetrieverQueryEngine(retriever=retriever, response_synthesizer=response_synthesizer)

    prefix_prompt = f'''O contexto, pergunta e resposta estão escritos em Português de Portugal. 
Usando apenas os documentos da disciplina {data.course} do ano {data.year} e restringindo a resposta ao contexto anterior.'''
    
    suffix_prompt = 'Não deves mencionar o nome dos ficheiros na resposta.'

    structure_prompt = '''Deves de seguir a seguinte estrutura:
- <Sumário do Ponto> : <Trecho representativo>
- <Sumário do Ponto> : <Trecho representativo>
Não uses Markdown.
Não adiciones mais nenhum texto para além do apresentado acima
Identifica os trechos com o uso de aspas.
Não te esqueças de usar o : entre o sumário e o trecho'''
    
    positive_prompt = f'''{prefix_prompt} 
Apresenta entre 2 a 5 pontos positivos mais frequentemente mencionados no contexto.
Por cada ponto inclui um trecho representativo.
{suffix_prompt}
{structure_prompt}'''
    
    negative_prompt = f'''{prefix_prompt} 
Apresenta entre 2 a 5 pontos negativos mais frequentemente mencionados no contexto.
Por cada ponto inclui um trecho representativo.
{suffix_prompt}
{structure_prompt}'''

    sentiment_prompt = f'''{prefix_prompt}
Conte quantos documentos têm um sentimento positivo, neutro ou negativo.
Sabendo que existem {len(data.observations)}, a soma das contagens deve igualar {len(data.observations)}.
A reposta deve apresentar apenas a contagem de documentos que se insere em cada um dos sentimentos, estruturada no seguinte formato:
Negativo:<contagem>
Neutro:<contagem>
Positivo:<contagem>
Não adiciones mais nenhum texto para além do apresentado acima'''

    # Prepare the response
    logger.info('Prepare the response')
    positive_response = query_engine.query(positive_prompt)
    negative_response = query_engine.query(negative_prompt)
    sentiment_response = query_engine.query(sentiment_prompt)

    logger.debug(f'{positive_response}')
    logger.debug(f'{negative_response}')
    logger.debug(f'{sentiment_response}')

    sentiment = {}
    total = 0.0
    for line in sentiment_response.response.splitlines():
        values = line.split(':')
        n = float(values[1])
        total += n
        sentiment[values[0]] = n

    for k in sentiment:
        sentiment[k] /= total

    # Remove temp folders
    logger.info('Remove temp folders')
    shutil.rmtree(ptxt)
    
    logger.info('Send the response')
    return {'positive':positive_response.response,
    'negative': negative_response.response,
    'sentiment': sentiment}
