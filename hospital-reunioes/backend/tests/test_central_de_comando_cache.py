"""As regras do cache com frescor da Central de Comando, testadas direto (issue #815).

Porte de `src/lib/analytics/cache.test.ts` do repositório antigo, teste por
teste, com o relógio controlado: o teste diz que horas são, e o cache não tem
outro relógio. A fonte é uma função de mentira que conta as idas e devolve o
que o teste mandar, ou levanta.

O cache é regra pura: nenhum teste daqui toca rede, banco ou a instância do
processo (`cache_da_central`). Quem testa o cache pela rota real, com o Google
de mentira, é `test_central_de_comando_frescor.py`.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import RelogioDeTeste  # noqa: E402

from app.services.central_de_comando.cache import CacheComFrescor, Frescor  # noqa: E402


class Fonte:
    """A fonte de mentira: conta as idas e devolve `valor`, ou levanta `erro`."""

    def __init__(self, valor=42):
        self.valor = valor
        self.erro: Exception | None = None
        self.idas = 0

    def __call__(self):
        self.idas += 1
        if self.erro is not None:
            raise self.erro
        return self.valor


def _cache(relogio: RelogioDeTeste) -> CacheComFrescor:
    return CacheComFrescor(relogio=relogio)


class TestFrescor:
    """Porte de "MemoryCache: frescor"."""

    def test_busca_na_primeira_vez_e_serve_do_cache_dentro_da_hora(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(42)

        assert cache.ler("k", fonte).valor == 42
        relogio.avancar(minutes=59)
        assert cache.ler("k", fonte).valor == 42

        assert fonte.idas == 1

    def test_com_uma_hora_completa_volta_a_fonte(self):
        """A hora do cache é de 60 minutos cravados: com exatamente 1 hora, o
        número já é velho e a leitura vai buscar outro."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(1)

        cache.ler("k", fonte)
        relogio.avancar(hours=1)
        fonte.valor = 2

        assert cache.ler("k", fonte).valor == 2
        assert fonte.idas == 2

    def test_forcar_ignora_o_cache_e_vai_a_fonte_na_hora(self):
        """É o Atualizar agora: o número guardado ainda está dentro da hora, e
        mesmo assim a leitura forçada busca outro."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(7)

        cache.ler("k", fonte)
        fonte.valor = 8

        assert cache.ler("k", fonte, forcar=True).valor == 8
        assert fonte.idas == 2

    def test_o_numero_forcado_passa_a_ser_o_guardado(self):
        """Depois do Atualizar agora, a leitura comum serve o número novo, sem
        voltar à fonte."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(7)
        cache.ler("k", fonte)
        fonte.valor = 8
        cache.ler("k", fonte, forcar=True)

        assert cache.ler("k", fonte).valor == 8
        assert fonte.idas == 2


class TestUltimoValorBom:
    """Porte de "MemoryCache: degradação graciosa"."""

    def test_na_falha_da_fonte_devolve_o_ultimo_valor_bom(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(100)
        cache.ler("k", fonte)
        fonte.erro = RuntimeError("rede caiu")

        assert cache.ler("k", fonte, forcar=True).valor == 100

    def test_numero_velho_com_a_fonte_fora_continua_na_tela(self):
        """Passou da hora e a fonte caiu: o número de antes segue valendo, em
        vez de a tela zerar."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(100)
        cache.ler("k", fonte)
        relogio.avancar(hours=3)
        fonte.erro = RuntimeError("rede caiu")

        assert cache.ler("k", fonte).valor == 100
        assert fonte.idas == 2

    def test_sem_valor_guardado_o_erro_sobe(self):
        """Erro honesto: sem número bom para mostrar, não há o que inventar."""
        cache = _cache(RelogioDeTeste())
        fonte = Fonte()
        fonte.erro = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            cache.ler("k", fonte)

    def test_so_a_falha_da_fonte_vira_ultimo_valor_bom(self):
        """Quem lê diz o que é falha da fonte (`falhas`). Outro erro, como um
        defeito do próprio código ou a configuração que sumiu, sobe mesmo com
        número guardado: esconder atrás do último valor bom seria mentir que o
        problema é passageiro."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(100)
        cache.ler("k", fonte, falhas=(ConnectionError,))
        fonte.erro = KeyError("defeito")

        with pytest.raises(KeyError):
            cache.ler("k", fonte, forcar=True, falhas=(ConnectionError,))

        fonte.erro = ConnectionError("rede caiu")
        assert cache.ler("k", fonte, forcar=True, falhas=(ConnectionError,)).valor == 100

    def test_falha_que_volta_depois_de_outra_leitura_renovar_nao_apaga_o_numero_novo(self):
        """Duas leituras da mesma chave ao mesmo tempo (a rota lê em thread):
        enquanto uma espera a fonte, a outra renova o número. Se a primeira
        falhar depois, o número novo continua guardado, sem marca de falha, e
        é ele que ela devolve."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        cache.ler("k", Fonte(1))
        relogio.avancar(hours=2)

        def fonte_que_cai_enquanto_outra_leitura_renova():
            cache.ler("k", Fonte(2), forcar=True)
            raise RuntimeError("caiu")

        leitura = cache.ler("k", fonte_que_cai_enquanto_outra_leitura_renova)
        depois = cache.ler("k", Fonte(3))

        assert leitura.valor == 2
        assert leitura.frescor.atualizacao_falhou is False
        assert depois.valor == 2
        assert depois.frescor.atualizacao_falhou is False

    def test_sem_numero_guardado_a_falha_devolve_o_que_outra_leitura_trouxe(self):
        """A primeira leitura da chave falhou, mas outra, no meio dela, trouxe
        o número: há o que mostrar, então não é erro."""
        cache = _cache(RelogioDeTeste())

        def fonte_que_cai_enquanto_outra_leitura_busca():
            cache.ler("k", Fonte(5))
            raise RuntimeError("caiu")

        assert cache.ler("k", fonte_que_cai_enquanto_outra_leitura_busca).valor == 5


class TestRegistroDeFrescor:
    """Porte de "MemoryCache: registro de frescor": cada número sai do cache
    dizendo de quando é e se a última tentativa de renová-lo falhou."""

    def test_no_sucesso_registra_quando_foi_atualizado_e_que_nada_falhou(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 13, 45, tzinfo=UTC))
        cache = _cache(relogio)

        leitura = cache.ler("k", Fonte(1))

        assert leitura.frescor == Frescor(
            atualizado_em=datetime(2026, 9, 18, 13, 45, tzinfo=UTC), atualizacao_falhou=False, motivo=None
        )

    def test_servido_do_cache_diz_a_hora_da_busca_e_nao_a_da_leitura(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 13, 45, tzinfo=UTC))
        cache = _cache(relogio)
        cache.ler("k", Fonte(1))
        relogio.avancar(minutes=20)

        leitura = cache.ler("k", Fonte(1))

        assert leitura.frescor.atualizado_em == datetime(2026, 9, 18, 13, 45, tzinfo=UTC)

    def test_no_ultimo_valor_bom_marca_a_falha_e_mantem_a_hora_do_numero_bom(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))
        cache = _cache(relogio)
        fonte = Fonte(1)
        cache.ler("k", fonte)
        relogio.avancar(minutes=30)
        fonte.erro = RuntimeError("x")

        leitura = cache.ler("k", fonte, forcar=True)

        assert leitura.frescor.atualizado_em == datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
        assert leitura.frescor.atualizacao_falhou is True

    def test_a_falha_grava_o_motivo_ao_servir_o_ultimo_valor_bom(self):
        """Porte de "classifyError grava o reason": lá o motivo era um código
        ("token"); aqui é a frase da falha, que a tela mostra no aviso."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(1)
        cache.ler("k", fonte)
        relogio.avancar(hours=2)
        fonte.erro = RuntimeError("O Google Analytics respondeu HTTP 500.")

        leitura = cache.ler("k", fonte)

        assert leitura.valor == 1
        assert leitura.frescor.atualizacao_falhou is True
        assert leitura.frescor.motivo == "O Google Analytics respondeu HTTP 500."

    def test_a_falha_fica_registrada_ate_a_proxima_busca_dar_certo(self):
        """O Atualizar agora falhou com o número ainda dentro da hora: a leitura
        comum seguinte serve o mesmo número e continua avisando da falha. Só a
        próxima busca bem-sucedida apaga o aviso."""
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))
        cache = _cache(relogio)
        fonte = Fonte(1)
        cache.ler("k", fonte)
        fonte.erro = RuntimeError("fora")
        cache.ler("k", fonte, forcar=True)
        relogio.avancar(minutes=10)

        ainda_falhou = cache.ler("k", fonte)
        fonte.erro = None
        fonte.valor = 2
        relogio.avancar(minutes=5)
        voltou = cache.ler("k", fonte, forcar=True)

        assert ainda_falhou.frescor.atualizacao_falhou is True
        assert voltou.valor == 2
        assert voltou.frescor == Frescor(
            atualizado_em=datetime(2026, 9, 18, 10, 15, tzinfo=UTC), atualizacao_falhou=False, motivo=None
        )


class TestFrescorDeVariasChaves:
    """Porte de "freshness(keys)": o carimbo de uma tela que junta várias
    chaves é o do número mais velho, e a falha de qualquer uma é a da tela."""

    def test_junta_a_hora_mais_antiga_e_qualquer_falha(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))
        cache = _cache(relogio)
        fonte = Fonte(1)
        cache.ler("b", fonte)
        relogio.avancar(minutes=10)
        cache.ler("c", fonte)
        relogio.avancar(minutes=10)
        cache.ler("a", fonte)
        fonte.erro = RuntimeError("b caiu")
        cache.ler("b", fonte, forcar=True)

        frescor = cache.frescor("a", "b", "c")

        assert frescor.atualizado_em == datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
        assert frescor.atualizacao_falhou is True
        assert frescor.motivo == "b caiu"

    def test_chave_que_nunca_foi_lida_nao_conta(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))
        cache = _cache(relogio)
        cache.ler("a", Fonte(1))

        assert cache.frescor("a", "nunca") == Frescor(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))

    def test_sem_nenhuma_chave_lida_nao_ha_hora_nenhuma(self):
        cache = _cache(RelogioDeTeste())

        assert cache.frescor("x") == Frescor(atualizado_em=None, atualizacao_falhou=False, motivo=None)
