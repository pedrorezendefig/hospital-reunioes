#!/usr/bin/env python3
"""Semeia o Supabase LOCAL com os dados de exemplo da página de Contas médicas
do manual e guarda os prints contra dado real (issue #1724, ADR 0094, decisão 5).

Tudo vem do `seed.json` ao lado: a faturista de exemplo (faixa P17240 a
P17249, só deste módulo), uma operadora de exemplo e três contas, duas na Fila
com o Guia pronto e uma esperando o prontuário. Nada aqui é gente, paciente ou
contrato de verdade, e o script recusa qualquer Supabase que não seja o local.

O banco local é compartilhado com o resto do trabalho, então este script só
mexe no que é dele: os atendimentos do seed e os envios da faturista de
exemplo. A cada rodada ele apaga as contas desses atendimentos e os envios da
faturista e cria tudo de novo, porque abrir o Guia no print muda a conta de A
fazer para Em correção. As linhas entram direto pela API REST com a chave de
serviço, sem passar pelas rotas do app: nenhuma análise com IA nasce de um print.

Uso:
  python3 scripts/manual/contas-medicas/semear.py
      semeia (ou devolve ao estado de exemplo).
  python3 scripts/manual/contas-medicas/semear.py --guarda <textos.json>
      confere o texto de cada print contra os nomes do banco local que não são
      do seed; sai com 1 e diz quais prints mostram dado de fora.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SEED = json.loads((AQUI / "seed.json").read_text(encoding="utf-8"))
ENV_LOCAL = Path(os.environ.get("ENV_LOCAL") or AQUI.parents[3] / ".env")


# --------------------------------------------------------------------------
# A guarda do dado real
# --------------------------------------------------------------------------


def nomes_de_fora_no_texto(texto: str, nomes_de_fora: list[str]) -> list[str]:
    """Os nomes de fora do seed que aparecem no texto de um print.

    A conta é em casefold: o app põe título, botão e etiqueta em caixa alta pelo
    CSS, e o texto lido da tela já vem transformado. Nome de uma palavra só fica
    de fora, porque casaria com qualquer texto da tela.
    """
    tela = texto.casefold()
    return sorted({n for n in nomes_de_fora if len(n.split()) >= 2 and n.casefold() in tela})


# --------------------------------------------------------------------------
# O banco local
# --------------------------------------------------------------------------


def credenciais_locais() -> tuple[str, str]:
    """URL e chave de serviço do `.env` local, nunca de produção."""
    env: dict[str, str] = {}
    for linha in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            env[chave.strip()] = valor.strip().strip('"')
    url = env.get("SUPABASE_URL", "")
    chave = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise SystemExit(f"recusado: '{url}' não é o Supabase local.")
    return url, chave


def _cabecalhos(chave: str, prefer: str | None = None) -> dict[str, str]:
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    if prefer:
        cabecalhos["Prefer"] = prefer
    return cabecalhos


def rest(url: str, chave: str, caminho: str, metodo: str = "GET", corpo=None, prefer=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(
        f"{url}/rest/v1/{caminho}", data=dados, headers=_cabecalhos(chave, prefer), method=metodo
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}") from e


def rest_tudo(url: str, chave: str, caminho: str, por_pagina: int = 500) -> list:
    """Todas as linhas de um GET, de página em página (o PostgREST corta em
    `max_rows` sem avisar)."""
    linhas: list = []
    while True:
        pagina = rest(url, chave, f"{caminho}&limit={por_pagina}&offset={len(linhas)}") or []
        linhas.extend(pagina)
        if len(pagina) < por_pagina:
            return linhas


def login_de_exemplo(url: str, chave: str, email: str, senha: str, nome: str) -> str:
    """Cria (ou reaproveita, com a senha do seed) o login da pessoa de exemplo."""
    corpo = {"email": email, "password": senha, "email_confirm": True, "user_metadata": {"nome": nome}}
    try:
        req = urllib.request.Request(
            f"{url}/auth/v1/admin/users", data=json.dumps(corpo).encode(), headers=_cabecalhos(chave)
        )
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}") from e
    pagina = 1
    while True:
        busca = urllib.request.Request(
            f"{url}/auth/v1/admin/users?page={pagina}&per_page=200", headers=_cabecalhos(chave)
        )
        with urllib.request.urlopen(busca, timeout=20) as resposta:
            usuarios = json.load(resposta)["users"]
        for usuario in usuarios:
            if usuario["email"] == email:
                troca = urllib.request.Request(
                    f"{url}/auth/v1/admin/users/{usuario['id']}",
                    data=json.dumps({"password": senha, "user_metadata": {"nome": nome}}).encode(),
                    headers=_cabecalhos(chave),
                    method="PUT",
                )
                urllib.request.urlopen(troca, timeout=20).close()
                return usuario["id"]
        if not usuarios:
            raise SystemExit(f"login {email} não encontrado depois de criado.")
        pagina += 1


def _em(valores) -> str:
    return "in.(" + ",".join(urllib.parse.quote(str(v)) for v in valores) + ")"


# --------------------------------------------------------------------------
# A semeadura
# --------------------------------------------------------------------------

CAMPOS_DA_CONTA = ("numero_conta", "situacao", "ordem_fila", "periodo_inicio", "periodo_fim", "total_lancado")
CAMPOS_DA_CONTA_PRONTA = ("nota_bruta", "valor_apontado")


def semear() -> None:
    url, chave = credenciais_locais()
    faturista = SEED["faturista"]
    contas = SEED["contas"]

    rest(
        url,
        chave,
        "participantes",
        "POST",
        [
            {
                "id": faturista["id"],
                "nome_completo": faturista["nome"],
                "email": faturista["email"],
                "cargo": faturista["cargo"],
                "role": "coordenador",
                "ativo": True,
                "access_profile": None,
                "perfil_contas_medicas": "faturista",
                "is_super_admin": False,
                "is_externo": False,
                "auth_user_id": login_de_exemplo(
                    url, chave, faturista["email"], faturista["senha"], faturista["nome"]
                ),
            }
        ],
        prefer="resolution=merge-duplicates",
    )

    operadora = SEED["operadora"]
    (gravada,) = rest(
        url,
        chave,
        "cm_operadora?on_conflict=sigla",
        "POST",
        [{"sigla": operadora["sigla"], "nome": operadora["nome"], "situacao": "PRONTA"}],
        prefer="resolution=merge-duplicates,return=representation",
    )

    # A rodada anterior sai inteira: as contas dos atendimentos do seed (com as
    # linhas, os Faltou isto e o resto, pelo cascade) e os envios da faturista.
    numeros = [receita["numero_atendimento"] for receita in contas.values()]
    antigos = rest(url, chave, f"cm_atendimento?numero_atendimento={_em(numeros)}&select=id") or []
    if antigos:
        rest(url, chave, f"cm_conta?atendimento_id={_em(a['id'] for a in antigos)}", "DELETE")
    rest(url, chave, f"cm_envio?usuario_id=eq.{faturista['id']}", "DELETE")

    atendimentos = rest(
        url,
        chave,
        "cm_atendimento?on_conflict=numero_atendimento",
        "POST",
        [
            {
                "numero_atendimento": receita["numero_atendimento"],
                "paciente_rotulo": receita["paciente_rotulo"],
                "idade_anos": receita["idade_anos"],
                "operadora_id": gravada["id"],
                "plano": operadora["plano"],
                "coluna_preco": "COMUM",
                "acomodacao_contratada": "ENFERMARIA",
            }
            for receita in contas.values()
        ],
        prefer="resolution=merge-duplicates,return=representation",
    )
    atendimento_de = {a["numero_atendimento"]: a["id"] for a in atendimentos}

    (envio,) = rest(
        url, chave, "cm_envio", "POST", [{"usuario_id": faturista["id"]}], prefer="return=representation"
    )
    agora = dt.datetime.now(dt.timezone.utc).isoformat()

    for receita in contas.values():
        atendimento_id = atendimento_de[receita["numero_atendimento"]]
        arquivo = {"envio_id": envio["id"], "atendimento_id": atendimento_id, "numero_atendimento": receita["numero_atendimento"]}
        (da_conta,) = rest(
            url,
            chave,
            "cm_arquivo",
            "POST",
            [{**arquivo, "tipo": "CONTA", "paginas": receita["paginas_da_conta"]}],
            prefer="return=representation",
        )
        if "paginas_do_prontuario" in receita:
            rest(
                url,
                chave,
                "cm_arquivo",
                "POST",
                [{**arquivo, "tipo": "PRONTUARIO", "paginas": receita["paginas_do_prontuario"], "paginas_ocr": 0}],
            )

        conta = {campo: receita[campo] for campo in CAMPOS_DA_CONTA}
        conta.update(atendimento_id=atendimento_id, arquivo_id=da_conta["id"], enviada_em=agora)
        if receita["situacao"] == "A_FAZER":
            conta.update({campo: receita[campo] for campo in CAMPOS_DA_CONTA_PRONTA})
            conta.update(pronta_em=agora, faltantes={"itens": [], "contagens": receita["contagens"]})
        (gravada_a_conta,) = rest(url, chave, "cm_conta", "POST", [conta], prefer="return=representation")

        if receita["linhas"]:
            rest(
                url,
                chave,
                "cm_guia_linha",
                "POST",
                [
                    {
                        "quantidade_lancada": None,
                        "quantidade_devida": None,
                        "preco_lancado": None,
                        "preco_tabela": None,
                        "evidencia_pagina": None,
                        "evidencia_trecho": None,
                        "nivel_evidencia": None,
                        **linha,
                        "conta_id": gravada_a_conta["id"],
                        "origem": "CODIGO",
                        "estado": "ABERTA",
                    }
                    for linha in receita["linhas"]
                ],
            )

    print("dados de exemplo da página de Contas médicas prontos.")


def nomes_de_fora() -> list[str]:
    """Os nomes do banco local que o seed não pôs lá: as pessoas e os pacientes."""
    url, chave = credenciais_locais()
    do_seed = {SEED["faturista"]["id"]}
    pacientes_do_seed = {receita["numero_atendimento"] for receita in SEED["contas"].values()}
    pessoas = rest_tudo(url, chave, "participantes?select=id,nome_completo&order=id")
    atendimentos = rest_tudo(url, chave, "cm_atendimento?select=numero_atendimento,paciente_rotulo&order=id")
    return [p["nome_completo"] for p in pessoas if p["id"] not in do_seed and p.get("nome_completo")] + [
        a["paciente_rotulo"]
        for a in atendimentos
        if a["numero_atendimento"] not in pacientes_do_seed and a.get("paciente_rotulo")
    ]


def guardar(arquivo_dos_textos: str) -> int:
    """Confere o texto de cada print. Devolve 1 quando algum mostra dado de fora."""
    textos = json.loads(Path(arquivo_dos_textos).read_text(encoding="utf-8"))
    de_fora = nomes_de_fora()
    recusados = 0
    for print_ in textos:
        achados = nomes_de_fora_no_texto(print_["texto"], de_fora)
        if achados:
            recusados += 1
            print(
                f"{print_['arquivo']}: a tela mostra {', '.join(achados)}, que não é dado de exemplo. "
                "O repositório é público: o print não sai.",
                file=sys.stderr,
            )
    return 1 if recusados else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--guarda"]:
        sys.exit(guardar(sys.argv[2]))
    semear()
