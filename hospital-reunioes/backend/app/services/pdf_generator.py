"""Serviço de Geração de PDF usando WeasyPrint."""

import copy
import io
import logging
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

logger = logging.getLogger(__name__)

# Configuração do Jinja2
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)


def formatar_data(data_str: str) -> str:
    """Formata data YYYY-MM-DD para DD/MM/YYYY"""
    if not data_str:
        return ""
    try:
        parts = data_str.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return data_str


# Adiciona filtros úteis ao Jinja
env.filters["formatar_data"] = formatar_data


def gerar_pdf_ata(reuniao_record: dict, json_ata: dict) -> bytes:
    """
    Recebe o registro da reunião e o dicionário json_ata,
    renderiza o template HTML e gera o PDF em memória.
    Retorna os bytes do PDF gerado.
    """
    try:
        json_ata = copy.deepcopy(json_ata)  # Protege o dict original de modificações in-place
        template = env.get_template("ata_template.html")

        # Formatar a data local e de geração para o PDF
        data_geracao = datetime.now().strftime("%d/%m/%Y às %H:%M")

        # Formata a data da reunião se estiver no formato YYYY-MM-DD
        reuniao_dict = dict(reuniao_record)
        if reuniao_dict.get("data"):
            reuniao_dict["data"] = formatar_data(str(reuniao_dict["data"]))

        # Formata o prazo no quadro de atribuições
        if "quadro_atribuicoes" in json_ata and isinstance(json_ata["quadro_atribuicoes"], list):
            for acao in json_ata["quadro_atribuicoes"]:
                if acao.get("prazo"):
                    acao["prazo"] = formatar_data(acao["prazo"])

        # Define o caminho para a logo
        logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "images", "logo_hospital.png")

        # Renderiza HTML
        html_content = template.render(
            reuniao=reuniao_dict, ata=json_ata, data_geracao=data_geracao, logo_path=f"file://{logo_path}"
        )

        # Converte HTML para PDF usando WeasyPrint em memória
        pdf_file = io.BytesIO()
        HTML(string=html_content).write_pdf(target=pdf_file)

        pdf_bytes = pdf_file.getvalue()
        logger.info(f"PDF gerado com sucesso para reunião {reuniao_dict.get('id_reuniao')} ({len(pdf_bytes)} bytes)")

        return pdf_bytes

    except Exception as e:
        logger.error(f"Erro ao gerar PDF da ata: {str(e)}")
        raise e
