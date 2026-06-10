"""Testes para process_ata_migrada: valida fluxo mock e normalizacao de prazo."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_processor import _mock_ata_migrada, process_ata_migrada
from app.services.pdf_parser_ata_migrada import extrair_estrutura

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "ATA_CallCenter_19032026_Clicksign.pdf"


@pytest.fixture(scope="module")
def estrutura_real() -> dict:
    return extrair_estrutura(FIXTURE_PDF.read_bytes())


# --- Modo MOCK (sem chave do OpenRouter) ---


def test_mock_preserva_participantes(estrutura_real: dict):
    out = _mock_ata_migrada(estrutura_real)
    assert len(out["participantes"]) == 4
    nomes = {p["nome"] for p in out["participantes"]}
    assert "Josiane Alves" in nomes


def test_mock_preserva_atribuicoes(estrutura_real: dict):
    out = _mock_ata_migrada(estrutura_real)
    assert len(out["quadro_atribuicoes"]) == 6
    for a in out["quadro_atribuicoes"]:
        assert a["status"] == "PENDENTE"
        # prazo_original preservado sempre
        assert "prazo_original" in a


def test_mock_converte_prazo_data_iso(estrutura_real: dict):
    out = _mock_ata_migrada(estrutura_real)
    # primeira pendencia tem prazo "27/03/2026" no PDF
    primeira = out["quadro_atribuicoes"][0]
    assert primeira["prazo"] == "2026-03-27"
    assert primeira["prazo_original"] == "27/03/2026"


def test_mock_metadados_basicos(estrutura_real: dict):
    out = _mock_ata_migrada(estrutura_real)
    assert out["data"] == "2026-03-19"
    assert out["hora_inicio"] == "08:12"
    assert out["_mock"] is True


def test_mock_converte_prazo_30_dias():
    """Fake estrutura com pendencia de '30 dias' a partir de 2026-03-19."""
    estrutura = {
        "metadados_brutos": {"data": "2026-03-19"},
        "tabela_participantes": [],
        "tabela_atribuicoes": [
            {
                "num": 1,
                "acao": "X",
                "responsavel": "Y",
                "cargo": "",
                "prazo_original": "30 dias",
                "meta": "",
                "status": "PENDENTE",
            }
        ],
    }
    out = _mock_ata_migrada(estrutura)
    assert out["quadro_atribuicoes"][0]["prazo"] == "2026-04-18"


def test_mock_prazo_ambiguo_fica_null():
    estrutura = {
        "metadados_brutos": {"data": "2026-03-19"},
        "tabela_participantes": [],
        "tabela_atribuicoes": [
            {
                "num": 1,
                "acao": "X",
                "responsavel": "Y",
                "cargo": "",
                "prazo_original": "A definir",
                "meta": "",
                "status": "PENDENTE",
            }
        ],
    }
    out = _mock_ata_migrada(estrutura)
    assert out["quadro_atribuicoes"][0]["prazo"] is None
    assert out["quadro_atribuicoes"][0]["prazo_original"] == "A definir"


# --- process_ata_migrada com mock de OpenRouter ---


def test_process_usa_mock_quando_key_ausente(estrutura_real: dict, monkeypatch):
    """Sem OPENROUTER_API_KEY válida, retorna ata mock sem chamar LLM."""
    from app import config

    monkeypatch.setattr(config.settings, "openrouter_api_key", "")
    out = process_ata_migrada(estrutura_real, participantes_ativos_dir="")
    assert out.get("_mock") is True
    assert len(out["participantes"]) == 4


def test_process_chama_llm_via_openrouter_quando_key_presente(estrutura_real: dict, monkeypatch):
    """Com OPENROUTER_API_KEY válida, LLM é chamado via OpenRouter e resposta é parseada."""
    from app import config
    from app.services import ai_processor

    fake_response = {
        "titulo": "Call Center",
        "tipo": "Coordenação",
        "data": "2026-03-19",
        "hora_inicio": "08:12",
        "hora_fim": "10:24",
        "facilitador_nome": "Josiane Alves",
        "assunto": None,
        "objetivo": None,
        "participantes": [],
        "registro_narrativo": "",
        "resumo_executivo": "",
        "quadro_atribuicoes": [
            {
                "acao": "X",
                "responsavel": "Y",
                "cargo": "",
                "prazo": "19/03/2026",  # Formato BR — deve ser normalizado
                "prazo_original": "19/03/2026",
                "entregavel": "",
                "status": "PENDENTE",
            }
        ],
        "proxima_reuniao": None,
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(fake_response)))]
    )

    monkeypatch.setattr(config.settings, "openrouter_api_key", "sk-or-test-key-abcd")
    monkeypatch.setattr(ai_processor, "OpenAI", lambda **kwargs: mock_client)

    out = process_ata_migrada(estrutura_real, participantes_ativos_dir="")
    # prazo normalizado de 19/03/2026 para ISO
    assert out["quadro_atribuicoes"][0]["prazo"] == "2026-03-19"
    assert out["titulo"] == "Call Center"
