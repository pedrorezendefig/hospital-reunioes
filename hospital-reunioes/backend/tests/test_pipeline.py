"""Smoke do pipeline ponta a ponta contra o Supabase LOCAL.

Sem provedor de LLM: `ai_processor` cai no modo mock quando não há chave do
OpenRouter, que é como este arquivo já roda no CI. Na máquina do dev era outra
história, porque ali o `.env` tem a chave de verdade e cada `pytest` mandava a
transcrição para o OpenRouter, com custo. A trava de rede da suíte (issue #546)
foi quem mostrou; zerar a chave aqui deixa o teste rodando o MESMO caminho que
ele já roda no CI, e não o transporte.
"""

import pytest

from app.dependencies import get_supabase_client
from app.pipeline.orchestrator import run_pipeline
from app.services import ai_processor


@pytest.fixture(autouse=True)
def _sem_provedor_de_llm(monkeypatch):
    """Sem chave, `ai_processor._llm_provider()` devolve "mock". Vale só sob o
    pytest: rodar o arquivo à mão continua exercitando o provedor do `.env`,
    que é para isso que o `__main__` lá embaixo existe."""
    monkeypatch.setattr(ai_processor.settings, "openrouter_api_key", "", raising=False)


def test():
    supabase = get_supabase_client()
    id_reuniao = "TEST_VALIDACAO"
    transcricao = "Reunião de teste na UTI pediátrica. Todos concordaram em revisar as métricas amanhã."

    try:
        supabase.table("reunioes").insert(
            {
                "id_reuniao": id_reuniao,
                "data": "2026-03-24",
                "tipo": "Gerencial",
                "status_ata": "PROCESSANDO",
                "fonte": "MOCK",
            }
        ).execute()
        print("Registro criado no banco.")
    except Exception as e:
        print("Registro já existe ou erro: ", e)

    transcricao_bytes = transcricao.encode("utf-8")
    run_pipeline(supabase, id_reuniao, transcricao_bytes, transcricao, ".txt", "Gerencial")


if __name__ == "__main__":
    test()
