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
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings  # noqa: E402
from app.services.contas_medicas import ia  # noqa: E402
from app.services.contas_medicas.memoria import ler_memoria  # noqa: E402
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria  # noqa: E402
from app.services.contas_medicas.operadoras import importar_memoria  # noqa: E402

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

    def test_a_linha_de_formulario_aceita_o_upsert_da_familia_composta(self):
        """Contrato com a #1132: `upsert(on_conflict="familia,linha")` pede o
        UNIQUE, e a família chega composta (`DOC_EDITOR|<título>`): texto livre,
        sem CHECK contra a lista de Famílias nem limite curto."""
        bloco = re.search(r"CREATE TABLE IF NOT EXISTS cm_linha_formulario \((.*?)\n\);", _sql(), flags=re.DOTALL)
        assert bloco
        corpo = bloco.group(1)

        assert re.search(r"UNIQUE \(familia, linha\)", corpo)
        (familia,) = [linha.strip() for linha in corpo.splitlines() if linha.strip().startswith("familia ")]
        assert re.fullmatch(r"familia\s+TEXT NOT NULL CHECK \(btrim\(familia\) <> ''\),", familia)

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


# Os DEFAULT das migrations que a importação deixa o banco preencher.
PADROES_DA_MIGRATION = {"cm_regra": {"ativa": True}}


class _Consulta:
    def __init__(self, banco: _BancoDeCusto, nome: str):
        self._banco, self._nome = banco, nome
        self._filtros: list = []
        self._ordem: str | None = None
        self._insert = self._update = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append((coluna, valor))
        return self

    def order(self, coluna, desc=False):
        self._ordem = coluna
        return self

    def insert(self, linhas):
        self._insert = linhas
        return self

    def update(self, campos):
        self._update = campos
        return self

    def execute(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            novas = [
                {
                    "id": f"{self._nome}-{len(tabela) + i}",
                    "criado_em": len(tabela) + i,
                    **PADROES_DA_MIGRATION.get(self._nome, {}),
                    **linha,
                }
                for i, linha in enumerate(self._insert if isinstance(self._insert, list) else [self._insert])
            ]
            tabela.extend(novas)
            return SimpleNamespace(data=[dict(linha) for linha in novas])
        casam = [linha for linha in tabela if all(linha.get(c) == v for c, v in self._filtros)]
        if self._update is not None:
            for linha in casam:
                linha.update(self._update)
        if self._ordem:
            casam.sort(key=lambda linha: linha.get(self._ordem))
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


MEMORIA = (
    "---\noperadora: ASSIM\n---\n\n## 1. PRINCÍPIOS\n\n| ID | Regra |\n|---|---|\n| ASSIM-PRI-01 | Atendimento |\n"
)


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

    def test_a_chamada_curta_usa_o_schema_de_quem_chama_e_grava_o_passo(self, provedor):
        class Proposta(BaseModel):
            codigo: str | None
            confianca: str

        banco = _BancoDeCusto([{"id": "c1"}])
        provedor.responder(('{"codigo": "90030001", "confianca": "MEDIA"}', USO_PADRAO))

        proposta = ia.chamada_curta(
            "Ache o código da conta para o termo.",
            "Termo: Clexane",
            Proposta,
            passo="DICIONARIO",
            supabase=banco,
            conta_id="c1",
        )

        assert proposta == Proposta(codigo="90030001", confianca="MEDIA")
        (corpo,) = provedor.corpos
        schema = corpo["response_format"]["json_schema"]["schema"]
        assert set(schema["properties"]) == {"codigo", "confianca"}
        assert corpo["provider"]["zdr"] is True
        (chamada,) = banco.tabelas["cm_chamada_ia"]
        assert (chamada["passo"], chamada["modelo"]) == ("DICIONARIO", corpo["model"])

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

    def test_o_motivo_da_linha_tem_ate_140_caracteres_no_schema_e_o_de_141_e_recusado(self, provedor):
        (linha,) = LINHAS_VALIDAS["linhas"]
        longa = {"linhas": [{**linha, "motivo": "x" * 141}], "resumo": "x"}
        no_limite = {"linhas": [{**linha, "motivo": "x" * 140}], "resumo": "x"}
        provedor.responder((json.dumps(longa), USO_PADRAO), (json.dumps(no_limite), USO_PADRAO))

        resultado = _comparar()

        # O schema do Anexo B limita o motivo a 140; o enviado ao provedor não
        # leva o limite, que a saída estrita da Anthropic recusa com 400 (quem
        # cobra é o Pydantic, e o prompt pede as 140).
        anexo_b = ia.LinhaDaComparacao.model_json_schema()["properties"]["motivo"]
        assert anexo_b["maxLength"] == 140
        enviado = provedor.corpos[0]["response_format"]["json_schema"]["schema"]
        assert enviado["properties"]["linhas"]["items"]["properties"]["motivo"] == {"type": "string"}
        # A primeira resposta, com 141, não passou no Pydantic; a de 140 vale.
        assert len(provedor.corpos) == 2
        assert [len(linha.motivo) for linha in resultado.linhas] == [140]

    def test_provedor_fora_do_ar_tambem_tem_tres_tentativas(self, provedor):
        provedor.responder(httpx.Response(503, json={"error": {"message": "sem provedor"}}))

        with pytest.raises(ia.ErroDaIA):
            _extrair()

        assert len(provedor.corpos) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 4. O custo de cada chamada
# ═══════════════════════════════════════════════════════════════════════════


def _uso(entrada: int, saida: int, cache: int, custo: float) -> dict:
    return {
        "prompt_tokens": entrada,
        "completion_tokens": saida,
        "total_tokens": entrada + saida,
        "prompt_tokens_details": {"cached_tokens": cache},
        "cost": custo,
    }


CAMPOS_DA_CHAMADA = (
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
    "sucesso",
)


class TestCustoDaChamada:
    def test_a_chamada_grava_tokens_cache_custo_e_duracao(self, provedor, monkeypatch):
        relogio = iter([100.0, 100.25])
        monkeypatch.setattr(ia, "perf_counter", lambda: next(relogio))
        banco = _BancoDeCusto([{"id": "c1"}])
        provedor.responder((json.dumps(LINHAS_VALIDAS), _uso(12000, 800, 11000, 0.0123)))

        _comparar(banco)

        (chamada,) = banco.tabelas["cm_chamada_ia"]
        assert {campo: chamada[campo] for campo in CAMPOS_DA_CHAMADA} == {
            "conta_id": "c1",
            "atendimento_id": "at-1",
            "passo": "B",
            "modelo": "anthropic/claude-sonnet-5.5",
            "tokens_entrada": 12000,
            "tokens_saida": 800,
            "tokens_cache": 11000,
            "custo_usd": 0.0123,
            "duracao_ms": 250,
            "tentativas": 1,
            "sucesso": True,
        }

    def test_uma_conta_com_duas_chamadas_mostra_a_soma(self, provedor):
        banco = _BancoDeCusto([{"id": "c1"}, {"id": "c2"}])
        provedor.responder(
            (json.dumps(EVENTOS_VALIDOS), _uso(3000, 500, 0, 0.0021)),
            (json.dumps(LINHAS_VALIDAS), _uso(12000, 800, 11000, 0.0123)),
        )

        _extrair(banco)
        _comparar(banco)

        conta, outra = banco.tabelas["cm_conta"]
        assert {k: conta[k] for k in ("tokens_entrada", "tokens_saida", "tokens_cache", "custo_usd")} == {
            "tokens_entrada": 15000,
            "tokens_saida": 1300,
            "tokens_cache": 11000,
            "custo_usd": 0.0144,
        }
        assert conta["modelo_ia"] == "google/gemini-3.7-flash, anthropic/claude-sonnet-5.5"
        assert outra == {"id": "c2"}

    def test_as_tentativas_fora_do_formato_tambem_custam(self, provedor):
        banco = _BancoDeCusto([{"id": "c1"}])
        provedor.responder(("não é JSON", _uso(1000, 10, 0, 0.001)))

        with pytest.raises(ia.ErroDaIA):
            _extrair(banco)

        (chamada,) = banco.tabelas["cm_chamada_ia"]
        assert (chamada["passo"], chamada["tentativas"], chamada["sucesso"]) == ("A", 3, False)
        assert (chamada["tokens_entrada"], chamada["custo_usd"]) == (3000, 0.003)
        assert banco.tabelas["cm_conta"][0]["custo_usd"] == 0.003


# ═══════════════════════════════════════════════════════════════════════════
# 5. O modelo de cada passo
# ═══════════════════════════════════════════════════════════════════════════


class TestModeloDeCadaPasso:
    def test_trocar_a_variavel_troca_o_modelo_da_requisicao(self, provedor, monkeypatch):
        monkeypatch.setenv("CM_IA_MODELO_PASSO_A", "openai/modelo-do-passo-a")
        monkeypatch.setenv("CM_IA_MODELO_PASSO_B", "google/modelo-do-passo-b")
        monkeypatch.setattr(ia, "settings", Settings())
        provedor.responder((json.dumps(EVENTOS_VALIDOS), USO_PADRAO), (json.dumps(LINHAS_VALIDAS), USO_PADRAO))

        _extrair()
        _comparar()

        assert [corpo["model"] for corpo in provedor.corpos] == ["openai/modelo-do-passo-a", "google/modelo-do-passo-b"]
        # Modelo que não é Anthropic no passo B: sem bloco de cache.
        assert "cache_control" not in json.dumps(provedor.corpos[1]["messages"])

    def test_sem_a_variavel_vale_o_flash_no_passo_a_e_o_sonnet_no_passo_b(self):
        assert Settings.model_fields["cm_ia_modelo_passo_a"].default == "google/gemini-3.7-flash"
        assert Settings.model_fields["cm_ia_modelo_passo_b"].default == "anthropic/claude-sonnet-5.5"


# ═══════════════════════════════════════════════════════════════════════════
# 6. O texto da memória gerado do banco
# ═══════════════════════════════════════════════════════════════════════════

MEMORIAS = Path(__file__).parent / "fixtures" / "contas_medicas" / "memoria"


def _importar(banco: _BancoDeCusto, arquivo: str) -> str:
    """Importa pelo caminho da tela Operadoras e devolve o id da operadora."""
    texto = (MEMORIAS / arquivo).read_text(encoding="utf-8")
    importar_memoria(banco, ler_memoria(texto), texto, None)
    (operadora,) = [o for o in banco.tabelas["cm_operadora"] if o["sigla"] == ler_memoria(texto).sigla]
    return operadora["id"]


def _regras_por_codigo(memoria) -> list:
    return sorted(memoria.regras, key=lambda regra: regra.codigo)


class TestTextoDaMemoria:
    def test_o_texto_gerado_do_banco_e_igual_ao_arquivo_importado(self):
        banco = _BancoDeCusto()
        operadora_id = _importar(banco, "MEMORIA-GAMA-v2.0.md")

        gerado = gerar_texto_memoria(banco, operadora_id)

        assert gerado == (MEMORIAS / "MEMORIA-GAMA-v2.0.md").read_text(encoding="utf-8")

    @pytest.mark.parametrize("arquivo", ["MEMORIA-ALFA-v1.0.md", "MEMORIA-BETA-v1.0.md"])
    def test_ida_e_volta_de_um_arquivo_do_diretor_nao_perde_regra_nem_parametro(self, arquivo):
        """O arquivo do diretor tem texto solto, comentário no cabeçalho e
        tabela com colunas próprias (a regra da BETA vira texto de várias
        linhas): o gerado é outro texto, a memória lida é a mesma."""
        banco = _BancoDeCusto()
        operadora_id = _importar(banco, arquivo)
        original = ler_memoria((MEMORIAS / arquivo).read_text(encoding="utf-8"))

        relida = ler_memoria(gerar_texto_memoria(banco, operadora_id))

        assert (relida.sigla, relida.nome, relida.versao, relida.situacao) == (
            original.sigla,
            original.nome,
            original.versao,
            original.situacao,
        )
        assert relida.parametros == original.parametros
        assert _regras_por_codigo(relida) == _regras_por_codigo(original)

    def test_a_regra_editada_no_banco_sai_no_texto(self):
        """É o texto do banco, e não o arquivo guardado: a regra mudada na tela
        vai para a IA como está agora."""
        banco = _BancoDeCusto()
        operadora_id = _importar(banco, "MEMORIA-GAMA-v2.0.md")
        regra = next(r for r in banco.tabelas["cm_regra"] if r["codigo"] == "GAMA-DIA-01")
        regra["texto"] = "A diária vence às 12h."

        relida = ler_memoria(gerar_texto_memoria(banco, operadora_id))

        assert next(r.texto for r in relida.regras if r.codigo == "GAMA-DIA-01") == "A diária vence às 12h."

    def test_a_versao_pedida_e_nao_a_vigente(self):
        banco = _BancoDeCusto()
        operadora_id = _importar(banco, "MEMORIA-GAMA-v2.0.md")
        (primeira,) = banco.tabelas["cm_memoria_versao"]
        texto_novo = (MEMORIAS / "MEMORIA-GAMA-v2.0.md").read_text(encoding="utf-8").replace("'2.0'", "'2.1'")
        importar_memoria(banco, ler_memoria(texto_novo), texto_novo, None)

        assert ler_memoria(gerar_texto_memoria(banco, operadora_id)).versao == "2.1"
        assert ler_memoria(gerar_texto_memoria(banco, operadora_id, primeira["id"])).versao == "2.0"


# ═══════════════════════════════════════════════════════════════════════════
# 7. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestKitDeConhecimento:
    """A sanidade geral do kit mora em `test_kit_conhecimento.py`; aqui, o que
    o texto tem que dizer da IA."""

    def test_diz_que_a_ia_entrou_o_que_ela_faz_e_que_o_custo_fica_gravado(self):
        secao = KIT.read_text(encoding="utf-8").split("## A inteligência artificial", 1)[1].split("\n## ", 1)[0]

        for trecho in (
            "lê o texto livre do prontuário",
            "compara",
            "memória da operadora",
            "não devolve valor em reais",
            "não guarda nada",
            "três vezes",
            "Tente de novo em alguns minutos",
            "O custo de cada chamada fica gravado",
            "Reanalisar",
        ):
            assert trecho in secao, trecho


# ═══════════════════════════════════════════════════════════════════════════
# 8. Tipografia
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]

ARQUIVOS_DA_FATIA = [
    MIGRATION_117,
    RAIZ_DO_APP / "backend/app/services/contas_medicas/ia.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/memoria_texto.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/memoria.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_passo_a.md",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_passo_b.md",
    RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_guia.py",
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/guia/[contaId]/page.tsx",
    MEMORIAS / "MEMORIA-GAMA-v2.0.md",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
