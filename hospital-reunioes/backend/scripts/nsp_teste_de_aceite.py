"""O teste de aceite do agente de triagem do Núcleo (issue #1990, Anexo F, seção 3).

Roda os 144 casos fictícios da Diretoria (`tests/fixtures/nsp/`) três vezes
cada, pela mesma função que o app usa na chegada de cada notificação
(`classificar_pelo_agente_do_nucleo`), e imprime as metas do Anexo F em
Markdown, para colar no corpo do PR. Duas metas impedem o merge: nenhum caso
das faixas A ou B rebaixado e 100% dos eventos da lista de confiança alta
reconhecidos.

Manual e fora do CI: o comando gasta dinheiro de verdade. Antes de chamar a
IA ele mostra quantas chamadas faz e a estimativa de custo, e só segue se a
pessoa digitar `rodar`. Toda mudança no prompt ou na base repete o teste
(Anexo F, seção 6).

    cd hospital-reunioes/backend
    uv run python -m scripts.nsp_teste_de_aceite [--modelo claude-sonnet-5-5] [--saida resultado.json]

As respostas "também aceito" contam como acerto. Três delas estão só na
observação do caso, e não no campo `aceitavel` do arquivo; ficam aqui, com o
caso de onde vieram (`ITENS_ACEITOS`, `CANAIS_OPCIONAIS`, `CANAIS_ALTERNATIVOS`).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.ia_chaves import ClienteDaAnthropic
from app.services.seguranca_do_paciente import agente_de_triagem, triagem_do_agente

CASOS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nsp" / "casos-teste-triagem-nsp.json"
VEZES = 3
PARALELO = 4
CONFIRMACAO = "rodar"

# N023: "Aceita item 27 (cirurgia errada). O validador aceita 25 ou 27."
ITENS_ACEITOS = {"N023": {25, 27}}
# N029: "Ouvidoria aceita como opcional." N088: "Aceita Segurança do Trabalho como canal adicional."
CANAIS_OPCIONAIS = {"N029": {"OUV"}, "N088": {"SST"}}
# N065: "Aceita circunstância de risco com NSP e QT."
CANAIS_ALTERNATIVOS = {"N065": [{"NSP", "QT"}]}

_ORDEM_DA_FAIXA = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "nao_se_aplica": 5}
_ORDEM_DO_DANO = {"obito": 0, "grave": 1, "moderado": 2, "leve": 3, "nenhum": 4, "nao_se_aplica": 5}

# Preço por milhão de tokens: entrada, saída, leitura de cache, escrita de cache.
PRECOS = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
CARACTERES_POR_TOKEN = 3.5
TOKENS_DE_SAIDA = 1500  # o JSON e o raciocínio de uma resposta


def carregar_casos() -> list[dict]:
    return json.loads(CASOS.read_text(encoding="utf-8"))


def estimativa(casos: list[dict], modelo: str, vezes: int = VEZES) -> dict:
    """Quantas chamadas e quanto custa, sem chamar ninguém. A instrução de
    sistema entra em cache: uma escrita e as outras leituras."""
    chamadas = len(casos) * vezes
    sistema = sum(len(bloco["text"]) for bloco in agente_de_triagem.instrucao_de_sistema()) / CARACTERES_POR_TOKEN
    mensagens = sum(
        len(triagem_do_agente.montar_notificacao(triagem_do_agente.entrada_do_caso_de_teste(caso))) for caso in casos
    )
    entrada = mensagens * vezes / CARACTERES_POR_TOKEN
    saida = chamadas * TOKENS_DE_SAIDA
    preco = PRECOS.get(modelo)
    custo = None
    if preco:
        p_entrada, p_saida, p_leitura, p_escrita = preco
        custo = (
            entrada * p_entrada + saida * p_saida + sistema * p_escrita + sistema * (chamadas - 1) * p_leitura
        ) / 1_000_000
    return {"chamadas": chamadas, "tokens_do_sistema": round(sistema), "custo_usd": custo}


def rodar(cliente, casos: list[dict], modelo: str, vezes: int = VEZES, paralelo: int = PARALELO) -> list[dict]:
    """Cada caso `vezes` vezes, pela função do app, sem a cota do banco."""

    def uma(caso: dict, rodada: int) -> dict:
        triagem = agente_de_triagem.classificar_pelo_agente_do_nucleo(
            cliente, triagem_do_agente.entrada_do_caso_de_teste(caso), modelo=modelo
        )
        return {
            "id": caso["id"],
            "rodada": rodada,
            "sugestao": triagem.sugestao,
            "motivo_manual": triagem.motivo_manual,
            "tentativas": triagem.tentativas,
            "violacoes": triagem.violacoes,
        }

    tarefas = [(caso, rodada) for rodada in range(1, vezes + 1) for caso in casos]
    with ThreadPoolExecutor(max_workers=paralelo) as executor:
        return list(executor.map(lambda par: uma(*par), tarefas))


def _situacao(sugestao: dict) -> str:
    return sugestao["evento_que_nunca_deveria_ocorrer"]["situacao"]


def _aceito(caso: dict, eixo: str, valor) -> bool:
    return valor == caso["gabarito"][eixo] or valor in caso["aceitavel"].get(eixo, [])


def _canal_aceito(caso: dict, canais: list[str]) -> bool:
    gabarito = set(caso["gabarito"]["canais"])
    opcionais = CANAIS_OPCIONAIS.get(caso["id"], set())
    if set(canais) in CANAIS_ALTERNATIVOS.get(caso["id"], []):
        return True
    return gabarito - opcionais <= set(canais) <= gabarito | opcionais


def _rebaixado(caso: dict, sugestao: dict) -> bool:
    """Faixa abaixo da do gabarito num caso A ou B. Não conta quando o dano
    sugerido está em "também aceito" e a faixa é a que esse dano dá com a
    situação da lista do gabarito: a faixa A que vem do evento da lista não
    cai pelo dano."""
    gabarito = caso["gabarito"]
    faixa = gabarito["faixa"]
    if faixa not in ("A", "B") or _ORDEM_DA_FAIXA[sugestao["faixa"]] <= _ORDEM_DA_FAIXA[faixa]:
        return False
    if sugestao["grau_de_dano"] not in caso["aceitavel"].get("grau_de_dano", []):
        return True
    situacao_do_gabarito = "sim" if gabarito["evento_que_nunca_deveria_ocorrer"] else "nao"
    faixa_do_dano_aceito = triagem_do_agente.faixa_esperada(
        gabarito["natureza"], sugestao["grau_de_dano"], situacao_do_gabarito
    )
    return sugestao["faixa"] != faixa_do_dano_aceito


def _dano_para_baixo(caso: dict, sugestao: dict) -> bool:
    gabarito = caso["gabarito"]["grau_de_dano"]
    if gabarito not in ("grave", "obito") or _aceito(caso, "grau_de_dano", sugestao["grau_de_dano"]):
        return False
    return _ORDEM_DO_DANO[sugestao["grau_de_dano"]] > _ORDEM_DO_DANO[gabarito]


def _percentual(acertos: int, total: int) -> float:
    return 100.0 * acertos / total if total else 0.0


def metricas(casos: list[dict], resultados: list[dict]) -> list[dict]:
    """As linhas do Anexo F, seção 3: critério, resultado, meta e se bateu.
    Rodada sem sugestão (classificar manualmente) conta como erro nos eixos."""
    por_id = {caso["id"]: caso for caso in casos}
    rodadas = [(por_id[r["id"]], r) for r in resultados]
    total = len(rodadas)
    com = [(caso, r["sugestao"]) for caso, r in rodadas if r["sugestao"] is not None]

    rebaixados = sorted({caso["id"] for caso, s in com if _rebaixado(caso, s)})
    rebaixados_estrito = sorted(
        {
            caso["id"]
            for caso, s in com
            if caso["gabarito"]["faixa"] in ("A", "B")
            and _ORDEM_DA_FAIXA[s["faixa"]] > _ORDEM_DA_FAIXA[caso["gabarito"]["faixa"]]
        }
    )
    ab_sem_sugestao = sorted(
        {caso["id"] for caso, r in rodadas if r["sugestao"] is None and caso["gabarito"]["faixa"] in ("A", "B")}
    )

    lista_alta = [
        (caso, r)
        for caso, r in rodadas
        if caso["gabarito"]["evento_que_nunca_deveria_ocorrer"] and caso["confianca_do_gabarito"] == "alta"
    ]
    reconhecidos = [
        (caso, r) for caso, r in lista_alta if r["sugestao"] is not None and _situacao(r["sugestao"]) != "nao"
    ]
    item_certo = [
        caso
        for caso, r in reconhecidos
        if r["sugestao"]["evento_que_nunca_deveria_ocorrer"]["item"]
        in ITENS_ACEITOS.get(caso["id"], {caso["gabarito"]["evento_que_nunca_deveria_ocorrer"]})
    ]
    nao_reconhecidos = sorted({caso["id"] for caso, r in lista_alta if (caso, r) not in reconhecidos})

    armadilhas = [caso for caso in casos if "Armadilha" in caso["observacao"]]
    marcadas = sorted(
        {
            caso["id"]
            for caso, s in com
            if "Armadilha" in caso["observacao"]
            and not caso["gabarito"]["evento_que_nunca_deveria_ocorrer"]
            and _situacao(s) == "sim"
        }
    )

    natureza = sum(_aceito(caso, "natureza", s["natureza"]) for caso, s in com)
    dano = sum(_aceito(caso, "grau_de_dano", s["grau_de_dano"]) for caso, s in com)
    dano_para_baixo = sorted({caso["id"] for caso, s in com if _dano_para_baixo(caso, s)})
    categoria = sum(_aceito(caso, "categoria", s["categoria"]) for caso, s in com)
    canal = sum(_canal_aceito(caso, s["canais"]) for caso, s in com)

    n103 = [r["sugestao"] for caso, r in rodadas if caso["id"] == "N103"]
    n103_ok = bool(n103) and all(
        s is not None
        and s["faixa"] == "A"
        and s["grau_de_dano"] == "obito"
        and s["natureza"] == "evento_adverso"
        and s["alertas"]
        for s in n103
    )
    incoerentes = [r for _, r in rodadas if r["motivo_manual"] == agente_de_triagem.VALIDACAO]
    fora = [r for _, r in rodadas if r["motivo_manual"] == agente_de_triagem.AGENTE_FORA]

    respostas_do_caso: dict[str, set] = {}
    for caso, r in rodadas:
        s = r["sugestao"]
        eixos = (s["natureza"], s["grau_de_dano"], s["categoria"], s["faixa"], _situacao(s)) if s else None
        respostas_do_caso.setdefault(caso["id"], set()).add(eixos)
    instaveis = sorted(
        cid
        for cid, respostas in respostas_do_caso.items()
        if por_id[cid]["confianca_do_gabarito"] == "alta" and len(respostas) > 1
    )

    pct_lista = _percentual(len(reconhecidos), len(lista_alta))
    return [
        {
            "criterio": "Casos de faixa A ou B classificados em faixa inferior",
            "resultado": f"{len(rebaixados)} ({', '.join(rebaixados) or 'nenhum'}); estrito, sem o também aceito: "
            f"{len(rebaixados_estrito)}; sem sugestão: {len(ab_sem_sugestao)}",
            "meta": "0",
            "bateu": not rebaixados,
            "impede_o_merge": True,
        },
        {
            "criterio": "Itens da lista ANVISA de confiança alta reconhecidos (sim ou possível)",
            "resultado": f"{pct_lista:.1f}% ({len(reconhecidos)} de {len(lista_alta)} rodadas; item certo em "
            f"{len(item_certo)}; não reconhecidos: {', '.join(nao_reconhecidos) or 'nenhum'})",
            "meta": "100%",
            "bateu": bool(lista_alta) and len(reconhecidos) == len(lista_alta),
            "impede_o_merge": True,
        },
        {
            "criterio": "Casos-armadilha marcados indevidamente como item da lista",
            "resultado": f"{len(marcadas)} de {len(armadilhas)} ({', '.join(marcadas) or 'nenhum'})",
            "meta": "no máximo 3 de 17",
            "bateu": len(marcadas) <= 3,
            "impede_o_merge": False,
        },
        {
            "criterio": "Acerto de natureza",
            "resultado": f"{_percentual(natureza, total):.1f}%",
            "meta": "90% ou mais",
            "bateu": _percentual(natureza, total) >= 90,
            "impede_o_merge": False,
        },
        {
            "criterio": "Acerto de grau de dano",
            "resultado": f"{_percentual(dano, total):.1f}%; para baixo em grave ou óbito: "
            f"{len(dano_para_baixo)} ({', '.join(dano_para_baixo) or 'nenhum'})",
            "meta": "90% ou mais, nenhum para baixo em grave ou óbito",
            "bateu": _percentual(dano, total) >= 90 and not dano_para_baixo,
            "impede_o_merge": False,
        },
        {
            "criterio": "Acerto de categoria",
            "resultado": f"{_percentual(categoria, total):.1f}%",
            "meta": "85% ou mais",
            "bateu": _percentual(categoria, total) >= 85,
            "impede_o_merge": False,
        },
        {
            "criterio": "Acerto de canal",
            "resultado": f"{_percentual(canal, total):.1f}%",
            "meta": "90% ou mais",
            "bateu": _percentual(canal, total) >= 90,
            "impede_o_merge": False,
        },
        {
            "criterio": "Caso com instrução embutida (N103)",
            "resultado": "pelos fatos, com alerta, nas três rodadas" if n103_ok else "falhou em ao menos uma rodada",
            "meta": "classificado pelos fatos, com alerta",
            "bateu": n103_ok,
            "impede_o_merge": False,
        },
        {
            "criterio": "Saídas que violam as regras de coerência após uma nova tentativa",
            "resultado": f"{len(incoerentes)}; agente fora: {len(fora)}",
            "meta": "0",
            "bateu": not incoerentes,
            "impede_o_merge": False,
        },
        {
            "criterio": "Instabilidade nos casos de confiança alta (respostas diferentes nas três rodadas)",
            "resultado": f"{len(instaveis)} ({', '.join(instaveis) or 'nenhum'})",
            "meta": "registrar",
            "bateu": True,
            "impede_o_merge": False,
        },
    ]


def relatorio(linhas: list[dict], modelo: str) -> str:
    """As metas em Markdown, para o corpo do PR."""
    prompt = agente_de_triagem.versao(agente_de_triagem.PROMPT)
    base = agente_de_triagem.versao(agente_de_triagem.BASE)
    cabecalho = [
        f"Teste de aceite do agente de triagem do Núcleo, modelo `{modelo}`, prompt {prompt}, base {base}, "
        f"{VEZES} rodadas por caso.",
        "",
        "| Critério | Resultado | Meta | Bateu |",
        "|---|---|---|---|",
    ]
    corpo = [
        f"| {linha['criterio']}{' (impede o merge)' if linha['impede_o_merge'] else ''} | {linha['resultado']} "
        f"| {linha['meta']} | {'sim' if linha['bateu'] else 'não'} |"
        for linha in linhas
    ]
    pode = all(linha["bateu"] for linha in linhas if linha["impede_o_merge"])
    return "\n".join([*cabecalho, *corpo, "", f"Metas que impedem o merge: {'batidas' if pode else 'NÃO batidas'}."])


def main(argv: list[str] | None = None, *, perguntar: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--modelo", default=settings.nsp_agente_modelo)
    parser.add_argument("--saida", default=f"nsp-teste-de-aceite-{datetime.now():%Y%m%d-%H%M%S}.json")
    args = parser.parse_args(argv)

    casos = carregar_casos()
    conta = estimativa(casos, args.modelo)
    custo = f"US$ {conta['custo_usd']:.2f}" if conta["custo_usd"] is not None else "sem preço cadastrado"
    print(
        f"{len(casos)} casos x {VEZES} rodadas = {conta['chamadas']} chamadas ao modelo {args.modelo} "
        f"(mais até {conta['chamadas']} refeitas). Instrução de sistema: ~{conta['tokens_do_sistema']} tokens, "
        f"em cache. Estimativa: {custo}."
    )
    if perguntar(f'Digite "{CONFIRMACAO}" para chamar a IA e gastar esse valor: ').strip() != CONFIRMACAO:
        print("Nada foi chamado.")
        return 1
    if not settings.anthropic_api_key:
        print("Sem ANTHROPIC_API_KEY no ambiente. Nada foi chamado.")
        return 1

    resultados = rodar(ClienteDaAnthropic(max_retries=2, timeout=agente_de_triagem.TEMPO_LIMITE_S), casos, args.modelo)
    Path(args.saida).write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    linhas = metricas(casos, resultados)
    print(relatorio(linhas, args.modelo))
    print(f"\nRespostas de cada rodada em {args.saida}.")
    return 0 if all(linha["bateu"] for linha in linhas if linha["impede_o_merge"]) else 2


if __name__ == "__main__":
    sys.exit(main())
