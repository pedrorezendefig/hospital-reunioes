"""O espelho de issue: o card que a Vitta abre pelo terminal vira Demanda (issue
#1554, PRD #1548, ADR 0084, decisao 4).

Uma funcao so decide, `decidir`, e devolve "cria", "ignora" ou "ja existe".
Por dentro estao as regras da issue-raiz do app:

- **Raiz, e nao parte.** A parte do `/to-issues` nasce com a secao "Pai" no
  corpo e so depois vira sub-issue nativa; as duas marcas valem. Fatia avulsa
  diz "Pai: Nenhum" e conta como raiz.
- **Sem o marcador da Demanda.** O card que o diretor cria no chat leva o
  `<!-- demanda-vitta -->` e ja tem Demanda; o `opened` dele chega antes de o
  app gravar o numero, e sem esta regra ele nasceria duas vezes.
- **Entrega do app:** `type:feature`, `type:fix` ou `type:bug`, e alguma
  `area:` de app (backend, frontend ou supabase). Ferramenta (`area:skills`,
  `area:docs` ou `area:infra` sozinhas) fica de fora.
- **Uma Demanda por issue.** A issue que ja tem Demanda devolve "ja existe";
  a lapide do Apagar devolve "ignora", para a issue fechada nao voltar.

Quem chama e o webhook (`issues.opened` e `issues.edited`) e a carga do
historico. `espelhar` e a costura com o GitHub e o banco: rele a issue e so
cria pelo que releu, nunca pelo corpo do evento.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from postgrest.exceptions import APIError

from app.config import settings
from app.services import github_client
from app.services.tecnologia import ORIGEM_VITTA, TABELA_DEMANDAS, TABELA_PRODUTOS
from app.services.tecnologia_sincronizacao import demanda_vinculada
from app.services.tecnologia_vinculo import ETAPA_REGISTRADA, normalizar_github_login

logger = logging.getLogger(__name__)

CRIA = "cria"
IGNORA = "ignora"
JA_EXISTE = "ja_existe"

# As acoes do evento `issues` que passam pelo espelho.
ACOES_DO_ESPELHO = ("opened", "edited")

# O Tipo da Demanda pela label de natureza da issue (`docs/agents/triage-labels.md`).
TIPO_DA_LABEL: dict[str, str] = {"type:feature": "novo", "type:fix": "defeito", "type:bug": "defeito"}
AREAS_DO_APP = frozenset({"area:backend", "area:frontend", "area:supabase"})

_MARCADOR_DA_DEMANDA = re.compile(r"<!--\s*demanda-vitta\b", re.IGNORECASE)
# "## Pai\n\n#1548" do template do `/to-issues`, ou "Pai: #1548".
_SECAO_PAI = re.compile(r"^(?:#{1,6}[ \t]*)?\**Pai\**[ \t]*:?\**\s*#\d+", re.IGNORECASE | re.MULTILINE)


def _labels(issue: dict[str, Any]) -> set[str]:
    nomes = set()
    for label in issue.get("labels") or []:
        nome = label.get("name") if isinstance(label, dict) else label
        if isinstance(nome, str):
            nomes.add(nome.strip().lower())
    return nomes


def _e_parte(issue: dict[str, Any]) -> bool:
    return bool(issue.get("parent_issue_url")) or bool(_SECAO_PAI.search(str(issue.get("body") or "")))


def decidir(issue: dict[str, Any], demanda: dict[str, Any] | None) -> str:
    """Se esta issue vira Demanda de Origem Vitta: `CRIA`, `IGNORA` ou `JA_EXISTE`.

    `demanda` e a que ja carrega o numero da issue, lapide inclusive, ou `None`.
    """
    if demanda is not None:
        return IGNORA if demanda.get("apagada_em") else JA_EXISTE
    if github_client.e_pull_request(issue):
        return IGNORA
    if _MARCADOR_DA_DEMANDA.search(str(issue.get("body") or "")):
        return IGNORA
    if _e_parte(issue):
        return IGNORA
    labels = _labels(issue)
    if not labels & TIPO_DA_LABEL.keys() or not labels & AREAS_DO_APP:
        return IGNORA
    return CRIA


def _tipo(issue: dict[str, Any]) -> str:
    labels = _labels(issue)
    return "defeito" if labels & {"type:fix", "type:bug"} else "novo"


def _autor_id(supabase, issue: dict[str, Any]) -> str | None:
    """Quem tem no cadastro o login de quem abriu a issue; sem ele, o dono
    configurado (`GITHUB_LOGIN_DONO`); sem nenhum dos dois, ninguem."""
    for bruto in ((issue.get("user") or {}).get("login"), settings.github_login_dono):
        login = normalizar_github_login(bruto)
        if not login:
            continue
        linhas = supabase.table("participantes").select("id").eq("github_login", login).execute().data or []
        if linhas:
            return str(linhas[0]["id"])
    return None


def _produto_padrao(supabase) -> dict[str, Any] | None:
    """O primeiro Produto ativo da lista: a Demanda exige um, e o terminal nao
    escolhe."""
    produtos = [p for p in (supabase.table(TABELA_PRODUTOS).select("*").execute().data or []) if p.get("ativo")]
    return min(produtos, key=lambda p: p.get("ordem") or 0) if produtos else None


def espelhar(supabase, numero: int) -> dict[str, Any] | None:
    """Rele a issue e cria a Demanda Vitta se o espelho manda. Devolve a linha
    criada, ou `None` quando nao cria. Quem chama sincroniza em seguida, e e a
    sincronizacao que da a Etapa, as partes e o Responsavel.

    As falhas do GitHub sobem para quem chamou. A corrida de dois eventos da
    mesma issue para no indice unico do numero: quem perde ve "ja existe".
    """
    issue = github_client.ler_issue(numero)
    if decidir(issue, demanda_vinculada(supabase, numero)) != CRIA:
        return None
    produto = _produto_padrao(supabase)
    if produto is None:
        logger.warning("[tecnologia] Sem Produto ativo; a issue #%s não virou Demanda.", numero)
        return None
    linha = {
        "titulo": str(issue.get("title") or f"Issue #{numero}"),
        "descricao": None,
        "tipo": _tipo(issue),
        "produto_id": produto["id"],
        "estado": "nova",
        "responsavel_id": None,
        "autor_id": _autor_id(supabase, issue),
        "prioridade": "normal",
        "origem": ORIGEM_VITTA,
        "github_issue_numero": numero,
        "etapa": ETAPA_REGISTRADA,
    }
    try:
        criada = supabase.table(TABELA_DEMANDAS).insert(linha).execute().data
    except APIError:
        if demanda_vinculada(supabase, numero) is not None:
            return None
        raise
    return criada[0] if criada else None
