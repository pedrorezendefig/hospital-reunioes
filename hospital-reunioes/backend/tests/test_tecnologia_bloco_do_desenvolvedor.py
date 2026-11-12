"""O bloco "Para o desenvolvedor" no PRD do diretor (issue #1633, PRD #1632).

O card da melhoria nasce com um bloco escrito para quem programa, logo depois do
bloco "Para o diretor": seis partes fixas, em negrito e sempre na mesma ordem,
que o Assistente de Tecnologia escreve no mesmo passo do resumo. O titulo e
contrato com o coletor do PedroOS e a pagina do Vitta OS.

Aqui: as funcoes puras que escrevem o bloco e o inserem num corpo, o corpo do
PRD, e a rota do resumo da melhoria (o que fica guardado, o que a tela recebe e
o que o card leva).
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tecnologia_vinculo import (  # noqa: E402
    CABECALHO_DO_BLOCO,
    CABECALHO_DO_DESENVOLVEDOR,
    bloco_do_desenvolvedor,
    bloco_para_o_diretor,
    corpo_do_prd_do_diretor,
    inserir_bloco_do_desenvolvedor,
)

PARTES = {
    "o_que_o_diretor_quer": "A recepção marca o retorno do paciente na saída.",
    "por_que_ele_pediu": "Hoje o retorno é anotado no papel e se perde.",
    "o_que_ja_ficou_decidido": "Só a recepção marca; o aviso sai por WhatsApp na véspera.",
    "onde_mexe_no_codigo": "A tela da recepção e o serviço de agenda do backend.",
    "cuidados": "O aviso por WhatsApp já tem um limite diário de envios.",
    "como_saber_que_acabou": "A recepção marca um retorno e o paciente recebe o aviso.",
}

RESUMO = {
    "decisoes": [{"pergunta": "Quem vai marcar o retorno?", "escolha": "Só a recepção.", "porque": "Ela vê a saída."}],
    "em_aberto": ["O que acontece quando o paciente falta."],
}


def _corpo(**resumo) -> str:
    return corpo_do_prd_do_diretor(
        demanda_id="d-1",
        titulo="Agenda de retorno na recepção",
        descricao="Hoje o retorno é marcado no papel e se perde.",
        resumo={**RESUMO, **resumo},
        link="https://app.exemplo/admin/tecnologia?demanda=d-1",
    )


def _bloco(corpo: str) -> str:
    """O texto do bloco do desenvolvedor: do titulo ate o separador seguinte."""
    inicio = corpo.index(CABECALHO_DO_DESENVOLVEDOR)
    fim = corpo.index("\n---\n", inicio)
    return corpo[inicio:fim]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O corpo do PRD do diretor
# ═══════════════════════════════════════════════════════════════════════════


class TestOCorpoDoPrd:
    def test_o_bloco_vem_logo_depois_do_bloco_do_diretor_com_as_seis_partes_na_ordem(self):
        corpo = _corpo(para_o_desenvolvedor=PARTES)

        assert CABECALHO_DO_DESENVOLVEDOR == "## 🛠️ Para o desenvolvedor"
        cabecalhos = re.findall(r"^## .+$", corpo, re.MULTILINE)
        assert cabecalhos[:3] == [CABECALHO_DO_BLOCO, CABECALHO_DO_DESENVOLVEDOR, "## Problema"]
        assert _bloco(corpo).split("\n") == [
            "## 🛠️ Para o desenvolvedor",
            "",
            "**O que o diretor quer:** A recepção marca o retorno do paciente na saída.",
            "",
            "**Por que ele pediu:** Hoje o retorno é anotado no papel e se perde.",
            "",
            "**O que já ficou decidido com ele:** Só a recepção marca; o aviso sai por WhatsApp na véspera.",
            "",
            "**Onde mexe no código:** A tela da recepção e o serviço de agenda do backend.",
            "",
            "**Cuidados:** O aviso por WhatsApp já tem um limite diário de envios.",
            "",
            "**Como saber que acabou:** A recepção marca um retorno e o paciente recebe o aviso.",
            "",
        ]
