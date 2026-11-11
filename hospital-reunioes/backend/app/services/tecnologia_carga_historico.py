"""A carga do historico de entregas desde o primeiro deploy (issue #1555, PRD
#1548, ADR 0084, decisao 8).

Script de uma vez, para a aba Entregas nao nascer vazia. Le as issues fechadas
do repositorio e o `history.json` da `main`, e:

- cria a Demanda Vitta de cada issue-raiz do app entregue que ainda nao tem
  Demanda, pelas regras do espelho (`tecnologia_espelho.decidir`): ferramenta e
  parte ficam de fora. A sincronizacao da a Etapa, as partes e o Responsavel;
- em toda Demanda entregue, preenche o que falta das datas: `entregue_em` (o
  fechamento da issue), `em_producao_em` e `versao_em_producao` (a PRIMEIRA
  subida do `history.json` que fecha a issue por PR ou a cita em `prds`).

Idempotente: so preenche coluna vazia, e a issue que ja tem Demanda nao cria
outra. Nao gera notificacao nem e-mail: escreve as datas direto, sem passar
pelos caminhos que avisam.

Rodar (no container do backend, ou local com o `.env` apontando o banco):

    python -m app.services.tecnologia_carga_historico --dry-run
    python -m app.services.tecnologia_carga_historico

O `--dry-run` le tudo e lista o que faria, sem gravar nada.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services import github_client
from app.services.registro_do_deploy import primeira_subida_de_cada_issue, versao_rotulada
from app.services.tecnologia import TABELA_DEMANDAS
from app.services.tecnologia_espelho import CRIA, criar, decidir
from app.services.tecnologia_sincronizacao import demanda_vinculada, sincronizar_demanda
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO, ETAPA_ENTREGUE, etapa_da_foto

logger = logging.getLogger(__name__)


@dataclass
class Relatorio:
    """O que a carga fez (ou faria, no `--dry-run`), por numero de issue."""

    criadas: list[int] = field(default_factory=list)
    datas: dict[int, dict[str, str]] = field(default_factory=dict)
    falhas: list[int] = field(default_factory=list)


def _entregue(issue: dict[str, Any]) -> bool:
    """A issue fechada como entrega, pela mesma regra da Etapa: a recusa
    (`not_planned`, `wontfix`) nao e entrega."""
    return etapa_da_foto(github_client.montar_foto(issue, [])) == ETAPA_ENTREGUE


def _datas_que_faltam(
    demanda: dict[str, Any],
    issue: dict[str, Any],
    subida: tuple[str, str] | None,
    data_da_versao: dict[str, str],
) -> dict[str, str]:
    """As colunas vazias que a carga preenche. Coluna ja gravada nao muda.

    A Demanda que ja tem versao (o webhook de deploy a gravou) e ainda nao tem
    `em_producao_em` recebe a data da subida DAQUELA versao, e nao a da
    primeira: a data e a versao contam a mesma subida.
    """
    mudanca: dict[str, str] = {}
    if not demanda.get("entregue_em") and issue.get("closed_at"):
        mudanca["entregue_em"] = issue["closed_at"]
    versao = demanda.get("versao_em_producao")
    if not versao and subida is not None:
        versao = mudanca["versao_em_producao"] = subida[0]
    if versao and not demanda.get("em_producao_em"):
        data = subida[1] if "versao_em_producao" in mudanca else data_da_versao.get(versao)
        if data:
            mudanca["em_producao_em"] = data
    # Entregue com a versao gravada e Em producao (`etapa_da_foto`, regra 0).
    if versao and demanda.get("etapa") == ETAPA_ENTREGUE:
        mudanca["etapa"] = ETAPA_EM_PRODUCAO
    return mudanca


def carregar(supabase, *, dry_run: bool) -> Relatorio:
    """A carga inteira. Falha e de UMA issue: a seguinte segue, e o relatorio
    diz quais ficaram para tras."""
    deploys = github_client.ler_historico_de_deploys()
    subidas = primeira_subida_de_cada_issue(deploys)
    data_da_versao = {
        versao_rotulada(e.get("app_version")): e.get("at") for e in deploys if isinstance(e, dict) and e.get("at")
    }
    linhas = supabase.table(TABELA_DEMANDAS).select("*").not_.is_("github_issue_numero", "null").execute().data
    demandas = {int(d["github_issue_numero"]): d for d in linhas or []}

    relatorio = Relatorio()
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
            if demanda.get("apagada_em"):
                continue
            mudanca = _datas_que_faltam(demanda, issue, subidas.get(numero), data_da_versao)
            if not mudanca:
                continue
            if not dry_run:
                supabase.table(TABELA_DEMANDAS).update(mudanca).eq("id", str(demanda["id"])).execute()
            relatorio.datas[numero] = mudanca
        except Exception:
            relatorio.falhas.append(numero)
            logger.warning("[tecnologia] A carga do histórico falhou na issue #%s.", numero, exc_info=True)
    return relatorio


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
    sincronizar_demanda(supabase, criada)
    return demanda_vinculada(supabase, numero)


def _imprimir(relatorio: Relatorio, *, dry_run: bool) -> None:
    verbo = "criaria" if dry_run else "criou"
    for numero in relatorio.criadas:
        print(f"{verbo} a Demanda da issue #{numero}")
    verbo = "preencheria" if dry_run else "preencheu"
    for numero, mudanca in sorted(relatorio.datas.items()):
        campos = ", ".join(f"{coluna}={valor}" for coluna, valor in mudanca.items())
        print(f"{verbo} na issue #{numero}: {campos}")
    for numero in relatorio.falhas:
        print(f"falhou na issue #{numero} (ver o log)")
    print(
        f"{len(relatorio.criadas)} Demanda(s), {len(relatorio.datas)} com datas, {len(relatorio.falhas)} falha(s)"
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
