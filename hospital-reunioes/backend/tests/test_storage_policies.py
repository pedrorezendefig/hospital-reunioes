"""Leitura do Storage só pelos fluxos do backend (issue #1285, PRD #1282).

O backend lê e grava os buckets com a service_role e entrega arquivo ao
navegador por URL assinada, depois de conferir o acesso. Uma policy de
`storage.objects` que libere SELECT a qualquer `authenticated` abre um segundo
caminho, direto pela Storage API com a anon key do bundle, que pula essa
conferência. As 066, 115 e 116 já nasceram sem ela; a 006 e a 049 criaram duas,
que a 120 remove.

O teste reconstrói o estado final das policies de `storage.objects` aplicando
as migrations em ordem (CREATE soma, DROP tira) e falha se sobrar alguma que dê
leitura a `authenticated` sem filtro de dono (`auth.uid()` comparado com o
dono do objeto no USING).
"""

from __future__ import annotations

import os
import re

import pytest

AQUI = os.path.dirname(__file__)
MIGRATIONS_DIR = os.path.join(AQUI, "..", "..", "supabase", "migrations")
FRONTEND_SRC = os.path.join(AQUI, "..", "..", "frontend", "src")

# Nome entre aspas (sensível a caixa) ou sem aspas (o Postgres dobra para
# minúscula), como na 023.
_NOME = r'(?:"(?P<citado>[^"]+)"|(?P<simples>[A-Za-z_][\w$]*))'
_TABELA = r'"?storage"?\s*\.\s*"?objects"?(?![\w$])'
_CREATE = re.compile(
    rf"CREATE\s+POLICY\s+{_NOME}\s+ON\s+{_TABELA}(?P<corpo>.*?);",
    re.IGNORECASE | re.DOTALL,
)
_DROP = re.compile(
    rf"DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?{_NOME}\s+ON\s+{_TABELA}",
    re.IGNORECASE,
)


def _nome(m: re.Match) -> str:
    return m.group("citado") if m.group("citado") is not None else m.group("simples").lower()


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
                vivas[_nome(m)] = m.group("corpo")
            else:
                vivas.pop(_nome(m), None)
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
    using = re.split(r"\bWITH\s+CHECK\b", corpo, flags=re.IGNORECASE)[0]
    return not _FILTRO_DE_DONO.search(using)


# `auth.uid()` só conta como filtro de dono comparado com uma coluna de dono
# do objeto (`owner`, `owner_id`) ou com a pasta dele; `IS NOT NULL` só
# confere que existe sessão.
_UID = r"\(?\s*(?:select\s+)?auth\.uid\s*\(\s*\)\s*\)?(?:\s*::\s*\w+)?"
_DONO = (
    r"(?:(?:storage\s*\.\s*)?(?:objects\s*\.\s*)?owner(?:_id)?(?![\w$])(?:\s*::\s*\w+)?"
    r"|\(\s*storage\s*\.\s*foldername\s*\(\s*name\s*\)\s*\)\s*\[\s*\d+\s*\])"
)
_FILTRO_DE_DONO = re.compile(rf"{_UID}\s*=\s*{_DONO}|{_DONO}\s*=\s*{_UID}", re.IGNORECASE)


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


def _abertas_em(tmp_path, sql: str) -> list[str]:
    """Policies abertas a logado depois de aplicar uma migration de teste."""
    (tmp_path / "001_teste.sql").write_text(sql, encoding="utf-8")
    vivas = policies_finais_storage(str(tmp_path))
    return sorted(nome for nome, corpo in vivas.items() if _abre_leitura_a_logado(corpo))


def test_policy_sem_aspas_aberta_a_logado_e_acusada(tmp_path):
    """A 023 já cria policy sem aspas; o parser não pode ficar cego a ela."""
    sql = "CREATE POLICY leitura_x ON storage.objects FOR SELECT TO authenticated USING (true);"
    assert _abertas_em(tmp_path, sql) == ["leitura_x"]


@pytest.mark.parametrize(
    "using",
    [
        "auth.uid() IS NOT NULL",
        "bucket_id = 'pdfs' AND (select auth.uid()) IS NOT NULL",
        "auth.uid() = auth.uid()",
    ],
)
def test_auth_uid_que_so_confere_sessao_nao_conta_como_filtro_de_dono(tmp_path, using):
    sql = f'CREATE POLICY "leitura y" ON storage.objects FOR SELECT TO authenticated USING ({using});'
    assert _abertas_em(tmp_path, sql) == ["leitura y"]


@pytest.mark.parametrize(
    "using",
    [
        "owner = auth.uid()",
        "auth.uid() = owner",
        "owner_id = (select auth.uid())::text",
        "bucket_id = 'pdfs' AND (storage.foldername(name))[1] = auth.uid()::text",
    ],
)
def test_filtro_de_dono_de_verdade_nao_e_acusado(tmp_path, using):
    sql = f'CREATE POLICY "leitura z" ON storage.objects FOR SELECT TO authenticated USING ({using});'
    assert _abertas_em(tmp_path, sql) == []
