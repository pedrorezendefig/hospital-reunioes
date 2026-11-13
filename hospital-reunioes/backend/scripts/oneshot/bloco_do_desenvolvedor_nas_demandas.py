"""A passada única do bloco "Para o desenvolvedor" (issue #1636, PRD #1632).

O card que nasce hoje já traz o bloco "🛠️ Para o desenvolvedor" logo depois
do bloco "Para o diretor" (issue #1633). Este comando põe o mesmo bloco nas
Demandas que já estavam na fila:

- entram as Demandas da Origem "Pedido do diretor", não apagadas, com issue
  vinculada e aberta, cujo corpo ainda não tem o bloco. A Demanda da Origem
  Vitta fica de fora;
- para cada uma, o modelo escreve as seis partes a partir da conversa com o
  agente e do corpo da issue, e o bloco sai pela mesma função do "Criar o
  card" (`bloco_do_desenvolvedor`), inserido pela mesma função
  (`inserir_bloco_do_desenvolvedor`): o resto do corpo, o marcador da Demanda
  inclusive, fica igual byte a byte;
- falha do modelo ou do GitHub numa Demanda vai para o relatório e a passada
  segue com as outras;
- nenhum email sai. A Conversa da Demanda (a de gente com gente) não entra no
  pedido ao modelo: ela nunca vai para a issue.

Rodar de novo não duplica: a issue que já tem o bloco sai da lista.

A chamada ao modelo tem custo e só roda por esta ação do Pedro (ADR 0082). A
prévia também chama o modelo, para mostrar o bloco de cada issue; o custo de
cada chamada fica em `tecnologia_chamadas_ia`, nas duas formas. O `--aplicar`
pede o bloco ao modelo de novo, e o relatório mostra o bloco que foi gravado.

Prévia (mostra quais issues mudam e o bloco de cada uma, sem gravar no GitHub):
    uv run python -m scripts.oneshot.bloco_do_desenvolvedor_nas_demandas

Aplicar (grava o bloco no corpo de cada issue no GitHub):
    uv run python -m scripts.oneshot.bloco_do_desenvolvedor_nas_demandas --aplicar
"""

from __future__ import annotations

import argparse
import sys

from supabase import create_client

from app.config import settings
from app.services import ai_processor, chat_tecnologia, github_client, planejamento_demanda
from app.services.conhecimento import carregar_kit
from app.services.tecnologia import (
    ORIGEM_DIRETOR,
    TABELA_DEMANDAS,
    TIPO_ROTULO,
    origem_da_demanda,
    recuar_continuacao,
)
from app.services.tecnologia_vinculo import (
    PARTES_DO_DESENVOLVEDOR,
    bloco_do_desenvolvedor,
    bloco_para_o_diretor,
    inserir_bloco_do_desenvolvedor,
    tem_bloco_do_desenvolvedor,
)

PROMPT = "bloco_do_desenvolvedor_system"

PREVIA = "prévia"
GRAVADO = "gravado"
FALHOU = "falhou"

MOTIVO_SEM_BLOCO_DO_DIRETOR = 'o corpo da issue não tem o bloco "Para o diretor"'
MOTIVO_MODELO = "o modelo não devolveu as seis partes"


def demandas_da_passada(supabase) -> list[dict]:
    """As Demandas do diretor, não apagadas e com issue vinculada. Se a issue
    está aberta e sem o bloco, só o GitHub diz."""
    linhas = (
        supabase.table(TABELA_DEMANDAS)
        .select("id, titulo, descricao, tipo, origem, github_issue_numero, criado_em")
        .is_("apagada_em", "null")
        .order("criado_em")
        .execute()
    ).data or []
    return [d for d in linhas if origem_da_demanda(d) == ORIGEM_DIRETOR and d.get("github_issue_numero")]


def pedido_da_passada(demanda: dict, mensagens: list[dict], corpo: str) -> str:
    """O que vai ao modelo: a Demanda, a conversa com o agente e o corpo da
    issue, cada texto de fora recuado para não passar por moldura."""
    antes, planejamento = chat_tecnologia.partes_da_melhoria(mensagens)
    conversa = [chat_tecnologia._linha_da_conversa(m) for m in antes] + [
        planejamento_demanda._linha_da_conversa(m) for m in planejamento
    ]
    tipo = str(demanda.get("tipo") or "")
    return "\n".join(
        [
            "PEDIDO: BLOCO PARA O DESENVOLVEDOR",
            "",
            "A DEMANDA",
            f"Tipo: {TIPO_ROTULO.get(tipo, tipo)}",
            recuar_continuacao(f"Título: {demanda.get('titulo') or ''}"),
            "Descrição:",
            recuar_continuacao(f"    {demanda.get('descricao') or '(sem descrição)'}"),
            "",
            "A CONVERSA COM O AGENTE",
            "\n".join(conversa) or "(sem conversa com o agente)",
            "",
            "O CORPO DA ISSUE",
            recuar_continuacao(f"    {corpo}"),
        ]
    )


def _seis_partes(dados) -> dict[str, str]:
    """As seis partes da resposta. Sem nenhuma delas, a resposta não serve."""
    if not isinstance(dados, dict):
        raise ValueError("resposta fora do formato")
    partes = {chave: str(dados.get(chave) or "").strip() for chave in PARTES_DO_DESENVOLVEDOR}
    if not any(partes.values()):
        raise ValueError("resposta sem nenhuma das seis partes")
    return partes


def _bloco_do_modelo(supabase, demanda: dict, corpo: str, kit: str) -> str | None:
    """O bloco escrito pelo modelo, ou `None` quando ele falhou. A linha de
    custo é gravada nos dois casos: o provedor cobra a resposta ruim também."""
    planejamento = planejamento_demanda.ler(supabase, str(demanda["id"])) or {}
    partes, chamada = planejamento_demanda.chamar_o_modelo(
        demanda=demanda,
        passo="resumo",
        conteudo=pedido_da_passada(demanda, planejamento.get("mensagens") or [], corpo),
        kit=kit,
        validar=_seis_partes,
        prompt=PROMPT,
    )
    planejamento_demanda.gravar_chamada(supabase, chamada)
    return bloco_do_desenvolvedor(partes) if partes else None


def passada(supabase, *, aplicar: bool, kit: str) -> list[dict]:
    """A passada inteira. Devolve o relatório, uma linha por issue que mudaria:
    `situacao` é prévia, gravado ou falhou, com o `bloco` ou o `motivo`."""
    relatorio: list[dict] = []
    for demanda in demandas_da_passada(supabase):
        numero = int(demanda["github_issue_numero"])
        linha = {"demanda_id": str(demanda["id"]), "numero": numero, "bloco": None, "motivo": None}
        try:
            issue = github_client.ler_issue(numero)
        except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
            relatorio.append({**linha, "situacao": FALHOU, "motivo": f"GitHub: {exc}"})
            continue
        corpo = str(issue.get("body") or "")
        if issue.get("state") != "open" or github_client.e_pull_request(issue) or tem_bloco_do_desenvolvedor(corpo):
            continue
        if bloco_para_o_diretor(corpo) is None:
            relatorio.append({**linha, "situacao": FALHOU, "motivo": MOTIVO_SEM_BLOCO_DO_DIRETOR})
            continue

        bloco = _bloco_do_modelo(supabase, demanda, corpo, kit)
        if bloco is None:
            relatorio.append({**linha, "situacao": FALHOU, "motivo": MOTIVO_MODELO})
            continue
        if not aplicar:
            relatorio.append({**linha, "situacao": PREVIA, "bloco": bloco})
            continue
        try:
            github_client.regravar_corpo(numero, corpo=inserir_bloco_do_desenvolvedor(corpo, bloco))
        except (github_client.GithubIndisponivelError, github_client.IssueNaoEncontradaError) as exc:
            relatorio.append({**linha, "situacao": FALHOU, "bloco": bloco, "motivo": f"GitHub: {exc}"})
            continue
        relatorio.append({**linha, "situacao": GRAVADO, "bloco": bloco})
    return relatorio


def texto_do_relatorio(relatorio: list[dict], *, aplicar: bool) -> str:
    """O que o comando imprime: cada issue com a situação e o bloco ou o motivo."""
    linhas: list[str] = []
    for item in relatorio:
        linhas.append(f"=== Issue {item['numero']} (Demanda {item['demanda_id']}): {item['situacao']} ===")
        if item.get("motivo"):
            linhas.append(f"Motivo: {item['motivo']}")
        if item.get("bloco"):
            linhas += ["", item["bloco"]]
        linhas.append("")
    contagem = {s: sum(1 for i in relatorio if i["situacao"] == s) for s in (PREVIA, GRAVADO, FALHOU)}
    if not relatorio:
        linhas.append("Nenhuma Demanda aberta do diretor está sem o bloco. Nada a fazer.")
    elif aplicar:
        linhas.append(f"Gravadas: {contagem[GRAVADO]}. Falharam: {contagem[FALHOU]}.")
    else:
        linhas.append(f"Mudariam: {contagem[PREVIA]}. Falharam: {contagem[FALHOU]}.")
        linhas.append("Nada foi gravado no GitHub. Rode de novo com --aplicar para valer.")
    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description='Põe o bloco "Para o desenvolvedor" nas Demandas abertas')
    parser.add_argument("--aplicar", action="store_true", help="grava no GitHub (sem isto, só mostra a prévia)")
    args = parser.parse_args()

    if not github_client.integracao_configurada():
        print("GITHUB_INTEGRACAO_TOKEN e GITHUB_INTEGRACAO_REPO precisam estar configurados. Nada foi feito.")
        return 1
    if ai_processor._llm_provider() == "mock":
        print("A IA está em modo mock (sem chave). Nada foi feito.")
        return 1

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    relatorio = passada(supabase, aplicar=args.aplicar, kit=carregar_kit())
    print(texto_do_relatorio(relatorio, aplicar=args.aplicar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
