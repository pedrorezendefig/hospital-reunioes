"""O depoimento do Canal de Conduta (issue #1830; especificação, seções 7.1 e
7.2; ADR 0097, decisão 2).

Cada classe é um critério de aceite da issue. As pessoas e os casos são de
teste; o banco e o Storage são os dublês de `conduta_apoio`, e a cifra é de
verdade, com uma chave gerada na hora.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from conduta_apoio import Banco
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.middleware.limite_corpo import LIMITE_CORPO_BYTES, LimiteDeCorpoMiddleware, teto_da_rota  # noqa: E402
from app.routers import conduta_comite, conduta_depoimentos  # noqa: E402
from app.services.conduta import casos, cifra, depoimentos  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

MB = 1024 * 1024

BASE = "/api/comite-de-conduta"
RELATO = "O supervisor grita com a equipe do almoxarifado e ameaça cortar as horas."
HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}
COORDENACAO, MEMBRO, DE_FORA = "COORD", "MEMB", "FORA"
NOMES = {COORDENACAO: "Ana Coordenadora", MEMBRO: "Bruno Membro", DE_FORA: "Carla de Fora"}

PESSOA_OUVIDA = {"nome": "Fulano de Tal", "cargo": "Supervisor do almoxarifado", "papel": "acusado"}
TRANSCRICAO = b"Entrevistador: o senhor confirma? Fulano: confirmo que levantei a voz."
# O começo de um M4A de verdade (caixa ftyp), seguido de "som".
AUDIO_M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom" + b"som do depoimento" * 64
FOTO_DO_TERMO = b"\xff\xd8\xff\xe0" + b"pixels do termo assinado" * 32


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())


def _pessoa(pid: str) -> dict[str, Any]:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": NOMES[pid],
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
    }


def _participacao(pid: str, papel: str) -> dict:
    return {
        "id": f"part-{pid}",
        "colegiado_id": COMITE["id"],
        "participante_id": pid,
        "papel": papel,
        "vigencia_inicio": (HOJE - timedelta(days=30)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=600)).isoformat(),
        "termo_assinado_em": "2026-10-01T12:00:00+00:00",
    }


class Comite:
    """Coordenação e membro do Comitê, mais alguém de fora dele, e um caso já
    na etapa Apuração do rito Rápido."""

    def __init__(self):
        self.banco = Banco(
            {
                "participantes": [_pessoa(p) for p in (COORDENACAO, MEMBRO, DE_FORA)],
                "colegiados": [dict(COMITE)],
                "participacoes": [_participacao(COORDENACAO, "coordenacao"), _participacao(MEMBRO, "membro")],
            }
        )

    def caso(self, etapa: str = "apuracao") -> str:
        novo = casos.registrar_caso(self.banco, relato=RELATO, categoria=None)
        linha = next(c for c in self.banco.tabelas["conduta_casos"] if c["id"] == novo["id"])
        linha.update(
            {
                "recebido_em": datetime.now().astimezone().isoformat(),
                "etapa": etapa,
                "rito": "rapido" if etapa == "apuracao" else None,
                "escopo": "dentro" if etapa == "apuracao" else None,
            }
        )
        return novo["id"]

    def cliente(self, pid: str) -> TestClient:
        app = FastAPI()
        app.include_router(conduta_comite.router, prefix="/api")
        app.include_router(conduta_depoimentos.router, prefix="/api")
        pessoa = next(p for p in self.banco.tabelas["participantes"] if p["id"] == pid)

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def abrir(self, pid: str, caso_id: str) -> dict:
        resposta = self.cliente(pid).get(f"{BASE}/casos/{caso_id}")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def adicionar(self, pid: str, caso_id: str, pessoa: dict | None = None):
        return self.cliente(pid).post(f"{BASE}/casos/{caso_id}/depoimentos", json=pessoa or PESSOA_OUVIDA)

    def depoimento(self, caso_id: str, pid: str = MEMBRO) -> str:
        resposta = self.adicionar(pid, caso_id)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["depoimento"]["id"]

    def anexar(self, pid: str, caso_id: str, dep: str, botao: str, nome: str, conteudo: bytes):
        return self.cliente(pid).post(
            f"{BASE}/casos/{caso_id}/depoimentos/{dep}/{botao}",
            files={"arquivo": (nome, conteudo, "application/octet-stream")},
        )

    def baixar(self, pid: str, caso_id: str, dep: str, arquivo_id: str):
        return self.cliente(pid).get(f"{BASE}/casos/{caso_id}/depoimentos/{dep}/arquivos/{arquivo_id}")

    def cartao(self, pid: str, caso_id: str, dep: str) -> dict:
        return next(d for d in self.abrir(pid, caso_id)["depoimentos"] if d["id"] == dep)

    def trilha(self, caso_id: str) -> list[str]:
        return [linha["acao"] for linha in self.banco.tabelas["conduta_trilha"] if linha["caso_id"] == caso_id]


@pytest.fixture
def comite() -> Comite:
    return Comite()


# ═══════════════════════════════════════════════════════════════════════════
# O cartão do depoimento recebe transcrição, áudio e termo assinado, cada um
# no seu botão, sem seletor de tipo
# ═══════════════════════════════════════════════════════════════════════════


class TestCartaoDoDepoimento:
    def test_adicionar_pessoa_a_ouvir_cria_o_cartao_com_nome_cargo_e_papel(self, comite):
        caso = comite.caso()

        dep = comite.depoimento(caso)

        cartao = comite.cartao(COORDENACAO, caso, dep)
        assert (cartao["nome"], cartao["cargo"], cartao["papel"]) == (
            "Fulano de Tal",
            "Supervisor do almoxarifado",
            "acusado",
        )
        assert cartao["situacao"] == "Aguardando assinatura"
        assert "adicionou_pessoa_a_ouvir" in comite.trilha(caso)

    def test_cada_botao_recebe_o_seu_arquivo_e_o_cartao_mostra_cada_um_no_seu_lugar(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        assert comite.anexar(MEMBRO, caso, dep, "transcricao", "transcricao.txt", TRANSCRICAO).status_code == 200
        assert comite.anexar(MEMBRO, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A).status_code == 200
        assert comite.anexar(MEMBRO, caso, dep, "termo-assinado", "IMG_0001.jpg", FOTO_DO_TERMO).status_code == 200

        arquivos = comite.cartao(MEMBRO, caso, dep)["arquivos"]
        assert [(tipo, len(arquivos[tipo])) for tipo in ("transcricao", "audio", "termo_assinado")] == [
            ("transcricao", 1),
            ("audio", 1),
            ("termo_assinado", 1),
        ]

    def test_o_botao_define_o_tipo_e_recusa_o_arquivo_de_outro_tipo(self, comite):
        """Sem seletor de tipo: o botão do áudio não aceita a transcrição, e o
        da transcrição não aceita o áudio."""
        caso = comite.caso()
        dep = comite.depoimento(caso)

        audio_errado = comite.anexar(MEMBRO, caso, dep, "audio", "transcricao.txt", TRANSCRICAO)
        transcricao_errada = comite.anexar(MEMBRO, caso, dep, "transcricao", "gravacao.m4a", AUDIO_M4A)

        assert (audio_errado.status_code, transcricao_errada.status_code) == (422, 422)
        assert "MP3, M4A ou OGG" in audio_errado.json()["detail"]
        assert comite.cartao(MEMBRO, caso, dep)["arquivos"] == {"transcricao": [], "audio": [], "termo_assinado": []}
        assert comite.banco.storage.objetos == {}

    def test_quem_nao_abre_o_caso_nao_anexa(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        resposta = comite.anexar(DE_FORA, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A)

        assert resposta.status_code == 403
        assert comite.banco.storage.objetos == {}

    def test_depoimento_de_outro_caso_nao_entra_pelo_caso_que_a_pessoa_abre(self, comite):
        caso, outro = comite.caso(), comite.caso()
        dep_do_outro = comite.depoimento(outro)

        resposta = comite.anexar(MEMBRO, caso, dep_do_outro, "audio", "gravacao.m4a", AUDIO_M4A)

        assert resposta.status_code == 404

    def test_so_na_etapa_apuracao(self, comite):
        caso = comite.caso(etapa="triagem")

        assert comite.adicionar(COORDENACAO, caso).status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# Um áudio de 250 MB em M4A sobe, fica cifrado no bucket e toca para um
# membro do caso
# ═══════════════════════════════════════════════════════════════════════════


class TestAudioDoDepoimento:
    def test_um_m4a_de_250_mb_cabe_no_botao_do_audio_e_um_de_301_nao(self):
        assert depoimentos.conferir_arquivo("audio", "depoimento.m4a", 250 * MB) == "audio/mp4"
        with pytest.raises(depoimentos.DepoimentoRecusadoError) as recusa:
            depoimentos.conferir_arquivo("audio", "depoimento.m4a", 301 * MB)
        assert recusa.value.status == 413

    def test_o_corpo_de_250_mb_passa_pelo_teto_do_app_so_na_rota_do_audio(self):
        """O teto global do app é 100 MB: sem a exceção da rota do áudio, o
        depoimento de duas horas voltaria 413 antes de chegar ao botão."""
        rota_do_audio = f"/api/comite-de-conduta/casos/{uuid.uuid4()}/depoimentos/{uuid.uuid4()}/audio"
        rota_da_transcricao = rota_do_audio.removesuffix("/audio") + "/transcricao"

        assert teto_da_rota(rota_do_audio) >= 250 * MB + MB
        assert teto_da_rota(rota_do_audio) >= depoimentos.LIMITE_DO_AUDIO + MB
        assert teto_da_rota(rota_da_transcricao) == LIMITE_CORPO_BYTES

    def test_o_middleware_usa_o_teto_da_rota(self):
        app = FastAPI()
        app.add_middleware(LimiteDeCorpoMiddleware, limite_bytes=1024)

        @app.post("/{caminho:path}")
        async def eco(request: Request):
            return {"bytes": len(await request.body())}

        cliente = TestClient(app)
        corpo = b"x" * 4096
        rota_do_audio = f"/api/comite-de-conduta/casos/{uuid.uuid4()}/depoimentos/{uuid.uuid4()}/audio"

        assert cliente.post(rota_do_audio, content=corpo).json() == {"bytes": 4096}
        assert cliente.post(rota_do_audio.removesuffix("/audio") + "/transcricao", content=corpo).status_code == 413

    def test_o_audio_fica_cifrado_no_bucket_e_toca_para_um_membro_do_caso(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso, pid=COORDENACAO)
        assert comite.anexar(COORDENACAO, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A).status_code == 200

        ((bucket, _), guardado), *_ = comite.banco.storage.objetos.items()
        assert bucket == "conduta-arquivos"
        assert b"som do depoimento" not in guardado and b"ftyp" not in guardado
        assert cifra.decifrar_arquivo(guardado) == AUDIO_M4A

        (versao,) = comite.cartao(MEMBRO, caso, dep)["arquivos"]["audio"]
        resposta = comite.baixar(MEMBRO, caso, dep, versao["paginas"][0]["id"])

        assert resposta.status_code == 200
        assert resposta.content == AUDIO_M4A
        assert resposta.headers["content-type"] == "audio/mp4"
        assert resposta.headers["cache-control"] == "no-store"
        assert "abriu_arquivo" in comite.trilha(caso)

    def test_quem_nao_abre_o_caso_nao_ouve(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A)
        (versao,) = comite.cartao(MEMBRO, caso, dep)["arquivos"]["audio"]

        resposta = comite.baixar(DE_FORA, caso, dep, versao["paginas"][0]["id"])

        assert resposta.status_code == 403
        assert AUDIO_M4A not in resposta.content

    def test_arquivo_de_outro_depoimento_nao_sai_pelo_depoimento_errado(self, comite):
        caso = comite.caso()
        dep, outro = comite.depoimento(caso), comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, outro, "audio", "gravacao.m4a", AUDIO_M4A)
        (versao,) = comite.cartao(MEMBRO, caso, outro)["arquivos"]["audio"]

        assert comite.baixar(MEMBRO, caso, dep, versao["paginas"][0]["id"]).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# O termo assinado sobe pela câmera do celular, e uma nova versão não apaga a
# anterior
# ═══════════════════════════════════════════════════════════════════════════


class TestTermoAssinado:
    def test_a_foto_da_camera_sobe_como_termo_assinado(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        resposta = comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)

        assert resposta.status_code == 200, resposta.text
        (versao,) = comite.cartao(MEMBRO, caso, dep)["arquivos"]["termo_assinado"]
        (pagina,) = versao["paginas"]
        assert pagina["content_type"] == "image/jpeg"
        assert comite.baixar(MEMBRO, caso, dep, pagina["id"]).content == FOTO_DO_TERMO

    def test_duas_fotos_viram_as_duas_paginas_da_mesma_versao(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        resposta = comite.cliente(MEMBRO).post(
            f"{BASE}/casos/{caso}/depoimentos/{dep}/termo-assinado",
            files=[
                ("arquivo", ("p1.jpg", FOTO_DO_TERMO, "image/jpeg")),
                ("arquivo", ("p2.heic", b"heic", "image/heic")),
            ],
        )

        assert resposta.status_code == 200, resposta.text
        (versao,) = comite.cartao(MEMBRO, caso, dep)["arquivos"]["termo_assinado"]
        assert [p["content_type"] for p in versao["paginas"]] == ["image/jpeg", "image/heic"]

    def test_a_versao_nova_nao_apaga_a_anterior(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)
        corrigido = FOTO_DO_TERMO + b" com a correcao do depoente"

        comite.anexar(COORDENACAO, caso, dep, "termo-assinado", "image.jpg", corrigido)

        versoes = comite.cartao(MEMBRO, caso, dep)["arquivos"]["termo_assinado"]
        assert [(v["versao"], v["enviado_por"]) for v in versoes] == [(2, NOMES[COORDENACAO]), (1, NOMES[MEMBRO])]
        conteudos = [comite.baixar(MEMBRO, caso, dep, v["paginas"][0]["id"]).content for v in versoes]
        assert conteudos == [corrigido, FOTO_DO_TERMO]
        assert len(comite.banco.storage.objetos) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Nenhum arquivo do depoimento é servido por URL assinada do bucket
# ═══════════════════════════════════════════════════════════════════════════


class TestSemUrlDoBucket:
    def test_nenhum_dos_tres_arquivos_sai_por_url_do_bucket(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, dep, "transcricao", "transcricao.txt", TRANSCRICAO)
        comite.anexar(MEMBRO, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A)
        comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)

        tela = comite.abrir(MEMBRO, caso)
        ids = [
            p["id"] for versoes in tela["depoimentos"][0]["arquivos"].values() for v in versoes for p in v["paginas"]
        ]
        conteudos = [comite.baixar(MEMBRO, caso, dep, i).content for i in ids]

        assert sorted(conteudos) == sorted([TRANSCRICAO, AUDIO_M4A, FOTO_DO_TERMO])
        assert comite.banco.storage.urls_assinadas == []
        assert "conduta-arquivos" not in str(tela) and "depoimentos/" not in str(tela)


# ═══════════════════════════════════════════════════════════════════════════
# "CONCLUIR DEPOIMENTO" fica bloqueado, com o motivo, até os sete itens
# estarem marcados
# ═══════════════════════════════════════════════════════════════════════════

ITENS_DA_LISTA = [
    "Transcrição anexada",
    "Áudio anexado",
    "Termo assinado anexado",
    "Abri os arquivos na aplicação e estão corretos",
    "Apaguei a gravação de áudio da plataforma de gravação",
    "Apaguei os arquivos do computador e do celular",
    "Guardei o original assinado no envelope do caso",
]
DECLARACOES = ("arquivos_corretos", "gravacao_apagada", "arquivos_apagados", "original_no_envelope")


def _marcar(comite: Comite, pid: str, caso: str, dep: str, item: str):
    return comite.cliente(pid).post(f"{BASE}/casos/{caso}/depoimentos/{dep}/conferencia", json={"item": item})


def _concluir(comite: Comite, pid: str, caso: str, dep: str):
    return comite.cliente(pid).post(f"{BASE}/casos/{caso}/depoimentos/{dep}/conclusao")


def _tres_arquivos(comite: Comite, caso: str, dep: str) -> None:
    comite.anexar(MEMBRO, caso, dep, "transcricao", "transcricao.txt", TRANSCRICAO)
    comite.anexar(MEMBRO, caso, dep, "audio", "gravacao.m4a", AUDIO_M4A)
    comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)


class TestConclusao:
    def test_a_lista_tem_os_sete_itens_da_especificacao_tres_automaticos(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        lista = comite.cartao(MEMBRO, caso, dep)["lista"]

        assert [i["rotulo"] for i in lista] == ITENS_DA_LISTA
        assert [i["automatico"] for i in lista] == [True, True, True, False, False, False, False]
        assert {i["estado"] for i in lista} == {"pendente"}

    def test_os_arquivos_marcam_os_tres_automaticos(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        _tres_arquivos(comite, caso, dep)

        lista = comite.cartao(MEMBRO, caso, dep)["lista"]
        assert [i["estado"] for i in lista] == ["feito"] * 3 + ["pendente"] * 4

    def test_sem_os_sete_concluir_fica_bloqueado_com_o_motivo(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        _tres_arquivos(comite, caso, dep)
        for item in DECLARACOES[:3]:
            assert _marcar(comite, MEMBRO, caso, dep, item).status_code == 200

        cartao = comite.cartao(MEMBRO, caso, dep)
        resposta = _concluir(comite, MEMBRO, caso, dep)

        motivo = "Falta marcar: Guardei o original assinado no envelope do caso."
        assert cartao["bloqueio_da_conclusao"] == motivo
        assert (resposta.status_code, resposta.json()["detail"]) == (409, motivo)
        assert comite.cartao(MEMBRO, caso, dep)["situacao"] != "Concluído"

    def test_com_os_sete_o_depoimento_conclui_e_nao_muda_mais(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        _tres_arquivos(comite, caso, dep)
        for item in DECLARACOES:
            _marcar(comite, MEMBRO, caso, dep, item)

        assert comite.cartao(MEMBRO, caso, dep)["bloqueio_da_conclusao"] is None
        assert _concluir(comite, MEMBRO, caso, dep).status_code == 200

        cartao = comite.cartao(MEMBRO, caso, dep)
        assert cartao["situacao"] == "Concluído"
        assert "concluiu_depoimento" in comite.trilha(caso)
        assert comite.anexar(MEMBRO, caso, dep, "audio", "outra.m4a", AUDIO_M4A).status_code == 409

    def test_sem_termo_assinado_o_cartao_diz_aguardando_assinatura(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, dep, "transcricao", "transcricao.txt", TRANSCRICAO)
        assert comite.cartao(MEMBRO, caso, dep)["situacao"] == "Aguardando assinatura"

        comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)
        assert comite.cartao(MEMBRO, caso, dep)["situacao"] == "Falta a lista de conferência"


# ═══════════════════════════════════════════════════════════════════════════
# Cada item marcado pelo membro registra quem marcou e quando
# ═══════════════════════════════════════════════════════════════════════════


class TestDeclaracoes:
    def test_o_item_marcado_guarda_quem_marcou_e_quando(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        antes = datetime.now().astimezone()

        assert _marcar(comite, COORDENACAO, caso, dep, "gravacao_apagada").status_code == 200

        item = next(i for i in comite.cartao(MEMBRO, caso, dep)["lista"] if i["item"] == "gravacao_apagada")
        assert (item["estado"], item["marcado_por"]) == ("feito", NOMES[COORDENACAO])
        assert datetime.fromisoformat(item["marcado_em"]) >= antes
        (linha,) = [x for x in comite.banco.tabelas["conduta_trilha"] if x["acao"] == "declarou_item_da_lista"]
        assert linha["autor_id"] == COORDENACAO
        assert "Apaguei a gravação" in linha["detalhe"]

    def test_a_declaracao_feita_nao_e_refeita_por_outro(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        _marcar(comite, COORDENACAO, caso, dep, "arquivos_corretos")

        segunda = _marcar(comite, MEMBRO, caso, dep, "arquivos_corretos")

        assert segunda.status_code == 409
        item = next(i for i in comite.cartao(MEMBRO, caso, dep)["lista"] if i["item"] == "arquivos_corretos")
        assert item["marcado_por"] == NOMES[COORDENACAO]

    def test_item_automatico_nao_se_marca_a_mao(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        assert _marcar(comite, MEMBRO, caso, dep, "audio").status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Sem gravação, os pontos digitados substituem a transcrição e os dois itens
# ficam "Não se aplica", com o motivo
# ═══════════════════════════════════════════════════════════════════════════

SEM_GRAVACAO = {"motivo": "A pessoa não aceitou ser gravada.", "pontos": "Confirmou que levantou a voz na reunião."}


def _sem_gravacao(comite: Comite, pid: str, caso: str, dep: str, corpo: dict | None = None):
    return comite.cliente(pid).post(
        f"{BASE}/casos/{caso}/depoimentos/{dep}/sem-gravacao", json=SEM_GRAVACAO if corpo is None else corpo
    )


class TestSemGravacao:
    def test_os_pontos_substituem_a_transcricao_e_os_dois_itens_nao_se_aplicam(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        assert _sem_gravacao(comite, MEMBRO, caso, dep).status_code == 200

        cartao = comite.cartao(MEMBRO, caso, dep)
        assert cartao["sem_gravacao"] == {**SEM_GRAVACAO, "registrado_por": NOMES[MEMBRO]}
        estados = {i["item"]: (i["estado"], i.get("motivo")) for i in cartao["lista"]}
        assert estados["transcricao"] == ("nao_se_aplica", SEM_GRAVACAO["motivo"])
        assert estados["audio"] == ("nao_se_aplica", SEM_GRAVACAO["motivo"])
        assert estados["termo_assinado"] == ("pendente", None)

    def test_sem_gravacao_conclui_com_o_termo_e_as_quatro_declaracoes(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        _sem_gravacao(comite, MEMBRO, caso, dep)
        comite.anexar(MEMBRO, caso, dep, "termo-assinado", "image.jpg", FOTO_DO_TERMO)
        for item in DECLARACOES:
            _marcar(comite, MEMBRO, caso, dep, item)

        assert _concluir(comite, MEMBRO, caso, dep).status_code == 200

    def test_os_pontos_e_o_motivo_ficam_cifrados(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        _sem_gravacao(comite, MEMBRO, caso, dep)

        (linha,) = comite.banco.tabelas["conduta_depoimentos"]
        assert SEM_GRAVACAO["pontos"] not in str(linha) and SEM_GRAVACAO["motivo"] not in str(linha)

    def test_sem_motivo_ou_sem_pontos_nao_vale(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)

        assert _sem_gravacao(comite, MEMBRO, caso, dep, {"motivo": "", "pontos": "algo"}).status_code == 422
        assert _sem_gravacao(comite, MEMBRO, caso, dep, {"motivo": "recusou", "pontos": " "}).status_code == 422

    def test_depoimento_gravado_nao_vira_sem_gravacao_e_vice_versa(self, comite):
        caso = comite.caso()
        gravado, sem = comite.depoimento(caso), comite.depoimento(caso)
        comite.anexar(MEMBRO, caso, gravado, "audio", "gravacao.m4a", AUDIO_M4A)
        _sem_gravacao(comite, MEMBRO, caso, sem)

        assert _sem_gravacao(comite, MEMBRO, caso, gravado).status_code == 409
        assert comite.anexar(MEMBRO, caso, sem, "audio", "gravacao.m4a", AUDIO_M4A).status_code == 409
        assert comite.anexar(MEMBRO, caso, sem, "transcricao", "t.txt", TRANSCRICAO).status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# A etapa Apuração não avança com depoimento em aberto (a trava do banco está
# em test_conduta_depoimentos_migration_banco.py)
# ═══════════════════════════════════════════════════════════════════════════


class TestApuracaoNaoAvanca:
    def test_com_depoimento_em_aberto_a_tela_diz_que_a_apuracao_nao_avanca(self, comite):
        caso = comite.caso()
        comite.depoimento(caso)

        tela = comite.abrir(MEMBRO, caso)

        assert tela["avanco_da_apuracao"] == "A Apuração só avança com todos os depoimentos concluídos. Falta 1."

    def test_com_todos_concluidos_a_trava_sai(self, comite):
        caso = comite.caso()
        dep = comite.depoimento(caso)
        _tres_arquivos(comite, caso, dep)
        for item in DECLARACOES:
            _marcar(comite, MEMBRO, caso, dep, item)
        _concluir(comite, MEMBRO, caso, dep)

        assert comite.abrir(MEMBRO, caso)["avanco_da_apuracao"] is None

    def test_a_regra_conta_os_que_faltam(self):
        abertos = [{"concluido_em": None}, {"concluido_em": "2026-11-20T10:00:00+00:00"}, {"concluido_em": None}]

        assert depoimentos.bloqueio_do_avanco(abertos) == (
            "A Apuração só avança com todos os depoimentos concluídos. Faltam 2."
        )
        assert depoimentos.bloqueio_do_avanco([]) is None
