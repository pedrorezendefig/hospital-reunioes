"""Revisão com o código de hoje, o "Atualizar o card" (issue #1558, PRD #1548, ADR 0084, decisão 3).

No fim da revisão, o resumo da melhoria troca o "Criar o card" pelo
"Atualizar o card". Ele regrava o corpo da issue-raiz com o PRD revisado,
mantendo byte a byte o marcador da Demanda, deixa um comentário com o que
entrou e o que saiu do escopo, fecha as partes não começadas como
"not_planned" e troca a label da raiz para `needs-triage`, para um novo
`/to-issues`. A Etapa volta para Em análise. Falha do GitHub não grava nada no
app, e o botão vale de novo.

Tudo pela ROTA, com o GitHub dublado no molde de `test_tecnologia_revisao`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _conversas,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_revisao import (  # noqa: E402
    CONVERSA_ENVIADA,
    DEMANDA,
    ITEM_QUE_JA_EXISTE,
    OUTRO_DIRETOR,
    RESUMO_ENVIADO,
    _card,
)
from test_tecnologia_vinculo import (  # noqa: E402
    BASE,
    DIRETOR,
    PEDRO,
    _GithubFalso,
    _issue,
    _sem_github_de_verdade,  # noqa: F401
)

from app.services import github_client, tecnologia_revisao  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_PLANEJADA,
    corpo_do_prd_do_diretor,
    link_da_demanda,
)

ATUALIZAR = f"{BASE}/chat/{DEMANDA}/atualizar-card"

# O marcador como estava na issue, com espaços que o app nunca escreveria: é
# ele, e não o que o app escreve hoje, que tem de ficar no corpo regravado.
MARCADOR_DA_ISSUE = f'<!--   demanda-vitta id="{DEMANDA}"  -->'


def _corpo_antigo() -> str:
    corpo = corpo_do_prd_do_diretor(
        demanda_id=DEMANDA,
        titulo="Retorno marcado na saída",
        descricao="Quero marcar o retorno do paciente na saída.",
        resumo=RESUMO_ENVIADO,
        link=link_da_demanda(DEMANDA),
    )
    return corpo.replace(f'<!-- demanda-vitta id="{DEMANDA}" -->', MARCADOR_DA_ISSUE)


# O resumo refeito na revisão: a decisão de antes continua, entra uma nova, e o
# ponto em aberto de antes foi respondido e sai.
RESUMO_REVISADO = {
    "decisoes": [
        {"pergunta": "Quem marca o retorno?", "escolha": "Só a recepção.", "porque": "É quem atende."},
        {"pergunta": "Quem vê o retorno?", "escolha": "A enfermagem também vê.", "porque": "Foi combinado."},
    ],
    "em_aberto": [],
    "termos": [],
    "candidatas_a_adr": [],
}

# A conversa revisada: o retrato com um item em Já existe, o "isso atende?"
# respondido com o sim, e o resumo refeito.
RETRATO = {
    "tipo": "retrato",
    "ja_existe": [{"item": ITEM_QUE_JA_EXISTE, "versao": "v0.245.0"}],
    "mudou": [],
    "em_aberto": [],
}
CONVERSA_REVISADA = [
    *CONVERSA_ENVIADA,
    RETRATO,
    tecnologia_revisao.pergunta_de_atende(RETRATO["ja_existe"][0], 0),
    {"tipo": "resposta", "opcao": "A", "texto": tecnologia_revisao.OPCAO_ATENDE},
]


class _GithubQueEscreve(_GithubFalso):
    """O GitHub que guarda o que o "Atualizar o card" escreveu, na ordem."""

    def __init__(self, *args, erro_ao_escrever=None, **kw):
        super().__init__(*args, **kw)
        self.erro_ao_escrever = erro_ao_escrever
        self.escritas: list[tuple] = []

    def _escrever(self, *escrita):
        if self.erro_ao_escrever is not None:
            raise self.erro_ao_escrever
        self.escritas.append(escrita)

    def comentar(self, numero: int, corpo: str) -> None:
        self._escrever("comentou", numero, corpo)

    def fechar_como_nao_planejada(self, numero: int, *, comentario: str) -> None:
        self._escrever("fechou", numero, comentario)
        for parte in self.sub_issues.get(900, []):
            if parte["number"] == numero:
                parte.update(state="closed", state_reason="not_planned")

    def regravar(self, numero: int, *, corpo: str, labels: list[str]) -> dict:
        self._escrever("regravou", numero, corpo, list(labels))
        self.issues[numero] = {**self.issues[numero], "body": corpo, "labels": [{"name": n} for n in labels]}
        return self.issues[numero]


def _parte(numero: int, *, estado: str = "open", labels=(), motivo=None) -> dict:
    return {**_issue(numero, estado=estado, labels=labels, motivo=motivo), "title": f"Parte {numero}"}


def _montar_o_card(
    monkeypatch,
    *,
    logado=DIRETOR,
    partes: list[dict] | None = None,
    etapa: str = ETAPA_PLANEJADA,
    estado: str = "resumido",
    erro_ao_escrever=None,
):
    gh = _GithubQueEscreve(
        {900: _issue(900, corpo=_corpo_antigo(), labels=("needs-triage", "type:feature", "ready-for-agent"))},
        sub_issues={900: partes if partes is not None else [_parte(901), _parte(902, estado="closed")]},
        erro_ao_escrever=erro_ao_escrever,
    )
    client, sb, _ = _cenario(
        monkeypatch,
        logado=logado,
        participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR],
        demandas=[_card(etapa)],
        github=gh,
    )
    for nome in ("comentar", "fechar_como_nao_planejada", "regravar"):
        monkeypatch.setattr(github_client, nome, getattr(gh, nome), raising=False)
    sb.tabelas["tecnologia_planejamentos"] = [
        {
            "id": "p-1",
            "demanda_id": DEMANDA,
            "estado": estado,
            "mensagens": [dict(m) for m in CONVERSA_REVISADA],
            "decisoes": [],
            "resumo": dict(RESUMO_REVISADO),
            "revisao_iniciada_em": "2026-11-10T12:00:00Z",
            "revisao_por": DIRETOR["id"],
            "revisao_versao_base": "v0.251.0",
            "atualizado_em": "2026-11-10T12:00:00Z",
        }
    ]
    return client, sb, gh


def _regravado(gh) -> tuple:
    [escrita] = [e for e in gh.escritas if e[0] == "regravou"]
    return escrita


def _comentario(gh) -> str:
    [escrita] = [e for e in gh.escritas if e[0] == "comentou"]
    return escrita[2]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O corpo regravado e o marcador da Demanda
# ═══════════════════════════════════════════════════════════════════════════


class TestOCorpoRegravado:
    def test_o_corpo_regravado_preserva_o_marcador_da_demanda_byte_a_byte(self, monkeypatch):
        client, _, gh = _montar_o_card(monkeypatch)

        resposta = client.post(ATUALIZAR)

        assert resposta.status_code == 200, resposta.text
        _, numero, corpo, _ = _regravado(gh)
        assert numero == 900
        assert MARCADOR_DA_ISSUE in corpo
        assert corpo.count("demanda-vitta") == 1
        assert "Só a recepção." in corpo
        assert "A enfermagem também vê." in corpo


# ═══════════════════════════════════════════════════════════════════════════
# 2. O comentário do que mudou
# ═══════════════════════════════════════════════════════════════════════════


class TestOComentario:
    def test_o_comentario_lista_o_que_entrou_e_o_que_saiu_do_escopo(self, monkeypatch):
        client, _, gh = _montar_o_card(monkeypatch)

        assert client.post(ATUALIZAR).status_code == 200

        comentario = _comentario(gh)
        assert comentario.startswith("<!-- automacao -->\n")
        entrou, saiu = comentario.split("Entrou no escopo:", 1)[1].split("Saiu do escopo:", 1)
        # A decisão nova entra; a de antes, que continua, não aparece.
        assert "- Quem vê o retorno? A enfermagem também vê." in entrou
        assert "Só a recepção." not in comentario
        # Sai o ponto em aberto que a revisão respondeu, e o que já existe com o "atende".
        assert "- Quem confirma o retorno com o paciente." in saiu
        assert f"- {ITEM_QUE_JA_EXISTE} (já existe" in saiu
        assert "v0.251.0" in comentario

    def test_o_comentario_vem_antes_do_corpo_regravado(self, monkeypatch):
        """Com o corpo já regravado, um segundo clique depois de uma falha não
        teria mais o corpo de antes para dizer o que mudou."""
        client, _, gh = _montar_o_card(monkeypatch)

        client.post(ATUALIZAR)

        assert [e[0] for e in gh.escritas][0] == "comentou"
        assert [e[0] for e in gh.escritas][-1] == "regravou"


# ═══════════════════════════════════════════════════════════════════════════
# 3. As partes
# ═══════════════════════════════════════════════════════════════════════════


class TestAsPartes:
    def test_as_partes_nao_comecadas_fecham_como_nao_planejadas(self, monkeypatch):
        partes = [_parte(901), _parte(902, labels=("ready-for-agent",)), _parte(903, estado="closed")]
        client, _, gh = _montar_o_card(monkeypatch, partes=partes)

        assert client.post(ATUALIZAR).status_code == 200

        assert [e[1] for e in gh.escritas if e[0] == "fechou"] == [901, 902]
        assert gh.sub_issues[900][1]["state_reason"] == "not_planned"
        # A parte já fechada fica como estava.
        assert gh.sub_issues[900][2]["state_reason"] is None
        assert "#901, #902" in _comentario(gh)

    def test_parte_em_desenvolvimento_impede_a_atualizacao_sem_escrever_nada(self, monkeypatch):
        """A lista do app pode estar atrasada: a parte que pegou `in-progress`
        depois da última sincronização também recusa, lida na hora."""
        partes = [_parte(901), _parte(902, labels=("in-progress",))]
        client, sb, gh = _montar_o_card(monkeypatch, partes=partes)

        resposta = client.post(ATUALIZAR)

        assert resposta.status_code == 409
        assert "já começou" in resposta.json()["detail"]
        assert gh.escritas == []
        assert _conversas(sb)[0]["estado"] == "resumido"
