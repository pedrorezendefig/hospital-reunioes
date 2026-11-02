"""A aba Tecnologia é o chat do agente, e só (issue #1386, PRD #1380, ADR 0077).

Saíram do código o Quadro, o Painel, a tela de Produtos, o formulário à mão, a
Conversa da Demanda espelhada com a issue, as menções, o e-mail da Tecnologia,
o Vínculo por número, a rota antiga do Assistente de entrada e a tela antiga do
Planejamento da Demanda. Ficam as rotas do chat, a leitura do print, o webhook
do GitHub que deriva a Etapa, a rota de automação dos anexos e o cron deles
(o cron tem os testes dele em `test_tecnologia_anexos.py` e
`test_tecnologia_webhook_github.py`).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PREFIXO_DA_ABA = "/api/admin/tecnologia"

# As rotas que a tela do chat chama, e só elas. Escritas à mão, e não lidas do
# router: a lista é o que a ADR 0077 deixou de pé.
ROTAS_DO_CHAT = {
    "/api/admin/tecnologia/chat",
    "/api/admin/tecnologia/chat/{demanda_id}",
    "/api/admin/tecnologia/chat/{demanda_id}/nao-bateu",
    "/api/admin/tecnologia/chat/{demanda_id}/resumo",
    "/api/admin/tecnologia/chat/{demanda_id}/criar-card",
    "/api/admin/tecnologia/assistente/descrever-imagem",
}

# O que fica de fora da aba e continua de pé (critério 2 da issue).
ROTAS_QUE_FICAM = (
    "/api/webhooks/github",
    "/api/webhooks/deploy",
    "/api/automacao/tecnologia/demandas/{demanda_id}/anexos",
)


def _caminhos_do_app() -> dict:
    """A fonte é o schema OpenAPI, e não `app.routes` (issues #542 e #546)."""
    from app.main import app

    cache = app.openapi_schema
    try:
        return app.openapi()["paths"]
    finally:
        app.openapi_schema = cache


def test_a_aba_tecnologia_so_tem_as_rotas_do_chat():
    caminhos = _caminhos_do_app()

    assert len(caminhos) > 50, "O schema voltou quase vazio: a varredura estaria olhando para nada"
    da_aba = {caminho for caminho in caminhos if caminho.startswith(PREFIXO_DA_ABA)}
    assert da_aba == ROTAS_DO_CHAT


def test_o_webhook_da_etapa_e_a_automacao_dos_anexos_continuam_no_app():
    caminhos = _caminhos_do_app()

    for rota in ROTAS_QUE_FICAM:
        assert rota in caminhos, rota

