"""O EXECUTE das RPCs da Ouvidoria não pode sobrar para a anon_key (issue #520).

A migration 092 escreveu `REVOKE ALL ... FROM PUBLIC` e achou que tinha
fechado a porta. Não fechou: o Supabase concede `EXECUTE` direto às roles
`anon` e `authenticated` por default privilege de schema, e revogar de PUBLIC
não mexe em grant dado a role nomeada. Em produção a chamada anônima devolvia
HTTP 200 com corpo vazio, e o corpo só veio vazio porque o RLS default-deny da
064 segurou a leitura da trilha. A camada que importa estava de pé; a segunda,
que a migration prometia, não.

Dois guardas moram aqui, e eles medem coisas diferentes de propósito:

* o guarda estático varre TODAS as migrations e cobra, de cada função da
  Ouvidoria que o PostgREST expõe, um `REVOKE EXECUTE` que nomeie `anon` e
  `authenticated`. É o teste que teria pego a 092 no dia em que ela nasceu, e é
  o que impede a próxima função do módulo de repetir o furo;
* o veredito da fumaça mede a produção de verdade, porque quem aplica a
  migration aqui é o humano no Studio, à mão, e migration escrita não é
  migration aplicada.

O veredito é onde mora a armadilha que esta issue nomeia. Um teste de fumaça
que só olha o corpo da resposta passa HOJE, com o furo escancarado, porque o
corpo vazio vem do RLS e não da recusa. E um teste que bate na porta errada (a
service_role em vez da anon, ou uma chave que o gateway nem aceitou) também
passaria por motivo nenhum. Por isso o veredito reprova o HTTP 200 seja qual
for o corpo, e reprova o 401 em vez de comemorá-lo.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts import smoke_revoke_rpc_ouvidoria as smoke  # noqa: E402

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")

# As funções SQL da Ouvidoria que o PostgREST publica em `/rest/v1/rpc/...`.
# Função que devolve `trigger` fica de fora porque o PostgREST não a expõe: ela
# só é chamável pelo gatilho que a declara.
FUNCOES_EXPOSTAS = {
    "ouvidoria_transicionar",
    "ouvidoria_relatorio_registrar_entrega",
    "ouvidoria_ultimo_movimento",
}


def _todas_migrations_sql() -> str:
    """O SQL de todas as migrations junto: o REVOKE de uma função pode nascer
    numa migration posterior à que criou a função (é o caso desta correção)."""
    blob = []
    for nome in sorted(os.listdir(MIGRATIONS_DIR)):
        if nome.endswith(".sql"):
            with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
                blob.append(f.read())
    return "\n".join(blob)


def _sem_comentarios(sql: str) -> str:
    """Só os comandos. Afirmar o que o banco recebeu exige olhar o SQL, não a
    prosa que explica o porquê: a 092 tinha a explicação certa e o comando
    incompleto."""
    return "\n".join(linha for linha in sql.splitlines() if not linha.strip().startswith("--"))


class TestGuardaDasMigrations:
    """O guarda que teria pego a 092."""

    @pytest.fixture(scope="class")
    def comandos(self) -> str:
        return _sem_comentarios(_todas_migrations_sql())

    def test_toda_funcao_exposta_da_ouvidoria_revoga_das_roles_nomeadas(self, comandos):
        for funcao in sorted(FUNCOES_EXPOSTAS):
            revokes = re.findall(
                rf"REVOKE\s+(?:ALL|EXECUTE)[^;]*?ON\s+FUNCTION\s+{re.escape(funcao)}\s*\([^)]*\)[^;]*?FROM([^;]+);",
                comandos,
                re.IGNORECASE | re.DOTALL,
            )
            assert revokes, f"`{funcao}` não tem REVOKE de EXECUTE em migration nenhuma."
            alvos = " ".join(revokes).lower()
            for role in ("anon", "authenticated"):
                assert re.search(rf"\b{role}\b", alvos), (
                    f"O REVOKE de `{funcao}` não nomeia `{role}`. Revogar de PUBLIC não remove "
                    f"o grant que o Supabase dá direto à role, e a anon_key viaja no bundle do frontend."
                )

    def test_a_correcao_devolve_o_execute_ao_backend(self, comandos):
        """Revogar de PUBLIC leva junto a permissão da service_role, que é a
        role com que o backend chama. Sem o GRANT de volta o conserto derruba a
        fila da Ouvidoria em produção."""
        for funcao in sorted(FUNCOES_EXPOSTAS):
            assert re.search(
                rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{re.escape(funcao)}\s*\([^)]*\)\s*TO[^;]*\bservice_role\b",
                comandos,
                re.IGNORECASE | re.DOTALL,
            ), f"`{funcao}` fica sem EXECUTE para a service_role, que é a role do backend."


class TestMigration094:
    """A migration do conserto: reaplicável e sem tocar em dado."""

    @pytest.fixture(scope="class")
    def ddl(self) -> str:
        caminho = os.path.join(MIGRATIONS_DIR, "094_ouvidoria_revoke_rpc_anon.sql")
        with open(caminho, encoding="utf-8") as f:
            return f.read()

    def test_so_mexe_em_permissao(self, ddl):
        """REVOKE e GRANT são reaplicáveis por natureza: rodar de novo não
        muda nada. Qualquer DDL de dado aqui quebraria essa promessa."""
        comandos = _sem_comentarios(ddl).lower()
        for proibido in ("create table", "alter table", "drop table", "drop function", "delete from", "update "):
            assert proibido not in comandos, f"A migration do conserto não pode conter `{proibido}`."

    def test_fecha_a_funcao_da_issue(self, ddl):
        comandos = _sem_comentarios(ddl).lower()
        assert "ouvidoria_ultimo_movimento" in comandos
        assert "anon" in comandos and "authenticated" in comandos


class TestVeredito:
    """O que a fumaça aceita como prova de recusa.

    Cada caso aqui é uma resposta que a produção pode devolver, e o teste diz
    se ela prova o conserto ou não."""

    def test_duzentos_com_corpo_vazio_reprova(self):
        """O estado exato de produção HOJE, com o furo aberto. Um teste que
        aprovasse este caso seria vácuo: ele passa antes e depois do conserto."""
        aprovado, motivo = smoke.veredito(200, "[]")

        assert aprovado is False
        assert "200" in motivo

    def test_duzentos_com_linhas_reprova(self):
        aprovado, _ = smoke.veredito(200, '[{"manifestacao_id":"abc","ultimo_movimento_em":"2026-09-01T10:00:00"}]')

        assert aprovado is False

    def test_permissao_negada_aprova(self):
        aprovado, motivo = smoke.veredito(
            403, '{"code":"42501","message":"permission denied for function ouvidoria_ultimo_movimento"}'
        )

        assert aprovado is True
        assert "42501" in motivo

    def test_funcao_fora_do_cache_do_postgrest_aprova(self):
        """Sem EXECUTE, o PostgREST pode responder que não conhece a função em
        vez de responder que negou. A função existe (a 092 a criou), então
        desconhecer é o mesmo fechamento por outro nome."""
        aprovado, _ = smoke.veredito(404, '{"code":"PGRST202","message":"Could not find the function"}')

        assert aprovado is True

    def test_chave_recusada_nao_prova_nada(self):
        """401 é a porta errada: a chave nem foi aceita, então a resposta não
        diz nada sobre o EXECUTE da role `anon`."""
        aprovado, motivo = smoke.veredito(401, '{"message":"Invalid API key"}')

        assert aprovado is False
        assert "401" in motivo

    def test_resposta_inesperada_nao_prova_nada(self):
        aprovado, _ = smoke.veredito(500, '{"message":"boom"}')

        assert aprovado is False


class TestPapelDaChave:
    """A fumaça precisa bater com a chave anônima, e não com a do backend.

    A service_role tem EXECUTE por GRANT explícito e continuará tendo depois do
    conserto: uma fumaça com ela devolveria 200 e reprovaria um conserto que
    está certo. O contrário é pior: uma fumaça que aceitasse a service_role
    aprovaria o furo se a resposta viesse 403 por outro motivo."""

    def _jwt(self, papel: str) -> str:
        import base64
        import json

        corpo = base64.urlsafe_b64encode(json.dumps({"role": papel}).encode()).decode().rstrip("=")
        return f"cabecalho.{corpo}.assinatura"

    def test_le_o_papel_da_chave_do_supabase(self):
        assert smoke.papel_da_chave(self._jwt("anon")) == "anon"
        assert smoke.papel_da_chave(self._jwt("service_role")) == "service_role"

    def test_chave_que_nao_e_jwt_nao_inventa_papel(self):
        assert smoke.papel_da_chave("sb_publishable_abc123") is None

    def test_a_fumaca_recusa_rodar_com_a_chave_do_backend(self):
        with pytest.raises(SystemExit):
            smoke.conferir_chave(self._jwt("service_role"))

    def test_a_fumaca_aceita_a_chave_anonima(self):
        smoke.conferir_chave(self._jwt("anon"))
