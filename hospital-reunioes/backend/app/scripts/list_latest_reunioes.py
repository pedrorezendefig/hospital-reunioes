import os
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def list_latest():
    r = supabase.table("reunioes").select("id_reuniao, status_ata, created_at, json_ata").order("created_at", desc=True).limit(5).execute()
    for x in r.data:
        id_r = x["id_reuniao"]
        status = x["status_ata"]
        json_ata = x["json_ata"]
        has_quadro = "quadro_atribuicoes" in json_ata if json_ata else False
        num_atribuicoes = len(json_ata["quadro_atribuicoes"]) if has_quadro else 0
        
        p_res = supabase.table("pendencias").select("id_acao", count="exact").eq("id_reuniao", id_r).execute()
        num_pendencias = p_res.count if p_res.count is not None else 0
        
        print(f"ID: {id_r} | Status: {status} | Has Quadro: {has_quadro} ({num_atribuicoes}) | Pendencias: {num_pendencias}")

if __name__ == "__main__":
    list_latest()
