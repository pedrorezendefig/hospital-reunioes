"""A IA de Contas médicas: a migration 117 e o adaptador (issue #1130, PRD #1128).

O adaptador é a única porta do módulo para a IA: toda chamada sai com saída
estruturada estrita, sem retenção do texto no provedor, com cache da instrução
e da memória quando o modelo é Anthropic, e com o custo gravado.

Os testes do adaptador conversam com o SDK de verdade e trocam só o transporte
HTTP (`httpx.MockTransport`): o que eles leem é o corpo JSON que sairia para o
OpenRouter, e nenhum deles chega à rede (a trava da suíte, `conftest.py`,
reprova quem tentar).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings  # noqa: E402
from app.services.contas_medicas import ia  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_117 = MIGRATIONS / "117_contas_medicas_ia.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 117
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_117.read_text(encoding="utf-8")


def _colunas_da_tabela(sql: str, tabela: str) -> set[str]:
    bloco = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\);", sql, flags=re.DOTALL)
    assert bloco, f"a 117 nao cria {tabela}"
    return {linha.split()[0] for linha in bloco.group(1).splitlines() if linha.strip() and linha.strip()[0].isalpha()}


def _valores_do_check(sql: str, constraint: str) -> set[str]:
    bloco = re.search(rf"ADD CONSTRAINT {constraint}\s+CHECK \((.*?)\);", sql, flags=re.DOTALL)
    assert bloco, f"a 117 nao refaz o CHECK {constraint}"
    return set(re.findall(r"'(\w+)'", bloco.group(1)))


class TestMigration117:
    def test_cria_a_chamada_de_ia_com_o_custo_de_cada_chamada(self):
        colunas = _colunas_da_tabela(_sql(), "cm_chamada_ia")

        assert {
            "conta_id",
            "atendimento_id",
            "passo",
            "modelo",
            "tokens_entrada",
            "tokens_saida",
            "tokens_cache",
            "custo_usd",
            "duracao_ms",
            "tentativas",
            "criado_em",
        } <= colunas

    def test_cria_a_linha_de_formulario_aprendida(self):
        assert {"familia", "linha", "contagem"} <= _colunas_da_tabela(_sql(), "cm_linha_formulario")

    def test_o_nivel_de_evidencia_aceita_prescrito_se_necessario(self):
        assert _valores_do_check(_sql(), "cm_guia_linha_nivel_evidencia_check") == {
            "REGISTRADO",
            "PRESCRITO",
            "PRESCRITO_SN",
            "POR_REGRA",
        }

    def test_a_conta_ganha_a_nota_de_saida_e_a_data_do_reenvio(self):
        sql = _sql()

        assert re.search(r"ALTER TABLE cm_conta\s+ADD COLUMN IF NOT EXISTS nota_saida NUMERIC", sql)
        assert re.search(r"ALTER TABLE cm_conta\s+ADD COLUMN IF NOT EXISTS reenviada_em TIMESTAMPTZ", sql)

    def test_o_dicionario_aceita_a_proposta_da_ia(self):
        sql = _sql()

        assert "PROPOSTO" in _valores_do_check(sql, "cm_item_dicionario_situacao_check")
        assert "IA" in _valores_do_check(sql, "cm_item_dicionario_origem_check")

    def test_indice_do_guia_por_causa_raiz_e_data(self):
        assert re.search(r"CREATE INDEX IF NOT EXISTS \w+\s+ON cm_guia_linha \(causa_raiz, data\)", _sql())

    def test_rls_nas_tabelas_novas(self):
        sql = _sql()

        for tabela in ("cm_chamada_ia", "cm_linha_formulario"):
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = "\n".join(linha for linha in _sql().splitlines() if not linha.startswith("--")).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (117) ON CONFLICT (numero) DO NOTHING;")


# ═══════════════════════════════════════════════════════════════════════════
# O provedor e o banco de mentira
# ═══════════════════════════════════════════════════════════════════════════

EVENTOS_VALIDOS = {
    "atendimento": "31245",
    "idade_anos": 67,
    "movimentacoes": [
        {
            "tipo": "INTERNACAO",
            "data_hora": "2026-10-03T21:45",
            "setor": "CTI ADULTO",
            "pagina": 2,
            "trecho": "Admitido no CTI às 21h45",
        }
    ],
    "terapias": [],
    "prescricoes": [],
    "procedimentos": [],
    "cirurgias": [],
    "documentos_ausentes": [],
    "observacoes": [],
}

LINHAS_VALIDAS = {
    "linhas": [
        {
            "acao": "INCLUIR",
            "data": "2026-10-03",
            "data_fim": "2026-10-05",
            "setor": "CTI ADULTO",
            "codigo": "70802726",
            "descricao": "Luva de procedimento",
            "quantidade_lancada": 0,
            "quantidade_devida": 180,
            "regra_id": "ASSIM-INS-33",
            "motivo": "60 por dia, de 03 a 05/10 · 3 diárias de CTI pagas",
            "evidencia": {"pagina": 2, "trecho": "Admitido no CTI às 21h45"},
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "REGRA_AUTOMATICA",
            "confianca": "ALTA",
        }
    ],
    "resumo": "Faltam as luvas do CTI.",
}

USO_PADRAO = {
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "total_tokens": 1200,
    "prompt_tokens_details": {"cached_tokens": 0},
    "cost": 0.01,
}


class _Provedor:
    """O OpenRouter do teste: guarda o corpo JSON de cada requisição e devolve
    as respostas na ordem; a última se repete."""

    def __init__(self):
        self.corpos: list[dict] = []
        self.respostas: list[tuple[str, dict]] = [(json.dumps(EVENTOS_VALIDOS), USO_PADRAO)]

    def responder(self, *respostas: tuple[str, dict] | httpx.Response) -> None:
        self.respostas = list(respostas)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.corpos.append(json.loads(request.content))
        resposta = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(resposta, httpx.Response):
            return resposta
        conteudo, uso = resposta
        return httpx.Response(
            200,
            json={
                "id": f"gen-{len(self.corpos)}",
                "object": "chat.completion",
                "created": 1,
                "model": self.corpos[-1]["model"],
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": conteudo}, "finish_reason": "stop"}
                ],
                "usage": uso,
            },
        )


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()

    def cliente():
        return OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        )

    monkeypatch.setattr(ia, "_cliente", cliente)
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


class _Consulta:
    def __init__(self, banco: _BancoDeCusto, nome: str):
        self._banco, self._nome = banco, nome
        self._filtros: list = []
        self._insert = self._update = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append((coluna, valor))
        return self

    def insert(self, linha):
        self._insert = linha
        return self

    def update(self, campos):
        self._update = campos
        return self

    def execute(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            tabela.append(dict(self._insert))
            return SimpleNamespace(data=[dict(self._insert)])
        casam = [linha for linha in tabela if all(linha.get(c) == v for c, v in self._filtros)]
        if self._update is not None:
            for linha in casam:
                linha.update(self._update)
        return SimpleNamespace(data=[dict(linha) for linha in casam])


class _BancoDeCusto:
    def __init__(self, contas: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {"cm_conta": contas or [], "cm_chamada_ia": []}

    def table(self, nome: str):
        return _Consulta(self, nome)


def _extrair(banco=None, conta_id="c1"):
    return ia.extrair_eventos(
        "[[PÁG 2 · EVOLUÇÃO MÉDICA · 03/10/2026 · CTI ADULTO]]\nAdmitido no CTI às 21h45",
        "ASSIM-PRI-01: identificar pelo atendimento.",
        supabase=banco or _BancoDeCusto(),
        conta_id=conta_id,
        atendimento_id="at-1",
    )


MEMORIA = "---\noperadora: ASSIM\n---\n\n## 1. PRINCÍPIOS\n\n| ID | Regra |\n|---|---|\n| ASSIM-PRI-01 | Atendimento |\n"


def _comparar(banco=None, conta_id="c1"):
    return ia.comparar_conta(
        MEMORIA,
        EVENTOS_VALIDOS,
        [{"data": "2026-10-03", "codigo": "70802726", "descricao": "LUVA", "quantidade": 0}],
        {"diarias_pagas": {"CTI ADULTO": ["2026-10-03", "2026-10-04", "2026-10-05"]}},
        supabase=banco or _BancoDeCusto(),
        conta_id=conta_id,
        atendimento_id="at-1",
    )


def _objetos_do_schema(no):
    """Todo objeto do JSON schema, em qualquer profundidade."""
    if isinstance(no, dict):
        if no.get("type") == "object":
            yield no
        for valor in no.values():
            yield from _objetos_do_schema(valor)
    elif isinstance(no, list):
        for valor in no:
            yield from _objetos_do_schema(valor)


# ═══════════════════════════════════════════════════════════════════════════
# 2. A requisição ao provedor
# ═══════════════════════════════════════════════════════════════════════════


class TestRequisicaoAoProvedor:
    def test_toda_chamada_sai_com_schema_estrito_sem_retencao_e_sem_coleta(self, provedor):
        provedor.responder((json.dumps(EVENTOS_VALIDOS), USO_PADRAO), (json.dumps(LINHAS_VALIDAS), USO_PADRAO))

        _extrair()
        _comparar()

        assert len(provedor.corpos) == 2
        for corpo in provedor.corpos:
            assert corpo["provider"] == {"require_parameters": True, "zdr": True, "data_collection": "deny"}
            formato = corpo["response_format"]
            assert formato["type"] == "json_schema"
            assert formato["json_schema"]["strict"] is True
            objetos = list(_objetos_do_schema(formato["json_schema"]["schema"]))
            assert objetos, "o schema tem que descrever objetos"
            for objeto in objetos:
                assert objeto["additionalProperties"] is False
                assert sorted(objeto["required"]) == sorted(objeto["properties"])
        passo_a, passo_b = (c["response_format"]["json_schema"]["schema"]["properties"] for c in provedor.corpos)
        assert {"movimentacoes", "terapias", "prescricoes", "procedimentos", "cirurgias"} <= set(passo_a)
        assert set(passo_b) == {"linhas", "resumo"}

    def test_modelo_anthropic_leva_a_instrucao_e_a_memoria_em_bloco_de_cache(self, provedor):
        provedor.responder((json.dumps(LINHAS_VALIDAS), USO_PADRAO))

        _comparar()

        (corpo,) = provedor.corpos
        assert corpo["model"].startswith("anthropic/")
        sistema, usuario = corpo["messages"]
        (instrucao,) = sistema["content"]
        assert instrucao["cache_control"] == {"type": "ephemeral"}
        assert "Você confere contas hospitalares" in instrucao["text"]
        assert 'Medicamento prescrito "se necessário" é sempre incluído.' in instrucao["text"]
        memoria, *resto = usuario["content"]
        assert memoria["cache_control"] == {"type": "ephemeral"}
        assert MEMORIA in memoria["text"]
        assert resto
        assert all("cache_control" not in bloco for bloco in resto)

    def test_modelo_que_nao_e_anthropic_nao_leva_bloco_de_cache(self, provedor):
        _extrair()

        (corpo,) = provedor.corpos
        assert not corpo["model"].startswith("anthropic/")
        assert "Você lê prontuários hospitalares" in corpo["messages"][0]["content"][0]["text"]
        assert "cache_control" not in json.dumps(corpo["messages"])


# ═══════════════════════════════════════════════════════════════════════════
# 3. A resposta fora do formato
# ═══════════════════════════════════════════════════════════════════════════


class TestRespostaForaDoFormato:
    def test_tres_respostas_fora_do_schema_levantam_o_erro_do_adaptador_com_espera_crescente(
        self, provedor, monkeypatch
    ):
        esperas: list[float] = []
        monkeypatch.setattr(ia, "_esperar", esperas.append)
        provedor.responder(('{"linhas": "não é lista", "resumo": "x"}', USO_PADRAO))

        with pytest.raises(ia.ErroDaIA):
            _comparar()

        assert len(provedor.corpos) == 3
        assert len(esperas) == 2
        assert 0 < esperas[0] < esperas[1]

    def test_a_segunda_tentativa_no_formato_vale(self, provedor):
        provedor.responder(("isto não é JSON", USO_PADRAO), (json.dumps(LINHAS_VALIDAS), USO_PADRAO))

        resultado = _comparar()

        assert len(provedor.corpos) == 2
        assert [linha.regra_id for linha in resultado.linhas] == ["ASSIM-INS-33"]

    def test_provedor_fora_do_ar_tambem_tem_tres_tentativas(self, provedor):
        provedor.responder(httpx.Response(503, json={"error": {"message": "sem provedor"}}))

        with pytest.raises(ia.ErroDaIA):
            _extrair()

        assert len(provedor.corpos) == 3
