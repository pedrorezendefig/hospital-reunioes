"""Remoção de arquivo no Supabase Storage (issue #397, item 1 da review do #394).

O Storage relata o resultado arquivo a arquivo no corpo da resposta: uma
remoção pode falhar sem levantar exceção nenhuma. Quem chama `delete_file`
apaga em seguida o ponteiro para o binário (a linha do anexo, do material do
POP), e um `True` de mentira transforma essa falha silenciosa em arquivo órfão
no bucket, sem ponteiro para ninguém achar depois.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import storage  # noqa: E402

BUCKET = "anexos-ouvidoria"
CAMINHO = "2020/anexo-1.jpg"


class _StorageFake:
    """O cliente do Storage devolvendo o corpo que o serviço real devolve:
    uma lista com uma entrada por arquivo."""

    def __init__(self, corpo=None, excecao: Exception | None = None):
        self.corpo = corpo
        self.excecao = excecao
        self.chamadas: list[tuple[str, list[str]]] = []
        self._bucket = ""

    def from_(self, bucket: str):
        self._bucket = bucket
        return self

    def remove(self, paths: list[str]):
        self.chamadas.append((self._bucket, list(paths)))
        if self.excecao is not None:
            raise self.excecao
        return self.corpo


class _SupabaseFake:
    def __init__(self, storage_fake: _StorageFake):
        self.storage = storage_fake


def _delete(corpo=None, excecao: Exception | None = None) -> bool:
    return storage.delete_file(_SupabaseFake(_StorageFake(corpo, excecao)), BUCKET, CAMINHO)


class TestDeleteFile:
    def test_arquivo_relatado_como_removido_conta_como_sucesso(self):
        assert _delete(corpo=[{"name": CAMINHO, "id": "abc", "bucket_id": BUCKET}]) is True

    def test_corpo_vazio_nao_conta_como_removido(self):
        """O caminho do bug: o Storage aceitou a chamada e não removeu nada.
        Sem o arquivo no corpo, ninguém pode afirmar que ele saiu do bucket."""
        assert _delete(corpo=[]) is False

    def test_erro_relatado_no_corpo_nao_conta_como_removido(self):
        """A falha arquivo a arquivo, que não levanta exceção nenhuma."""
        assert _delete(corpo=[{"name": CAMINHO, "error": "Object not found"}]) is False

    def test_erro_junto_de_um_sucesso_derruba_a_remocao_inteira(self):
        """Uma entrada boa não compra a outra: se qualquer arquivo da chamada
        ficou para trás, a resposta é não."""
        assert _delete(corpo=[{"name": CAMINHO}, {"name": "outro.jpg", "error": "Object not found"}]) is False

    def test_formato_inesperado_nao_conta_como_removido(self):
        """A biblioteca já mudou a forma da resposta entre versões (o mesmo
        cuidado do `signed_url`). Forma que não dá para ler vira recusa, não
        vira sucesso otimista."""
        assert _delete(corpo={"data": []}) is False

    def test_item_ilegivel_dentro_da_lista_nao_conta_como_removido(self):
        """A lista veio, mas o que tem dentro não dá para ler. Sem conseguir
        procurar o `error` do item, ninguém pode afirmar que o arquivo saiu."""
        assert _delete(corpo=[42]) is False

    def test_excecao_continua_sendo_falha(self):
        assert _delete(excecao=RuntimeError("bucket fora do ar")) is False

    def test_o_caminho_pedido_e_o_caminho_removido(self):
        storage_fake = _StorageFake(corpo=[{"name": CAMINHO}])

        storage.delete_file(_SupabaseFake(storage_fake), BUCKET, CAMINHO)

        assert storage_fake.chamadas == [(BUCKET, [CAMINHO])]
