"""Os membros do Comitê de Conduta (issue #1822, PRD #1786, ADR 0097, decisão 3).

A tela Membros lista cadeira, vigência e situação, e a composição numa data
passada. Só quem tem o perfil de cadastro do módulo inclui e encerra
Participação: o super admin sem o perfil recebe 403. Toda inclusão, saída e
todo perfil dado ou tirado avisa os membros vigentes (sino e e-mail sem
conteúdo de caso) e entra no registro do módulo, com autor e data.

As pessoas daqui são de teste. O banco é o dublê de `conduta_apoio`, e o
e-mail é capturado na borda (`_enviar_email`), sem sair para fora.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from datetime import date, timedelta
from typing import Any

import pytest
from conduta_apoio import Banco
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import conduta_comite, conduta_membros  # noqa: E402
from app.routers.admin import usuarios  # noqa: E402
from app.services.conduta import casos  # noqa: E402
from app.services.conduta import membros as servico  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo, pessoa_no_comite  # noqa: E402

ROTA = "/api/comite-de-conduta/membros"
RECUSA = {"detail": "Sem acesso a este conteúdo do Canal de Conduta"}

HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}
NUCLEO = {"id": "col-nsp", "slug": "nsp", "nome": "Núcleo de Segurança do Paciente"}
SUPER_ADMIN = {"access_profile": "super_admin", "is_super_admin": True}
CADASTRO = {"perfil_conduta": "cadastro_de_membros"}


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    limiter._storage.reset()
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _termo_sem_clicksign(monkeypatch) -> list[str]:
    """O Termo que a inclusão gera (issue #1823) é dublê aqui: nenhum teste
    deste arquivo chega à ClickSign. O envio de verdade está em
    `test_conduta_assinaturas`."""
    enviados: list[str] = []

    def _enviar(_supabase, participacao):
        enviados.append(participacao["id"])
        return {"erro": None}

    monkeypatch.setattr(conduta_membros.assinaturas, "enviar_termo_de_posse", _enviar)
    return enviados


@pytest.fixture
def emails(monkeypatch) -> list[dict]:
    enviados: list[dict] = []

    def _capturar(destinatario, assunto, html, texto, *_a, **_kw):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html, "texto": texto})
        return True

    monkeypatch.setattr(servico, "_enviar_email", _capturar)
    return enviados


def _pessoa(pid: str, nome: str | None = None, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome or f"Pessoa {pid}",
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_conduta": None,
    }
    return {**base, **campos}


def _participacao(pid: str, *, papel="membro", inicio=-30, fim=600, colegiado=COMITE, **campos) -> dict:
    return {
        "id": f"part-{pid}-{colegiado['slug']}",
        "colegiado_id": colegiado["id"],
        "participante_id": pid,
        "papel": papel,
        "e_diretor": False,
        "vigencia_inicio": (HOJE + timedelta(days=inicio)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=fim)).isoformat(),
        "encerrada_em": None,
        "termo_assinado_em": "2026-10-01T12:00:00+00:00",
        **campos,
    }


class _Cenario:
    """`quem` é a pessoa logada; `pessoas` e `participacoes` são o resto do banco."""

    def __init__(self, quem: dict, pessoas: list[dict] = (), participacoes: list[dict] = ()):
        self.quem = quem
        self.banco = Banco(
            {
                "participantes": [quem, *pessoas],
                "colegiados": [dict(COMITE), dict(NUCLEO)],
                "participacoes": [dict(p) for p in participacoes],
            }
        )

    def cliente(self) -> TestClient:
        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(conduta_membros.router, prefix="/api")
        app.include_router(conduta_comite.router, prefix="/api")
        app.include_router(usuarios.router, prefix="/api")
        quem = self.quem

        async def _usuario() -> dict[str, Any]:
            return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def tabela(self, nome: str) -> list[dict]:
        return self.banco.tabelas.get(nome, [])

    def avisos(self) -> list[dict]:
        return [n for n in self.tabela("notificacoes") if n["tipo"] == "CONDUTA"]


def _comite_de_tres() -> list[dict]:
    return [
        _participacao("M1", papel="coordenacao"),
        _participacao("M2", papel="segundo_leitor"),
        _participacao("M3", papel="membro"),
    ]


def _membros_de_tres() -> list[dict]:
    return [_pessoa("M1", "Ana Coordenação"), _pessoa("M2", "Bruno Leitor"), _pessoa("M3", "Carla Membro")]


def _incluir(cliente: TestClient, pid: str = "N1", **campos):
    corpo = {"participante_id": pid, "papel": "membro", "vigencia_inicio": HOJE.isoformat(), **campos}
    return cliente.post(ROTA, json=corpo)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A lista: cadeira, vigência, situação e a composição numa data passada
# ═══════════════════════════════════════════════════════════════════════════


class TestLista:
    def test_membro_ve_a_lista_com_cadeira_vigencia_e_situacao(self):
        passado = _participacao("M4", papel="suplente", inicio=-900, fim=-200)
        cenario = _Cenario(
            _pessoa("M1", "Ana Coordenação"),
            _membros_de_tres()[1:] + [_pessoa("M4", "Davi Antigo")],
            _comite_de_tres() + [passado],
        )
        resposta = cenario.cliente().get(ROTA)

        assert resposta.status_code == 200, resposta.text
        por_nome = {m["nome"]: m for m in resposta.json()["membros"]}
        assert por_nome["Ana Coordenação"]["cadeira"] == "Coordenação"
        assert por_nome["Bruno Leitor"]["cadeira"] == "Membro e segundo leitor"
        assert por_nome["Davi Antigo"]["cadeira"] == "Suplente"
        assert por_nome["Carla Membro"]["vigencia_fim"] == (HOJE + timedelta(days=600)).isoformat()
        assert por_nome["Carla Membro"]["situacao"] == "vigente"
        assert por_nome["Davi Antigo"]["situacao"] == "vencida"
        assert resposta.json()["pode_cadastrar"] is False

    def test_a_composicao_numa_data_passada_mostra_quem_valia_naquele_dia(self):
        antigo = _participacao("M4", papel="membro", inicio=-900, fim=-200)
        cenario = _Cenario(_pessoa("M1"), [_pessoa("M2"), _pessoa("M3"), _pessoa("M4")], _comite_de_tres() + [antigo])
        dia = (HOJE - timedelta(days=300)).isoformat()

        resposta = cenario.cliente().get(ROTA, params={"data": dia})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["data"] == dia
        assert [m["participante_id"] for m in resposta.json()["membros"]] == ["M4"]

    def test_a_lista_nao_traz_participacao_do_nucleo(self):
        do_nucleo = _participacao("M9", colegiado=NUCLEO)
        cenario = _Cenario(_pessoa("M1"), [_pessoa("M9")], [_participacao("M1"), do_nucleo])
        ids = [m["participante_id"] for m in cenario.cliente().get(ROTA).json()["membros"]]
        assert ids == ["M1"]

    def test_quem_tem_o_perfil_de_cadastro_ve_a_lista_e_pode_cadastrar(self):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())
        resposta = cenario.cliente().get(ROTA)
        assert resposta.status_code == 200
        assert resposta.json()["pode_cadastrar"] is True

    @pytest.mark.parametrize("campos", [{}, SUPER_ADMIN])
    def test_quem_nao_e_do_comite_nem_tem_o_perfil_nao_ve_a_lista(self, campos):
        cenario = _Cenario(_pessoa("X1", **campos), _membros_de_tres(), _comite_de_tres())
        resposta = cenario.cliente().get(ROTA)
        assert resposta.status_code == 403
        assert resposta.json() == RECUSA


# ═══════════════════════════════════════════════════════════════════════════
# 2. Quem inclui e encerra
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemCadastra:
    def test_quem_tem_o_perfil_inclui_membro_com_mandato_de_dois_anos(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), [_pessoa("N1", "Nina Nova")])
        inicio = date(2026, 12, 1)

        resposta = _incluir(cenario.cliente(), vigencia_inicio=inicio.isoformat(), e_diretor=True)

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["nome"] == "Nina Nova"
        assert resposta.json()["vigencia_fim"] == "2028-11-30"
        [nova] = [p for p in cenario.tabela("participacoes") if p["participante_id"] == "N1"]
        assert nova["colegiado_id"] == COMITE["id"]
        assert nova["e_diretor"] is True

    def test_quem_tem_o_perfil_encerra_a_participacao(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())

        resposta = cenario.cliente().post(f"{ROTA}/part-M3-conduta/encerrar", json={})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["situacao"] == "encerrada"
        assert resposta.json()["encerrada_em"] == HOJE.isoformat()

    @pytest.mark.parametrize("campos", [SUPER_ADMIN, {}])
    def test_sem_o_perfil_de_cadastro_incluir_e_encerrar_dao_403(self, campos, emails):
        """Mutante: deixar o super admin passar no portão do cadastro."""
        cenario = _Cenario(_pessoa("M1", **campos), [_pessoa("N1"), *_membros_de_tres()[1:]], _comite_de_tres())
        cliente = cenario.cliente()

        incluir = _incluir(cliente)
        encerrar = cliente.post(f"{ROTA}/part-M3-conduta/encerrar", json={})

        assert incluir.status_code == 403 and incluir.json() == RECUSA
        assert encerrar.status_code == 403 and encerrar.json() == RECUSA
        assert len(cenario.tabela("participacoes")) == 3
        assert cenario.tabela("participacoes")[2]["encerrada_em"] is None
        assert cenario.tabela("conduta_registro") == []

    def test_participacao_a_comecar_se_desfaz_e_a_pessoa_nunca_fica_no_comite(self, emails):
        """Incluída por engano com início futuro: encerrar hoje desfaz a
        inclusão. Ela não vale no primeiro dia, nem na composição, nem na fila
        comum dos casos, e a pessoa pode ser incluída de novo."""
        inicio = HOJE + timedelta(days=10)
        futura = _participacao("N1", inicio=10, fim=740)
        cenario = _Cenario(
            _pessoa("C1", **CADASTRO), [*_membros_de_tres(), _pessoa("N1", "Nina Nova")], _comite_de_tres() + [futura]
        )
        cliente = cenario.cliente()

        resposta = cliente.post(f"{ROTA}/part-N1-conduta/encerrar", json={})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["situacao"] == "encerrada"
        composicao = cliente.get(ROTA, params={"data": inicio.isoformat()}).json()["membros"]
        assert "N1" not in [m["participante_id"] for m in composicao]
        assert pessoa_no_comite(cenario.banco, "N1", inicio).na_fila_comum is False
        assert "N1" not in servico.ids_dos_membros_vigentes(cenario.banco, inicio)
        assert _incluir(cliente, "N1", vigencia_inicio=inicio.isoformat()).status_code == 201

    def test_participacao_ja_comecada_nao_se_encerra_antes_do_inicio(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())
        antes = (HOJE - timedelta(days=31)).isoformat()

        resposta = cenario.cliente().post(f"{ROTA}/part-M3-conduta/encerrar", json={"data": antes})

        assert resposta.status_code == 422
        assert cenario.tabela("participacoes")[2]["encerrada_em"] is None

    def test_pessoa_com_participacao_aberta_nao_e_incluida_de_novo(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())
        resposta = _incluir(cenario.cliente(), "M3")
        assert resposta.status_code == 409

    def test_cadeira_desconhecida_e_recusada(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), [_pessoa("N1")])
        assert _incluir(cenario.cliente(), papel="presidencia").status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 3. Incluir ou retirar avisa todos os membros vigentes, e fica registrado
# ═══════════════════════════════════════════════════════════════════════════


class TestAvisoDaComposicao:
    def test_incluir_avisa_todos_os_membros_vigentes_no_sino_e_por_email(self, emails):
        vencido = _participacao("M4", inicio=-900, fim=-200)
        cenario = _Cenario(
            _pessoa("C1", **CADASTRO),
            [*_membros_de_tres(), _pessoa("M4"), _pessoa("N1", "Nina Nova")],
            _comite_de_tres() + [vencido],
        )

        assert _incluir(cenario.cliente()).status_code == 201

        avisados = sorted(n["destinatario_id"] for n in cenario.avisos())
        assert avisados == ["M1", "M2", "M3", "N1"]
        assert "Nina Nova" in cenario.avisos()[0]["mensagem"]
        assert sorted(e["para"] for e in emails) == ["m1@hsm.test", "m2@hsm.test", "m3@hsm.test", "n1@hsm.test"]

    def test_retirar_avisa_os_membros_que_ficam(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())

        assert cenario.cliente().post(f"{ROTA}/part-M3-conduta/encerrar", json={}).status_code == 200

        assert sorted(n["destinatario_id"] for n in cenario.avisos()) == ["M1", "M2"]
        assert all("Carla Membro" in n["mensagem"] for n in cenario.avisos())
        assert sorted(e["para"] for e in emails) == ["m1@hsm.test", "m2@hsm.test"]

    def test_o_email_nao_leva_nome_nem_conteudo(self, emails):
        cenario = _Cenario(
            _pessoa("C1", **CADASTRO), [*_membros_de_tres(), _pessoa("N1", "Nina Nova")], _comite_de_tres()
        )
        _incluir(cenario.cliente())
        assert emails
        for email in emails:
            for texto in (email["assunto"], email["html"], email["texto"]):
                assert "Nina" not in texto
            assert "/comite-de-conduta/membros" in email["texto"]

    def test_inclusao_e_saida_ficam_no_registro_com_autor_e_data(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), [*_membros_de_tres(), _pessoa("N1")], _comite_de_tres())
        cliente = cenario.cliente()
        _incluir(cliente)
        cliente.post(f"{ROTA}/part-M3-conduta/encerrar", json={})

        registro = cenario.tabela("conduta_registro")
        assert [(r["acao"], r["participante_id"], r["autor_id"]) for r in registro] == [
            ("inclusao", "N1", "C1"),
            ("encerramento", "M3", "C1"),
        ]
        lido = cliente.get(f"{ROTA}/registro").json()["registro"]
        assert {r["acao"] for r in lido} == {"inclusao", "encerramento"}
        assert all(r["autor"] == "Pessoa C1" for r in lido)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Dar ou tirar o perfil de cadastro também avisa e fica registrado
# ═══════════════════════════════════════════════════════════════════════════


class TestPerfilDeCadastro:
    def _cenario(self, alvo_perfil=None) -> _Cenario:
        return _Cenario(
            _pessoa("A1", "Admin da Plataforma", **SUPER_ADMIN),
            [*_membros_de_tres(), _pessoa("P9", "Paulo Cadastro", perfil_conduta=alvo_perfil)],
            _comite_de_tres(),
        )

    def test_dar_o_perfil_avisa_os_membros_e_fica_registrado(self, emails):
        cenario = self._cenario()

        resposta = cenario.cliente().patch("/api/admin/usuarios/P9", json={"perfil_conduta": "cadastro_de_membros"})

        assert resposta.status_code == 200, resposta.text
        [linha] = cenario.tabela("conduta_registro")
        assert (linha["acao"], linha["participante_id"], linha["autor_id"]) == ("perfil_dado", "P9", "A1")
        assert linha.get("registrado_em") or linha.get("id")
        assert sorted(n["destinatario_id"] for n in cenario.avisos()) == ["M1", "M2", "M3"]
        assert "Paulo Cadastro" in cenario.avisos()[0]["mensagem"]
        assert len(emails) == 3

    def test_tirar_o_perfil_avisa_os_membros_e_fica_registrado(self, emails):
        cenario = self._cenario("cadastro_de_membros")

        resposta = cenario.cliente().patch("/api/admin/usuarios/P9", json={"perfil_conduta": None})

        assert resposta.status_code == 200, resposta.text
        assert [r["acao"] for r in cenario.tabela("conduta_registro")] == ["perfil_tirado"]
        assert sorted(n["destinatario_id"] for n in cenario.avisos()) == ["M1", "M2", "M3"]

    def test_editar_outro_campo_nao_avisa_o_comite(self, emails):
        cenario = self._cenario("cadastro_de_membros")
        cenario.cliente().patch("/api/admin/usuarios/P9", json={"cargo": "Analista"})
        assert cenario.tabela("conduta_registro") == []
        assert cenario.avisos() == []
        assert emails == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Participação encerrada não é apagada
# ═══════════════════════════════════════════════════════════════════════════


class TestNadaSeApaga:
    def test_a_participacao_encerrada_continua_na_lista(self, emails):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())
        cliente = cenario.cliente()
        cliente.post(f"{ROTA}/part-M3-conduta/encerrar", json={})

        assert len(cenario.tabela("participacoes")) == 3
        por_id = {m["participante_id"]: m for m in cliente.get(ROTA).json()["membros"]}
        assert por_id["M3"]["situacao"] == "encerrada"

    def test_nao_existe_rota_que_apague_membro(self):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), _membros_de_tres(), _comite_de_tres())
        resposta = cenario.cliente().delete(f"{ROTA}/part-M3-conduta")
        assert resposta.status_code in (404, 405)
        assert len(cenario.tabela("participacoes")) == 3
        assert not any("DELETE" in rota.methods for rota in conduta_membros.router.routes)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Quem só tem o perfil de cadastro não lista nem abre caso
# ═══════════════════════════════════════════════════════════════════════════


class TestPerfilNaoAbreCaso:
    def test_quem_so_tem_o_perfil_de_cadastro_nao_lista_nem_abre_caso(self):
        cenario = _Cenario(_pessoa("C1", **CADASTRO, **SUPER_ADMIN))
        caso = casos.registrar_caso(cenario.banco, relato="Relato de teste.", categoria="assedio_moral", rota="comum")
        cliente = cenario.cliente()

        lista = cliente.get("/api/comite-de-conduta/casos")
        aberto = cliente.get(f"/api/comite-de-conduta/casos/{caso['id']}")

        assert lista.status_code == 403 and lista.json() == RECUSA
        assert aberto.status_code == 403 and aberto.json() == RECUSA


# ═══════════════════════════════════════════════════════════════════════════
# A situação, pura
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("inicio", "fim", "encerrada", "esperada"),
    [
        (-10, 10, None, "vigente"),
        (0, 0, None, "vigente"),
        (5, 700, None, "a_comecar"),
        (-700, -1, None, "vencida"),
        (-10, 0, "hoje", "encerrada"),
    ],
)
def test_situacao_da_participacao(inicio, fim, encerrada, esperada):
    participacao = _participacao("M1", inicio=inicio, fim=fim, encerrada_em=HOJE.isoformat() if encerrada else None)
    assert servico.situacao(participacao, HOJE) == esperada


# ═══════════════════════════════════════════════════════════════════════════
# 8. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


def test_o_kit_do_canal_diz_quem_cadastra_e_que_toda_mudanca_avisa_o_comite():
    from pathlib import Path

    kit = (Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "canal-de-conduta.md").read_text(
        encoding="utf-8"
    )
    assert "## A tela Membros" in kit
    assert "O super admin sem esse perfil não cadastra" in kit
    assert "avisa os membros vigentes do Comitê no sino do aplicativo e por e-mail" in kit
    assert "Encerrar não apaga" in kit
    assert "o cadastro dos membros chegam nas próximas entregas" not in kit


# ═══════════════════════════════════════════════════════════════════════════
# O menu: o /me diz quem vê a tela Membros
# ═══════════════════════════════════════════════════════════════════════════


class TestMenu:
    def _me(self, cenario: _Cenario) -> dict:
        from app.routers import participantes

        app = FastAPI()
        app.include_router(participantes.router, prefix="/api")
        quem = cenario.quem

        async def _usuario() -> dict[str, Any]:
            return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: cenario.banco
        resposta = TestClient(app).get("/api/participantes/me")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    @pytest.mark.parametrize(
        ("quem", "participacoes", "ve"),
        [
            (_pessoa("M1"), [_participacao("M1", papel="suplente")], True),
            (_pessoa("C1", **CADASTRO), [], True),
            (_pessoa("A1", **SUPER_ADMIN), [], False),
            (_pessoa("M1"), [_participacao("M1", inicio=-900, fim=-200)], False),
        ],
    )
    def test_o_me_diz_se_a_pessoa_ve_a_tela_membros(self, quem, participacoes, ve):
        assert self._me(_Cenario(quem, [], participacoes))["ve_membros_do_comite"] is ve
