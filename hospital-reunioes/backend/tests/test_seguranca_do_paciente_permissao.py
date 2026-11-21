"""A permissão efetiva do módulo Segurança do Paciente (issue #1765, ADR 0095).

Função pura: o perfil do módulo (Acesso pleno ao NSP), a Participação vigente
no Núcleo, o estado do Termo de Adesão, o cargo de Diretoria e a flag de super
admin entram; o conjunto de recursos que a pessoa alcança sai.

O esperado de cada perfil é escrito à mão a partir da seção 3 da
especificação da Diretoria (e do glossário, "Membro do Núcleo"), recurso a
recurso, para o teste poder discordar do código. Nada aqui é derivado da
própria função.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.seguranca_do_paciente.permissao import (  # noqa: E402
    RECURSOS_NSP,
    SituacaoNsp,
    recursos_nsp,
)

TODOS = {
    "ver_modulo",
    "painel",
    "calendario",
    "agenda",
    "membros",
    "documentos",
    "capacitacoes",
    "reunioes",
    "casos",
    "identidade_notificante",
    "triagem",
    "gerir_nucleo",
    "configuracao",
}

# Membro sem Termo válido: painel, calendário e agenda (seção 3 e glossário).
SEM_TERMO = {"ver_modulo", "painel", "calendario", "agenda"}

MEMBRO = SEM_TERMO | {"membros", "documentos", "capacitacoes", "reunioes", "casos"}

DIRETORIA = SEM_TERMO | {"membros"}


def _situacao(**campos) -> SituacaoNsp:
    base = {
        "acesso_pleno": False,
        "papel_vigente": None,
        "termo_valido": False,
        "diretoria": False,
        "super_admin": False,
    }
    return SituacaoNsp(**{**base, **campos})


def test_a_lista_de_recursos_e_a_da_especificacao():
    """Piso do próprio teste: se a função ganhar ou perder um recurso, a tabela
    abaixo para de cobrir tudo e o teste diz qual."""
    assert set(RECURSOS_NSP) == TODOS


CASOS = [
    ("acesso pleno", _situacao(acesso_pleno=True), TODOS),
    ("presidência com Termo", _situacao(papel_vigente="presidencia", termo_valido=True), TODOS),
    ("membro com Termo", _situacao(papel_vigente="membro", termo_valido=True), MEMBRO),
    ("suplente com Termo", _situacao(papel_vigente="suplente", termo_valido=True), MEMBRO),
    ("membro sem Termo", _situacao(papel_vigente="membro"), SEM_TERMO),
    ("presidência sem Termo", _situacao(papel_vigente="presidencia"), SEM_TERMO),
    ("diretoria", _situacao(diretoria=True), DIRETORIA),
    ("super admin sem Acesso pleno", _situacao(super_admin=True), {"configuracao"}),
    ("pessoa de fora", _situacao(), set()),
    (
        "super admin que é membro com Termo",
        _situacao(super_admin=True, papel_vigente="membro", termo_valido=True),
        MEMBRO | {"configuracao"},
    ),
    ("diretoria que é membro sem Termo", _situacao(diretoria=True, papel_vigente="membro"), DIRETORIA),
]


@pytest.mark.parametrize("perfil,situacao,esperado", CASOS, ids=[c[0] for c in CASOS])
@pytest.mark.parametrize("recurso", sorted(TODOS))
def test_cada_perfil_contra_cada_recurso(perfil, situacao, esperado, recurso):
    alcanca = recurso in recursos_nsp(situacao)

    assert alcanca == (recurso in esperado), f"{perfil} {'não ' if alcanca else ''}deveria alcançar {recurso}"


def test_super_admin_sem_acesso_pleno_nao_alcanca_conteudo():
    """ADR 0095, decisão 4: o super admin só chega à configuração técnica."""
    recursos = recursos_nsp(_situacao(super_admin=True))

    assert recursos == frozenset({"configuracao"})
    assert "ver_modulo" not in recursos


def test_papel_desconhecido_nao_abre_nada():
    """Um papel que a migration não conhece não vira membro por engano."""
    assert recursos_nsp(_situacao(papel_vigente="convidado", termo_valido=True)) == frozenset()
