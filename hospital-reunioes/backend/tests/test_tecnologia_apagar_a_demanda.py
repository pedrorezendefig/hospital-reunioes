"""Apagar a Demanda, e a migration da ADR 0084 (issue #1549, PRD #1548).

Um pedido que não vale mais sai da lista da Tecnologia. Só se apaga até
Planejada: a conversa Registrada, quem apaga é o autor; o card criado (Em
análise ou Planejada), só o Desenvolvedor. De Em desenvolvimento em diante, o
app recusa.

No GitHub a issue-raiz e as partes abertas fecham como "not_planned", com um
comentário de motivo, e a issue nunca é apagada. No app a Demanda vira lápide:
a linha fica, com `apagada_em` e `apagada_por`, para o webhook reconhecer a
issue; a conversa, o planejamento e a Conversa da Demanda saem, e os anexos
saem do bucket.

Tudo pela ROTA, no molde de `test_tecnologia_conversa_da_demanda`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_anexos import BUCKET, _StorageFake  # noqa: E402
from test_tecnologia_vinculo import (  # noqa: E402
    BASE,
    DIRETOR,
    PEDRO,
    _demanda,
    _GithubFalso,
    _integracao_configurada,  # noqa: F401
    _issue,
    _montar,
    _pessoa,
    _sem_github_de_verdade,  # noqa: F401
)

from app.limiter import limiter  # noqa: E402
from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPA_REGISTRADA,
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_130 = MIGRATIONS / "130_tecnologia_adr_0084.sql"

# Outra pessoa da diretoria: Super admin sem login do GitHub, que não é autor.
OUTRO_DIRETOR = _pessoa("P3", "Outro Diretor")

DEMANDA = "d-1"
APAGAR = f"{BASE}/chat/{DEMANDA}"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _conversa_registrada(**campos) -> dict:
    """A conversa do DIRETOR que ainda não virou card."""
    return _demanda(DEMANDA, autor_id=DIRETOR["id"], responsavel_id=None, etapa=ETAPA_REGISTRADA, **campos)


def _card(etapa: str = ETAPA_EM_ANALISE, **campos) -> dict:
    """O card do DIRETOR, já criado no GitHub como a issue #900."""
    base = {"autor_id": DIRETOR["id"], "responsavel_id": PEDRO["id"], "github_issue_numero": 900, "etapa": etapa}
    return _demanda(DEMANDA, **{**base, **campos})


class _GithubQueFecha(_GithubFalso):
    """O GitHub falso que também fecha issue, e grava cada fechamento na ordem:
    (número, motivo, comentário)."""

    def __init__(self, *a, erro_ao_fechar: Exception | None = None, **kw):
        super().__init__(*a, **kw)
        self.erro_ao_fechar = erro_ao_fechar
        self.fechadas: list[tuple[int, str, str]] = []

    def fechar_como_nao_planejada(self, numero: int, *, comentario: str) -> None:
        if self.erro_ao_fechar is not None:
            raise self.erro_ao_fechar
        self.fechadas.append((numero, "not_planned", comentario))


def _parte(numero: int, *, estado: str = "open") -> dict:
    return {**_issue(numero, estado=estado), "title": f"Parte {numero}"}


def _github_do_card() -> _GithubQueFecha:
    """A issue-raiz #900 com duas partes abertas e uma já fechada."""
    return _GithubQueFecha(
        {900: _issue(900)},
        sub_issues={900: [_parte(901), _parte(902), _parte(903, estado="closed")]},
    )


def _cenario(monkeypatch, *, logado: dict, demanda: dict, github: _GithubFalso | None = None):
    """A Demanda com a conversa, o planejamento, a Conversa da Demanda e um
    anexo no bucket: tudo o que o Apagar leva junto."""
    github = github or _github_do_card()
    client, sb, gh = _montar(
        logado=logado,
        participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR],
        demandas=[demanda],
        github=github,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(github_client, "fechar_como_nao_planejada", gh.fechar_como_nao_planejada, raising=False)
    sb.storage = _StorageFake()
    caminho = f"demanda-{DEMANDA}/sorteado1.png"
    sb.storage.arquivos[f"{BUCKET}/{caminho}"] = b"png"
    sb.tabelas["tecnologia_anexos"] = [
        {
            "id": "a-1",
            "demanda_id": DEMANDA,
            "ordem": 1,
            "storage_path": caminho,
            "nome_original": "print.png",
            "content_type": "image/png",
            "tamanho_bytes": 3,
            "anexado_por": DIRETOR["id"],
            "apagado_em": None,
        }
    ]
    sb.tabelas["tecnologia_planejamentos"] = [
        {"id": "p-1", "demanda_id": DEMANDA, "estado": "em_andamento", "mensagens": [{"tipo": "ia", "texto": "Oi"}]}
    ]
    sb.tabelas["tecnologia_conversa_da_demanda"] = [
        {"id": "c-1", "demanda_id": DEMANDA, "autor_id": DIRETOR["id"], "texto": "Alguma novidade?"}
    ]
    return client, sb, gh


def _a_demanda(sb) -> dict:
    return sb.tabelas["tecnologia_demandas"][0]


def _nada_foi_apagado(sb) -> None:
    demanda = _a_demanda(sb)
    assert demanda.get("apagada_em") is None
    assert demanda.get("apagada_por") is None
    assert len(sb.tabelas["tecnologia_planejamentos"]) == 1
    assert len(sb.tabelas["tecnologia_conversa_da_demanda"]) == 1
    assert len(sb.storage.arquivos) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 130
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_130.read_text(encoding="utf-8")


def _sem_comentarios() -> str:
    return "\n".join(linha for linha in _sql().splitlines() if not linha.lstrip().startswith("--"))


class TestMigration:
    def test_cria_as_colunas_da_demanda_e_do_planejamento_da_adr_0084(self):
        sql = _sem_comentarios()

        for tabela, colunas in (
            (
                "tecnologia_demandas",
                ("origem", "apagada_em", "apagada_por", "em_producao_em", "demonstracao_url", "demonstracao_em"),
            ),
            ("tecnologia_planejamentos", ("documento", "revisao_iniciada_em", "revisao_por", "revisao_versao_base")),
        ):
            for coluna in colunas:
                assert re.search(
                    rf"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} ", sql
                ), f"{tabela}.{coluna}"

    def test_a_origem_nasce_diretor_e_so_aceita_diretor_ou_vitta(self):
        sql = _sem_comentarios()

        assert "ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'diretor';" in sql
        check = sql[sql.index("ADD CONSTRAINT tecnologia_demandas_origem_check") :].split(";", 1)[0]
        assert "origem IN ('diretor', 'vitta')" in check

    def test_o_turno_do_planejamento_diz_quem_respondeu(self):
        """Os turnos moram no JSONB `mensagens`: o contrato do campo novo fica
        no comentário da coluna, como a migration 127 fez com `documentos`."""
        sql = _sql()
        comentario = sql[sql.index("COMMENT ON COLUMN tecnologia_planejamentos.mensagens IS") :].split("';", 1)[0]

        assert "respondido_por" in comentario

    def test_nenhuma_tabela_nova_nem_policy(self):
        sql = _sem_comentarios().upper()

        assert "CREATE TABLE" not in sql
        assert "CREATE POLICY" not in sql

    def test_termina_com_o_recibo_do_proprio_numero(self):
        assert _sem_comentarios().strip().endswith(
            "INSERT INTO migracoes_aplicadas (numero) VALUES (130) ON CONFLICT (numero) DO NOTHING;"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Quem apaga a conversa Registrada
# ═══════════════════════════════════════════════════════════════════════════


class TestAConversaRegistrada:
    def test_o_autor_apaga_a_propria_conversa_registrada(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch, logado=DIRETOR, demanda=_conversa_registrada())

        resposta = client.delete(APAGAR)

        assert resposta.status_code == 204, resposta.text
        demanda = _a_demanda(sb)
        assert demanda["apagada_em"]
        assert demanda["apagada_por"] == DIRETOR["id"]

    def test_outro_super_admin_sem_login_do_github_recebe_403(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch, logado=OUTRO_DIRETOR, demanda=_conversa_registrada())

        resposta = client.delete(APAGAR)

        assert resposta.status_code == 403
        _nada_foi_apagado(sb)

    def test_a_conversa_sem_card_nao_chama_o_github(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch, logado=DIRETOR, demanda=_conversa_registrada())

        assert client.delete(APAGAR).status_code == 204
        assert gh.fechadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Quem apaga o card criado, e até onde
# ═══════════════════════════════════════════════════════════════════════════


class TestOCardCriado:
    @pytest.mark.parametrize("etapa", [ETAPA_EM_ANALISE, ETAPA_PLANEJADA])
    def test_o_desenvolvedor_apaga_o_card_em_analise_e_planejado(self, monkeypatch, etapa):
        client, sb, _ = _cenario(monkeypatch, logado=PEDRO, demanda=_card(etapa))

        resposta = client.delete(APAGAR)

        assert resposta.status_code == 204, resposta.text
        assert _a_demanda(sb)["apagada_por"] == PEDRO["id"]

    @pytest.mark.parametrize(
        "etapa", [ETAPA_EM_DESENVOLVIMENTO, ETAPA_ENTREGUE, ETAPA_EM_PRODUCAO, ETAPA_NAO_SERA_FEITA]
    )
    def test_de_em_desenvolvimento_em_diante_o_app_recusa_com_409(self, monkeypatch, etapa):
        client, sb, gh = _cenario(monkeypatch, logado=PEDRO, demanda=_card(etapa))

        resposta = client.delete(APAGAR)

        assert resposta.status_code == 409
        assert gh.fechadas == []
        _nada_foi_apagado(sb)

    def test_o_autor_sem_login_do_github_nao_apaga_o_proprio_card(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch, logado=DIRETOR, demanda=_card(ETAPA_EM_ANALISE))

        resposta = client.delete(APAGAR)

        assert resposta.status_code == 403
        assert gh.fechadas == []
        _nada_foi_apagado(sb)


# ═══════════════════════════════════════════════════════════════════════════
# 4. O GitHub: a raiz e as partes abertas fecham como "not_planned"
# ═══════════════════════════════════════════════════════════════════════════


class TestNoGithub:
    def test_fecha_cada_parte_aberta_e_depois_a_raiz_com_comentario(self, monkeypatch):
        """As partes antes da raiz: se a raiz fechasse primeiro, o webhook dela
        moveria a Etapa para Não será feita e o Apagar de novo daria 409."""
        client, _, gh = _cenario(monkeypatch, logado=PEDRO, demanda=_card())

        assert client.delete(APAGAR).status_code == 204

        assert [(numero, motivo) for numero, motivo, _ in gh.fechadas] == [
            (901, "not_planned"),
            (902, "not_planned"),
            (900, "not_planned"),
        ]
        for _, _, comentario in gh.fechadas:
            assert comentario.splitlines()[0] == "<!-- automacao -->"
            assert "apagado" in comentario

    def test_o_cliente_comenta_e_depois_fecha_a_issue_como_nao_planejada(self, monkeypatch):
        """Um degrau abaixo do cliente falso: o cliente roda de verdade e só a
        rede é falsa, para ver o JSON que sai para o GitHub."""
        chamadas: list[tuple[str, str, dict | None]] = []

        def _rede(metodo, url, *, headers, json, timeout):
            chamadas.append((metodo, url, json))
            return httpx.Response(200, json={"number": 900}, request=httpx.Request(metodo, url))

        monkeypatch.setattr(github_client.httpx, "request", _rede)

        github_client.fechar_como_nao_planejada(900, comentario="motivo")

        issue = "https://api.github.com/repos/pedrorezendefig/hospital-reunioes/issues/900"
        assert chamadas == [
            ("POST", f"{issue}/comments", {"body": "motivo"}),
            ("PATCH", issue, {"state": "closed", "state_reason": "not_planned"}),
        ]
