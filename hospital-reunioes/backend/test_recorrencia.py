import asyncio

from fastapi import HTTPException

from app.dependencies import get_supabase_client
from app.routers.reunioes import cancelar_grupo_recorrencia


async def main():
    supabase = get_supabase_client()
    try:
        await cancelar_grupo_recorrencia("undefined_group", current_user={"email": "test@test.com"}, supabase=supabase)
    except HTTPException as e:
        print("HTTP Error:", e.detail)
    except Exception:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
