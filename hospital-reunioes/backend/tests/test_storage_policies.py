"""Leitura do Storage só pelos fluxos do backend (issue #1285, PRD #1282).

O backend lê e grava os buckets com a service_role e entrega arquivo ao
navegador por URL assinada, depois de conferir o acesso. Uma policy de
`storage.objects` que libere SELECT a qualquer `authenticated` abre um segundo
caminho, direto pela Storage API com a anon key do bundle, que pula essa
conferência. As 066, 115 e 116 já nasceram sem ela; a 006 e a 049 criaram duas,
que a 120 remove.

O teste reconstrói o estado final das policies de `storage.objects` aplicando
as migrations em ordem (CREATE soma, DROP tira) e falha se sobrar alguma que dê
leitura a `authenticated` sem filtro de dono (`auth.uid()` no USING).
"""

from __future__ import annotations

import os
import re

AQUI = os.path.dirname(__file__)
MIGRATIONS_DIR = os.path.join(AQUI, "..", "..", "supabase", "migrations")
FRONTEND_SRC = os.path.join(AQUI, "..", "..", "frontend", "src")

_CREATE = re.compile(
    r'CREATE\s+POLICY\s+"(?P<nome>[^"]+)"\s+ON\s+storage\.objects\b(?P<corpo>.*?);',
    re.IGNORECASE | re.DOTALL,
)
_DROP = re.compile(
    r'DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?"(?P<nome>[^"]+)"\s+ON\s+storage\.objects\b',
    re.IGNORECASE,
)


def _sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def policies_finais_storage(migrations_dir: str = MIGRATIONS_DIR) -> dict[str, str]:
    """Nome -> corpo de cada policy de storage.objects que sobra depois de
    aplicar todas as migrations em ordem de arquivo."""
    vivas: dict[str, str] = {}
    for nome in sorted(os.listdir(migrations_dir)):
        if not nome.endswith(".sql"):
            continue
        with open(os.path.join(migrations_dir, nome), encoding="utf-8") as f:
            sql = _sem_comentarios(f.read())
        eventos = [(m.start(), "create", m) for m in _CREATE.finditer(sql)]
        eventos += [(m.start(), "drop", m) for m in _DROP.finditer(sql)]
        for _, tipo, m in sorted(eventos, key=lambda e: e[0]):
            if tipo == "create":
                vivas[m.group("nome")] = m.group("corpo")
            else:
                vivas.pop(m.group("nome"), None)
    return vivas


def _abre_leitura_a_logado(corpo: str) -> bool:
    """SELECT (ou ALL, ou sem FOR) para um papel que inclui `authenticated`
    (sem TO é PUBLIC), sem `auth.uid()` restringindo ao dono."""
    comando = re.search(r"\bFOR\s+(\w+)", corpo, re.IGNORECASE)
    if comando and comando.group(1).upper() not in ("SELECT", "ALL"):
        return False
    papeis = re.search(r"\bTO\s+([\w\s,]+?)\s+(?:USING|WITH)\b", corpo, re.IGNORECASE)
    if papeis:
        nomes = {p.strip().lower() for p in papeis.group(1).split(",")}
        if not nomes & {"authenticated", "public"}:
            return False
    return "auth.uid()" not in corpo.lower()


def test_nenhuma_policy_do_storage_da_leitura_a_qualquer_logado():
    abertas = sorted(nome for nome, corpo in policies_finais_storage().items() if _abre_leitura_a_logado(corpo))
    assert abertas == [], (
        f"Policies de storage.objects que deixam qualquer usuário logado ler os buckets "
        f"direto pela Storage API, pulando o gate do backend: {abertas}. "
        f"Remova com DROP POLICY IF EXISTS numa migration nova (molde: 066, 115, 116)."
    )


def test_policy_da_service_role_continua_de_pe():
    """Piso de sanidade: se o parser não visse nada, o teste acima passaria
    sobre lista vazia. A policy da service_role (006) tem que sobrar."""
    vivas = policies_finais_storage()
    assert "Service Role Management" in vivas
    assert not _abre_leitura_a_logado(vivas["Service Role Management"])


def test_frontend_nao_le_storage_direto_pelo_cliente_supabase():
    """Sem policy aberta, leitura direta do navegador quebraria em silêncio;
    arquivo chega ao usuário só por rota do backend com URL assinada."""
    usos = []
    for raiz, _, arquivos in os.walk(FRONTEND_SRC):
        for arquivo in arquivos:
            if not arquivo.endswith((".ts", ".tsx", ".js", ".jsx")):
                continue
            caminho = os.path.join(raiz, arquivo)
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
            if re.search(r"\.storage\s*\.\s*from\s*\(|/storage/v1/", texto):
                usos.append(os.path.relpath(caminho, FRONTEND_SRC))
    assert os.path.isdir(FRONTEND_SRC)
    assert usos == [], f"Leitura direta do Supabase Storage no frontend: {usos}"
