from supabase import create_client

from app.config import settings

supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

r = supabase.table("pendencias").select("id_acao", count="exact").execute()
print(f"Total pendencias: {r.count}")

p = supabase.table("participantes").select("id", count="exact").execute()
print(f"Total participantes: {p.count}")

re = supabase.table("reunioes").select("id_reuniao", count="exact").execute()
print(f"Total reunioes: {re.count}")
