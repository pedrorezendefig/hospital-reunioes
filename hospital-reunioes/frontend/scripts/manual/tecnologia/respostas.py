#!/usr/bin/env python3
"""As respostas de exemplo da aba Tecnologia para os prints do manual (issue
#1727, ADR 0094, decisão 5).

Imprime, em JSON, a tabela que o `roteiro.sh` serve no lugar do backend: a
chave é a rota depois de `/api/admin/tecnologia/`, com a consulta quando há
(`chat?projeto=ana`), e o valor é o corpo da resposta. Tudo sai do `seed.json`,
com as datas contadas a partir de hoje, no fuso do hospital: assim o Quadro
abre com as colunas cheias e as Entregas caem nas últimas semanas, em qualquer
dia que o roteiro rodar. Nada aqui é gente, pedido ou card de verdade.

Uso: python3 scripts/manual/tecnologia/respostas.py
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

AQUI = Path(__file__).resolve().parent
SEED = json.loads((AQUI / "seed.json").read_text(encoding="utf-8"))
FUSO = ZoneInfo("America/Sao_Paulo")
HOJE = datetime.now(FUSO).date()
SEMANAS_DO_GRAFICO = 12


def instante(dias_atras: int, hora: str = "10:00") -> str:
    """O instante de `dias_atras` dias antes de hoje, na hora dada, no fuso do hospital."""
    h, m = (int(p) for p in hora.split(":"))
    return datetime.combine(HOJE - timedelta(days=dias_atras), time(h, m), FUSO).isoformat()


def segunda(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def demanda(d: dict) -> dict:
    """A Demanda como a lista do chat a manda, vista pelo diretor que pediu."""
    registrada = d["etapa"] == "registrada"
    entregue = d.get("entregue_ha")
    entregues, total = d.get("partes", [None, None])
    textos = d.get("partes_texto", [])
    partes = [
        {
            "o_que_muda": texto,
            "situacao": "em_producao" if i < entregues else ("em_desenvolvimento" if i == entregues else "planejada"),
            "fechada_em": instante(10 - 3 * i) if i < entregues else None,
        }
        for i, texto in enumerate(textos)
    ]
    return {
        "id": d["id"],
        "numero": d["numero"],
        "titulo": d["titulo"],
        "criado_em": instante(d["dias"], d["hora"]),
        "etapa": d["etapa"],
        "classificacao": d["classificacao"],
        "projeto": d["projeto"],
        "origem": d["origem"],
        "minha": d["origem"] == "diretor",
        "tem_vinculo": not registrada,
        "responsavel": d.get("responsavel"),
        "partes_entregues": entregues,
        "partes_total": total,
        "partes": partes,
        "o_que_muda": d.get("o_que_muda"),
        "versao": d.get("versao") if d["etapa"] == "em_producao" else None,
        "fechada_em": instante(entregue) if entregue is not None else None,
        "em_producao_em": instante(entregue, "18:00") if d["etapa"] == "em_producao" else None,
        "demonstracao_url": d.get("demonstracao"),
        "demonstracao_em": instante(entregue) if d.get("demonstracao") else None,
        "autor": None,
        "issue_numero": None,
        "issue_url": None,
        "envio_falhou": False,
        "designacao_falhou": False,
        "envio_motivo": None,
        "pode_apagar": registrada,
        "pode_revisar": False,
        "em_revisao": False,
    }


def fala(f: dict) -> dict:
    return {
        "autor": f["autor"],
        "texto": f["texto"],
        "fonte": None,
        "opcoes": f.get("opcoes", []),
        "recomendada": f.get("recomendada"),
        "nao_bateu": False,
        "cartao": f.get("cartao"),
    }


def conversa(demanda_id: str, estado: str, falas: list[dict], **resto) -> dict:
    return {
        "demanda_id": demanda_id,
        "estado": estado,
        "mensagens": [fala(f) for f in falas],
        "resumo": None,
        "resumo_da_melhoria": None,
        "anexos": 0,
        "planejamento": False,
        "aviso_dos_anexos": None,
        "custo": None,
        "anexos_da_demanda": [],
        "responsavel": None,
        "documento": None,
        "revisao": None,
        **resto,
    }


def conversas(lista: list[dict]) -> dict:
    """A conversa com o Assistente de cada pedido do diretor, e a Conversa da Demanda de cada card."""
    abrir = SEED["abrir"]
    tabela: dict[str, dict] = {}
    for d in lista:
        if d["origem"] != "vitta":
            pedido = {"autor": "diretor", "texto": f"Quero {d['titulo'][0].lower()}{d['titulo'][1:]}."}
            tabela[f"chat/{d['id']}"] = conversa(
                d["id"], "enviado" if d["tem_vinculo"] else "em_andamento", [pedido], responsavel=d["responsavel"]
            )
        if d["tem_vinculo"]:
            tabela[f"chat/{d['id']}/conversa"] = {"mensagens": [], "mencionaveis": []}

    melhoria = SEED["melhoria"]
    tabela[f"chat/{abrir['melhoria']}"] = conversa(
        abrir["melhoria"],
        "em_andamento",
        melhoria["falas"],
        planejamento=True,
        documento=melhoria["documento"],
        custo=melhoria["custo"],
    )
    bug = SEED["bug"]
    tabela[f"chat/{abrir['bug']}"] = conversa(
        abrir["bug"], "resumido", bug["falas"], resumo=bug["resumo"], custo=bug["custo"]
    )
    tabela[f"chat/{abrir['painel']}/conversa"] = {
        "mensagens": [
            {
                "id": f"exemplo-mensagem-{i}",
                "autor": m["autor"],
                "texto": m["texto"],
                "criado_em": instante(m["dias"], f"{9 + i}:15"),
                "minha": m["minha"],
            }
            for i, m in enumerate(SEED["conversa_da_demanda"])
        ],
        "mencionaveis": [{"id": dev["id"], "nome": dev["nome"]} for dev in SEED["desenvolvedores"]],
    }
    return tabela


def entregas(lista: list[dict]) -> dict:
    """O ritmo das 12 semanas e a lista por semana, como a aba Entregas os lê."""
    corrente = segunda(HOJE)
    inicios = [corrente - timedelta(weeks=atras) for atras in range(SEMANAS_DO_GRAFICO - 1, -1, -1)]

    anteriores = [
        {
            **demanda(
                {
                    "id": f"exemplo-entrega-{i}",
                    "numero": 30 + i,
                    "dias": e["entregue_ha"] + 10,
                    "hora": "10:00",
                    "etapa": "em_producao" if e.get("versao") else "entregue",
                    "origem": "diretor" if e["projeto"] == "hospital" else "vitta",
                    **e,
                }
            ),
            "tamanho": e["tamanho"],
        }
        for i, e in enumerate(SEED["entregas_anteriores"], start=1)
    ]
    do_quadro = [{**demanda(d), "tamanho": d["tamanho"]} for d in SEED["demandas"] if "tamanho" in d]
    entregues = sorted(do_quadro + anteriores, key=lambda e: e["fechada_em"], reverse=True)

    def semana_de(e: dict) -> date:
        return segunda(datetime.fromisoformat(e["fechada_em"]).date())

    semanas = []
    for inicio, ritmo in zip(inicios, SEED["ritmo"]):
        saiu = [e for e in entregues if semana_de(e) == inicio]
        contagem = {t.lower(): sum(1 for e in saiu if e["tamanho"] == t) for t in "GMP"} if saiu else {
            t: ritmo[t] for t in "gmp"
        }
        semanas.append(
            {
                "inicio": inicio.isoformat(),
                "pedidos": ritmo["pedidos"],
                **contagem,
                "entregas": [{"titulo": e["titulo"], "tamanho": e["tamanho"], "projeto": e["projeto"]} for e in saiu],
            }
        )

    def soma(trecho: list[dict], *chaves: str) -> int:
        return sum(s[c] for s in trecho for c in chaves)

    topo, antes = semanas[-4:], semanas[-8:-4]
    pedidos = soma(topo, "pedidos")
    bugs = round(pedidos * 0.3)
    grupos = [
        {"inicio": inicio.isoformat(), "entregas": [e for e in entregues if semana_de(e) == inicio]}
        for inicio in reversed(inicios)
        if any(semana_de(e) == inicio for e in entregues)
    ]
    return {
        "topo": {
            "pedidos": {"total": pedidos, "anteriores": soma(antes, "pedidos"), "bugs": bugs, "melhorias": pedidos - bugs},
            "entregas": {
                "total": soma(topo, "g", "m", "p"),
                "anteriores": soma(antes, "g", "m", "p"),
                "g": soma(topo, "g"),
                "m": soma(topo, "m"),
                "p": soma(topo, "p"),
            },
        },
        "semanas": semanas,
        "grupos": grupos,
        "proximo_corte": inicios[0].isoformat(),
        "responsaveis": [{"valor": dev["id"], "nome": dev["nome"]} for dev in SEED["desenvolvedores"]],
    }


def tabela() -> dict:
    lista = [demanda(d) for d in SEED["demandas"]]
    return {
        "eu": {"desenvolvedor": False},
        "desenvolvedores": SEED["desenvolvedores"],
        "chat": lista,
        "chat?projeto=ana": [d for d in lista if d["projeto"] == "ana"],
        "chat?projeto=hospital": [d for d in lista if d["projeto"] == "hospital"],
        **conversas(lista),
        "entregas": entregas(lista),
    }


if __name__ == "__main__":
    print(json.dumps(tabela(), ensure_ascii=False))
