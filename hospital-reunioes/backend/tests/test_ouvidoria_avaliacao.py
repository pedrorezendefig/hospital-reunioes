"""A Avaliação do QR (issue #1622, PRD #1527, ADR 0086).

O cartaz deixa de abrir direto o formulário: a pessoa dá uma nota de 1 a 5,
marca os motivos se quiser e deixa um comentário opcional. A nota é gravada no
envio, não vira protocolo e não guarda nada de quem avaliou. Quem pede retorno
(ou quer deixar um elogio) segue para a Manifestação guiada, e o caso fica
ligado à avaliação, menos no anonimato.

Os testes sobem a rota real com um banco falso que conhece a tabela nova.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_formulario_publico import (  # noqa: E402
    CLIENTE_DIRETO,
    _BancoFake,
    _make_app,
    _Query,
)

from app.limiter import limiter  # noqa: E402

CODIGO = "AB2CD3"
OUTRO_CODIGO = "XY7ZW8"
ROTA_AVALIACAO = f"/api/ouvidoria/publico/pontos/{CODIGO}/avaliacoes"
ROTA_MANIFESTACAO = "/api/ouvidoria/publico/manifestacoes"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _ponto(codigo: str, *, ativo: bool = True, titulo: str = "atendimento_hoje") -> dict:
    return {
        "id": f"ponto-{codigo}",
        "codigo": codigo,
        "setor": "Pronto Socorro",
        "ponto": "Hall da emergência",
        "ativo": ativo,
        "criado_em": "2026-11-01T12:00:00+00:00",
        "nome_publico": "Emergência adulta",
        "descricao_local": "Hall, parede ao lado da passagem",
        "titulo_cartaz": titulo,
        "codigo_controle": None,
        "ala_internacao": False,
    }


class _BancoComAvaliacoes(_BancoFake):
    """O banco do formulário público, mais a tabela da Avaliação."""

    def __init__(self, **kwargs):
        kwargs.setdefault("pontos", [_ponto(CODIGO), _ponto(OUTRO_CODIGO)])
        super().__init__(**kwargs)
        self.avaliacoes: list[dict] = []

    def inserir_avaliacao(self, payload: dict) -> dict:
        linha = {
            "id": f"avaliacao-{len(self.avaliacoes) + 1}",
            "criada_em": "2026-11-12T15:00:00+00:00",
            "pediu_retorno": False,
            **payload,
        }
        self.avaliacoes.append(linha)
        return linha


class _QueryComAvaliacoes(_Query):
    def __init__(self, banco, tabela):
        super().__init__(banco, tabela)
        self._pending_update: dict | None = None

    def update(self, payload: dict):
        self._pending_update = payload
        return self

    def execute(self):
        if self._tabela != "ouvidoria_avaliacoes":
            return super().execute()
        banco = self._banco
        if self._pending_insert is not None:
            return type("R", (), {"data": [banco.inserir_avaliacao(self._pending_insert)]})()
        alvo = [a for a in banco.avaliacoes if all(a.get(c) == v for c, v in self._filters.items())]
        if self._pending_update is not None:
            for linha in alvo:
                linha.update(self._pending_update)
        data = [dict(a) for a in alvo]
        if self._colunas:
            data = [{c: row.get(c) for c in self._colunas} for row in data]
        return type("R", (), {"data": data})()


def _app(banco: _BancoComAvaliacoes | None = None, **kwargs):
    """O app do formulário público com o banco que conhece a avaliação."""
    banco = banco or _BancoComAvaliacoes()
    client, _ = _make_app(banco, **kwargs)
    app = client.app
    from app.dependencies import get_supabase_client

    class _Supabase:
        def table(self, name: str):
            return _QueryComAvaliacoes(banco, name)

    app.dependency_overrides[get_supabase_client] = _Supabase
    return client, banco


class TestATelaDeNota:
    """A tela N1 abre com o nome público e o título do cartaz daquele ponto
    (seção 4.1 da especificação)."""

    def test_o_cartaz_diz_o_nome_publico_e_o_titulo(self):
        client, _banco = _app(_BancoComAvaliacoes(pontos=[_ponto(CODIGO, titulo="um_minuto")]))

        r = client.get(f"/api/ouvidoria/publico/pontos/{CODIGO}")

        assert r.status_code == 200
        assert r.json() == {"nome_publico": "Emergência adulta", "titulo_cartaz": "um_minuto"}
        assert "Pronto Socorro" not in r.text


class TestANotaNaoViraProtocolo:
    """Critério 1: enviar uma nota não cria manifestação nem protocolo."""

    def test_a_nota_e_gravada_como_avaliacao_e_nao_cria_caso(self):
        client, banco = _app()

        r = client.post(
            ROTA_AVALIACAO,
            json={"nota": 2, "motivos": ["tempo_espera", "limpeza"], "comentario": "Demorou muito."},
        )

        assert r.status_code == 201, r.text
        assert banco.inserts == []
        assert banco.rows == []
        assert len(banco.avaliacoes) == 1
        gravada = banco.avaliacoes[0]
        assert gravada["ponto_id"] == f"ponto-{CODIGO}"
        assert gravada["canal"] == "qr"
        assert gravada["nota"] == 2
        assert gravada["motivos"] == ["tempo_espera", "limpeza"]
        assert gravada["comentario"] == "Demorou muito."
        # O recibo diz só o que a tela precisa para seguir, e nunca protocolo.
        assert r.json() == {"id": gravada["id"], "nota": 2}

    def test_pular_grava_so_a_nota(self):
        """O Pular da tela N2 também grava: a nota já foi dada."""
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json={"nota": 5})

        assert r.status_code == 201, r.text
        assert banco.avaliacoes[0]["nota"] == 5
        assert banco.avaliacoes[0]["motivos"] == []
        assert banco.avaliacoes[0]["comentario"] is None

    @pytest.mark.parametrize(
        "corpo",
        [
            {"nota": 0},
            {"nota": 6},
            {"nota": "3"},
            {"nota": 3, "motivos": ["comida"]},
            {"nota": 3, "comentario": "x" * 501},
        ],
    )
    def test_nota_fora_da_regra_e_recusada_sem_gravar(self, corpo):
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json=corpo)

        assert r.status_code == 422
        assert banco.avaliacoes == []

    def test_cartaz_aposentado_nao_recebe_nota(self):
        """A página abre a Manifestação guiada sem origem nesse caso."""
        client, banco = _app(_BancoComAvaliacoes(pontos=[_ponto(CODIGO, ativo=False)]))

        r = client.post(ROTA_AVALIACAO, json={"nota": 4})

        assert r.status_code == 404
        assert banco.avaliacoes == []

    def test_a_avaliacao_nao_grava_nada_de_quem_avaliou(self):
        """ADR 0086, decisão 2: sem IP, sem aparelho, sem contato, nem quando o
        corpo tenta mandar."""
        client, banco = _app(cliente=CLIENTE_DIRETO)

        r = client.post(
            ROTA_AVALIACAO,
            json={"nota": 1, "nome": "Maria", "contato": "maria@exemplo.com", "ip": "1.2.3.4"},
            headers={"User-Agent": "Celular da Maria"},
        )

        assert r.status_code == 201, r.text
        gravada = banco.avaliacoes[0]
        assert set(gravada) - {"id", "criada_em", "pediu_retorno"} == {
            "ponto_id",
            "canal",
            "nota",
            "motivos",
            "comentario",
        }
        valores = " ".join(str(v) for v in gravada.values())
        for rastro in (CLIENTE_DIRETO[0], "Maria", "Celular"):
            assert rastro not in valores


class TestOLimiteDeNotas:
    """Critério 2: a quarta nota em 10 minutos do mesmo endereço e cartaz é
    recusada, sem gravar nada que identifique quem avaliou."""

    def test_a_quarta_nota_do_mesmo_endereco_e_cartaz_e_recusada(self):
        client, banco = _app(cliente=CLIENTE_DIRETO)

        respostas = [client.post(ROTA_AVALIACAO, json={"nota": 3}) for _ in range(4)]

        assert [r.status_code for r in respostas] == [201, 201, 201, 429]
        assert len(banco.avaliacoes) == 3

    def test_outro_cartaz_do_mesmo_endereco_tem_conta_propria(self):
        client, banco = _app(cliente=CLIENTE_DIRETO)
        for _ in range(3):
            client.post(ROTA_AVALIACAO, json={"nota": 3})

        r = client.post(f"/api/ouvidoria/publico/pontos/{OUTRO_CODIGO}/avaliacoes", json={"nota": 3})

        assert r.status_code == 201, r.text
        assert banco.avaliacoes[-1]["ponto_id"] == f"ponto-{OUTRO_CODIGO}"

    @pytest.mark.parametrize("grafia", [CODIGO.lower(), "Ab2cD3", f"{CODIGO}%20"])
    def test_outra_grafia_do_codigo_nao_abre_conta_nova(self, grafia):
        """O limitador conta pelo caminho da URL. Se `ab2cd3` gravasse, cada
        grafia do mesmo código seria um balde novo, e o limite viraria 3 vezes
        64 para o mesmo cartaz. A nota só entra pela grafia do cartaz, e a
        página manda o código em maiúscula."""
        client, banco = _app(cliente=CLIENTE_DIRETO)
        for _ in range(3):
            client.post(ROTA_AVALIACAO, json={"nota": 3})

        r = client.post(f"/api/ouvidoria/publico/pontos/{grafia}/avaliacoes", json={"nota": 3})

        assert r.status_code in (404, 429)
        assert len(banco.avaliacoes) == 3

    def test_a_recusa_nao_escreve_o_endereco_no_log(self, caplog):
        """O slowapi escreve a chave do limite no log quando ele estoura. A
        chave é endereço e cartaz resumidos, e o IP não aparece."""
        client, _banco = _app(cliente=CLIENTE_DIRETO)
        caplog.set_level(logging.DEBUG)

        respostas = [client.post(ROTA_AVALIACAO, json={"nota": 3}) for _ in range(4)]

        assert respostas[-1].status_code == 429
        assert any("exceeded" in registro.getMessage() for registro in caplog.records)
        assert CLIENTE_DIRETO[0] not in caplog.text


def _manifestacao(**overrides) -> dict:
    """O envio da Manifestação guiada de quem veio da nota, identificado."""
    payload = {
        "anonimo": False,
        "sobre": "mim",
        "data_ocorrencia": "2026-11-10",
        "periodo": "tarde",
        "local_informado": "Emergência adulta",
        "relato": "Esperei duas horas na emergência sem nenhuma informação.",
        "expectativa": "resposta",
        "nome": "Maria Souza",
        "contato": "maria@exemplo.com",
        "p": CODIGO,
    }
    payload.update(overrides)
    return {chave: valor for chave, valor in payload.items() if valor is not None}


def _avaliar(client, nota: int, codigo: str = CODIGO) -> str:
    r = client.post(f"/api/ouvidoria/publico/pontos/{codigo}/avaliacoes", json={"nota": nota})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestQuemPedeRetorno:
    """Critério 3: nota 1 a 3 com "Sim, quero retorno" leva à manifestação, e o
    caso fica ligado à avaliação (e ao cartaz, ADR 0086 decisão 3)."""

    def test_o_caso_de_quem_pediu_retorno_fica_ligado_a_avaliacao_e_ao_cartaz(self):
        client, banco = _app()
        avaliacao_id = _avaliar(client, 2)

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id=avaliacao_id))

        assert r.status_code == 201, r.text
        caso = banco.inserts[0]
        assert caso["avaliacao_id"] == avaliacao_id
        assert caso["canal"] == "qr"
        assert caso["canal_ponto"] == "Hall da emergência"
        assert banco.avaliacoes[0]["pediu_retorno"] is True

    def test_o_elogio_da_nota_alta_tambem_fica_ligado_sem_contar_como_retorno(self):
        """Nota 4 ou 5 oferece o elogio, que não é pedido de retorno."""
        client, banco = _app()
        avaliacao_id = _avaliar(client, 5)

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id=avaliacao_id, natureza_informada="elogio"))

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["avaliacao_id"] == avaliacao_id
        assert banco.avaliacoes[0]["pediu_retorno"] is False

    def test_quem_vem_direto_do_cartaz_entra_sem_ligacao(self):
        client, banco = _app()

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao())

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["avaliacao_id"] is None

    def test_avaliacao_de_outro_cartaz_nao_e_ligada(self):
        """A ligação é com a nota do mesmo cartaz: um id solto não pendura o
        caso na avaliação de outro lugar."""
        client, banco = _app()
        avaliacao_id = _avaliar(client, 1, codigo=OUTRO_CODIGO)

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id=avaliacao_id))

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["avaliacao_id"] is None
        assert banco.avaliacoes[0]["pediu_retorno"] is False

    def test_a_avaliacao_liga_um_caso_so(self):
        client, banco = _app()
        avaliacao_id = _avaliar(client, 2)
        client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id=avaliacao_id))

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id=avaliacao_id))

        assert r.status_code == 201, r.text
        assert banco.inserts[1]["avaliacao_id"] is None

    def test_avaliacao_que_nao_existe_nao_custa_a_manifestacao(self):
        client, banco = _app()

        r = client.post(ROTA_MANIFESTACAO, json=_manifestacao(avaliacao_id="avaliacao-999"))

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["avaliacao_id"] is None


class TestQuemSegueAnonimo:
    """Critério 4: seguindo anônimo, o caso não guarda o cartaz nem a ligação
    com a avaliação (ADR 0086, decisão 3)."""

    def test_o_anonimo_que_veio_da_nota_nao_guarda_o_cartaz_nem_a_ligacao(self):
        client, banco = _app()
        avaliacao_id = _avaliar(client, 1)

        r = client.post(
            ROTA_MANIFESTACAO,
            json=_manifestacao(anonimo=True, nome=None, contato=None, avaliacao_id=avaliacao_id),
        )

        assert r.status_code == 201, r.text
        caso = banco.inserts[0]
        assert caso["avaliacao_id"] is None
        assert caso["canal_ponto"] is None
        valores = " ".join(str(v) for v in caso.values())
        for rastro in (avaliacao_id, CODIGO, "Hall da emergência"):
            assert rastro not in valores
        # Nem a avaliação fica sabendo: marcar o retorno nela seria a ligação
        # escrita do outro lado.
        assert banco.avaliacoes[0]["pediu_retorno"] is False


class TestOKitDeConhecimento:
    """Critério 7: o Assistente de Tecnologia responde sobre a Ouvidoria pelo
    kit. Se o texto não disser que o QR abre a nota, ele responde que o cartaz
    abre o formulário."""

    @pytest.fixture
    def texto(self) -> str:
        from app.services.conhecimento import CONHECIMENTO_DIR

        return (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")

    @pytest.fixture
    def entrada(self, texto) -> str:
        achados = [linha for linha in texto.splitlines() if linha.startswith("- **Nota do QR.**")]
        assert len(achados) == 1
        return achados[0]

    def test_diz_que_o_qr_abre_a_nota_que_nao_vira_protocolo(self, entrada):
        assert "nota de 1 a 5" in entrada
        assert "não vira protocolo" in entrada
        assert "três notas a cada 10 minutos" in entrada

    def test_diz_o_funil_depois_da_nota(self, entrada):
        assert "de 1 a 3 pergunta se a pessoa quer retorno" in entrada
        assert "4 ou 5 oferece deixar um elogio" in entrada
        assert "fica ligado à nota, menos quando a pessoa escolhe ficar anônima" in entrada

    def test_o_apagamento_diz_o_comentario_da_nota(self, texto):
        paragrafo = next(p for p in texto.split("\n\n") if p.startswith("O relato de um caso encerrado"))
        assert "comentário da nota do QR" in paragrafo
        assert "a nota e os motivos ficam" in paragrafo

    def test_nao_diz_mais_que_a_nota_ainda_vai_chegar(self, texto):
        assert "vai abrir primeiro uma nota" not in texto
        assert "que hoje abre o formulário" not in texto


MIGRATION = Path(__file__).parent.parent.parent / "supabase" / "migrations" / "140_ouvidoria_avaliacao_do_qr.sql"


def _ddl() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))


class TestAMigration:
    """O fake do PostgREST não aplica CHECK nem RLS, então é a leitura do
    arquivo que segura as regras do banco."""

    def test_a_tabela_nasce_com_rls_que_nega_por_padrao(self):
        ddl = _ddl()

        assert "CREATE TABLE IF NOT EXISTS ouvidoria_avaliacoes" in ddl
        assert "ALTER TABLE ouvidoria_avaliacoes ENABLE ROW LEVEL SECURITY" in ddl
        assert "CREATE POLICY" not in ddl.upper()

    def test_a_tabela_nao_tem_coluna_que_identifique_quem_avaliou(self):
        corpo = re.search(r"CREATE TABLE IF NOT EXISTS ouvidoria_avaliacoes \((.*?)\n\);", _ddl(), re.S).group(1)
        colunas = {
            m.group(1) for m in re.finditer(r"^\s+([a-z_]+)\s+[A-Z]", corpo, re.M) if m.group(1) not in {"CONSTRAINT"}
        }

        assert {"nota", "motivos", "comentario", "ponto_id"} <= colunas
        for proibida in ("ip", "endereco", "user_agent", "aparelho", "nome", "contato", "telefone"):
            assert not any(proibida in coluna for coluna in colunas), proibida

    def test_os_motivos_do_banco_batem_com_os_da_rota(self):
        from app.services import ouvidoria_avaliacoes

        lista = ", ".join(f"'{m}'" for m in ouvidoria_avaliacoes.MOTIVOS)

        assert f"motivos <@ ARRAY[{lista}]::TEXT[]" in _ddl()

    def test_o_caso_ganha_a_ligacao_com_a_avaliacao(self):
        ddl = _ddl()

        assert "ALTER TABLE ouvidoria_protocolos ADD COLUMN IF NOT EXISTS avaliacao_id UUID" in ddl
        assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_avaliacao" in ddl
        assert "VALUES (140)" in ddl


# Relógio congelado: 12 de novembro de 2026. O corte dos cinco anos é
# 12/11/2021, 12h.
AGORA = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.UTC)


class _AvaliacoesDaRetencao:
    """O PostgREST da tabela da avaliação, com os filtros que a retenção usa."""

    def __init__(self, linhas: list[dict]):
        self.linhas = linhas
        self.falhar = False

    def table(self, nome: str):
        assert nome == "ouvidoria_avaliacoes", nome
        return _ConsultaDaRetencao(self)


class _ConsultaDaRetencao:
    def __init__(self, banco: _AvaliacoesDaRetencao):
        self._banco = banco
        self._update: dict | None = None
        self._condicoes: list = []
        self._negar = False

    def update(self, payload: dict):
        self._update = payload
        return self

    def lte(self, coluna, valor):
        self._condicoes.append(lambda linha: linha[coluna] <= valor)
        return self

    @property
    def not_(self):
        self._negar = True
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        negar, self._negar = self._negar, False
        self._condicoes.append(lambda linha: (linha[coluna] is None) != negar)
        return self

    def execute(self):
        if self._banco.falhar:
            raise RuntimeError("banco fora do ar")
        alvo = [linha for linha in self._banco.linhas if all(c(linha) for c in self._condicoes)]
        for linha in alvo:
            linha.update(self._update or {})
        return type("R", (), {"data": [dict(linha) for linha in alvo]})()


def _avaliacao_antiga(criada_em: str, comentario: str | None) -> dict:
    return {
        "id": f"avaliacao-{criada_em}",
        "nota": 2,
        "motivos": ["tempo_espera", "recepcao"],
        "comentario": comentario,
        "criada_em": criada_em,
    }


class TestARetencaoDoComentario:
    """Critério 5: a Retenção apaga o comentário de avaliação com mais de cinco
    anos e mantém nota e motivos (ADR 0086, decisão 9)."""

    def test_o_comentario_de_mais_de_cinco_anos_sai_e_a_nota_e_os_motivos_ficam(self):
        from app.services import ouvidoria_retencao

        velha = _avaliacao_antiga("2021-11-11T09:00:00+00:00", "A moça da recepção, Joana, foi grossa.")
        recente = _avaliacao_antiga("2021-11-13T09:00:00+00:00", "Demorou muito.")
        banco = _AvaliacoesDaRetencao([velha, recente])

        apagados = ouvidoria_retencao.apagar_comentarios_de_avaliacao(banco, AGORA)

        assert apagados == 1
        assert velha["comentario"] is None
        assert velha["nota"] == 2
        assert velha["motivos"] == ["tempo_espera", "recepcao"]
        assert recente["comentario"] == "Demorou muito."

    def test_com_o_freio_puxado_nada_sai(self, monkeypatch):
        from app.config import settings
        from app.services import ouvidoria_retencao

        monkeypatch.setattr(settings, "ouvidoria_retencao_ativa", False)
        velha = _avaliacao_antiga("2020-01-01T09:00:00+00:00", "Comentário antigo.")

        apagados = ouvidoria_retencao.apagar_comentarios_de_avaliacao(_AvaliacoesDaRetencao([velha]), AGORA)

        assert apagados == 0
        assert velha["comentario"] == "Comentário antigo."

    def test_o_job_da_retencao_varre_os_comentarios_mesmo_com_os_casos_fora_do_ar(self, monkeypatch):
        """As varreduras do job são independentes: a falha de uma não deixa a
        outra sem rodar."""
        from app.cron import scheduler as cron
        from app.services import ouvidoria_retencao

        chamadas: list[str] = []

        def _falha(*_args):
            raise RuntimeError("casos fora do ar")

        monkeypatch.setattr(cron, "_supabase", lambda: object())
        monkeypatch.setattr(ouvidoria_retencao, "anonimizar_encerradas_antigas", _falha)
        monkeypatch.setattr(ouvidoria_retencao, "concluir_apagamentos_pendentes", _falha)
        monkeypatch.setattr(
            ouvidoria_retencao,
            "apagar_comentarios_de_avaliacao",
            lambda _supabase, _agora: chamadas.append("comentarios") or 0,
        )

        cron.anonimizar_manifestacoes_antigas()

        assert chamadas == ["comentarios"]
