from app.dependencies import get_supabase_client
from app.pipeline.orchestrator import run_pipeline


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

    run_pipeline(supabase, id_reuniao, transcricao.encode("utf-8"), "Gerencial")


if __name__ == "__main__":
    test()
