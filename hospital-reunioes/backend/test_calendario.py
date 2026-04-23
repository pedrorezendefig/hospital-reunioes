import asyncio

from app.dependencies import get_supabase_client
from app.routers.reunioes import list_reunioes_calendario


async def main():
    try:
        supabase = get_supabase_client()
        res = await list_reunioes_calendario(
            data_inicio=None, data_fim=None, _={"email": "test@test.com"}, supabase=supabase
        )
        print("Success! Result length:", len(res))
        # Serialize to json to test if it's a serialization issue
        import json

        json.dumps(res, default=str)
        print("JSON serialization succeeded")
    except Exception:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
