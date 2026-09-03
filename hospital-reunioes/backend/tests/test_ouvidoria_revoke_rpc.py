"""O EXECUTE das RPCs da Ouvidoria não pode sobrar para a anon_key (issue #520).

A migration 092 escreveu `REVOKE ALL ... FROM PUBLIC` e achou que tinha
fechado a porta. Não fechou: o Supabase concede `EXECUTE` direto às roles
`anon` e `authenticated` por default privilege de schema, e revogar de PUBLIC
não mexe em grant dado a role nomeada. Em produção a chamada anônima devolvia
HTTP 200 com corpo vazio, e o corpo só veio vazio porque o RLS default-deny da
064 segurou a leitura da trilha. A camada que importa estava de pé; a segunda,
que a migration prometia, não.

Dois guardas moram aqui, e eles medem coisas diferentes de propósito:

* o guarda estático varre TODAS as migrations e cobra que nenhuma função da
  Ouvidoria exposta pelo PostgREST TERMINE com EXECUTE ao alcance da anon_key.
  Termina, e não "tenha um REVOKE em algum lugar": as migrations rodam em
  ordem, então um `CREATE` que recria a função ou um `GRANT` que a reconcede
  DEPOIS do último `REVOKE` reabrem a porta, e um guarda que só procurasse o
  `REVOKE` ficaria verde nos dois casos. É o teste que teria pego a 092 no dia
  em que ela nasceu, e é o que impede a próxima função do módulo de repetir o
  furo;
* o veredito da fumaça mede a produção de verdade, porque quem aplica a
  migration aqui é o humano no Studio, à mão, e migration escrita não é
  migration aplicada.

O veredito é onde mora a armadilha que esta issue nomeia. Um teste de fumaça
que só olha o corpo da resposta passa HOJE, com o furo escancarado, porque o
corpo vazio vem do RLS e não da recusa. E um teste que bate na porta errada (a
service_role em vez da anon, ou uma chave que o gateway nem aceitou) também
passaria por motivo nenhum. Por isso o veredito só aprova a recusa NOMEADA: o
SQLSTATE 42501 no corpo. Quem decide é o SQLSTATE, e não o status, e essa lição
custou um falso negativo em produção. Com a 095 já aplicada, a recusa chegou
como HTTP **401** com o 42501 dentro, e uma versão anterior deste script, que
tinha fixado o 403, reprovou um conserto correto. A chave inválida responde 401
também, mas com o corpo do GATEWAY (`Unauthorized`) e sem SQLSTATE nenhum,
porque a requisição não chega ao banco. É o 42501 que separa os dois, e é ele
que prova ao mesmo tempo que a porta fechou e que a fumaça bateu na porta certa.
O 200 reprova seja qual for o corpo, e o 401 ou 403 nu reprova também.

O mesmo guarda estático cobra também as cinco funções de FORA da Ouvidoria
(issue #541, migration 097). Elas não têm prefixo comum para derivar do SQL,
então entram por lista escrita à mão, e a lista tem guarda próprio: cada nome
precisa casar com um `CREATE FUNCTION` de verdade, e a lista não pode estar
vazia. Sem esses dois, um nome torto ou uma lista esvaziada deixariam a
varredura verde em cima de função nenhuma.

As regras dos dois guardas são exercidas contra SQL e respostas SINTÉTICAS, e
não só contra as migrations de hoje. Rodar só contra o repositório real
provaria pouco: ele está certo agora, então o teste ficaria verde mesmo com
metade das regras apagadas.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts import smoke_revoke_rpc_ouvidoria as smoke  # noqa: E402

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")

# As funções da Ouvidoria que já se sabe expostas. Não é a lista que o guarda
# cobra: é o piso que prova que a varredura abaixo não voltou vazia. Uma regex
# que deixasse de casar transformaria o guarda inteiro em vácuo silencioso.
FUNCOES_CONHECIDAS = {
    "ouvidoria_transicionar",
    "ouvidoria_relatorio_registrar_entrega",
    "ouvidoria_ultimo_movimento",
}


# O nome da função no SQL, com ou sem o schema à frente. Nenhuma migration da
# casa usa `public.` hoje, e é justamente por isso que o prefixo precisa estar
# aqui: a primeira que usar escaparia da varredura em silêncio, e silêncio é o
# modo de falha que esta issue existe para fechar.
NOME = r"(?:public\.)?({funcao})\s*\("

ROLES_PUBLICAS = ("anon", "authenticated")

# As cinco funções de fora da Ouvidoria que a issue #541 nomeia. Aqui a lista é
# escrita à mão porque não existe prefixo comum para derivar: elas nasceram em
# quatro migrations diferentes (001, 010, 024, 029), com nomes que só têm em
# comum o fato de o PostgREST publicá-las. Escrever à mão traz o risco de o
# nome sair torto, e é por isso que `test_os_cinco_nomes_existem_no_sql` existe:
# nome que não casa com nenhum `CREATE FUNCTION` reprova, em vez de virar uma
# cobrança sobre função nenhuma.
FUNCOES_FORA_DA_OUVIDORIA = {
    "generate_participant_id",
    "incrementar_acoes_concluidas",
    "decrementar_acoes_concluidas",
    "confirmar_importacao_atomico",
    "merge_participante_externo",
}


def _funcoes_expostas(comandos: str) -> set[str]:
    """As funções da Ouvidoria que o PostgREST publica em `/rest/v1/rpc/...`.

    Derivada do SQL, e não escrita à mão: uma lista fixa aqui envelheceria em
    silêncio, e a função que alguém criar amanhã escaparia do guarda sem
    ninguém notar, que é exatamente como a 092 passou.

    Função que devolve `trigger` fica de fora porque o PostgREST não a expõe:
    ela só é chamável pelo gatilho que a declara."""
    expostas = set()
    padrao = r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?(ouvidoria_\w+)"
    for achado in re.finditer(padrao, comandos, re.IGNORECASE):
        # O `RETURNS` vem logo depois da lista de parâmetros. Casar a lista
        # inteira é que seria frágil, porque `VARCHAR(10)` tem parênteses
        # aninhados dentro dela.
        retorno = re.search(
            r"\bRETURNS\s+(?:TABLE\b|SETOF\s+)?(\w+)", comandos[achado.end() : achado.end() + 2000], re.IGNORECASE
        )
        if retorno is not None and retorno.group(1).lower() == "trigger":
            continue
        expostas.add(achado.group(1))
    return expostas


def _ultima_posicao(padrao: str, comandos: str) -> int | None:
    """Onde o último comando que casa acontece, ou None se nenhum casa.

    Posição importa porque o banco aplica as migrations EM ORDEM, e o blob vem
    ordenado por nome de arquivo. Um `REVOKE` que existe mas roda ANTES de um
    `CREATE` que recria a função não protege nada: a função nasce de novo com o
    EXECUTE que o `ALTER DEFAULT PRIVILEGES` do Supabase concede."""
    achados = list(re.finditer(padrao, comandos, re.IGNORECASE | re.DOTALL))
    return achados[-1].start() if achados else None


def _nomeia_role_publica(alvos: str) -> set[str]:
    """Quais das roles do bundle aparecem nesta lista de alvos de REVOKE/GRANT."""
    return {role for role in ROLES_PUBLICAS if re.search(rf"\b{role}\b", alvos, re.IGNORECASE)}


def _falhas_de_permissao(comandos: str, funcoes: set[str] | None = None) -> list[str]:
    """Toda função exposta que termina as migrations com EXECUTE ao alcance da
    anon_key, e por quê.

    Sem `funcoes`, cobra as da Ouvidoria que a varredura derivou do SQL. Com
    `funcoes`, cobra a lista dada: é assim que as cinco de fora do módulo
    (issue #541) entram, porque elas não compartilham prefixo nenhum e não há
    o que derivar. Uma lista escrita à mão envelhece, e por isso ela tem um
    guarda próprio provando que cada nome existe mesmo no SQL.

    Três formas de terminar aberta, e o guarda cobra as três, porque fechar só
    a primeira deixaria as outras duas como caminho de volta:

    1. nunca ter sido revogada, ou ter sido revogada só de PUBLIC (o bug da 092);
    2. ter sido revogada e RECRIADA depois, porque o `CREATE` traz o EXECUTE de
       volta pela default privilege do Supabase;
    3. ter sido revogada e RECONCEDIDA depois por um `GRANT ... TO anon`.
    """
    falhas = []
    for funcao in sorted(_funcoes_expostas(comandos) if funcoes is None else funcoes):
        nome = NOME.format(funcao=re.escape(funcao))
        revokes = list(
            re.finditer(
                rf"REVOKE\s+(?:ALL|EXECUTE)\b[^;]*?\bON\s+FUNCTION\s+{nome}[^;]*?\bFROM\b([^;]+);",
                comandos,
                re.IGNORECASE,
            )
        )
        fechadas: set[str] = set()
        ultimo_revoke = None
        for revoke in revokes:
            nomeadas = _nomeia_role_publica(revoke.group(2))
            if nomeadas:
                fechadas |= nomeadas
                ultimo_revoke = revoke.start()
        faltando = set(ROLES_PUBLICAS) - fechadas
        if faltando:
            falhas.append(
                f"`{funcao}`: nenhum REVOKE de EXECUTE nomeia {sorted(faltando)}. Revogar de PUBLIC "
                f"não remove o grant que o Supabase dá direto à role, e a anon_key viaja no bundle."
            )
            continue

        criacao = _ultima_posicao(rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+{nome}", comandos)
        if criacao is not None and criacao > ultimo_revoke:
            falhas.append(
                f"`{funcao}`: recriada por um CREATE que roda DEPOIS do último REVOKE. O CREATE "
                f"devolve o EXECUTE às roles nomeadas pela default privilege do schema `public`."
            )
            continue

        for grant in re.finditer(
            rf"GRANT\s+(?:ALL|EXECUTE)\b[^;]*?\bON\s+FUNCTION\s+{nome}[^;]*?\bTO\b([^;]+);",
            comandos,
            re.IGNORECASE,
        ):
            reabertas = _nomeia_role_publica(grant.group(2))
            if reabertas and grant.start() > ultimo_revoke:
                falhas.append(f"`{funcao}`: um GRANT devolve o EXECUTE a {sorted(reabertas)} DEPOIS do último REVOKE.")
                break
    return falhas


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

    @pytest.fixture(scope="class")
    def expostas(self, comandos) -> set[str]:
        return _funcoes_expostas(comandos)

    def test_a_varredura_acha_as_funcoes_que_a_casa_ja_conhece(self, expostas):
        """O guarda dos guardas. Se a varredura voltar vazia (regex quebrada,
        migration renomeada), os dois testes abaixo passam sem olhar nada, e o
        furo que esta issue conserta voltaria a passar despercebido."""
        assert FUNCOES_CONHECIDAS <= expostas, f"A varredura perdeu {FUNCOES_CONHECIDAS - expostas}."

    def test_a_varredura_ignora_as_funcoes_de_gatilho(self, expostas):
        """`RETURNS TRIGGER` não vira rota do PostgREST. Cobrar REVOKE delas
        seria ruído, e ruído no guarda é o que faz alguém afrouxar o guarda."""
        assert "ouvidoria_movimento_imutavel" not in expostas
        assert "ouvidoria_movimento_anonimizavel" not in expostas

    def test_nenhuma_funcao_exposta_termina_com_execute_ao_alcance_da_anon(self, comandos):
        """O guarda que teria pego a 092. Olha o estado FINAL, depois de todas
        as migrations, e não só a existência de um REVOKE em algum lugar."""
        assert _falhas_de_permissao(comandos) == []

    def test_a_correcao_devolve_o_execute_ao_backend(self, expostas, comandos):
        """A `service_role` também tem grant NOMEADO, pela mesma default
        privilege, então `REVOKE ... FROM PUBLIC` não a atinge, exatamente como
        não atingiu a `anon`. O GRANT explícito não conserta uma perda: ele
        tira a permissão do backend da dependência desse default implícito, que
        é o mesmo mecanismo que criou este bug."""
        for funcao in sorted(expostas):
            assert re.search(
                rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{NOME.format(funcao=re.escape(funcao))}[^;]*?\bTO\b"
                rf"[^;]*?\bservice_role\b",
                comandos,
                re.IGNORECASE,
            ), f"`{funcao}` fica sem EXECUTE explícito para a service_role, que é a role do backend."


class TestDetectorDeFalha:
    """O detector contra SQL sintético.

    Rodá-lo só contra as migrations reais provaria pouco: elas estão certas
    agora, então o teste ficaria verde mesmo com metade das regras apagadas. Os
    casos abaixo são as três formas de terminar com a porta aberta, escritas à
    mão para que apagar qualquer regra fique vermelho."""

    CRIACAO = "CREATE OR REPLACE FUNCTION ouvidoria_x() RETURNS TABLE (a INT) AS $$ SELECT 1; $$;"
    REVOKE = "REVOKE EXECUTE ON FUNCTION ouvidoria_x() FROM PUBLIC, anon, authenticated;"

    def test_fechada_de_verdade_nao_e_falha(self):
        assert _falhas_de_permissao(f"{self.CRIACAO}\n{self.REVOKE}") == []

    def test_revoke_so_de_public_e_falha(self):
        """O bug da 092, literal."""
        sql = f"{self.CRIACAO}\nREVOKE ALL ON FUNCTION ouvidoria_x() FROM PUBLIC;"

        assert "nenhum REVOKE" in " ".join(_falhas_de_permissao(sql))

    def test_sem_revoke_nenhum_e_falha(self):
        assert len(_falhas_de_permissao(self.CRIACAO)) == 1

    def test_recriar_a_funcao_depois_do_revoke_e_falha(self):
        """`DROP` + `CREATE` numa migration posterior devolve o EXECUTE pela
        default privilege, e o REVOKE antigo continua no blob dizendo que está
        tudo bem."""
        sql = f"{self.CRIACAO}\n{self.REVOKE}\nDROP FUNCTION ouvidoria_x();\n{self.CRIACAO}"

        assert "recriada" in " ".join(_falhas_de_permissao(sql))

    def test_reconceder_depois_do_revoke_e_falha(self):
        sql = f"{self.CRIACAO}\n{self.REVOKE}\nGRANT EXECUTE ON FUNCTION ouvidoria_x() TO anon;"

        assert "DEPOIS do último REVOKE" in " ".join(_falhas_de_permissao(sql))

    def test_grant_ao_backend_depois_do_revoke_nao_e_falha(self):
        """A `service_role` não é a anon_key: o GRANT dela é o que mantém o
        backend de pé, e é sempre posterior ao REVOKE."""
        sql = f"{self.CRIACAO}\n{self.REVOKE}\nGRANT EXECUTE ON FUNCTION ouvidoria_x() TO service_role;"

        assert _falhas_de_permissao(sql) == []

    def test_funcao_qualificada_com_o_schema_nao_escapa(self):
        """`public.ouvidoria_x()` é a mesma função. Sem o prefixo no padrão,
        ela sairia da varredura e o guarda ficaria verde sem olhar nada."""
        sql = "CREATE OR REPLACE FUNCTION public.ouvidoria_x() RETURNS TABLE (a INT) AS $$ SELECT 1; $$;"

        assert "ouvidoria_x" in _funcoes_expostas(sql)
        assert len(_falhas_de_permissao(sql)) == 1


class TestMigration095:
    """A migration do conserto: reaplicável e sem tocar em dado."""

    @pytest.fixture(scope="class")
    def ddl(self) -> str:
        caminho = os.path.join(MIGRATIONS_DIR, "095_ouvidoria_revoke_rpc_anon.sql")
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

    def test_403_com_o_sqlstate_aprova(self):
        """O status que a documentação do PostgREST descreve para a negação de
        EXECUTE. Esta casa devolve 401, mas o 403 continua aceito: é a mesma
        recusa, e travar num status só foi justamente o erro que gerou o falso
        negativo em produção."""
        aprovado, motivo = smoke.veredito(
            403, '{"code":"42501","message":"permission denied for function ouvidoria_ultimo_movimento"}'
        )

        assert aprovado is True
        assert "42501" in motivo

    def test_403_sem_o_sqlstate_nao_prova_nada(self):
        """A regra central do script, e a que faltava provar. 403 nu é o que um
        WAF, um proxy ou o nginx devolvem por motivos que nada têm a ver com o
        EXECUTE da role. Só a recusa NOMEADA pelo Postgres aprova."""
        aprovado, motivo = smoke.veredito(403, '{"message":"Forbidden"}')

        assert aprovado is False
        assert "403" in motivo

    def test_403_de_outro_sqlstate_nao_prova_nada(self):
        """Segundo eixo do mesmo discriminador: não basta o corpo trazer um
        código, tem que ser o 42501."""
        aprovado, _ = smoke.veredito(403, '{"code":"42P01","message":"relation does not exist"}')

        assert aprovado is False

    def test_funcao_fora_do_cache_do_postgrest_nao_aprova_sozinha(self):
        """Sem EXECUTE, o PostgREST pode responder que não conhece a função em
        vez de responder que negou. Só que é a MESMA resposta de URL errada, de
        banco sem as migrations e de cache velho: aprovar aqui seria dar verde
        sem prova, que é o gênero de erro que abriu esta issue. O script manda
        conferir no catálogo em vez de concluir."""
        aprovado, motivo = smoke.veredito(404, '{"code":"PGRST202","message":"Could not find the function"}')

        assert aprovado is False
        assert "has_function_privilege" in motivo

    def test_401_com_o_sqlstate_aprova(self):
        """A resposta REAL da produção com a 095 aplicada, colada do curl.

        Nesta casa a negação de EXECUTE volta com 401, e não com 403. Uma versão
        anterior deste script fixou o 403 como o único status capaz de carregar
        a recusa e REPROVOU um conserto correto. Este é o teste que impede o
        falso negativo de voltar."""
        aprovado, motivo = smoke.veredito(
            401,
            '{"code":"42501","details":null,"hint":null,'
            '"message":"permission denied for function ouvidoria_ultimo_movimento"}',
        )

        assert aprovado is True
        assert "42501" in motivo

    def test_401_sem_o_sqlstate_nao_prova_nada(self):
        """O outro eixo, e o motivo de o discriminador ser o SQLSTATE e não o
        status: a chave inválida responde 401 também. O corpo literal abaixo é
        o do controle com chave quebrada, e vem do GATEWAY, não do banco: sem
        SQLSTATE, porque a requisição nem chegou ao Postgres."""
        aprovado, motivo = smoke.veredito(401, '{"message":"Unauthorized","request_id":"abc123"}')

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

    def test_a_fumaca_recusa_a_chave_secreta_no_formato_novo(self):
        """`sb_secret_...` é a sucessora da service_role e NÃO é JWT, então não
        tem claim `role` para ler. Sem esta guarda ela passaria direto, e a
        fumaça rodaria com a chave do backend achando que era a do bundle."""
        with pytest.raises(SystemExit):
            smoke.conferir_chave("sb_secret_abc123")

    def test_a_fumaca_aceita_a_chave_publicavel_no_formato_novo(self):
        smoke.conferir_chave("sb_publishable_abc123")

    def test_a_fumaca_aceita_a_chave_anonima(self):
        smoke.conferir_chave(self._jwt("anon"))


class TestGuardaDasFuncoesForaDaOuvidoria:
    """As cinco de fora do módulo (issue #541), pelas mesmas regras da 095.

    A causa raiz é a mesma da #520: o `ALTER DEFAULT PRIVILEGES` do Supabase dá
    `EXECUTE` direto a `anon` e `authenticated` para toda função criada no
    schema `public`, e nenhuma destas cinco tinha `REVOKE` nenhum.

    A que lidera é a `generate_participant_id()`, e ela é a única onde o RLS
    não é defesa alguma: o corpo é um `nextval`, e sequence não passa por RLS.
    Nas outras quatro o default-deny da 009 segura de fato, mas a defesa mora
    noutro arquivo, que é exatamente o arranjo que a #520 veio corrigir."""

    @pytest.fixture(scope="class")
    def comandos(self) -> str:
        return _sem_comentarios(_todas_migrations_sql())

    def test_a_lista_das_cinco_nao_pode_estar_vazia(self):
        """O guarda dos guardas. Os testes abaixo varrem uma lista, e varredura
        vazia fica verde em cima de nada: esvaziar a lista tem que reprovar
        aqui, e não passar em silêncio lá."""
        assert len(FUNCOES_FORA_DA_OUVIDORIA) == 5

    def test_os_cinco_nomes_existem_no_sql(self, comandos):
        """Nome torto na lista cobraria REVOKE de função que não existe, e um
        REVOKE com o mesmo nome torto satisfaria a cobrança. As duas pontas
        ficariam verdes, e o banco continuaria aberto."""
        for funcao in sorted(FUNCOES_FORA_DA_OUVIDORIA):
            assert re.search(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+{NOME.format(funcao=re.escape(funcao))}",
                comandos,
                re.IGNORECASE,
            ), f"`{funcao}` não é criada por nenhuma migration: o nome na lista está errado."

    def test_nenhuma_das_cinco_termina_com_execute_ao_alcance_da_anon(self, comandos):
        """Estado FINAL depois de todas as migrations, e não a mera existência
        de um REVOKE: as mesmas três formas de terminar aberta que o guarda da
        Ouvidoria já cobra valem aqui."""
        assert _falhas_de_permissao(comandos, FUNCOES_FORA_DA_OUVIDORIA) == []

    def test_as_cinco_continuam_executaveis_pelo_backend(self, comandos):
        """O `REVOKE` desta correção é o que fecha, e o `GRANT` é o que prova
        que fechar não derrubou o backend: `pendencias.py` chama as duas de
        `acoes_concluidas` e `admin/usuarios.py` chama o merge, todas com a
        service_role."""
        for funcao in sorted(FUNCOES_FORA_DA_OUVIDORIA):
            assert re.search(
                rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{NOME.format(funcao=re.escape(funcao))}[^;]*?\bTO\b"
                rf"[^;]*?\bservice_role\b",
                comandos,
                re.IGNORECASE,
            ), f"`{funcao}` fica sem EXECUTE explícito para a service_role, que é a role do backend."


class TestMigration097:
    """A migration do conserto das cinco: reaplicável, e sem levar junto quem
    tem que continuar entrando.

    O guarda acima olha o blob de TODAS as migrations, e por isso ele fica
    verde com o REVOKE escrito em qualquer arquivo. Esta classe olha o arquivo
    da correção: é onde se cobra que ela não faça mais do que prometeu."""

    MIGRATION = "097_revoke_rpc_anon_fora_da_ouvidoria.sql"

    @pytest.fixture(scope="class")
    def comandos(self) -> str:
        with open(os.path.join(MIGRATIONS_DIR, self.MIGRATION), encoding="utf-8") as f:
            return _sem_comentarios(f.read())

    def test_so_mexe_em_permissao(self, comandos):
        """REVOKE e GRANT são reaplicáveis por natureza: rodar de novo não muda
        nada, e quem aplica esta migration é o humano no Studio, que pode
        reaplicá-la. Qualquer DDL de dado aqui quebraria essa promessa."""
        minusculo = comandos.lower()
        for proibido in ("create table", "alter table", "drop table", "drop function", "delete from", "update "):
            assert proibido not in minusculo, f"A migration do conserto não pode conter `{proibido}`."

    def test_revoga_exatamente_as_cinco_funcoes_da_issue(self, comandos):
        """Nem de menos nem de mais. De menos deixa a função aberta; de mais
        fecha uma porta que ninguém pediu para fechar, e esse efeito só aparece
        em produção, na hora em que alguma tela para de funcionar."""
        revogadas = {
            achado.group(1)
            for achado in re.finditer(
                r"REVOKE\s+(?:ALL|EXECUTE)\b[^;]*?\bON\s+FUNCTION\s+(?:public\.)?(\w+)\s*\(",
                comandos,
                re.IGNORECASE,
            )
        }

        assert revogadas == FUNCOES_FORA_DA_OUVIDORIA

    def test_nao_revoga_de_quem_precisa_continuar_executando(self, comandos):
        """A `service_role` é a role do backend, e ela também tem o grant
        NOMEADO pela mesma default privilege: varrê-la junto num `REVOKE`
        derrubaria `pendencias.py` e o merge de participante."""
        for achado in re.finditer(r"REVOKE\b[^;]*?\bFROM\b([^;]+);", comandos, re.IGNORECASE):
            assert not re.search(r"\bservice_role\b", achado.group(1), re.IGNORECASE), (
                f"Este REVOKE leva a service_role junto: `{achado.group(0).strip()}`"
            )
