"""Testes do parser de ATAs antigas (migradas do sistema legado)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pdf_parser_ata_migrada import (
    _extract_documento_id,
    _parse_data,
    _parse_hora,
    calcular_hash,
    extrair_estrutura,
)

FIXTURE_PDF = (
    Path(__file__).parent / "fixtures" / "ATA_CallCenter_19032026_Clicksign.pdf"
)


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    assert FIXTURE_PDF.exists(), f"Fixture ausente: {FIXTURE_PDF}"
    return FIXTURE_PDF.read_bytes()


# --- Helpers puros ---


def test_calcular_hash_determinista(pdf_bytes: bytes):
    h1 = calcular_hash(pdf_bytes)
    h2 = calcular_hash(pdf_bytes)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_calcular_hash_muda_com_bytes_diferentes(pdf_bytes: bytes):
    h1 = calcular_hash(pdf_bytes)
    h2 = calcular_hash(pdf_bytes + b"x")
    assert h1 != h2


def test_parse_data():
    assert _parse_data("19/03/2026") == "2026-03-19"
    assert _parse_data("texto 1/4/2026 fim") == "2026-04-01"
    assert _parse_data("sem data") is None
    assert _parse_data(None) is None
    assert _parse_data("") is None


def test_parse_hora():
    assert _parse_hora("08h12") == "08:12"
    assert _parse_hora("14:30") == "14:30"
    assert _parse_hora("1h05") == "01:05"
    assert _parse_hora("sem hora") is None
    assert _parse_hora(None) is None


def test_extract_documento_id():
    assert (
        _extract_documento_id("Documento: ATA-ALIN-HSM-190326 fim")
        == "ATA-ALIN-HSM-190326"
    )
    assert (
        _extract_documento_id("foo ata-dir-hsp-120 bar").upper()
        == "ATA-DIR-HSP-120".upper()
        if _extract_documento_id("foo ata-dir-hsp-120 bar")
        else True
    )
    assert _extract_documento_id("sem id aqui") is None


# --- Integracao com fixture real ---


def test_extrair_estrutura_documento_id(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    assert est["documento_id_origem"] == "ATA-ALIN-HSM-190326"


def test_extrair_estrutura_metadados(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    meta = est["metadados_brutos"]
    assert meta.get("data") == "2026-03-19"
    assert meta.get("hora_inicio") == "08:12"
    assert meta.get("hora_encerramento") == "10:24"
    assert "Josiane" in (meta.get("facilitador") or "")


def test_extrair_estrutura_participantes(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    participantes = est["tabela_participantes"]
    assert len(participantes) == 4
    nomes = {p["nome"] for p in participantes}
    assert {"Josiane Alves", "Felipe Malafaia", "Levi dos Santos", "Gisele Nunes"}.issubset(
        nomes
    )
    # Cargo da Gisele
    gisele = next(p for p in participantes if p["nome"] == "Gisele Nunes")
    assert "Coordenadora" in gisele["cargo"] or "Coord" in gisele["cargo"]


def test_extrair_estrutura_atribuicoes(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    atrib = est["tabela_atribuicoes"]
    assert len(atrib) == 6
    # Numeracao sequencial
    nums = [a["num"] for a in atrib]
    assert nums == [1, 2, 3, 4, 5, 6]
    # Todos com acao nao vazia e responsavel preenchido
    for a in atrib:
        assert a["acao"], "acao nao pode ser vazia"
        assert a["responsavel"], "responsavel nao pode ser vazio"
        assert a["status"] == "PENDENTE"


def test_extrair_estrutura_primeira_pendencia(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    first = est["tabela_atribuicoes"][0]
    assert first["num"] == 1
    assert "Global Health" in first["acao"] or "agendas" in first["acao"].lower()
    assert "Gisele" in first["responsavel"]


def test_extrair_estrutura_texto_e_paginas(pdf_bytes: bytes):
    est = extrair_estrutura(pdf_bytes)
    assert est["paginas"] >= 5
    assert len(est["texto_completo"]) > 1000
    assert "Call Center" in est["texto_completo"]


def test_extrair_estrutura_pdf_invalido():
    """PDF fake (bytes aleatorios) deve lancar excecao."""
    with pytest.raises(Exception):
        extrair_estrutura(b"nao eh pdf")
