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

from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import tecnologia_email  # noqa: E402
from app.services.assistente_tecnologia import LIMITE_DA_IMAGEM  # noqa: E402
from app.services.tecnologia_anexos import (  # noqa: E402
    MOTIVO_ANEXOS_DEMAIS,
    MOTIVO_ARQUIVO_VAZIO,
    MOTIVO_DEMANDA_ENCERRADA,
)
from test_tecnologia_vinculo import BASE, PEDRO, _demanda, _montar  # noqa: E402

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
