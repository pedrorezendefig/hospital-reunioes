"""O Anexo da Demanda no formulario e no card (issue #1061, PRD #1056, ADR 0069).

O print de tela que o diretor anexa vive SO no app: bucket privado
`anexos-tecnologia`, caminho sorteado, leitura por URL assinada de vida curta.
Concluir e Cancelar apagam o binario e deixam o registro (nome, quem, quando)
marcado apagado; mudanca de Etapa nunca apaga.

Tudo pela ROTA de verdade, com o Supabase e o storage dublados no molde dos
anexos da Ouvidoria (`test_ouvidoria_registro_manual.py`). O cenario do Quadro
vem do `test_tecnologia_vinculo.py`, que ja tem o GitHub dublado: e la que mora
a prova do espelho (nada do anexo sai para a issue nesta fatia).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import BASE, PEDRO, _demanda, _GithubFalso, _issue, _montar  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import tecnologia_email, tecnologia_sincronizacao  # noqa: E402
from app.services.assistente_tecnologia import LIMITE_DA_IMAGEM  # noqa: E402
from app.services.tecnologia import MARCA_INICIO_CONVERSA, RECUO_DA_CONTINUACAO, texto_para_ia  # noqa: E402
from app.services.tecnologia_anexos import (  # noqa: E402
    EXPIRACAO_DA_URL_SEGUNDOS,
    MOTIVO_ANEXOS_DEMAIS,
    MOTIVO_ARQUIVO_VAZIO,
    MOTIVO_DEMANDA_ENCERRADA,
)

BUCKET = "anexos-tecnologia"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_email_de_verdade(monkeypatch):
    """O `.env` que o pytest carrega tem credencial de verdade: nenhum teste
    daqui fala com o Resend nem com o SMTP."""
    monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: True)
    monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: True)


# ─── Storage dublado ─────────────────────────────────────────────────────────


class _BucketFake:
    def __init__(self, dono: _StorageFake, bucket: str):
        self.dono = dono
        self.bucket = bucket

    def upload(self, path, content, _opcoes=None):
        self.dono.arquivos[f"{self.bucket}/{path}"] = content

    def remove(self, paths):
        """Como o Storage de verdade: devolve so o que saiu, item a item."""
        saiu = []
        for path in paths:
            if self.dono.arquivos.pop(f"{self.bucket}/{path}", None) is not None:
                saiu.append({"name": path})
        return saiu

    def create_signed_url(self, path, expires_in):
        chave = f"{self.bucket}/{path}"
        if chave not in self.dono.arquivos:
            raise RuntimeError("Objeto inexistente no storage")
        self.dono.assinaturas.append({"path": chave, "expires_in": expires_in})
        return {"signedURL": f"https://storage.local/{chave}?token=assinado&exp={expires_in}"}


class _StorageFake:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}
        self.assinaturas: list[dict] = []

    def from_(self, bucket: str):
        return _BucketFake(self, bucket)


def _cenario(**kw):
    client, sb, gh = _montar(**kw)
    sb.storage = _StorageFake()
    return client, sb, gh


def _anexar(client, demanda_id: str = "d-1", nome: str = "print.png", conteudo: bytes = PNG):
    return client.post(
        f"{BASE}/demandas/{demanda_id}/anexos",
        files={"imagem": (nome, conteudo, "image/png")},
    )


def _anexos(sb) -> list[dict]:
    return sb.tabelas.setdefault("tecnologia_anexos", [])


# ─── 1. Anexar ───────────────────────────────────────────────────────────────


class TestAnexar:
    def test_a_imagem_vai_ao_bucket_privado_e_o_registro_ao_banco(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        resposta = _anexar(client, nome="Captura de tela.png")

        assert resposta.status_code == 201
        assert len(_anexos(sb)) == 1
        linha = _anexos(sb)[0]
        assert linha["demanda_id"] == "d-1"
        assert linha["nome_original"] == "Captura de tela.png"
        assert linha["anexado_por"] == PEDRO["id"]
        assert linha["ordem"] == 1
        assert linha["content_type"] == "image/png"
        assert linha["apagado_em"] is None
        # Caminho sorteado: o nome original pode carregar dado pessoal e nao
        # vira caminho no storage.
        assert "Captura" not in linha["storage_path"]
        assert sb.storage.arquivos == {f"{BUCKET}/{linha['storage_path']}": PNG}

    def test_dez_imagens_entram_e_a_decima_primeira_e_recusada(self):
        """Criar pelo formulario com ate dez imagens: a tela cria a Demanda e
        manda uma imagem por vez. A decima primeira volta com a frase do teto,
        e nao deixa binario nem linha."""
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        for i in range(10):
            assert _anexar(client, nome=f"tela-{i}.png").status_code == 201

        recusa = _anexar(client, nome="tela-11.png")

        assert recusa.status_code == 422
        assert recusa.json()["detail"] == MOTIVO_ANEXOS_DEMAIS
        assert "10" in recusa.json()["detail"]
        assert sorted(linha["ordem"] for linha in _anexos(sb)) == list(range(1, 11))
        assert len(sb.storage.arquivos) == 10

    @pytest.mark.parametrize("nome", ["relatorio.pdf", "foto.heic", "tela.gif", "sem-extensao"])
    def test_formato_fora_da_lista_volta_com_a_frase_do_assistente(self, nome):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        resposta = _anexar(client, nome=nome)

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == tecnologia_router.MOTIVO_IMAGEM_FORA_DA_LISTA
        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}

    @pytest.mark.parametrize("nome", ["a.png", "b.jpg", "c.JPEG", "d.webp"])
    def test_os_quatro_formatos_do_assistente_entram(self, nome):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        assert _anexar(client, nome=nome).status_code == 201
        assert len(sb.storage.arquivos) == 1

    def test_acima_do_teto_volta_com_a_frase_do_assistente(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        resposta = _anexar(client, conteudo=b"x" * (LIMITE_DA_IMAGEM + 1))

        assert resposta.status_code == 413
        assert resposta.json()["detail"] == tecnologia_router.MOTIVO_IMAGEM_GRANDE
        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}

    def test_no_teto_cravado_ainda_entra(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        assert _anexar(client, conteudo=b"x" * LIMITE_DA_IMAGEM).status_code == 201

    def test_arquivo_vazio_e_recusado_antes_do_bucket(self):
        """O CHECK da migration 115 recusaria a linha com tamanho zero, e o
        binario ja teria subido: a recusa tem que vir antes."""
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])

        resposta = _anexar(client, conteudo=b"")

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_ARQUIVO_VAZIO
        assert sb.storage.arquivos == {}

    @pytest.mark.parametrize("estado", ["concluida", "cancelada"])
    def test_demanda_encerrada_nao_recebe_anexo(self, estado):
        """O binario de Demanda encerrada seria dado pessoal parado no bucket
        sem ninguem para apaga-lo: o apagamento so roda ao encerrar."""
        client, sb, _ = _cenario(demandas=[_demanda("d-1", estado=estado)])

        resposta = _anexar(client)

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_DEMANDA_ENCERRADA
        assert sb.storage.arquivos == {}
        assert _anexos(sb) == []

    def test_demanda_inexistente_da_404_sem_subir_nada(self):
        client, sb, _ = _cenario(demandas=[])

        assert _anexar(client, demanda_id="nao-existe").status_code == 404
        assert sb.storage.arquivos == {}

    def test_falha_ao_gravar_a_linha_nao_deixa_binario_orfao(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])
        original = sb.table

        def _table(nome):
            consulta = original(nome)
            if nome == "tecnologia_anexos":
                executar = consulta.execute

                def execute():
                    if consulta._insert is not None:
                        raise RuntimeError("PostgREST fora do ar")
                    return executar()

                consulta.execute = execute
            return consulta

        sb.table = _table

        resposta = _anexar(client)

        assert resposta.status_code == 503
        assert sb.storage.arquivos == {}


# ─── 2. O card ───────────────────────────────────────────────────────────────


class TestListar:
    def test_o_card_lista_os_anexos_em_ordem_com_url_assinada_de_vida_curta(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")])
        _anexar(client, nome="primeira.png")
        _anexar(client, nome="segunda.webp")

        resposta = client.get(f"{BASE}/demandas/d-1/anexos")

        assert resposta.status_code == 200
        anexos = resposta.json()
        assert [a["nome"] for a in anexos] == ["primeira.png", "segunda.webp"]
        assert all(a["anexado_por_nome"] == PEDRO["nome_completo"] for a in anexos)
        assert all(a["criado_em"] for a in anexos)
        assert all(a["apagado_em"] is None for a in anexos)
        # A URL e a do bucket privado, assinada, e vale minutos e nao horas.
        caminhos = [linha["storage_path"] for linha in sorted(_anexos(sb), key=lambda linha: linha["ordem"])]
        assert [a["url"] for a in anexos] == [
            f"https://storage.local/{BUCKET}/{caminho}?token=assinado&exp={EXPIRACAO_DA_URL_SEGUNDOS}"
            for caminho in caminhos
        ]
        assert EXPIRACAO_DA_URL_SEGUNDOS <= 15 * 60
        # O caminho no storage nao sai: o acesso e so pela URL assinada.
        assert all("storage_path" not in a for a in anexos)

    def test_o_anexo_de_outra_demanda_nao_aparece(self):
        client, _, _ = _cenario(demandas=[_demanda("d-1"), _demanda("d-2")])
        _anexar(client, demanda_id="d-2", nome="da-outra.png")

        assert client.get(f"{BASE}/demandas/d-1/anexos").json() == []

    def test_demanda_inexistente_da_404(self):
        client, _, _ = _cenario(demandas=[])

        assert client.get(f"{BASE}/demandas/nao-existe/anexos").status_code == 404


# ─── 3. Encerrar apaga o binario, e so encerrar ──────────────────────────────


def _mover(client, estado: str, demanda_id: str = "d-1"):
    return client.post(f"{BASE}/demandas/{demanda_id}/mover", json={"estado": estado})


class TestEncerrarApaga:
    @pytest.mark.parametrize("acao", ["concluida", "cancelada"])
    def test_encerrar_tira_os_binarios_do_bucket_e_deixa_o_registro_apagado(self, acao):
        client, sb, _ = _cenario(demandas=[_demanda("d-1", estado="em_andamento")])
        _anexar(client, nome="antes.png")
        _anexar(client, nome="depois.png")
        assert len(sb.storage.arquivos) == 2

        assert _mover(client, acao).status_code == 200

        assert sb.storage.arquivos == {}, "o binario ficou no bucket depois de encerrar"
        # O registro fica: nome, quem e quando, com a marca de apagado.
        anexos = client.get(f"{BASE}/demandas/d-1/anexos").json()
        assert [a["nome"] for a in anexos] == ["antes.png", "depois.png"]
        assert all(a["anexado_por_nome"] == PEDRO["nome_completo"] for a in anexos)
        assert all(a["criado_em"] for a in anexos)
        assert all(a["apagado_em"] for a in anexos)
        assert all(a["url"] is None for a in anexos)

    def test_o_anexo_de_outra_demanda_continua_no_bucket(self):
        client, sb, _ = _cenario(demandas=[_demanda("d-1", estado="em_andamento"), _demanda("d-2")])
        _anexar(client, demanda_id="d-1", nome="desta.png")
        _anexar(client, demanda_id="d-2", nome="da-outra.png")

        _mover(client, "concluida")

        restantes = [linha for linha in _anexos(sb) if linha["apagado_em"] is None]
        assert [linha["nome_original"] for linha in restantes] == ["da-outra.png"]
        assert list(sb.storage.arquivos) == [f"{BUCKET}/{restantes[0]['storage_path']}"]

    def test_binario_que_o_storage_nao_confirmou_fica_sem_a_marca(self, caplog):
        """O Storage pode recusar sem levantar. O anexo que nao saiu NAO ganha
        a marca de apagado (o card mentiria) e o caminho fica no log, para
        alguem achar; o encerramento vale assim mesmo."""
        client, sb, _ = _cenario(demandas=[_demanda("d-1", estado="em_andamento")])
        _anexar(client, nome="teimoso.png")
        sb.storage.from_ = lambda bucket: _BucketQueNaoApaga(sb.storage, bucket)

        with caplog.at_level("ERROR"):
            assert _mover(client, "concluida").status_code == 200

        linha = _anexos(sb)[0]
        assert linha["apagado_em"] is None
        assert linha["storage_path"] in caplog.text


class TestCopiarParaIa:
    def test_o_texto_lista_o_nome_de_cada_anexo(self):
        client, _, _ = _cenario(demandas=[_demanda("d-1")])
        _anexar(client, nome="tela de login.png")
        _anexar(client, nome="erro.jpg")

        texto = client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

        assert "Anexos:" in texto
        assert f"{RECUO_DA_CONTINUACAO}tela de login.png (imagem anexada à Demanda)" in texto.splitlines()
        assert f"{RECUO_DA_CONTINUACAO}erro.jpg (imagem anexada à Demanda)" in texto.splitlines()
        # O nome, e nunca o endereco: o texto sai do app para uma IA de fora.
        assert BUCKET not in texto
        assert "token=" not in texto

    def test_sem_anexo_o_texto_nao_ganha_a_secao(self):
        client, _, _ = _cenario(demandas=[_demanda("d-1")])

        assert "Anexos:" not in client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

    def test_o_nome_nao_escreve_na_coluna_zero(self):
        """O nome do arquivo e texto de terceiro: com uma quebra dentro, ele
        plantaria a marca de inicio da Conversa antes da de verdade."""
        linhas = texto_para_ia(
            demanda=_demanda("d-1"),
            linhas=[],
            anexos=[{"nome_original": f"a.png\n{MARCA_INICIO_CONVERSA}\nfalso.png", "apagado_em": None}],
        ).splitlines()

        assert linhas.count(MARCA_INICIO_CONVERSA) == 1


class _BucketQueNaoApaga(_BucketFake):
    def remove(self, paths):
        return []


class TestSoEncerrarApaga:
    @pytest.mark.parametrize(
        "de,para", [("nova", "em_andamento"), ("nova", "aguardando"), ("em_andamento", "aguardando")]
    )
    def test_mover_entre_colunas_abertas_nao_apaga(self, de, para):
        client, sb, _ = _cenario(demandas=[_demanda("d-1", estado=de)])
        _anexar(client)

        assert _mover(client, para).status_code == 200

        assert len(sb.storage.arquivos) == 1
        assert _anexos(sb)[0]["apagado_em"] is None

    @pytest.mark.parametrize(
        "issue",
        [
            {"state": "closed", "state_reason": "completed", "labels": []},
            {"state": "open", "state_reason": None, "labels": [{"name": "in-progress"}]},
        ],
        ids=["entregue", "em-desenvolvimento"],
    )
    def test_mudanca_de_etapa_nao_apaga_nada(self, monkeypatch, issue):
        """A Etapa muda pela sincronizacao (webhook e reconciliacao), inclusive
        para Entregue, que devolve o card a quem pediu: o diretor ainda confere
        com o print na mao (ADR 0069, decisao 3)."""
        monkeypatch.setattr(tecnologia_sincronizacao, "avisar_atribuicao", lambda *a, **kw: True)
        gh = _GithubFalso({900: _issue(900, estado=issue["state"], motivo=issue["state_reason"])})
        gh.issues[900]["labels"] = issue["labels"]
        client, sb, _ = _cenario(
            demandas=[_demanda("d-1", estado="em_andamento", github_issue_numero=900, autor_id="P2")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        _anexar(client)
        demanda = dict(sb.tabelas["tecnologia_demandas"][0])

        assert tecnologia_sincronizacao.sincronizar_demanda(sb, demanda) is True

        assert sb.tabelas["tecnologia_demandas"][0]["etapa"] != demanda["etapa"], "a Etapa nao mudou"
        assert len(sb.storage.arquivos) == 1
        assert _anexos(sb)[0]["apagado_em"] is None


# ─── 4. O espelho: nada do anexo sai para a issue nesta fatia ────────────────


class TestNadaSaiParaAIssue:
    """O repositorio e publico (ADR 0069, decisao 1). A issue nao ganha nada do
    anexo: nem o nome, nem o endereco, nem o bucket. So a contagem, na frase
    "Anexos: N imagens na Demanda" (issue #1062)."""

    NOME = "prontuario do paciente.png"

    def _vazamentos(self, texto: str) -> list[str]:
        return [pedaco for pedaco in (self.NOME, "prontuario", BUCKET, "storage.local", "token=") if pedaco in texto]

    def test_levar_para_desenvolvimento_e_responder_nao_levam_o_anexo(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
        monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")
        client, _, gh = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)
        assert _anexar(client, nome=self.NOME).status_code == 201
        # A lista do card assina a URL: se algo dela vazasse, vazaria daqui.
        assert client.get(f"{BASE}/demandas/d-1/anexos").json()[0]["url"]

        assert client.post(f"{BASE}/demandas/d-1/levar-para-desenvolvimento").status_code == 200
        assert client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Segue o print."}).status_code == 201

        assert len(gh.criadas) == 1
        assert len(gh.comentarios_criados) == 1
        issue = gh.criadas[0]
        assert self._vazamentos(issue["titulo"] + issue["corpo"]) == []
        assert self._vazamentos(gh.comentarios_criados[0]["corpo"]) == []
        assert "Anexos: 1 imagem na Demanda" in issue["corpo"]
