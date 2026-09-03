import os
import sys

# Adicionar o diretório atual ao path para importar a app
sys.path.append(os.getcwd())

from app.dependencies import get_supabase_client


def sync_all_users():
    supabase = get_supabase_client()

    print("--- 🔄 Iniciando Sincronização em Massa de Participantes ---")

    # 1. Listar participantes sem auth_user_id
    p_result = supabase.table("participantes").select("id, email, nome_completo, auth_user_id").execute()
    participantes = p_result.data or []
    print(f"Total de participantes no banco: {len(participantes)}")

    # 2. Listar todos os usuários do Supabase Auth (admin API)
    auth_response = supabase.auth.admin.list_users()

    # Diferentes versões do supabase-py retornam lista direta ou objeto com .users
    if isinstance(auth_response, list):
        auth_users = auth_response
    else:
        auth_users = getattr(auth_response, "users", []) or []

    print(f"Total de usuários no Auth: {len(auth_users)}")

    # Mapear email -> id do Auth
    email_to_auth_id = {u.email: str(u.id) for u in auth_users if u.email}

    updated_count = 0
    already_linked = 0
    not_found = 0

    for p in participantes:
        email = p.get("email")
        if not email:
            continue

        auth_id = email_to_auth_id.get(email)

        if auth_id:
            if not p.get("auth_user_id"):
                # Realiza o vínculo
                supabase.table("participantes").update({"auth_user_id": auth_id}).eq("id", p["id"]).execute()
                print(f"✅ Vinculado: {email} -> {auth_id}")
                updated_count += 1
            else:
                already_linked += 1
        else:
            print(f"⚠️ Não encontrado no Auth: {email}")
            not_found += 1

    print("\n--- 📊 Resumo da Sincronização ---")
    print(f"Novos vínculos realizados: {updated_count}")
    print(f"Já estavam vinculados: {already_linked}")
    print(f"Não encontrados no Auth: {not_found}")
    print("--- 🏁 Concluído ---")


if __name__ == "__main__":
    sync_all_users()
