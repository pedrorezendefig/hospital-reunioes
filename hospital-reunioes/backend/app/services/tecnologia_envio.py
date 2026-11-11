"""O envio do card ao GitHub, a porta unica (issue #1535, PRD #1529, ADR 0083, decisao 7).

"Criar o card" e "Reenviar" passam por aqui, e so por aqui. A porta toma a vez
de criar (a trava do duplo clique), pede a issue ao GitHub e grava o resultado
na Demanda: criada e vinculada, ou "Envio falhou" com o motivo. Quem decide o
corpo, as labels e o assignee e quem chama; quem traduz o resultado em HTTP
tambem.

O estado mora em tres colunas da Demanda (migration 128): `envio_estado`,
`envio_motivo` e `envio_em`. Elas substituem o `github_sincronizado_em`, que
fazia de trava antes e e da sincronizacao com o GitHub.

O cron de reconciliacao nao passa por aqui: ele so rele Demandas JA vinculadas.
Reenviar sozinho criaria a issue duplicada quando a primeira tentativa passou e
so a resposta se perdeu (ADR 0083, decisao 7).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services import github_client
from app.services.tecnologia import TABELA_DEMANDAS, instante_do_banco
from app.services.tecnologia_sincronizacao import mudanca_da_foto
from app.services.tecnologia_vinculo import titulo_da_issue

logger = logging.getLogger(__name__)

ESTADO_ENVIANDO = "enviando"
ESTADO_FALHOU = "falhou"
ESTADO_DESIGNACAO_FALHOU = "designacao_falhou"

# Por quanto tempo a vez de criar segura a porta.
#
# Maior que o timeout do cliente do GitHub (10 s) com folga para a escrita que
# vem depois, e curto o bastante para um processo morto no meio da criacao nao
# trancar a Demanda para sempre. O caminho normal nem chega perto disso: a
# falha grava "Envio falhou" na hora, e este teto e so a rede de baixo.
JANELA_DA_CRIACAO = timedelta(seconds=60)


class EnvioEmAndamentoError(RuntimeError):
    """Outro pedido esta criando a issue desta Demanda agora."""


class DemandaSumiuError(LookupError):
    """A Demanda saiu do banco entre a leitura e a escrita do Vinculo."""


@dataclass(frozen=True)
class Envio:
    """O resultado da porta: a Demanda vinculada, ou o motivo da falha.

    `integracao_desligada` separa a falta de configuracao (nao ha o que tentar
    sem mexer no ambiente) da indisponibilidade do GitHub. `designacao_falhou`
    e a Demanda vinculada a uma issue que nasceu sem o Responsavel (issue #1536).
    """

    demanda: dict[str, Any] | None = None
    motivo: str | None = None
    integracao_desligada: bool = False
    designacao_falhou: bool = False

    @property
    def criado(self) -> bool:
        return self.demanda is not None


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def envio_falhou(demanda: dict[str, Any]) -> bool:
    """Se a Demanda esta em "Envio falhou": a falha gravada e nenhuma issue.

    A Demanda que ganhou issue depois (pelo Reenviar de outra pessoa) nao fica
    com o selo, mesmo que a coluna ainda diga falhou.
    """
    return demanda.get("envio_estado") == ESTADO_FALHOU and not demanda.get("github_issue_numero")


def designacao_falhou(demanda: dict[str, Any]) -> bool:
    """Se a issue da Demanda nasceu e a designacao ao Responsavel nao (issue #1536)."""
    return demanda.get("envio_estado") == ESTADO_DESIGNACAO_FALHOU and bool(demanda.get("github_issue_numero"))


def motivo_da_designacao(numero: int, logins: list[str]) -> str:
    """O motivo tecnico da designacao falhada, que so o Desenvolvedor le."""
    return f"A issue #{numero} nasceu sem o Responsável ({', '.join(logins)})"


def _em_andamento(demanda: dict[str, Any]) -> bool:
    if demanda.get("envio_estado") != ESTADO_ENVIANDO:
        return False
    carimbo = instante_do_banco(demanda.get("envio_em"))
    if carimbo is None:
        return False
    return datetime.now(UTC) - carimbo < JANELA_DA_CRIACAO


def _tomar_a_vez(supabase, *, demanda_id: str, carimbo_lido: str | None, responsavel_id: str | None) -> bool:
    """Marca a Demanda como "enviando", ou devolve False.

    E o que fecha a janela do duplo clique DO LADO DO SERVIDOR: o
    `github_issue_numero` so existe DEPOIS de a issue nascer, entao dois
    pedidos concorrentes leem os dois "sem Vinculo" e criariam duas issues
    publicas.

    O UPDATE e condicionado ao `envio_em` que ESTE pedido leu (compare-and-swap):
    o Postgres serializa os dois, o segundo reavalia a condicao com a linha ja
    escrita e volta sem nenhuma. O Responsavel escolhido fica guardado aqui,
    para o "Reenviar" usar o mesmo.
    """
    consulta = (
        supabase.table(TABELA_DEMANDAS)
        .update(
            {
                "envio_estado": ESTADO_ENVIANDO,
                "envio_motivo": None,
                "envio_em": _agora(),
                "responsavel_id": responsavel_id,
            }
        )
        .eq("id", demanda_id)
    )
    # Coluna nulavel: `.eq(coluna, None)` nao casa NULL no PostgREST, `.is_` casa.
    consulta = consulta.eq("envio_em", carimbo_lido) if carimbo_lido else consulta.is_("envio_em", "null")
    return bool(consulta.execute().data)


def _gravar_a_falha(supabase, *, demanda_id: str, motivo: str) -> None:
    supabase.table(TABELA_DEMANDAS).update(
        {"envio_estado": ESTADO_FALHOU, "envio_motivo": motivo, "envio_em": _agora()}
    ).eq("id", demanda_id).execute()


def enviar(
    supabase,
    *,
    demanda: dict[str, Any],
    ator: dict[str, Any],
    corpo: Callable[[str], str],
    assignees: list[str],
    labels: list[str],
    responsavel_id: str | None,
) -> Envio:
    """Cria a issue da Demanda e vincula, ou grava "Envio falhou".

    Recebe a Demanda ja lida e as guardas da porta ja passadas. O titulo passa
    pela peneira (o repositorio e publico), e o `corpo(titulo)` vem de quem
    chama. Levanta `EnvioEmAndamentoError` no duplo clique.
    """
    demanda_id = str(demanda["id"])
    if _em_andamento(demanda):
        raise EnvioEmAndamentoError(demanda_id)
    if not _tomar_a_vez(
        supabase, demanda_id=demanda_id, carimbo_lido=demanda.get("envio_em"), responsavel_id=responsavel_id
    ):
        # Outro pedido tomou a vez entre a leitura e agora: ele esta criando a
        # issue, e este para aqui em vez de criar a segunda.
        raise EnvioEmAndamentoError(demanda_id)

    titulo = titulo_da_issue(demanda.get("titulo"))
    try:
        dados = github_client.criar_issue(titulo=titulo, corpo=corpo(titulo), labels=labels, assignees=assignees)
        numero = dados.get("number")
        if not isinstance(numero, int):
            # A issue pode ter nascido; o Vinculo, nao. Sem o numero nao ha par,
            # e gravar `None` no lugar dele e o meio Vinculo proibido.
            logger.error("[tecnologia] a criacao da issue da Demanda %s voltou sem numero", demanda_id)
            raise github_client.GithubIndisponivelError("A criacao da issue voltou sem numero")
    except github_client.GithubNaoConfiguradoError as exc:
        # A configuracao pode ter sumido entre a guarda de quem chama e a chamada.
        _gravar_a_falha(supabase, demanda_id=demanda_id, motivo=str(exc))
        return Envio(motivo=str(exc), integracao_desligada=True)
    except github_client.GithubIndisponivelError as exc:
        logger.warning("[tecnologia] GitHub indisponivel ao criar o card da Demanda %s: %s", demanda_id, exc)
        _gravar_a_falha(supabase, demanda_id=demanda_id, motivo=str(exc))
        return Envio(motivo=str(exc))

    # A issue acabou de nascer: ela nao tem sub-issue nenhuma, e a foto sai do
    # proprio JSON da criacao, sem uma segunda leitura. O SHAPE do cache vem de
    # `mudanca_da_foto`, o mesmo do webhook e da reconciliacao (issue #678); a
    # Etapa sai derivada dali, da label da triagem da issue nova.
    #
    # A issue nascida sem o Responsavel e o terceiro resultado (issue #1536): a
    # Demanda fica vinculada E guarda a designacao falhada, que o "Designar de
    # novo" resolve sem criar outra issue.
    designada = not assignees or github_client.designado(dados, assignees)
    if not designada:
        logger.warning("[tecnologia] a issue #%s da Demanda %s nasceu sem o Responsavel", numero, demanda_id)
    mudanca = {
        **mudanca_da_foto(github_client.montar_foto(dados, [])),
        "github_issue_numero": numero,
        "vinculado_por": ator["id"],
        "responsavel_id": responsavel_id,
        "envio_estado": None if designada else ESTADO_DESIGNACAO_FALHOU,
        "envio_motivo": None if designada else motivo_da_designacao(numero, assignees),
        "envio_em": _agora(),
    }
    result = supabase.table(TABELA_DEMANDAS).update(mudanca).eq("id", demanda_id).execute()
    if not result.data:
        raise DemandaSumiuError(demanda_id)
    return Envio(demanda=result.data[0], designacao_falhou=not designada)
