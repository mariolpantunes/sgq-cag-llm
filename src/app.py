import logging
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# LlamaIndex Imports
from llama_index.core import VectorStoreIndex, Document, Settings, get_response_synthesizer
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
import ollama
import src.const as const

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --- Setup LlamaIndex Global Settings ---
# Note: Keep timeouts high for local LLM inference
llm = Ollama(
    base_url=const.base_url,
    model="llama3.2:3b",
    request_timeout=1000,
    client=ollama.Client(
        host='https://skynet.av.it.pt/ollama/',
        headers={'Authorization': const.token}
    )
)

ollama_embedding = OllamaEmbedding(
    model_name="llama3.2:3b",
    request_timeout=1000,
    base_url=const.base_url,
    client_kwargs={"headers": {'Authorization': const.token}}
)

text_splitter = SentenceSplitter(chunk_size=2048)

Settings.llm = llm
Settings.embed_model = ollama_embedding
Settings.transformations = [text_splitter]


class Data(BaseModel):
    course: str
    year: int
    observations: List[str] # Added explicit type hint for contents


app = FastAPI()

@app.get('/')
def root():
    # Changed to synchronous 'def' to prevent blocking event loop on file read
    # Or use aiofiles if you want to keep it async
    try:
        with open('README.md') as f:
            txt = f.read()
        # Assuming markdown_to_json is simple CPU bound, it's fine here
        import markdown_to_json
        rv = markdown_to_json.dictify(txt)
        return rv
    except FileNotFoundError:
        return {"error": "README.md not found"}


@app.post('/report')
async def report(data: Data):
    logger.info(f'Generate Report for {data.course} {data.year}')

    if not data.observations:
        return {"positive": "No data", "negative": "No data"}

    # 1. OPTIMIZATION: Create Documents in Memory (No disk I/O)
    documents = []
    for obs in data.observations:
        # Add metadata to help the LLM distinguish context if needed
        doc = Document(
            text=obs,
            metadata={
                "course": data.course,
                "year": data.year
            }
        )
        documents.append(doc)

    try:
        # 2. Create Vector Store (In-Memory)
        logger.info('Create the Vector Store')
        index = VectorStoreIndex.from_documents(documents)

        # 3. Retrieve
        # LIMITATION FIX: Don't retrieve len(observations) if it's huge.
        # Cap it at a reasonable number (e.g., 50) or use a SummaryIndex instead of VectorIndex
        # if you essentially want to summarize *everything*.
        top_k = min(len(data.observations), 50)

        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=top_k
        )

        response_synthesizer = get_response_synthesizer(response_mode='compact')
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer
        )

        # Prompts (Kept mostly same, formatted for readability)
        prefix_prompt = (
            f"O contexto, pergunta e resposta estão escritos em Português de Portugal.\n"
            f"Usando apenas os documentos da disciplina {data.course} do ano {data.year}."
        )

        structure_prompt = (
            "Deves seguir a seguinte estrutura:\n"
            "- <Sumário do Ponto> : \"<Trecho representativo>\"\n"
            "Não uses Markdown. Identifica os trechos com aspas."
        )

        positive_prompt = (
            f"{prefix_prompt}\n"
            f"Apresenta entre 2 a 5 pontos positivos mais frequentemente mencionados.\n"
            f"{structure_prompt}"
        )

        negative_prompt = (
            f"{prefix_prompt}\n"
            f"Apresenta entre 2 a 5 pontos negativos mais frequentemente mencionados.\n"
            f"{structure_prompt}"
        )

        # 4. Query
        logger.info('Querying LLM...')
        positive_response = query_engine.query(positive_prompt)
        negative_response = query_engine.query(negative_prompt)

        return {
            'positive': str(positive_response),
            'negative': str(negative_response)
        }

    except Exception as e:
        logger.error(f"Error processing report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # No 'finally' needed for cleanup because we didn't use the filesystem!