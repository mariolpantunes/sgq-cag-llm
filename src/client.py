#!/usr/bin/env python3
# coding: utf-8

import csv
import logging
import argparse
import requests

import matplotlib.pyplot as plt
import json

from markdown_pdf import MarkdownPdf,Section


logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def main(args):
    logger.info(f'Load file {args.i}')

    observations = []
    with open(args.i, newline='', mode='r') as file:
        csvFile = csv.reader(file, delimiter=',')
        for line in csvFile:
            observations.append(line[0])

    logger.info(f'Query the service {args.u}')
    response = requests.post(args.u, timeout=None, 
    json = {'course':args.c, 'year':args.y, 'observations':observations})

    if not response.ok:
        logger.error(f"POST /report {response.status_code}: {response.reason}")
        quit()
        
    data = response.json()
    logger.info("POST /report 200 OK")
    logger.debug(json.dumps(data, indent=4))

    logger.info(f'Plot the sentiment analysis')
    colors = ['lightcoral', 'lightskyblue', 'lightgreen']  # One color for each bar
    categories = ['Negativo', 'Neutro', 'Positivo']
    logger.info
    values = [data['sentiment'][k] for k in data['sentiment']]
    plt.bar(categories, values, color=colors)
    plt.title('Distribuição dos sentimentos')
    plt.xlabel('Pontuação de sentimento')
    plt.ylabel('Frequência')
    plt.savefig('sentiment.png', dpi=300)

    logger.info(f'Generate the Report')

    texto_pdf = f'''## Sumário Executivo - Avaliação da Disciplina de {args.c} ({args.y})\n\n
### Objetivo
Este relatório resume os principais pontos positivos e negativos identificados nas 
respostas dos alunos à disciplina de {args.c}, com base numa análise de conteúdo textual e sentimentos.
### Pontos positivos
{str(data['positive'])}
### Pontos a melhorar
{str(data['negative'])}
### Distribuição dos sentimentos
![Distribuição de sentimentos](sentiment.png)'''
    pdf = MarkdownPdf(toc_level=0, optimize=True)
    pdf.add_section(Section(texto_pdf))
    pdf.save("report.pdf")
    logger.info(texto_pdf)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SGQ-CAG-LLM client')
    parser.add_argument('-i', type=str, required=True, help='input file')
    parser.add_argument('-u', type=str, default='http://127.0.0.1:80/report', help='service url')
    parser.add_argument('-c', type=str, default='Cálculo 1', help='course')
    parser.add_argument('-y', type=int, default=2025, help='year')
    args = parser.parse_args()
    
    main(args)