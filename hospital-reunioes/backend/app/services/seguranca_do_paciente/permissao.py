"""A permissão efetiva do módulo Segurança do Paciente (ADR 0095, decisões 3 e 4).

Uma função pura decide o que a pessoa alcança no módulo: entram o perfil do
módulo (Acesso pleno ao NSP), o papel da Participação vigente no Núcleo, o
estado do Termo de Adesão, o cargo de Diretoria e a flag de super admin; sai o
conjunto de recursos. Toda rota do módulo passa por ela (o gate
`require_recurso_nsp` em `app.dependencies`).

O que muda em relação aos outros módulos: o super admin NÃO passa por cima.
Ele só alcança a configuração técnica (decisão 4). Quem lê tudo é o Acesso
pleno, nominal, do Diretor Executivo.

A leitura do banco (a Participação vigente) fica em `situacao_da_pessoa`, ao
lado, para a função de regra continuar sem banco nos testes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from postgrest.exceptions import APIError

from app.services import colegiados
from app.services.colegiados import Colegiado

logger = logging.getLogger(__name__)

# O slug do Núcleo na tabela `colegiados` (a migration 146 o cria).
SLUG_DO_NUCLEO = "nsp"

PERFIL_ACESSO_PLENO = "acesso_pleno"

PAPEIS_DO_NUCLEO = ("presidencia", "suplente", "membro")

# O Núcleo para o serviço compartilhado de membros e de Termo (issue #1819).
NUCLEO = Colegiado(
    slug=SLUG_DO_NUCLEO,
    nome="Núcleo",
    sigla="NSP",
    papeis=PAPEIS_DO_NUCLEO,
    termos_envios="nsp_termos_envios",
    documentos="nsp_documentos",
    documentos_envios="nsp_documentos_envios",
    bucket_dos_documentos="supabase_storage_bucket_nsp_documentos",
    modelo_do_termo="nsp_termo_adesao.html",
)

# O cargo de Diretoria no cadastro (o `role` da pessoa).
ROLES_DA_DIRETORIA = ("diretor", "presidente")

RECURSOS_NSP = (
    # O item do menu e a página inicial do módulo.
    "ver_modulo",
    "painel",
    "calendario",
    # A agenda regulatória.
    "agenda",
    "membros",
    "documentos",
    "capacitacoes",
    # Reuniões e atas do Núcleo.
    "reunioes",
    # Notificações de incidente e investigações (a partir da Fase 2).
    "casos",
    # Quem notificou: só a Presidência e o Acesso pleno (seção 3).
    "identidade_notificante",
    # Confirmar ou ajustar a triagem: só a Presidência e o Acesso pleno (issue #1992).
    "triagem",
    # Cadastrar membro, publicar documento, validar ata.
    "gerir_nucleo",
    # A configuração técnica do módulo, a única coisa que o super admin alcança.
    "configuracao",
)

# Membro sem Termo válido vê painel, calendário e agenda (glossário, "Membro do
# Núcleo"), e nada sobre casos, investigações ou atas.
_SEM_TERMO = frozenset({"ver_modulo", "painel", "calendario", "agenda"})
_MEMBRO = _SEM_TERMO | {"membros", "documentos", "capacitacoes", "reunioes", "casos"}
_DIRETORIA = _SEM_TERMO | {"membros"}
_TUDO = frozenset(RECURSOS_NSP)


@dataclass(frozen=True)
class SituacaoNsp:
    acesso_pleno: bool
    papel_vigente: str | None
    termo_valido: bool
    diretoria: bool
    super_admin: bool


def recursos_nsp(situacao: SituacaoNsp) -> frozenset[str]:
    """O que a pessoa alcança no módulo. A união do que cada fonte dá."""
    if situacao.acesso_pleno:
        return _TUDO
    recursos: set[str] = set()
    if situacao.papel_vigente in PAPEIS_DO_NUCLEO:
        if not situacao.termo_valido:
            recursos |= _SEM_TERMO
        elif situacao.papel_vigente == "presidencia":
            recursos |= _TUDO
        else:
            recursos |= _MEMBRO
    if situacao.diretoria:
        recursos |= _DIRETORIA
    if situacao.super_admin:
        recursos.add("configuracao")
    return frozenset(recursos)


def hoje_em_sao_paulo() -> date:
    return datetime.now(tz=ZoneInfo("America/Sao_Paulo")).date()


def id_do_nucleo(supabase) -> str | None:
    """O id do Núcleo em `colegiados`, ou None quando a migration não rodou."""
    return colegiados.id_do_colegiado(supabase, NUCLEO)


# As Participações vigentes de um Colegiado, sem executar (o serviço compartilhado).
participacoes_vigentes = colegiados.participacoes_vigentes


def situacao_da_pessoa(
    supabase, participante: dict[str, Any], *, super_admin: bool, hoje: date | None = None
) -> SituacaoNsp:
    """Monta a entrada da função de regra a partir do cadastro e do banco.

    Falha ao ler a Participação (tabela que ainda não existe entre o deploy e a
    migration, ou o PostgREST fora do ar) vale como "sem Participação": o
    módulo fica fechado e o resto do app segue de pé.
    """
    hoje = hoje or hoje_em_sao_paulo()
    try:
        papel, termo = colegiados.vinculo_vigente(supabase, NUCLEO, participante["id"], hoje)
    except (APIError, httpx.HTTPError) as erro:
        logger.warning("Participação no Núcleo ilegível; o módulo fica fechado para a pessoa: %s", erro)
        papel, termo = None, False
    return SituacaoNsp(
        acesso_pleno=participante.get("perfil_nsp") == PERFIL_ACESSO_PLENO,
        papel_vigente=papel,
        termo_valido=termo,
        diretoria=participante.get("role") in ROLES_DA_DIRETORIA,
        super_admin=super_admin,
    )
