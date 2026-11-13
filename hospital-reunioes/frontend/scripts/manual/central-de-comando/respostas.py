#!/usr/bin/env python3
"""As respostas de exemplo das telas da Central de Comando, para os prints do
manual (issue #1725, ADR 0094, decisão 5).

Os números da Central vêm do Google Analytics, do Instagram e da leitura
semanal da nota no Google. No app local nenhuma dessas fontes está ligada, e
ligar seria mostrar número real. Então o roteiro responde no lugar do backend,
só nas rotas da Central, com o que sai daqui: os números do `seed.json` ao
lado, montados no formato que cada tela pede. As datas acompanham o dia de
hoje, para o período e o "Atualizado há" saírem coerentes em qualquer rodada.

Uso: python3 respostas.py <tela>
     python3 respostas.py miniatura <publicação>
Telas: visao-geral, dados-do-google, instagram, objetivos, lente, nota, ao-vivo.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

SEED = json.loads((Path(__file__).resolve().parent / "seed.json").read_text(encoding="utf-8"))
DIAS = 28
HOJE = dt.date.today()


def variacao(atual: float, anterior: float) -> float | None:
    return None if not anterior else (atual - anterior) / anterior


def percentuais(itens: list[dict]) -> list[dict]:
    total = sum(i["visitas"] for i in itens)
    return [{**i, "percentual": round(100 * i["visitas"] / total)} for i in itens]


def periodo() -> dict:
    fim = HOJE - dt.timedelta(days=1)
    inicio = fim - dt.timedelta(days=DIAS - 1)
    fim_anterior = inicio - dt.timedelta(days=1)
    inicio_anterior = fim_anterior - dt.timedelta(days=DIAS - 1)
    return {
        "chave": "28d",
        "dias": DIAS,
        "atual": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "anterior": {"inicio": inicio_anterior.isoformat(), "fim": fim_anterior.isoformat()},
    }


def frescor() -> dict:
    """Números buscados há 12 minutos, sem falha."""
    quando = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=12)
    return {"atualizado_em": quando.isoformat(), "atualizacao_falhou": False, "motivo": None}


def fluxo(numero: dict) -> dict:
    return {**numero, "variacao": variacao(numero["atual"], numero["anterior"])}


# A tela só mostra miniatura com endereço https. O roteiro responde neste
# endereço, que não existe, com a imagem lisa de `miniatura`.
MINIATURAS = "https://miniaturas.exemplo.local"


def publicacao(identificador: str) -> dict:
    return next(p for p in SEED["instagram"]["principais_publicacoes"] if p["id"] == identificador)


def miniatura(identificador: str) -> str:
    """Uma miniatura lisa no lugar da foto da publicação: nenhuma imagem real."""
    p = publicacao(identificador)
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'>"
        f"<rect width='400' height='400' fill='{p['cor']}'/>"
        "<text x='200' y='215' font-family='Arial' font-size='40' fill='white' "
        f"text-anchor='middle'>{p['rotulo_tipo']}</text></svg>"
    )


def site() -> dict:
    return SEED["site"]


def movimento() -> list[dict]:
    p = periodo()
    inicio = dt.date.fromisoformat(p["atual"]["inicio"])
    inicio_anterior = dt.date.fromisoformat(p["anterior"]["inicio"])
    pontos = []
    for i, (hoje, antes) in enumerate(zip(site()["visitantes_por_dia"], site()["visitantes_por_dia_anterior"])):
        pontos.append(
            {
                "data": (inicio + dt.timedelta(days=i)).isoformat(),
                "visitantes": hoje,
                "data_anterior": (inicio_anterior + dt.timedelta(days=i)).isoformat(),
                "visitantes_anterior": antes,
                "variacao": variacao(hoje, antes),
            }
        )
    return pontos


def areas() -> list[dict]:
    return [{**a, "variacao": variacao(a["visitas"], a["visitas_anterior"])} for a in site()["areas_do_site"]]


def instagram_de_relance() -> dict:
    ig = SEED["instagram"]
    return {
        "estado": "ok",
        "seguidores": {"total": ig["seguidores"]["total"], "crescimento": ig["seguidores"]["crescimento"]},
        "alcance": fluxo(ig["alcance"]),
        "visualizacoes": fluxo(ig["visualizacoes"]),
        "interacoes": fluxo(ig["interacoes"]),
    }


def objetivo(identificador: str) -> dict:
    return next(o for o in SEED["objetivos"] if o["id"] == identificador)


def visao_geral() -> dict:
    origens = percentuais(site()["origem_do_publico"])
    dispositivos = percentuais(site()["dispositivos"])
    area = max(site()["areas_do_site"], key=lambda a: a["visitas"])
    em_foco = [
        {k: o[k] for k in ("id", "nome", "descricao")}
        | {"numero": {"rotulo": o["numero"]["rotulo"], "valor": o["numero"]["valor"]}}
        for o in SEED["objetivos"][:3]
    ]
    return {
        "periodo": periodo(),
        "visitantes": {
            "estado": "ok",
            **fluxo(site()["visitantes"]),
            "contexto": {
                "area": {"chave": area["chave"], "nome": area["nome"], "visitas": area["visitas"]},
                "origem": {k: origens[0][k] for k in ("chave", "rotulo", "percentual")},
                "dispositivo": {k: dispositivos[0][k] for k in ("chave", "rotulo", "percentual")},
            },
        },
        "instagram": instagram_de_relance(),
        "objetivos": {"em_foco": em_foco},
        "frescor": frescor(),
    }


def dados_do_google() -> dict:
    return {
        "periodo": periodo(),
        "movimento": movimento(),
        "dispositivos": percentuais(site()["dispositivos"]),
        "areas_do_site": areas(),
        "origem_do_publico": percentuais(site()["origem_do_publico"]),
        "contatos_gerados": site()["contatos_gerados"],
        "frescor": frescor(),
    }


def instagram() -> dict:
    ig = SEED["instagram"]
    return {
        "periodo": periodo(),
        "seguidores": ig["seguidores"],
        "alcance": fluxo(ig["alcance"]),
        "visualizacoes": fluxo(ig["visualizacoes"]),
        "engajamento": {
            "interacoes": ig["interacoes"]["atual"],
            "interacoes_anterior": ig["interacoes"]["anterior"],
            "variacao": variacao(ig["interacoes"]["atual"], ig["interacoes"]["anterior"]),
            "partes": ig["partes"],
            "contas_engajadas": ig["contas_engajadas"]["atual"],
            "contas_engajadas_anterior": ig["contas_engajadas"]["anterior"],
        },
        "principais_publicacoes": [
            {
                "id": p["id"],
                "legenda": p["legenda"],
                "tipo": p["tipo"],
                "rotulo_tipo": p["rotulo_tipo"],
                "miniatura": f"{MINIATURAS}/{p['id']}.svg",
                "link": "#",
                "interacoes": p["interacoes"],
            }
            for p in ig["principais_publicacoes"]
        ],
        "frescor": frescor(),
    }


def galeria() -> dict:
    return {"objetivos": SEED["objetivos"], "frescor": frescor()}


def lente() -> dict:
    ig = SEED["instagram"]
    o = objetivo(SEED["lente"]["id"])
    return {
        "objetivo": {k: o[k] for k in ("id", "nome", "descricao")},
        "periodo": {"chave": "28d", "dias": DIAS},
        "periodos": ["7d", "28d"],
        "numeros": [
            {
                "chave": "interactions",
                "rotulo": "Interações",
                "valor": ig["interacoes"]["atual"],
                "anterior": ig["interacoes"]["anterior"],
                "variacao": variacao(ig["interacoes"]["atual"], ig["interacoes"]["anterior"]),
            },
            {
                "chave": "accountsEngaged",
                "rotulo": "Contas que engajaram",
                "valor": ig["contas_engajadas"]["atual"],
                "anterior": ig["contas_engajadas"]["anterior"],
                "variacao": variacao(ig["contas_engajadas"]["atual"], ig["contas_engajadas"]["anterior"]),
            },
        ],
        "sugestoes": SEED["lente"]["sugestoes"],
        "frescor": frescor(),
    }


def leituras(lista: list[dict], mes: dt.date) -> list[dict]:
    return [
        {
            "lida_em": dt.datetime(mes.year, mes.month, item["dia"], 12, tzinfo=dt.timezone.utc).isoformat(),
            "nota": item["nota"],
            "total": item["total"],
        }
        for item in lista
    ]


def nota() -> dict:
    n = SEED["nota"]
    este_mes = HOJE.replace(day=1)
    mes_anterior = (este_mes - dt.timedelta(days=1)).replace(day=1)
    do_mes = leituras(n["leituras_do_mes"], este_mes)
    o = objetivo("google-reputacao")
    ligado_em = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=n["convite"]["ligado_ha_dias"])
    pontos = [{**p, "taxa": p["cliques"] / p["convites"]} for p in n["convite"]["pontos"]]
    convites = sum(p["convites"] for p in pontos)
    cliques = sum(p["cliques"] for p in pontos)
    p = periodo()
    return {
        "objetivo": {k: o[k] for k in ("id", "nome", "descricao")},
        "reputacao": {
            "medida": True,
            "nota": do_mes[-1]["nota"],
            "escala": n["escala"],
            "total": do_mes[-1]["total"],
            "lida_em": do_mes[-1]["lida_em"],
            "avaliacoes_do_mes": do_mes[-1]["total"] - do_mes[0]["total"],
            "nota_mes_anterior": n["nota_mes_anterior"],
            "tendencia": n["tendencia"],
            "leituras_do_mes": do_mes,
            "leituras_mes_anterior": leituras(n["leituras_mes_anterior"], mes_anterior),
        },
        "convite": {
            "periodo": "28d",
            "ligado": True,
            "ligado_em": ligado_em.isoformat(),
            "dias_ligado": n["convite"]["ligado_ha_dias"],
            "dias_do_teste": 60,
            "reavaliar": False,
            "intervalo": p["atual"],
            "pontos": pontos,
            "total": {"convites": convites, "cliques": cliques, "taxa": cliques / convites},
        },
    }


TELAS = {
    "visao-geral": visao_geral,
    "dados-do-google": dados_do_google,
    "instagram": instagram,
    "objetivos": galeria,
    "lente": lente,
    "nota": nota,
    "ao-vivo": lambda: {"pessoas": site()["ao_vivo"]},
}

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "miniatura":
        print(miniatura(sys.argv[2]))
        raise SystemExit(0)
    if len(sys.argv) != 2 or sys.argv[1] not in TELAS:
        raise SystemExit(f"uso: respostas.py <{'|'.join(TELAS)}>")
    print(json.dumps(TELAS[sys.argv[1]](), ensure_ascii=False))
