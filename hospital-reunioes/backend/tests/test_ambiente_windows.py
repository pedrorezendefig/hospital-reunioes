"""A suíte e os scripts do repo rodam numa máquina Windows (issue #844).

Toda onda rodada no Windows pagou o mesmo pedágio: falhas que só existem lá
(módulo `resource`, `pgrep`, `SIGKILL`, `sendmsg`, `read_text()` caindo em
cp1252) e scripts que só andavam com `PYTHONUTF8=1`. Cada agente redescobria e
escrevia o próprio contorno fora do repo.

O CI é Linux, então estes testes não rodam no Windows de verdade: eles provam
as regras que fazem o Windows funcionar, e que o Linux não perde nada com elas.
"""

from __future__ import annotations

import pytest

import conftest


class _ItemDeMentira:
    """O mínimo de um `pytest.Item` que a regra do `so_unix` consulta."""

    def __init__(self, *marcas: pytest.MarkDecorator) -> None:
        self._marcas = [m.mark for m in marcas]
        self.acrescentadas: list[pytest.Mark] = []

    def get_closest_marker(self, nome: str):
        return next((m for m in self._marcas if m.name == nome), None)

    def add_marker(self, marca: pytest.MarkDecorator) -> None:
        self.acrescentadas.append(marca.mark)


class TestSoUnix:
    def test_no_windows_o_teste_marcado_vira_skip_com_o_motivo(self):
        item = _ItemDeMentira(pytest.mark.so_unix("mede RSS pelo ps"))

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="win32")

        assert [m.name for m in item.acrescentadas] == ["skip"]
        assert "mede RSS pelo ps" in item.acrescentadas[0].kwargs["reason"]

    def test_no_linux_o_teste_marcado_continua_rodando(self):
        """O CI é Linux: a marca não pode tirar teste nenhum de lá."""
        item = _ItemDeMentira(pytest.mark.so_unix("mede RSS pelo ps"))

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="linux")

        assert item.acrescentadas == []

    def test_no_windows_o_teste_sem_marca_continua_rodando(self):
        item = _ItemDeMentira()

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="win32")

        assert item.acrescentadas == []
