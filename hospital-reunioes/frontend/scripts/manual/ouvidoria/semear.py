#!/usr/bin/env python3
"""Semeia o Supabase LOCAL com os dados de exemplo da página de Ouvidoria do
manual (issue #1723, ADR 0094, decisão 5).

Tudo vem do `seed.json` ao lado: a ouvidora de exemplo (faixa P1300), o
responsável do setor e uma manifestação por situação que a página mostra.
Nada aqui é gente de verdade, e o roteiro recusa qualquer Supabase que não seja
o local.

O banco local é compartilhado com o resto do trabalho, então este script só
cria e só mexe no que é dele: toda manifestação nasce com `conversa_id` igual à
marca do seed, e é por ela que a rodada seguinte acha a anterior e devolve o
caso ao estado semeado, em vez de duplicar. As linhas entram direto pela API
REST com a chave de serviço, sem passar pelas rotas do app, para nenhum
acionamento nem email nascer de um print.

Uso: python3 scripts/manual/ouvidoria/semear.py
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SEED = json.loads((AQUI / "seed.json").read_text(encoding="utf-8"))
ENV_LOCAL = AQUI.parents[3] / ".env"


def credenciais_locais() -> tuple[str, str]:
    """URL e chave de serviço do `.env` local, nunca de produção."""
    env: dict[str, str] = {}
    for linha in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            env[chave] = valor.strip().strip('"')
    url = env.get("SUPABASE_URL", "")
    chave = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise SystemExit(f"recusado: '{url}' não é o Supabase local.")
    return url, chave


def rest(url: str, chave: str, caminho: str, metodo: str = "GET", corpo=None, prefer=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(f"{url}/rest/v1/{caminho}", data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}") from e


def login_de_exemplo(url: str, chave: str, email: str, senha: str) -> str:
    """Cria (ou reaproveita, com a senha do seed) o login da pessoa de exemplo."""
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    corpo = json.dumps({"email": email, "password": senha, "email_confirm": True}).encode()
    try:
        req = urllib.request.Request(f"{url}/auth/v1/admin/users", data=corpo, headers=cabecalhos)
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}") from e
    pagina = 1
    while True:
        busca = urllib.request.Request(
            f"{url}/auth/v1/admin/users?page={pagina}&per_page=200", headers=cabecalhos
        )
        with urllib.request.urlopen(busca, timeout=20) as resposta:
            usuarios = json.load(resposta)["users"]
        for usuario in usuarios:
            if usuario["email"] == email:
                troca = urllib.request.Request(
                    f"{url}/auth/v1/admin/users/{usuario['id']}",
                    data=json.dumps({"password": senha}).encode(),
                    headers=cabecalhos,
                    method="PUT",
                )
                urllib.request.urlopen(troca, timeout=20).close()
                return usuario["id"]
        if not usuarios:
            raise SystemExit(f"login {email} não encontrado depois de criado.")
        pagina += 1


def quando(receita: str) -> str:
    """"-2 dias" e "+1 dia" viram o instante correspondente, em ISO."""
    sinal = -1 if receita.startswith("-") else 1
    dias = int(receita.strip("+-").split()[0])
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=sinal * dias)).isoformat()


def relativa(valor) -> bool:
    return isinstance(valor, str) and valor[:1] in ("-", "+") and "dia" in valor


def linha_do_caso(receita: dict) -> dict:
    return {campo: quando(valor) if relativa(valor) else valor for campo, valor in receita.items()}


def semear() -> None:
    url, chave = credenciais_locais()
    marca = SEED["marca"]
    ouvidora = SEED["ouvidora"]

    rest(
        url,
        chave,
        "participantes",
        "POST",
        [
            {
                "id": ouvidora["id"],
                "nome_completo": ouvidora["nome"],
                "email": ouvidora["email"],
                "cargo": ouvidora["cargo"],
                "role": "coordenador",
                "ativo": True,
                "access_profile": "regular",
                "perfil_ouvidoria": "ouvidor",
                "is_super_admin": False,
                "is_externo": False,
                "auth_user_id": login_de_exemplo(url, chave, ouvidora["email"], ouvidora["senha"]),
            }
        ],
        prefer="resolution=merge-duplicates",
    )

    responsavel = SEED["responsavel"]
    filtro = (
        "ouvidoria_setor_responsaveis?setor=eq."
        + urllib.parse.quote(responsavel["setor"])
        + "&email=eq."
        + urllib.parse.quote(responsavel["email"])
        + "&select=id"
    )
    if not rest(url, chave, filtro):
        rest(
            url,
            chave,
            "ouvidoria_setor_responsaveis",
            "POST",
            [{**responsavel, "vigencia_inicio": "2026-01-01"}],
        )

    for receita in SEED["casos"].values():
        linha = linha_do_caso(receita)
        achado = rest(
            url,
            chave,
            f"ouvidoria_protocolos?conversa_id=eq.{marca}"
            f"&resumo=eq.{urllib.parse.quote(receita['resumo'])}&select=id",
        )
        if achado:
            rest(url, chave, f"ouvidoria_protocolos?id=eq.{achado[0]['id']}", "PATCH", linha)
        else:
            rest(
                url,
                chave,
                "ouvidoria_protocolos",
                "POST",
                [
                    {
                        **linha,
                        "conversa_id": marca,
                        "data_abertura": dt.date.today().isoformat(),
                        "dados_incompletos": False,
                        "anonimo": False,
                    }
                ],
            )

    print("dados de exemplo da página de Ouvidoria prontos.")


if __name__ == "__main__":
    semear()
