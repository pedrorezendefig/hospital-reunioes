"""O Documento do card (issue #1552, PRD #1548, ADR 0084, decisão 7).

O detalhe do card vira um documento com seções fixas. Do lado do servidor, o
que muda são as datas: cada parte guarda a data de fechamento lida na
sincronização, a raiz guarda a dela (a data de entrega), e a lista entrega ao
documento as três datas do card (criado, entregue, em produção).

A data em produção que a subida grava está em `test_tecnologia_webhook_deploy.py`,
ao lado do webhook e da reconciliação que a gravam.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import DIRETOR, _demanda  # noqa: E402
from test_tecnologia_webhook_github import (  # noqa: E402
    _corpo,
    _demandas,
    _entregar,
    _GithubFalso,
    _issue,
    _montar,
    _pr_do_app,  # noqa: F401  (autouse)
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
    ETAPA_PLANEJADA,
)

FECHOU_A_PARTE = "2026-11-05T14:00:00Z"


def _fechada(numero: int, quando: str, **kw) -> dict:
    """A issue fechada como concluída, com a data do fechamento como o GitHub a
    devolve (`closed_at`, em UTC)."""
    return {**_issue(numero, estado="closed", motivo="completed", **kw), "closed_at": quando}


class TestAsPartesComAData:
    def test_cada_parte_guarda_a_etapa_e_a_data_de_fechamento_lida_na_sincronizacao(self, monkeypatch):
        gh = _GithubFalso(
            {673: _issue(673)},
            sub_issues={673: [_fechada(678, FECHOU_A_PARTE), _issue(679, labels=("in-progress",))]},
        )
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        _entregar(cliente, _corpo())

        [demanda] = _demandas(sb)
        assert [(p["situacao"], p["fechada_em"]) for p in demanda["partes"]] == [
            (ETAPA_ENTREGUE, FECHOU_A_PARTE),
            (ETAPA_EM_DESENVOLVIMENTO, None),
        ]


ENTREGOU = "2026-11-06T18:00:00Z"
SUBIU = "2026-11-07T10:00:00-03:00"


def _card(etapa: str, **campos) -> dict:
    """O card do diretor com a raiz e uma parte fechadas, como a sincronização
    os deixa no cache."""
    base = {
        "autor_id": DIRETOR["id"],
        "criado_em": "2026-11-01T09:00:00Z",
        "github_issue_numero": 673,
        "etapa": etapa,
        "github_foto": {"numero": 673, "estado": "closed", "fechada_em": ENTREGOU},
        "partes": [
            {"numero": 678, "o_que_muda": "O selo aparece.", "situacao": ETAPA_ENTREGUE, "fechada_em": ENTREGOU}
        ],
    }
    return _demanda("d-1", **{**base, **campos})


class TestAsDatasDoDocumento:
    def test_a_lista_entrega_as_tres_datas_e_a_data_de_cada_parte(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch,
            logado=DIRETOR,
            participantes=[DIRETOR],
            demandas=[_card(ETAPA_EM_PRODUCAO, versao_em_producao="v0.246.0", em_producao_em=SUBIU)],
        )

        [item] = client.get(CHAT).json()

        assert (item["criado_em"], item["fechada_em"], item["em_producao_em"]) == (
            "2026-11-01T09:00:00Z",
            ENTREGOU,
            SUBIU,
        )
        assert item["partes"] == [{"o_que_muda": "O selo aparece.", "situacao": ETAPA_ENTREGUE, "fechada_em": ENTREGOU}]

    def test_a_data_de_uma_subida_anterior_nao_aparece_com_o_card_reaberto(self, monkeypatch):
        """A issue reaberta para um ajuste tira o card de Em produção, e a coluna
        guarda a data da subida anterior. Mostrá-la diria que está no ar o que
        ainda não está, como a versão (`versao_da_entrega`)."""
        client, _, _ = _cenario(
            monkeypatch,
            logado=DIRETOR,
            participantes=[DIRETOR],
            demandas=[_card(ETAPA_PLANEJADA, github_foto={"numero": 673, "estado": "open"}, em_producao_em=SUBIU)],
        )

        [item] = client.get(CHAT).json()

        assert (item["fechada_em"], item["em_producao_em"]) == (None, None)


class TestOKitDizODocumento:
    def test_o_kit_da_tecnologia_descreve_o_documento_do_card(self):
        """O kit é a língua em que o Assistente fala com o diretor: sem o
        comportamento novo escrito, ele descreveria o texto corrido de antes."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## A Etapa", 1)[1].split("\n## ", 1)[0]
        for trecho in (
            "**Em uma frase**",
            "até cinco tópicos",
            "**Ver tudo**",
            "quando ficou pronta",
            "**Datas**",
            "Descrição em preparação",
        ):
            assert trecho in secao, trecho
