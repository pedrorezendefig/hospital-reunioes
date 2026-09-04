"""
Bulk seed: provisiona contas de participantes no Supabase.

A LISTA DE PESSOAS NAO VIVE NO GIT. Ela e um insumo humano e fica em
`local/bulk_seed_participantes.json` (pasta `local/`, ADR 0044). Nome, cargo e
e-mail de pessoa real sao dado pessoal: publicar isso no repositorio expoe o
time sem base legal.

A SENHA E ALEATORIA POR PESSOA. Nao existe regra derivavel do nome. Uma regra
escrita no repositorio vira a chave junto com a fechadura: quem le o arquivo
calcula a senha de qualquer conta e entra pela tela de login publica.

As credenciais geradas saem em `local/bulk_seed_credenciais.csv` (modo 600) e
nunca no log, porque o log do backend e lido por gente que nao precisa dela.

Formato do JSON de entrada (lista de objetos):
    [{"nome_completo": "...", "cargo": "...", "email": "...",
      "area": "...", "setor": "...", "role": "diretor"}]

Executar (do host, de dentro de backend/; a pasta scripts/ nao entra na imagem):
    uv run python -m scripts.bulk_seed
"""

import csv
import json
import logging
import os
import secrets
import sys
from pathlib import Path

from supabase import create_client

from app.config import settings
from app.services.auth_provisioning import provision_auth_user

logging.basicConfig(level=logging.INFO, format="[bulk_seed] %(message)s")
logger = logging.getLogger(__name__)

# backend/scripts/bulk_seed.py -> sobe 4 niveis ate a raiz do repositorio.
RAIZ = Path(__file__).resolve().parents[3]
ENTRADA = RAIZ / "local" / "bulk_seed_participantes.json"
SAIDA_CREDENCIAIS = RAIZ / "local" / "bulk_seed_credenciais.csv"

CAMPOS = ("nome_completo", "cargo", "email", "area", "setor", "role")


def carregar_participantes() -> list[dict]:
    """Le a lista de fora do git e falha alto se ela nao estiver la."""
    if not ENTRADA.exists():
        logger.error(f"lista nao encontrada: {ENTRADA}")
        logger.error("Crie o arquivo com a lista de participantes antes de rodar.")
        sys.exit(1)

    dados = json.loads(ENTRADA.read_text(encoding="utf-8"))

    for i, p in enumerate(dados, 1):
        faltando = [c for c in CAMPOS if not p.get(c)]
        if faltando:
            logger.error(f"registro {i} sem os campos: {', '.join(faltando)}")
            sys.exit(1)

    return dados


def gerar_senha() -> str:
    """Senha aleatoria. Nao ha relacao alguma com o nome da pessoa."""
    return secrets.token_urlsafe(18)


def main():
    participantes = carregar_participantes()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    total = len(participantes)
    ok = 0
    skip = 0
    erros = 0
    credenciais: list[tuple[str, str, str]] = []

    for i, p in enumerate(participantes, 1):
        nome = p["nome_completo"]
        email = p["email"].strip().lower()
        role = p["role"]

        # Idempotência: skip se já existe
        existing = supabase.table("participantes").select("id").eq("email", email).execute()
        if existing.data:
            logger.info(f"[{i}/{total}] SKIP (já existe): {email} → {existing.data[0]['id']}")
            skip += 1
            continue

        senha = gerar_senha()

        # Criar auth user
        auth_uid = provision_auth_user(supabase, nome, email, role, password=senha)
        if not auth_uid:
            logger.error(f"[{i}/{total}] ERRO auth: {email}")
            erros += 1
            continue

        # Inserir participante
        try:
            result = (
                supabase.table("participantes")
                .insert(
                    {
                        "nome_completo": nome,
                        "cargo": p["cargo"],
                        "email": email,
                        "area": p["area"],
                        "setor": p["setor"],
                        "role": role,
                        "ativo": True,
                        "is_externo": False,
                        "auth_user_id": auth_uid,
                    }
                )
                .execute()
            )

            pid = result.data[0]["id"] if result.data else "?"
            # A senha NAO entra no log. Ela vai so para o CSV local.
            logger.info(f"[{i}/{total}] OK: {email} → {pid} (role={role})")
            credenciais.append((nome, email, senha))
            ok += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] ERRO insert: {email} — {e}")
            erros += 1

    if credenciais:
        SAIDA_CREDENCIAIS.parent.mkdir(parents=True, exist_ok=True)
        with SAIDA_CREDENCIAIS.open("w", encoding="utf-8", newline="") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(["nome_completo", "email", "senha_inicial"])
            escritor.writerows(credenciais)
        os.chmod(SAIDA_CREDENCIAIS, 0o600)
        logger.info(f"credenciais gravadas em {SAIDA_CREDENCIAIS} (modo 600)")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"RESULTADO: {ok} criados, {skip} já existiam, {erros} erros (total: {total})")
    logger.info(f"{'=' * 60}")

    if erros > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
