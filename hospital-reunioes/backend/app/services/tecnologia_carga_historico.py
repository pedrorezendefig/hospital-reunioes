"""A carga do historico de entregas desde o primeiro deploy (issue #1555, PRD
#1548, ADR 0084, decisao 8).

Script de uma vez, para a aba Entregas nao nascer vazia. Le as issues fechadas
do repositorio e o `history.json` da `main`, e:

- cria a Demanda Vitta de cada issue-raiz do app entregue que ainda nao tem
  Demanda, pelas regras do espelho (`tecnologia_espelho.decidir`): ferramenta e
  parte ficam de fora. A sincronizacao da a Etapa, as partes e o Responsavel;
- em toda Demanda entregue e aberta, preenche o que falta das datas:
  `entregue_em` (o fechamento da issue), `em_producao_em` e
  `versao_em_producao` (a PRIMEIRA subida do `history.json` de depois do
  fechamento atual que fecha a issue por PR ou a cita em `prds`). Com a versao
  gravada, a Etapa Entregue vira Em producao, como no carimbo da subida;
- em toda Demanda com Vinculo, aberta ou fechada no GitHub, preenche o
  `criada_em` da foto (a data de criacao da issue-raiz, issue #1702) quando ele
  falta. A issue e lida pelo numero guardado na Demanda, e nunca pelo marcador:
  a Demanda da Origem Vitta nao tem marcador.

Idempotente: so preenche coluna vazia, e a issue que ja tem Demanda nao cria
outra. Nao gera notificacao nem e-mail: escreve as datas direto, sem passar
pelos caminhos que avisam.

Promovida a Em producao com a entrega de mais de 30 dias, a Demanda tem os
prints vencidos, e a passada seguinte do cron apaga os binarios do bucket de
vez. O relatorio (e o `--dry-run`, antes) lista quais Demandas com anexo
guardado entram nessa conta.

Rodar (no container do backend, ou local com o `.env` apontando o banco):

    python -m app.services.tecnologia_carga_historico --dry-run
    python -m app.services.tecnologia_carga_historico

O `--dry-run` le tudo e lista o que faria, sem gravar nada.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services import github_client
from app.services.registro_do_deploy import subidas_de_cada_issue, versao_rotulada
from app.services.tecnologia import ESTADOS_ABERTOS, ESTADOS_FECHADOS, TABELA_DEMANDAS
from app.services.tecnologia_anexos import TABELA_ANEXOS, _print_venceu
from app.services.tecnologia_espelho import CRIA, criar, decidir
from app.services.tecnologia_sincronizacao import (
    _subiu_depois_do_fechamento,
    _versao_que_segura,
    demanda_vinculada,
    sincronizar_demanda,
)
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO, ETAPA_ENTREGUE, etapa_da_foto

logger = logging.getLogger(__name__)


@dataclass
class Relatorio:
    """O que a carga fez (ou faria, no `--dry-run`), por numero de issue."""

    criadas: list[int] = field(default_factory=list)
    datas: dict[int, dict[str, str]] = field(default_factory=dict)
    falhas: list[int] = field(default_factory=list)
    # As Demandas com anexo guardado cujo print a mudanca faz vencer: a
    # passada seguinte do cron (`apagar_vencidos`) apaga os binarios de vez.
    anexos_vencem: list[int] = field(default_factory=list)
    # A data de criacao da issue-raiz que a carga pos na foto (issue #1702).
    criada_em: dict[int, str] = field(default_factory=dict)


def _entregue(issue: dict[str, Any]) -> bool:
    """A issue fechada como entrega, pela mesma regra da Etapa: a recusa
    (`not_planned`, `wontfix`) nao e entrega."""
    return etapa_da_foto(github_client.montar_foto(issue, [])) == ETAPA_ENTREGUE


def _datas_que_faltam(
    demanda: dict[str, Any],
    issue: dict[str, Any],
    subidas: list[tuple[str, str]],
    data_da_versao: dict[str, str],
) -> dict[str, str]:
    """As colunas vazias que a carga preenche. Coluna ja gravada nao muda.

    A versao que a carga grava e a da primeira subida de DEPOIS do fechamento
    atual da issue (`_subiu_depois_do_fechamento`, a mesma regra da
    reconciliacao): a subida de antes levou um fechamento anterior (a issue
    reaberta para um ajuste) ou uma fatia do PRD que ainda nao fechava a
    entrega. Sem subida assim, a Demanda fica Entregue e espera o webhook.

    A versao ja gravada so vale com a Etapa Em producao (`_versao_que_segura`):
    com a Etapa Entregue ela sobrou de uma subida anterior e nao leva a Em
    producao. A Demanda Em producao que ainda nao tem `em_producao_em` recebe
    a data da subida DAQUELA versao: a data e a versao contam a mesma subida.
    """
    mudanca: dict[str, str] = {}
    if not demanda.get("entregue_em") and issue.get("closed_at"):
        mudanca["entregue_em"] = issue["closed_at"]
    if demanda.get("etapa") == ETAPA_EM_PRODUCAO:
        versao = _versao_que_segura(demanda)
        if versao and not demanda.get("em_producao_em") and data_da_versao.get(versao):
            mudanca["em_producao_em"] = data_da_versao[versao]
        return mudanca
    if demanda.get("etapa") != ETAPA_ENTREGUE:
        return mudanca
    depois = [s for s in subidas if _subiu_depois_do_fechamento(s[1], issue.get("closed_at"))]
    if depois:
        versao, data = depois[0]
        # Entregue com a versao gravada e Em producao (`etapa_da_foto`, regra 0),
        # o mesmo carimbo de `_carimbar_em_producao`.
        mudanca.update({"versao_em_producao": versao, "em_producao_em": data, "etapa": ETAPA_EM_PRODUCAO})
    return mudanca


def carregar(supabase, *, dry_run: bool) -> Relatorio:
    """A carga inteira. Falha e de UMA issue: a seguinte segue, e o relatorio
    diz quais ficaram para tras."""
    deploys = github_client.ler_historico_de_deploys()
    subidas = subidas_de_cada_issue(deploys)
    data_da_versao = {
        versao_rotulada(e.get("app_version")): e.get("at") for e in deploys if isinstance(e, dict) and e.get("at")
    }
    linhas = supabase.table(TABELA_DEMANDAS).select("*").not_.is_("github_issue_numero", "null").execute().data
    demandas = {int(d["github_issue_numero"]): d for d in linhas or []}

    guardados = supabase.table(TABELA_ANEXOS).select("demanda_id, apagado_em").execute().data or []
    com_anexo = {str(a["demanda_id"]) for a in guardados if not a.get("apagado_em")}
    agora = datetime.now(UTC)

    relatorio = Relatorio()
    # Antes das datas: a linha regravada aqui (com o `atualizado_em` novo) e a
    # que a passada das datas trava no UPDATE dela.
    _preencher_criada_em(supabase, demandas, relatorio, dry_run=dry_run)
    for issue in sorted(github_client.listar_issues_fechadas(), key=lambda i: i["number"]):
        numero = int(issue["number"])
        if not _entregue(issue):
            continue
        try:
            demanda = demandas.get(numero)
            if demanda is None:
                demanda = _nova_demanda(supabase, issue, dry_run=dry_run)
                if demanda is None:
                    continue
                relatorio.criadas.append(numero)
            # A lapide do Apagar e o estado congelado de antes da ADR 0077 nao
            # sao tocados, como na sincronizacao e no carimbo da subida.
            if demanda.get("apagada_em") or str(demanda.get("estado") or "") in ESTADOS_FECHADOS:
                continue
            mudanca = _datas_que_faltam(demanda, issue, subidas.get(numero, []), data_da_versao)
            if not mudanca:
                continue
            if not dry_run and not _gravar(supabase, demanda, mudanca):
                relatorio.falhas.append(numero)
                logger.warning(
                    "[tecnologia] A Demanda da issue #%s mudou durante a carga; rode de novo para completar.", numero
                )
                continue
            relatorio.datas[numero] = mudanca
            if (
                str(demanda.get("id")) in com_anexo
                and _print_venceu({**demanda, **mudanca}, agora)
                and not _print_venceu(demanda, agora)
            ):
                relatorio.anexos_vencem.append(numero)
        except Exception:
            relatorio.falhas.append(numero)
            logger.warning("[tecnologia] A carga do histórico falhou na issue #%s.", numero, exc_info=True)
    return relatorio


def _preencher_criada_em(supabase, demandas: dict[int, dict[str, Any]], relatorio: Relatorio, *, dry_run: bool) -> None:
    """O `criada_em` da foto nas Demandas com Vinculo que ainda nao o tem
    (issue #1702). A foto ja com a data nao e relida nem regravada: rodar de
    novo nao grava nada. A lapide e o estado congelado nao sao tocados, como no
    resto da carga. A Demanda sem foto fica para a sincronizacao, que a grava
    inteira, ja com a data.
    """
    for numero, demanda in sorted(demandas.items()):
        foto = demanda.get("github_foto")
        if not isinstance(foto, dict) or foto.get(github_client.FATO_CRIADA_EM):
            continue
        if demanda.get("apagada_em") or str(demanda.get("estado") or "") in ESTADOS_FECHADOS:
            continue
        try:
            criada_em = github_client.ler_issue(numero).get("created_at")
            if not criada_em:
                continue
            if not dry_run:
                linha = _gravar_foto(supabase, demanda, {**foto, github_client.FATO_CRIADA_EM: criada_em})
                if linha is None:
                    relatorio.falhas.append(numero)
                    logger.warning(
                        "[tecnologia] A Demanda da issue #%s mudou durante a carga; rode de novo para completar.",
                        numero,
                    )
                    continue
                demandas[numero] = linha
            relatorio.criada_em[numero] = criada_em
        except Exception:
            relatorio.falhas.append(numero)
            logger.warning("[tecnologia] A data do pedido falhou na issue #%s.", numero, exc_info=True)


def _gravar_foto(supabase, demanda: dict[str, Any], foto: dict[str, Any]) -> dict[str, Any] | None:
    """O UPDATE da foto, so se a Demanda segue como foi lida (a trava do
    `atualizado_em`, como em `_gravar`). Devolve a linha gravada, ou `None`
    quando ela nao casou."""
    casou = (
        supabase.table(TABELA_DEMANDAS)
        .update({"github_foto": foto})
        .eq("id", str(demanda["id"]))
        .eq("atualizado_em", demanda.get("atualizado_em"))
        .execute()
    )
    return casou.data[0] if casou.data else None


def _gravar(supabase, demanda: dict[str, Any], mudanca: dict[str, str]) -> bool:
    """O UPDATE da carga, so se a Demanda segue como foi lida. `False` quando
    a linha nao casou.

    O retrato vem do comeco da carga, que leva minutos de chamadas ao GitHub:
    o webhook de deploy, a sincronizacao ou o Encerrar podem ter mexido na
    Demanda nesse meio tempo. As travas moram no proprio UPDATE, como em
    `_carimbar_em_producao` e `_escrever`: estado aberto, a Etapa lida
    (compare-and-swap) e o `atualizado_em` lido, que o gatilho da migration
    102 troca a cada escrita.
    """
    casou = (
        supabase.table(TABELA_DEMANDAS)
        .update(mudanca)
        .eq("id", str(demanda["id"]))
        .in_("estado", list(ESTADOS_ABERTOS))
        .eq("etapa", demanda.get("etapa"))
        .eq("atualizado_em", demanda.get("atualizado_em"))
        .execute()
    )
    return bool(casou.data)


def _nova_demanda(supabase, issue: dict[str, Any], *, dry_run: bool) -> dict[str, Any] | None:
    """A Demanda Vitta que o espelho cria para esta issue, ja sincronizada, ou
    `None` quando ele nao cria.

    O filtro pela lista e barato e corta quase tudo; a decisao final e pela
    issue relida, como no webhook, porque so a leitura da issue traz o pai
    nativo da parte. No `--dry-run` a Demanda e so o que a carga precisa saber
    dela: entregue e sem data nenhuma.
    """
    if decidir(issue, None) != CRIA:
        return None
    numero = int(issue["number"])
    relida = github_client.ler_issue(numero)
    if decidir(relida, None) != CRIA:
        return None
    if dry_run:
        return {"etapa": ETAPA_ENTREGUE}
    criada = criar(supabase, relida)
    if criada is None:
        return None
    # Sem aviso (issue #1560): o link de Demonstracao da entrega antiga nao e novidade.
    sincronizar_demanda(supabase, criada, avisar=False)
    return demanda_vinculada(supabase, numero)


def _imprimir(relatorio: Relatorio, *, dry_run: bool) -> None:
    verbo = "criaria" if dry_run else "criou"
    for numero in relatorio.criadas:
        print(f"{verbo} a Demanda da issue #{numero}")
    verbo = "preencheria" if dry_run else "preencheu"
    for numero, mudanca in sorted(relatorio.datas.items()):
        campos = ", ".join(f"{coluna}={valor}" for coluna, valor in mudanca.items())
        print(f"{verbo} na issue #{numero}: {campos}")
    for numero, criada_em in sorted(relatorio.criada_em.items()):
        print(f"{verbo} a data do pedido na issue #{numero}: criada_em={criada_em}")
    verbo = "apagaria" if dry_run else "apaga"
    for numero in relatorio.anexos_vencem:
        print(f"atenção: a issue #{numero} tem anexo guardado: o cron {verbo} os prints na próxima passada")
    for numero in relatorio.falhas:
        print(f"falhou na issue #{numero} (ver o log)")
    print(
        f"{len(relatorio.criadas)} Demanda(s), {len(relatorio.datas)} com datas, "
        f"{len(relatorio.criada_em)} com a data do pedido, "
        f"{len(relatorio.anexos_vencem)} com anexo que o cron {verbo}, {len(relatorio.falhas)} falha(s)"
        + (" (dry-run: nada gravado)" if dry_run else "")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga do histórico de entregas da aba Tecnologia (issue #1555).")
    parser.add_argument("--dry-run", action="store_true", help="lista o que faria, sem gravar")
    args = parser.parse_args(argv)

    from app.dependencies import get_supabase_client

    relatorio = carregar(get_supabase_client(), dry_run=args.dry_run)
    _imprimir(relatorio, dry_run=args.dry_run)
    return 1 if relatorio.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
