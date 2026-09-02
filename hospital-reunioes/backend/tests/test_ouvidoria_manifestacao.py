"""Manifestação nasce: schema do dossiê, estados, perfis e migração (issue #320).

ADR 0034 emenda a decisão 3 do ADR 0031 ("índice, não dossiê"): a manifestação
completa passa a viver neste app. A fundação da migration 063 (sequence,
protocolo ANO-NNNN gerado pelo banco) é preservada inteira.

Cobre (critérios de aceite da issue #320):
- Protocolo registrado pela Ana (contrato atual) entra em classificação.
- Protocolos pré-existentes seguem consultáveis; a sequence continua.
- Ouvidor e diretoria abrem o dossiê; demais papéis veem só o índice;
  super admin não abre manifestação sigilosa.
- Transição inválida é recusada; a válida grava o movimento na mesma transação.
- Movimento não é editável nem apagável por nenhum caminho.
- Acesso a manifestação gera log.
- Tabelas novas com RLS default-deny e migrations idempotentes.
"""

from __future__ import annotations

import os

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION_MANIFESTACAO = "064_ouvidoria_manifestacao.sql"

# Estados do PRD (ADR 0034, consequência "a máquina de estados atual é
# substituída"). 'aguardando_manifestante' é do PRD de governança de prazo
# (#318), não desta fatia.
ESTADOS = ("novo", "em_classificacao", "aguardando_area", "respondido", "encerrado")


def _ddl(nome: str = MIGRATION_MANIFESTACAO) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


class TestMaquinaDeEstados:
    """A manifestação nasce aguardando classificação (ADR 0034, decisão 3):
    nenhum processo automático despacha."""

    def test_status_aceita_os_cinco_estados_do_prd(self):
        ddl = _ddl().lower()
        for estado in ESTADOS:
            assert f"'{estado}'" in ddl, f"Estado do PRD ausente no CHECK de status: {estado}"

    def test_manifestacao_nova_nasce_em_classificacao(self):
        ddl = _ddl().lower()
        assert "set default 'em_classificacao'" in ddl, (
            "Sem default 'em_classificacao', o POST atual da Ana (que não manda status) "
            "gravaria o estado antigo 'aberto', fora da máquina de estados nova."
        )


import sys  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
FACILITADOR = {"id": "P01", "nome_completo": "Ana Facilitadora", "access_profile": "regular"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "em_classificacao",
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-4711",
        "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "classificacao_ia": {"gravidade_sugerida": "medio", "confianca": 0.72},
        "desfecho": None,
        "desfecho_descricao": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa aqui: a resposta traz SO as
    colunas pedidas no select. Sem isso, o teste esconderia a rota que filtra
    por uma coluna que nao pediu (e viria None em producao)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: r[col], reverse=desc)
        return self

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            self.rows.extend(dict(n) for n in novos)
            return type("R", (), {"data": [dict(n) for n in novos]})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _AgregadoFake:
    """A leitura da função `ouvidoria_ultimo_movimento` do jeito que a rota a
    faz: em páginas (`ler_tudo`) e com ordem estável. O recorte recorta de
    verdade, senão o laço de paginação giraria até o teto de páginas."""

    def __init__(self, linhas: list[dict]):
        self._linhas = sorted(linhas, key=lambda linha: linha["manifestacao_id"])

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        return _AgregadoFake(self._linhas[inicio : fim + 1])

    def execute(self):
        return type("R", (), {"data": [dict(linha) for linha in self._linhas]})()


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict]):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes,
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
        }

    def table(self, nome: str):
        return _TabelaFake(self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, params: dict):
        """Efeito da funcao `ouvidoria_transicionar` (migration 064): aplica o
        estado e grava o movimento juntos. O fake nao revalida a regra, porque
        quem valida antes de chamar e a rota, e a recusa ja e testada pelos
        casos que nunca chegam aqui."""
        # Efeito da função `ouvidoria_ultimo_movimento` (migration 092, issue
        # #484): o instante do movimento mais recente de cada caso, agregado da
        # trilha. É o outro lado da comparação que acende o ponto de novidade.
        if nome == "ouvidoria_ultimo_movimento":
            ultimo: dict[str, str] = {}
            for mov in self.tabelas.get("ouvidoria_movimentos", []):
                quando = mov.get("ocorrido_em")
                if quando is None:
                    continue
                caso = str(mov["manifestacao_id"])
                ultimo[caso] = max(str(quando), ultimo.get(caso, ""))
            agregado = [{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()]
            return _AgregadoFake(agregado)
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        alvo["status"] = params["p_estado_novo"]
        if params.get("p_desfecho") is not None:
            alvo["desfecho"] = params["p_desfecho"]
        if params.get("p_desfecho_descricao") is not None:
            alvo["desfecho_descricao"] = params["p_desfecho_descricao"]
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_id": params["p_autor_id"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


def _client(monkeypatch, participante: dict | None, manifestacoes: list[dict] | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = _SupabaseFake(manifestacoes if manifestacoes is not None else [_manifestacao()])

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestAcessoAoDossie:
    """Dossie completo so para ouvidor e diretoria executiva (ADR 0034,
    decisao 8). Demais papeis de Reunioes veem apenas o indice."""

    @pytest.mark.parametrize("perfil", [OUVIDOR, DIRETORIA])
    def test_ouvidor_e_diretoria_abrem_o_dossie(self, monkeypatch, perfil):
        client, _ = _client(monkeypatch, perfil)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert r.status_code == 200
        dossie = r.json()
        assert dossie["relato_integral"].startswith("Cheguei as 8h")
        assert dossie["manifestante_nome"] == "Joana da Silva"
        assert dossie["manifestante_contato"] == "(31) 99999-0000"

    @pytest.mark.parametrize("papel", [SECRETARIA, FACILITADOR, SUPER_ADMIN])
    def test_papeis_de_reunioes_nao_abrem_o_dossie(self, monkeypatch, papel):
        """Papel nas Reunioes da acesso ao indice, nunca ao Dossie: o super
        admin tecnico esta nessa lista porque administrar o app nao e ler o
        relato de quem manifestou."""
        client, _ = _client(monkeypatch, papel)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert r.status_code == 403

    def test_papeis_de_reunioes_continuam_vendo_o_indice(self, monkeypatch):
        client, _ = _client(monkeypatch, SECRETARIA)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        indice = r.json()["protocolos"][0]
        assert indice["protocolo"] == "2026-0007"
        for campo_do_dossie in ("relato_integral", "manifestante_nome", "manifestante_contato"):
            assert campo_do_dossie not in indice, "Campo do Dossie vazou no indice do painel"


class TestOrigemDoCartazNoDossie:
    """Issue #375, item 11: `canal_setor` e `canal_ponto` eram write-only. O
    canal aberto gravava os dois e nenhuma tupla de leitura os trazia, então o
    ouvidor nunca via de qual cartaz o caso veio. Dado gravado que ninguém lê
    não serve a ninguém."""

    def test_o_dossie_mostra_de_qual_cartaz_o_caso_veio(self, monkeypatch):
        do_cartaz = _manifestacao(numero=11, canal="qr", canal_setor="Recepcao", canal_ponto="Poltrona 12")
        client, _ = _client(monkeypatch, OUVIDOR, [do_cartaz])

        r = client.get("/api/ouvidoria/manifestacoes/uuid-11")

        assert r.status_code == 200, r.text
        dossie = r.json()
        assert dossie["canal_setor"] == "Recepcao"
        assert dossie["canal_ponto"] == "Poltrona 12"

    def test_a_origem_do_cartaz_nao_entra_no_indice(self, monkeypatch):
        """A origem é dado do caso, e o índice é o que quem está fora da
        Ouvidoria enxerga: ela fica no Dossiê, atrás do mesmo gate do relato."""
        client, _ = _client(monkeypatch, SECRETARIA)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        indice = r.json()["protocolos"][0]
        assert "canal_setor" not in indice
        assert "canal_ponto" not in indice


class TestNaturezaInformadaNoDossie:
    """Issue #474: a natureza que o MANIFESTANTE marcou no formulário público
    (issue #473, migration 090) era gravada e nenhuma tupla de leitura a
    trazia. É sugestão de quem manifestou, não classificação: quem classifica é
    o ouvidor, e o campo dele é `tipo_manifestacao`."""

    def test_o_dossie_mostra_a_natureza_que_o_manifestante_informou(self, monkeypatch):
        com_natureza = _manifestacao(numero=12, natureza_informada="elogio")
        client, _ = _client(monkeypatch, OUVIDOR, [com_natureza])

        r = client.get("/api/ouvidoria/manifestacoes/uuid-12")

        assert r.status_code == 200, r.text
        assert r.json()["natureza_informada"] == "elogio"

    def test_a_natureza_informada_nao_entra_no_indice(self, monkeypatch):
        """O que a pessoa disse que traz é dado do caso, e o índice é o que
        quem está fora da Ouvidoria enxerga. A natureza fica no Dossiê, atrás
        do mesmo gate do relato."""
        com_natureza = _manifestacao(numero=12, natureza_informada="elogio")
        client, _ = _client(monkeypatch, SECRETARIA, [com_natureza])

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        assert "natureza_informada" not in r.json()["protocolos"][0]

    def test_exibir_a_sugestao_nao_altera_tipo_sigilo_nem_estado(self, monkeypatch):
        """A soberania da classificação é do ouvidor (ADR 0040, decisão 3). Um
        caso que chegou pelo canal aberto dizendo "elogio" continua SEM tipo,
        sigiloso fail-closed (ADR 0037) e em classificação depois de o Dossiê
        ser aberto: ler não é classificar."""
        do_canal_aberto = _manifestacao(
            numero=12,
            natureza_informada="elogio",
            tipo_manifestacao=None,
            sigilo_reforcado=True,
            status="em_classificacao",
        )
        client, supabase = _client(monkeypatch, OUVIDOR, [do_canal_aberto])

        r = client.get("/api/ouvidoria/manifestacoes/uuid-12")

        assert r.status_code == 200, r.text
        # A leitura chegou até o fim: sem isto o resto seria verde por vácuo.
        assert r.json()["natureza_informada"] == "elogio"
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["tipo_manifestacao"] is None
        assert gravado["sigilo_reforcado"] is True
        assert gravado["status"] == "em_classificacao"
        assert supabase.tabelas["ouvidoria_movimentos"] == []


class TestSigiloReforcado:
    """Denuncia e relato de conduta nascem sigilosos (ADR 0034, decisao 1 e 8):
    so ouvidor e diretoria leem, e o super admin tecnico fica de fora (RN-40).
    O resumo de uma denuncia ja identifica: por isso a sigilosa nao entra nem
    no indice de quem esta fora da Ouvidoria."""

    def _com_sigilosa(self):
        return [
            _manifestacao(numero=7),
            _manifestacao(
                numero=9,
                sigilo_reforcado=True,
                categoria="Denuncia",
                resumo="Relato de conduta de colaborador do setor de Enfermagem.",
            ),
        ]

    @pytest.mark.parametrize("papel", [SECRETARIA, FACILITADOR, SUPER_ADMIN])
    def test_sigilosa_nao_aparece_no_indice_de_quem_esta_fora_da_ouvidoria(self, monkeypatch, papel):
        client, _ = _client(monkeypatch, papel, self._com_sigilosa())

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        numeros = [p["numero"] for p in r.json()["protocolos"]]
        assert numeros == [7], "Manifestacao sigilosa vazou no indice"

    @pytest.mark.parametrize("perfil", [OUVIDOR, DIRETORIA])
    def test_ouvidor_e_diretoria_veem_e_abrem_a_sigilosa(self, monkeypatch, perfil):
        client, _ = _client(monkeypatch, perfil, self._com_sigilosa())

        indice = client.get("/api/ouvidoria/protocolos")
        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-9")

        assert sorted(p["numero"] for p in indice.json()["protocolos"]) == [7, 9]
        assert dossie.status_code == 200
        assert dossie.json()["sigilo_reforcado"] is True


class TestPortaDeEntradaUnica:
    """Toda mudanca de estado passa por uma porta so, que valida a regra e
    grava o movimento na MESMA transacao (RPC no banco). Nao existe caminho
    que mude o status sem deixar rastro."""

    def test_encerrar_sem_desfecho_e_recusado(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="respondido")])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "encerrado"},
        )

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_movimentos"] == [], "Transicao recusada nao pode deixar movimento"
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

    def test_salto_de_estado_e_recusado(self, monkeypatch):
        """Manifestacao em classificacao nao pula direto para respondido: a
        area precisa ter sido acionada antes."""
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="em_classificacao")])

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/transicoes", json={"estado": "respondido"})

        assert r.status_code == 409
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"

    def test_transicao_valida_grava_o_movimento_correspondente(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="em_classificacao")])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "aguardando_area", "observacao": "Encaminhado a Recepcao."},
        )

        assert r.status_code == 200
        assert r.json()["status"] == "aguardando_area"
        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 1
        movimento = movimentos[0]
        assert movimento["estado_anterior"] == "em_classificacao"
        assert movimento["estado_novo"] == "aguardando_area"
        assert movimento["autor_id"] == OUVIDOR["id"]
        assert movimento["observacao"] == "Encaminhado a Recepcao."

    def test_encerrar_com_desfecho_e_aceito(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="respondido")])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={
                "estado": "encerrado",
                "desfecho": "procedente",
                "desfecho_descricao": "Recepcao ajustou a escala; manifestante avisado por telefone.",
            },
        )

        assert r.status_code == 200
        manifestacao = supabase.tabelas["ouvidoria_protocolos"][0]
        assert manifestacao["status"] == "encerrado"
        assert manifestacao["desfecho"] == "procedente"
        assert len(supabase.tabelas["ouvidoria_movimentos"]) == 1

    @pytest.mark.parametrize("papel", [SECRETARIA, FACILITADOR, SUPER_ADMIN])
    def test_quem_esta_fora_da_ouvidoria_nao_transiciona(self, monkeypatch, papel):
        client, supabase = _client(monkeypatch, papel, [_manifestacao(numero=7, status="em_classificacao")])

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/transicoes", json={"estado": "aguardando_area"})

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_movimentos"] == []


class TestLogDeAcesso:
    """Dado pessoal e por vezes sensivel: todo acesso a manifestacao deixa
    registro de quem, o que e quando (ADR 0034, consequencia LGPD)."""

    def test_abrir_o_dossie_gera_registro_de_log(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.get("/api/ouvidoria/manifestacoes/uuid-7")

        acessos = supabase.tabelas["ouvidoria_acessos"]
        assert len(acessos) == 1
        acesso = acessos[0]
        assert acesso["manifestacao_id"] == "uuid-7"
        assert acesso["ator_id"] == OUVIDOR["id"]
        assert acesso["ator_nome"] == OUVIDOR["nome_completo"]
        assert acesso["acao"] == "abrir_dossie"

    def test_acesso_recusado_nao_vira_log_de_leitura(self, monkeypatch):
        """403 nao leu nada: registrar como acesso poluiria a trilha de quem de
        fato viu o Dossie."""
        client, supabase = _client(monkeypatch, SECRETARIA)

        client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert supabase.tabelas["ouvidoria_acessos"] == []

    def test_transicao_tambem_e_acesso_registrado(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="em_classificacao")])

        client.post("/api/ouvidoria/manifestacoes/uuid-7/transicoes", json={"estado": "aguardando_area"})

        acoes = [a["acao"] for a in supabase.tabelas["ouvidoria_acessos"]]
        assert acoes == ["transicionar"]


class TestTrilhaImutavel:
    """Movimento nao e editado nem apagado por ninguem: nem pela API (nao
    existe rota) nem pelo caminho da aplicacao (trigger no banco recusa)."""

    def test_nenhuma_rota_edita_ou_apaga_movimento(self):
        """A guarda e sobre ESCRITA, e nao sobre a palavra no caminho.

        Ate a issue #485 nenhuma rota citava movimento, e proibir a palavra
        inteira era o jeito mais barato de dizer isso. A linha do tempo do caso
        leu a trilha pela primeira vez (PRD #470, D-08), e leitura nao ameaca a
        imutabilidade: o que a ameaca e um POST, PUT, PATCH ou DELETE apontando
        para la, porque a escrita da trilha entra so pela porta de entrada da
        maquina de estados."""
        from app.main import app as app_real

        for caminho, metodos in app_real.openapi()["paths"].items():
            if "movimentos" not in caminho:
                continue
            escritas = [m.upper() for m in metodos if m.lower() != "get"]
            assert not escritas, (
                f"Rota que escreve movimento: {escritas} em {caminho}. A trilha e append-only, "
                "escrita so pela porta de entrada da maquina de estados."
            )

    def test_codigo_da_aplicacao_nunca_faz_update_ou_delete_em_movimento(self):
        alvo = os.path.join(os.path.dirname(__file__), "..", "app")
        for raiz, _dirs, arquivos in os.walk(alvo):
            for arquivo in arquivos:
                if not arquivo.endswith(".py"):
                    continue
                with open(os.path.join(raiz, arquivo), encoding="utf-8") as f:
                    codigo = f.read()
                for tabela in ("ouvidoria_movimentos", "ouvidoria_acessos"):
                    if f'table("{tabela}")' not in codigo:
                        continue
                    trecho = codigo.split(f'table("{tabela}")')[1][:120]
                    assert ".update(" not in trecho and ".delete(" not in trecho, (
                        f"{arquivo} tenta alterar {tabela}: a trilha e append-only."
                    )

    def test_banco_recusa_update_e_delete_no_movimento(self):
        ddl = _ddl()
        for tabela in ("ouvidoria_movimentos", "ouvidoria_acessos"):
            for operacao in ("UPDATE", "DELETE"):
                assert f"BEFORE {operacao} ON {tabela}" in ddl, (
                    f"Sem trigger de {operacao} em {tabela}: super admin com acesso ao banco apagaria a trilha."
                )
        assert "RAISE EXCEPTION" in ddl


class TestFundacaoPreservada:
    """A numeracao da migration 063 nao e tocada: numeros ja foram comunicados
    a pacientes e reiniciar numeracao e proibido (ADR 0034, decisao 2)."""

    def test_migration_nao_mexe_na_sequence_nem_no_numero(self):
        ddl = _ddl().lower()
        for proibido in ("drop table ouvidoria_protocolos", "drop sequence", "drop column numero", "setval"):
            assert proibido not in ddl, f"A migration mexe na fundacao da numeracao: {proibido}"

    def test_migration_nao_recria_a_coluna_gerada_do_protocolo(self):
        ddl = _ddl().lower()
        assert "generated always as" not in ddl, (
            "Recriar a coluna protocolo mudaria os numeros ja comunicados; a 064 so acrescenta."
        )

    def test_protocolos_existentes_migram_de_aberto_para_em_classificacao(self):
        ddl = _ddl().lower()
        assert "update ouvidoria_protocolos set status = 'em_classificacao' where status = 'aberto'" in ddl


class TestPadraoDaCasa:
    def test_tabelas_novas_nascem_com_rls_default_deny(self):
        ddl = _ddl()
        for tabela in ("ouvidoria_movimentos", "ouvidoria_acessos"):
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY" in ddl

    def test_migration_e_idempotente(self):
        """Rodar duas vezes nao pode estourar: o padrao do repo e IF NOT EXISTS
        no CREATE e DROP ... IF EXISTS antes de recriar constraint e trigger."""
        ddl = _ddl().lower()
        assert ddl.count("create table if not exists") == 2
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl
        assert "create or replace function" in ddl
        # Constraint e trigger nao tem IF NOT EXISTS em Postgres: derruba antes.
        assert ddl.count("alter table") >= 1
        for constraint in (
            "ouvidoria_protocolos_status_check",
            "ouvidoria_protocolos_vinculo_check",
            "participantes_perfil_ouvidoria_check",
        ):
            assert f"drop constraint if exists {constraint}" in ddl
        assert ddl.count("drop trigger if exists") == 4


class TestPortaUnicaDeVerdade:
    """A porta de entrada e unica: o PATCH de status do painel antigo (issue
    #292) mudava o estado sem deixar movimento e falava a lingua antiga
    (aberto/respondido). Ele sai; quem muda estado e a rota de transicoes."""

    def test_patch_de_status_do_painel_antigo_nao_existe_mais(self):
        from app.main import app as app_real

        caminhos = set(app_real.openapi()["paths"].keys())
        assert "/api/ouvidoria/protocolos/{protocolo_id}/status" not in caminhos
        assert "/api/ouvidoria/manifestacoes/{manifestacao_id}/transicoes" in caminhos

    def test_estado_antigo_aberto_nao_e_mais_aceito(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_manifestacao(numero=7, status="em_classificacao")])

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/transicoes", json={"estado": "aberto"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_movimentos"] == []


class TestApiDaAnaSegueIntacta:
    """O POST da Ana nao muda de contrato nesta fatia (os campos de dossie sao
    da #324): ela continua mandando os mesmos quatro campos, e o caso entra em
    classificacao, com dados_incompletos, para o ouvidor completar na
    validacao (ADR 0034, decisao 10 e consequencia)."""

    def test_contrato_do_post_da_ana_nao_ganhou_campo_obrigatorio(self):
        from app.routers.ana import RegistroProtocolo

        obrigatorios = {nome for nome, campo in RegistroProtocolo.model_fields.items() if campo.is_required()}
        assert obrigatorios == {"categoria", "setor", "resumo"}

    def test_resposta_da_ana_segue_fechada_no_indice(self):
        """A Ana fala com pacientes: nem o relato nem o nome de quem manifestou
        podem voltar por essa rota, mesmo agora que a tabela os guarda."""
        from app.routers.ana import _CAMPOS_PROTOCOLO_TUPLA

        for campo_do_dossie in (
            "relato_integral",
            "manifestante_nome",
            "manifestante_contato",
            "classificacao_ia",
        ):
            assert campo_do_dossie not in _CAMPOS_PROTOCOLO_TUPLA

    def test_caso_da_ana_nasce_incompleto_para_o_ouvidor_completar(self):
        ddl = _ddl().lower()
        assert "dados_incompletos    boolean not null default true" in ddl


class TestFrontendDescobreOPerfil:
    """O painel decide o que mostrar pelo perfil da pessoa: sem o campo em
    /participantes/me, a tela nao sabe se pode oferecer o Dossie."""

    def test_participante_me_expoe_o_perfil_de_ouvidoria(self):
        from app.models.schemas import ParticipanteResponse

        assert "perfil_ouvidoria" in ParticipanteResponse.model_fields

    def test_rota_me_pede_a_coluna_do_perfil_de_ouvidoria(self):
        import inspect

        from app.routers import participantes

        fonte = inspect.getsource(participantes.get_me)
        assert "perfil_ouvidoria" in fonte, (
            "A rota /me nao pede a coluna: o campo voltaria sempre None e o painel esconderia o Dossie do ouvidor."
        )


class TestErrosNaoMascarados:
    """Correções do code-review do PR #328: erro de infra não pode se
    disfarçar de regra de negócio, nem vazar detalhe interno do banco."""

    def test_id_malformado_na_transicao_nao_vaza_detalhe_do_banco(self, monkeypatch):
        from postgrest.exceptions import APIError

        client, supabase = _client(monkeypatch, OUVIDOR)

        class _TabelaEstoura(_TabelaFake):
            def execute(self):
                raise APIError({"message": "invalid input syntax for type uuid", "code": "22P02"})

        monkeypatch.setattr(supabase, "table", lambda nome: _TabelaEstoura([]))
        resp = client.post(
            "/api/ouvidoria/manifestacoes/nao-e-uuid/transicoes",
            json={"estado": "aguardando_area"},
        )
        assert resp.status_code == 404
        assert "invalid input" not in resp.text

    def test_desfecho_em_transicao_nao_terminal_e_recusado(self, monkeypatch):
        manifestacao = _manifestacao(status="em_classificacao")
        client, supabase = _client(monkeypatch, OUVIDOR, [manifestacao])
        resp = client.post(
            f"/api/ouvidoria/manifestacoes/{manifestacao['id']}/transicoes",
            json={"estado": "aguardando_area", "desfecho": "procedente", "desfecho_descricao": "x"},
        )
        assert resp.status_code == 422
        assert supabase.tabelas["ouvidoria_protocolos"][0]["desfecho"] is None

    def test_erro_de_infra_na_rpc_nao_vira_409(self, monkeypatch):
        from postgrest.exceptions import APIError

        manifestacao = _manifestacao(status="em_classificacao")
        client, supabase = _client(monkeypatch, OUVIDOR, [manifestacao])

        def _rpc_ausente(nome, params):
            raise APIError({"message": "function not found", "code": "PGRST202"})

        monkeypatch.setattr(supabase, "rpc", _rpc_ausente)
        resp = client.post(
            f"/api/ouvidoria/manifestacoes/{manifestacao['id']}/transicoes",
            json={"estado": "aguardando_area"},
        )
        assert resp.status_code == 500
        assert "function not found" not in resp.text

    def test_recusa_do_banco_segue_sendo_409(self, monkeypatch):
        from postgrest.exceptions import APIError

        manifestacao = _manifestacao(status="em_classificacao")
        client, supabase = _client(monkeypatch, OUVIDOR, [manifestacao])

        def _rpc_recusa(nome, params):
            raise APIError({"message": "Transicao invalida", "code": "23514"})

        monkeypatch.setattr(supabase, "rpc", _rpc_recusa)
        resp = client.post(
            f"/api/ouvidoria/manifestacoes/{manifestacao['id']}/transicoes",
            json={"estado": "aguardando_area"},
        )
        assert resp.status_code == 409
