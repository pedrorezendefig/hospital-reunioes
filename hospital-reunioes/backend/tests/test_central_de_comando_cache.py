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
import threading
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import RelogioDeTeste  # noqa: E402

from app.services.central_de_comando.cache import CacheComFrescor, Frescor  # noqa: E402


class FonteForaError(Exception):
    """A falha da fonte de mentira, com frase fixa, como a `GoogleError`."""


# O que os testes declaram como falha da fonte: sem declarar, nada vira último
# valor bom (`test_quem_nao_declara_falhas_nao_ganha_ultimo_valor_bom`).
FALHAS = (FonteForaError,)


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
        fonte.erro = FonteForaError("rede caiu")

        assert cache.ler("k", fonte, forcar=True, falhas=FALHAS).valor == 100

    def test_numero_velho_com_a_fonte_fora_continua_na_tela(self):
        """Passou da hora e a fonte caiu: o número de antes segue valendo, em
        vez de a tela zerar."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(100)
        cache.ler("k", fonte)
        relogio.avancar(hours=3)
        fonte.erro = FonteForaError("rede caiu")

        assert cache.ler("k", fonte, falhas=FALHAS).valor == 100
        assert fonte.idas == 2

    def test_sem_valor_guardado_o_erro_sobe(self):
        """Erro honesto: sem número bom para mostrar, não há o que inventar."""
        cache = _cache(RelogioDeTeste())
        fonte = Fonte()
        fonte.erro = FonteForaError("boom")

        with pytest.raises(FonteForaError, match="boom"):
            cache.ler("k", fonte, falhas=FALHAS)

    def test_quem_nao_declara_falhas_nao_ganha_ultimo_valor_bom(self):
        """Sem `falhas`, nenhuma exceção vira último valor bom. A frase dela iria
        para a tela num 200 e ficaria guardada no cache: o texto cru de um erro
        de HTTP traz a URL inteira, e a de uma API com token na query traria o
        token. Quem quer o último valor bom declara a exceção da fonte, que tem
        frase fixa. A falha não declarada também não marca o registro."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(100)
        cache.ler("k", fonte)
        fonte.erro = FonteForaError("https://api.exemplo/?access_token=SEGREDO")

        with pytest.raises(FonteForaError):
            cache.ler("k", fonte, forcar=True)

        assert cache.frescor("k").atualizacao_falhou is False
        assert cache.frescor("k").motivo is None

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
            raise FonteForaError("caiu")

        leitura = cache.ler("k", fonte_que_cai_enquanto_outra_leitura_renova, falhas=FALHAS)
        depois = cache.ler("k", Fonte(3))

        assert leitura.valor == 2
        assert leitura.frescor.atualizacao_falhou is False
        assert depois.valor == 2
        assert depois.frescor.atualizacao_falhou is False

    def test_sem_numero_guardado_a_falha_devolve_o_que_outra_leitura_trouxe(self):
        """A primeira leitura da chave falhou, mas outra, no meio dela, trouxe
        o número: há o que mostrar, então não é erro. A do meio é um Atualizar
        agora: uma leitura comum esperaria a ida que já está no ar (#858)."""
        cache = _cache(RelogioDeTeste())

        def fonte_que_cai_enquanto_outra_leitura_busca():
            cache.ler("k", Fonte(5), forcar=True)
            raise FonteForaError("caiu")

        assert cache.ler("k", fonte_que_cai_enquanto_outra_leitura_busca, falhas=FALHAS).valor == 5


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
        fonte.erro = FonteForaError("x")

        leitura = cache.ler("k", fonte, forcar=True, falhas=FALHAS)

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
        fonte.erro = FonteForaError("O Google Analytics respondeu HTTP 500.")

        leitura = cache.ler("k", fonte, falhas=FALHAS)

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
        fonte.erro = FonteForaError("fora")
        cache.ler("k", fonte, forcar=True, falhas=FALHAS)
        relogio.avancar(minutes=10)

        ainda_falhou = cache.ler("k", fonte)
        fonte.erro = None
        fonte.valor = 2
        relogio.avancar(minutes=5)
        voltou = cache.ler("k", fonte, forcar=True, falhas=FALHAS)

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
        fonte.erro = FonteForaError("b caiu")
        cache.ler("b", fonte, forcar=True, falhas=FALHAS)

        frescor = cache.frescor("a", "b", "c")

        assert frescor.atualizado_em == datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
        assert frescor.atualizacao_falhou is True
        assert frescor.motivo == "b caiu"

    def test_chave_que_nunca_foi_lida_nao_conta(self):
        relogio = RelogioDeTeste(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))
        cache = _cache(relogio)
        cache.ler("a", Fonte(1))

        assert cache.frescor("a", "nunca") == Frescor(datetime(2026, 9, 18, 10, 0, tzinfo=UTC))

    def test_chaves_lidas_sem_hora_registrada_dao_sem_hora_e_nao_erro(self):
        """O contrato do `Frescor` admite hora nula. Se todas as chaves lidas
        estiverem assim, o frescor da tela é "sem hora", e não um `ValueError`
        do `min` de uma lista vazia. Um relógio que não diz hora é o único
        jeito de chegar lá pela porta pública."""
        cache = CacheComFrescor(relogio=lambda: None)
        cache.ler("a", Fonte(1))
        cache.ler("b", Fonte(2))

        assert cache.frescor("a", "b") == Frescor(atualizado_em=None, atualizacao_falhou=False, motivo=None)

    def test_sem_nenhuma_chave_lida_nao_ha_hora_nenhuma(self):
        cache = _cache(RelogioDeTeste())

        assert cache.frescor("x") == Frescor(atualizado_em=None, atualizacao_falhou=False, motivo=None)


class RelogioQueConta(RelogioDeTeste):
    """O relógio do teste que conta quantas vezes o cache olhou a hora, para o
    teste saber que uma leitura já passou pela conferência da hora."""

    def __init__(self):
        super().__init__()
        self.chamadas = 0
        self._mudou = threading.Condition()

    def __call__(self):
        with self._mudou:
            self.chamadas += 1
            self._mudou.notify_all()
        return super().__call__()

    def esperar_chamadas(self, quantas: int) -> bool:
        with self._mudou:
            return self._mudou.wait_for(lambda: self.chamadas >= quantas, timeout=5)


class TestUmaIdaPorChave:
    """Leituras que chegam juntas numa chave vencida esperam a ida que já está
    no ar (issue #858): N abas abertas na mesma tela fazem 1 ida, não N. A rota
    lê em thread, então o teste usa threads de verdade. O único tempo real é a
    folga para as leituras de trás chegarem enquanto a fonte segura a primeira:
    a hora do cache continua no relógio do teste."""

    def test_leituras_ao_mesmo_tempo_da_chave_vencida_fazem_uma_ida_so(self):
        relogio = RelogioQueConta()
        cache = _cache(relogio)
        cache.ler("k", Fonte(1))
        relogio.avancar(hours=1)

        no_ar = threading.Event()
        liberar = threading.Event()
        idas = []

        def fonte_lenta():
            idas.append(1)
            no_ar.set()
            liberar.wait(5)
            return 2

        valores = []

        def ler():
            valores.append(cache.ler("k", fonte_lenta).valor)

        primeira = threading.Thread(target=ler)
        primeira.start()
        assert no_ar.wait(5)
        olharam = relogio.chamadas
        de_tras = [threading.Thread(target=ler) for _ in range(2)]
        for t in de_tras:
            t.start()
        # As duas de trás já viram que o número passou da hora com a ida no ar:
        # daqui em diante, ou esperam a ida, ou vão à fonte. Sem tempo real.
        assert relogio.esperar_chamadas(olharam + 2)
        liberar.set()
        for t in [primeira, *de_tras]:
            t.join(5)

        assert len(idas) == 1
        assert valores == [2, 2, 2]

    def test_a_ida_de_uma_chave_nao_segura_a_leitura_de_outra(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        no_ar = threading.Event()
        liberar = threading.Event()

        def fonte_lenta():
            no_ar.set()
            liberar.wait(5)
            return 1

        lenta = threading.Thread(target=lambda: cache.ler("lenta", fonte_lenta))
        lenta.start()
        assert no_ar.wait(5)
        outra = threading.Thread(target=lambda: cache.ler("outra", Fonte(9)))
        outra.start()
        outra.join(2)
        segurada = outra.is_alive()
        liberar.set()
        lenta.join(5)

        assert segurada is False


class TestEsperaDepoisDeFalha:
    """Depois de uma falha da fonte, a leitura comum não volta a ela por 5
    minutos (issue #858): com o Google fora, toda leitura de uma chave vencida
    ia bater nele de novo. O Atualizar agora ignora a espera."""

    def _com_falha(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte(10)
        cache.ler("k", fonte, falhas=FALHAS)
        relogio.avancar(hours=1)
        fonte.erro = FonteForaError("fora")
        cache.ler("k", fonte, falhas=FALHAS)
        return relogio, cache, fonte

    def test_dentro_da_espera_a_leitura_serve_o_ultimo_valor_bom_sem_ir_a_fonte(self):
        relogio, cache, fonte = self._com_falha()
        relogio.avancar(minutes=4, seconds=59)

        leitura = cache.ler("k", fonte, falhas=FALHAS)

        assert fonte.idas == 2
        assert leitura.valor == 10
        assert leitura.frescor.atualizacao_falhou is True
        assert leitura.frescor.motivo == "fora"

    def test_passada_a_espera_a_leitura_tenta_de_novo(self):
        relogio, cache, fonte = self._com_falha()
        relogio.avancar(minutes=5)
        fonte.erro = None
        fonte.valor = 11

        leitura = cache.ler("k", fonte, falhas=FALHAS)

        assert fonte.idas == 3
        assert leitura.valor == 11
        assert leitura.frescor.atualizacao_falhou is False

    def test_o_atualizar_agora_ignora_a_espera(self):
        relogio, cache, fonte = self._com_falha()
        relogio.avancar(minutes=1)
        fonte.erro = None
        fonte.valor = 12

        assert cache.ler("k", fonte, forcar=True, falhas=FALHAS).valor == 12
        assert fonte.idas == 3

    def test_sem_numero_guardado_a_falha_se_repete_sem_ir_a_fonte(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte()
        fonte.erro = FonteForaError("fora")
        with pytest.raises(FonteForaError):
            cache.ler("k", fonte, falhas=FALHAS)
        relogio.avancar(minutes=4)

        with pytest.raises(FonteForaError, match="fora"):
            cache.ler("k", fonte, falhas=FALHAS)
        assert fonte.idas == 1

        relogio.avancar(minutes=1)
        fonte.erro = None
        assert cache.ler("k", fonte, falhas=FALHAS).valor == 42
        assert fonte.idas == 2

    def test_falha_que_nao_e_da_fonte_nao_ganha_espera(self):
        """Defeito do código não é "a fonte caiu": a leitura seguinte tenta."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fonte = Fonte()
        fonte.erro = RuntimeError("defeito")
        with pytest.raises(RuntimeError):
            cache.ler("k", fonte, falhas=FALHAS)
        fonte.erro = None

        assert cache.ler("k", fonte, falhas=FALHAS).valor == 42
        assert fonte.idas == 2


class TestSincroniaPeloAtualizarAgora:
    """O Atualizar agora de uma chave vence as outras que leem da mesma fonte
    (issue #858): a próxima leitura delas busca, e as telas vizinhas param de
    mostrar números diferentes para a mesma métrica. Só marca, não busca junto:
    um clique não vira uma rajada de idas."""

    def _tres_chaves(self):
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        fontes = {"lente": Fonte(1), "galeria": Fonte(1), "site": Fonte(1)}
        cache.ler("lente", fontes["lente"], fontes={("instagram", "28d")})
        cache.ler("galeria", fontes["galeria"], fontes={("instagram", "28d"), ("google", "28d")})
        cache.ler("site", fontes["site"], fontes={("google", "28d")})
        return relogio, cache, fontes

    def test_quem_le_da_mesma_fonte_busca_na_proxima_leitura(self):
        relogio, cache, fontes = self._tres_chaves()
        fontes["lente"].valor = 2
        fontes["galeria"].valor = 2
        cache.ler("lente", fontes["lente"], forcar=True, fontes={("instagram", "28d")})

        assert fontes["galeria"].idas == 1
        assert cache.ler("galeria", fontes["galeria"]).valor == 2
        assert fontes["galeria"].idas == 2

    def test_quem_le_de_outra_fonte_continua_servido_do_cache(self):
        relogio, cache, fontes = self._tres_chaves()
        cache.ler("lente", fontes["lente"], forcar=True, fontes={("instagram", "28d")})

        cache.ler("site", fontes["site"])

        assert fontes["site"].idas == 1

    def test_a_chave_vencida_volta_ao_cache_depois_de_buscar(self):
        relogio, cache, fontes = self._tres_chaves()
        cache.ler("lente", fontes["lente"], forcar=True, fontes={("instagram", "28d")})
        cache.ler("galeria", fontes["galeria"])

        cache.ler("galeria", fontes["galeria"])

        assert fontes["galeria"].idas == 2

    def test_a_renovacao_pela_hora_nao_vence_as_vizinhas(self):
        """Só o Atualizar agora sincroniza: se a renovação pela hora também
        vencesse as vizinhas, cada leitura derrubaria a outra, e as telas iam
        à fonte a cada abertura."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        lente, galeria = Fonte(1), Fonte(1)
        cache.ler("lente", lente, fontes={("instagram", "28d")})
        relogio.avancar(minutes=30)
        cache.ler("galeria", galeria, fontes={("instagram", "28d")})
        relogio.avancar(minutes=30)
        cache.ler("lente", lente, fontes={("instagram", "28d")})

        cache.ler("galeria", galeria)

        assert lente.idas == 2
        assert galeria.idas == 1

    def test_atualizar_agora_que_falha_nao_vence_ninguem(self):
        relogio, cache, fontes = self._tres_chaves()
        fontes["lente"].erro = FonteForaError("fora")
        cache.ler("lente", fontes["lente"], forcar=True, falhas=FALHAS, fontes={("instagram", "28d")})

        cache.ler("galeria", fontes["galeria"])

        assert fontes["galeria"].idas == 1

    def test_leitura_da_vizinha_que_ja_estava_no_ar_nao_apaga_a_marca(self):
        """A galeria estava indo à fonte quando alguém clicou no Atualizar agora
        da lente. O número que a galeria traz é de antes do clique: ela continua
        vencida, e a próxima leitura busca de novo."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        cache.ler("lente", Fonte(1), fontes={("instagram", "28d")})
        cache.ler("galeria", Fonte(1), fontes={("instagram", "28d")})
        relogio.avancar(hours=1)

        def galeria_que_volta_depois_do_clique():
            cache.ler("lente", Fonte(2), forcar=True, fontes={("instagram", "28d")})
            return 1

        cache.ler("galeria", galeria_que_volta_depois_do_clique, fontes={("instagram", "28d")})
        galeria = Fonte(2)

        assert cache.ler("galeria", galeria).valor == 2
        assert galeria.idas == 1

    def test_a_vizinha_em_espera_por_falha_busca_mesmo_assim(self):
        """O Atualizar agora que deu certo mostra que a fonte voltou: a espera
        da falha antiga da vizinha não segura a busca dela."""
        relogio = RelogioDeTeste()
        cache = _cache(relogio)
        galeria = Fonte(1)
        cache.ler("lente", Fonte(1), fontes={("instagram", "28d")})
        cache.ler("galeria", galeria, falhas=FALHAS, fontes={("instagram", "28d")})
        relogio.avancar(hours=1)
        galeria.erro = FonteForaError("fora")
        cache.ler("galeria", galeria, falhas=FALHAS)
        relogio.avancar(minutes=1)
        cache.ler("lente", Fonte(2), forcar=True, fontes={("instagram", "28d")})
        galeria.erro = None
        galeria.valor = 2

        leitura = cache.ler("galeria", galeria, falhas=FALHAS)

        assert leitura.valor == 2
        assert leitura.frescor.atualizacao_falhou is False
        assert galeria.idas == 3

    def test_o_erro_repetido_na_espera_e_um_novo_a_cada_leitura(self):
        """Dentro da espera, sem número guardado, a leitura repete o erro com a
        mesma frase, mas não a mesma exceção: relançar a guardada faria o
        traceback dela crescer a cada leitura, segurando os frames de todas."""
        cache = _cache(RelogioDeTeste())
        fonte = Fonte()
        fonte.erro = FonteForaError("fora")
        with pytest.raises(FonteForaError):
            cache.ler("k", fonte, falhas=FALHAS)

        erros = []
        for _ in range(2):
            with pytest.raises(FonteForaError, match="fora") as capturado:
                cache.ler("k", fonte, falhas=FALHAS)
            erros.append(capturado.value)

        assert erros[0] is not erros[1]
        assert erros[0] is not fonte.erro
