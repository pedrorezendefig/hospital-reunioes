import asyncio
from app.routers.reunioes import cancelar_grupo_recorrencia
from app.dependencies import get_supabase_client
from fastapi import HTTPException

async def main():
    supabase = get_supabase_client()
    try:
        await cancelar_grupo_recorrencia("undefined_group", current_user={"email": "test@test.com"}, supabase=supabase)
    except HTTPException as e:
        print("HTTP Error:", e.detail)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
