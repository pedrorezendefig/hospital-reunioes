"""Os quatro marcos do caso e o tempo decorrido em cada trecho (issue #480,
PRD #468, RN-55, diagnóstico D-05 e D-10).

O módulo é puro: recebe o caso, o instante da medição e os feriados, e devolve
o que a página do caso mostra. Não lê banco e não consulta o relógio, como o
motor de prazos de onde ele tira a régua.

O que estes testes protegem, e por que cada um existe:

* o tempo é de EXPEDIENTE, não de calendário. Fim de semana e feriado no meio
  de um trecho não podem virar dias de trabalho, senão a Diretoria lê "o setor
  levou 3 dias" onde a área teve 1 dia de mesa;
* marco que não aconteceu é PENDENTE, e pendente não vira data. Preencher com
  "agora" ou com o marco anterior faria a tela inventar um fato do caso;
* o prazo conclusivo da tela é a coluna CONGELADA (`prazo_conclusivo_em`), e
  não a régua recalculada das métricas. Ver a decisão escrita em
  `app/services/ouvidoria_marcos.py`.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ouvidoria_marcos import (  # noqa: E402
    AGUARDANDO_VALIDACAO,
    DEFINIDO,
    NOTA_AREA_VENCE_DEPOIS,
    NOTA_REABERTURA,
    NOTA_VENCIDO_NA_TRIAGEM,
    SEM_PRAZO,
    marcos_do_caso,
)

SEM_FERIADO: frozenset[dt.date] = frozenset()

# A quarta-feira no meio do último trecho, quando o hospital não trabalha.
FERIADO_DE_QUARTA = frozenset({dt.date(2026, 8, 19)})

# O caso inteiro, marco a marco, em UTC (o expediente é 08h às 17h de Brasília,
# ou seja, 11h às 20h aqui).
T0 = "2026-08-14T19:00:00+00:00"  # sexta, 16h
T1 = "2026-08-17T12:00:00+00:00"  # segunda, 9h
T2 = "2026-08-18T13:00:00+00:00"  # terça, 10h
T3 = "2026-08-20T14:00:00+00:00"  # quinta, 11h

AGORA = dt.datetime(2026, 8, 21, 14, 0, tzinfo=dt.UTC)  # sexta, 11h


def _caso(**overrides) -> dict:
    caso = {
        "id": "uuid-7",
        "status": "encerrado",
        "contato_em": T0,
        "data_abertura": "2026-08-14",
        "gravidade": "medio",
        "validada_em": T1,
        "respondida_em": T2,
        "encerrada_em": T3,
        "prazo_area_em": "2026-08-19T20:00:00+00:00",
        "prazo_conclusivo_em": "2026-08-25T20:00:00+00:00",
        "pausada_em": None,
        "minutos_pausados": 0,
        "reincidencia": False,
        "reaberta_em": None,
    }
    caso.update(overrides)
    return caso


def _por_chave(retorno: dict, campo: str) -> dict:
    return {linha["chave"]: linha for linha in retorno[campo]}


class TestOsQuatroMarcos:
    def test_o_caso_percorrido_mostra_os_quatro_marcos_com_data_hora(self):
        marcos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")

        assert [m["chave"] for m in marcos.values()] == ["T0", "T1", "T2", "T3"]
        assert marcos["T0"]["em"] == T0
        assert marcos["T1"]["em"] == T1
        assert marcos["T2"]["em"] == T2
        assert marcos["T3"]["em"] == T3
        assert not any(m["pendente"] for m in marcos.values())

    def test_marco_que_nao_aconteceu_vem_pendente_e_sem_data(self):
        """Sem data inventada: o caso ainda na fila não tem validação, nem
        resposta, nem conclusão, e a tela precisa poder dizer isso."""
        marcos = _por_chave(
            marcos_do_caso(
                _caso(status="em_classificacao", validada_em=None, respondida_em=None, encerrada_em=None),
                AGORA,
                SEM_FERIADO,
            ),
            "marcos",
        )

        assert marcos["T0"]["em"] == T0
        for chave in ("T1", "T2", "T3"):
            assert marcos[chave]["pendente"] is True
            assert marcos[chave]["em"] is None

    def test_caso_sem_entrada_nao_inventa_o_marco_de_entrada(self):
        """O import histórico do NocoDB trouxe linha sem contato e sem data de
        abertura. Ali não existe T0, e sem T0 não existe trecho para medir."""
        marcos = _por_chave(
            marcos_do_caso(_caso(contato_em=None, data_abertura=None), AGORA, SEM_FERIADO),
            "marcos",
        )

        assert marcos["T0"]["pendente"] is True
        assert marcos["T0"]["em"] is None
        assert marcos["T1"]["minutos_uteis"] is None

    def test_o_marco_lido_sem_fuso_vale_como_hora_do_hospital(self):
        """As colunas são `timestamptz` e chegam com fuso. Se uma vier sem, a
        página não pode cair: o motor recusa instante ingênuo, então o valor
        entra como hora de parede do hospital, a mesma leitura que o teto da
        prorrogação já faz com `contato_em`."""
        marcos = _por_chave(
            marcos_do_caso(_caso(validada_em="2026-08-17T09:00:00"), AGORA, SEM_FERIADO),
            "marcos",
        )

        assert marcos["T1"]["minutos_uteis"] == 120


class TestTempoDecorrido:
    def test_o_trecho_que_atravessa_o_fim_de_semana_conta_so_o_expediente(self):
        """Sexta 16h a segunda 9h são 65 horas de calendário e 2 horas úteis:
        uma hora antes do fechamento e uma depois da abertura."""
        marcos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")

        assert marcos["T1"]["minutos_uteis"] == 120
        assert marcos["T1"]["trecho"] == "Triagem da Ouvidoria"

    def test_o_trecho_da_area_conta_da_validacao_ate_a_resposta(self):
        marcos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")

        assert marcos["T2"]["minutos_uteis"] == 600
        assert marcos["T2"]["trecho"] == "Resposta da área"

    def test_o_feriado_no_meio_do_trecho_nao_conta_como_dia_de_trabalho(self):
        """O mesmo caso, medido com e sem o feriado de quarta: 9 horas de
        expediente a menos. Sem esta subtração a Ouvidoria apareceria levando
        um dia inteiro a mais para dar o desfecho."""
        sem_feriado = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")
        com_feriado = _por_chave(marcos_do_caso(_caso(), AGORA, FERIADO_DE_QUARTA), "marcos")

        assert sem_feriado["T3"]["minutos_uteis"] == 1140
        assert com_feriado["T3"]["minutos_uteis"] == 600
        assert com_feriado["T3"]["trecho"] == "Desfecho pela Ouvidoria"

    def test_o_trecho_ainda_aberto_conta_ate_agora_e_se_declara_em_curso(self):
        """O caso parado na fila precisa mostrar o tempo que já queimou, senão
        o gargalo da própria Ouvidoria fica invisível (D-05)."""
        agora = dt.datetime(2026, 8, 17, 17, 0, tzinfo=dt.UTC)  # segunda, 14h
        marcos = _por_chave(
            marcos_do_caso(
                _caso(status="em_classificacao", validada_em=None, respondida_em=None, encerrada_em=None),
                agora,
                SEM_FERIADO,
            ),
            "marcos",
        )

        assert marcos["T1"]["minutos_uteis"] == 420
        assert marcos["T1"]["em_curso"] is True
        # Trecho que nem começou não tem tempo, e não tem zero: zero diria que
        # a área respondeu na hora, quando ela nem foi acionada.
        assert marcos["T2"]["minutos_uteis"] is None
        assert marcos["T2"]["em_curso"] is False

    def test_o_trecho_fechado_nao_se_declara_em_curso(self):
        marcos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")

        assert all(m["em_curso"] is False for m in marcos.values())

    def test_o_caso_pausado_mede_o_trecho_aberto_no_instante_em_que_parou(self):
        """A espera pelo manifestante não é tempo da área (issue #335): medir
        contra o relógio de parede cobraria dela uma espera que não é dela, e é
        a mesma régua do painel."""
        marcos = _por_chave(
            marcos_do_caso(
                _caso(
                    status="aguardando_manifestante",
                    respondida_em=None,
                    encerrada_em=None,
                    pausada_em="2026-08-17T13:00:00+00:00",  # segunda, 10h
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "marcos",
        )

        # Segunda 9h às 10h, e não segunda 9h até a sexta seguinte.
        assert marcos["T2"]["minutos_uteis"] == 60
        assert marcos["T2"]["em_curso"] is True

    def test_o_caso_devolvido_reabre_o_trecho_da_area(self):
        """A devolução por insuficiência limpa o marco T2 de propósito (issue
        #334): a área ainda deve resposta. O trecho dela volta a correr, e o
        estouro que ela já consumou não vira tempo de mais ninguém."""
        marcos = _por_chave(
            marcos_do_caso(
                _caso(
                    status="aguardando_area",
                    respondida_em=None,
                    encerrada_em=None,
                    area_estourou_em="2026-08-19T20:00:00+00:00",
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "marcos",
        )

        assert marcos["T2"]["pendente"] is True
        assert marcos["T2"]["em_curso"] is True
        # O trecho seguinte não começou: sem resposta não há desfecho a medir.
        assert marcos["T3"]["minutos_uteis"] is None

    def test_marco_no_futuro_nao_devolve_tempo_negativo(self):
        """Relógio de máquina adiantado, ou marco digitado à frente, não pode
        virar tempo negativo na tela. O motor devolve zero, e zero aqui é o
        mínimo honesto: nada de expediente passou."""
        antes_de_tudo = dt.datetime(2026, 8, 14, 18, 0, tzinfo=dt.UTC)  # sexta, 15h
        marcos = _por_chave(
            marcos_do_caso(
                _caso(status="em_classificacao", validada_em=None, respondida_em=None, encerrada_em=None),
                antes_de_tudo,
                SEM_FERIADO,
            ),
            "marcos",
        )

        assert marcos["T1"]["minutos_uteis"] == 0


class TestCasoReaberto:
    """A reabertura por reincidência preserva `encerrada_em` de propósito (é o
    marco da tramitação anterior, que os relatórios leem), mas o caso voltou a
    tramitar."""

    def test_a_conclusao_anterior_nao_passa_por_conclusao_do_caso_aberto(self):
        marcos = _por_chave(
            marcos_do_caso(
                _caso(status="aguardando_area", reincidencia=True, reaberta_em="2026-08-21T12:00:00+00:00"),
                AGORA,
                SEM_FERIADO,
            ),
            "marcos",
        )

        assert marcos["T3"]["pendente"] is True
        assert marcos["T3"]["em"] is None
        # O fato não some da tela: ele é dito pelo que é.
        assert marcos["T3"]["tramitacao_anterior_em"] == T3

    def test_caso_encerrado_nao_carrega_tramitacao_anterior(self):
        marcos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "marcos")

        assert marcos["T3"]["tramitacao_anterior_em"] is None


class TestOsDoisPrazos:
    def test_os_dois_prazos_saem_com_data_e_com_a_contagem_do_motor(self):
        prazos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "prazos")

        assert prazos["area"]["situacao"] == DEFINIDO
        assert prazos["area"]["em"] == "2026-08-19T20:00:00+00:00"
        assert prazos["conclusivo"]["situacao"] == DEFINIDO
        assert prazos["conclusivo"]["em"] == "2026-08-25T20:00:00+00:00"
        # A contagem regressiva é a mesma frase do painel e do email do setor.
        assert prazos["conclusivo"]["rotulo_prazo"] == "vence em 2 dias úteis"
        assert prazos["conclusivo"]["estourado"] is False

    def test_caso_ainda_nao_validado_diz_que_o_prazo_sai_no_acionamento(self):
        """Os dois prazos nascem no despacho. Antes dele a coluna é nula porque
        o ato não aconteceu, e isso não é o mesmo que gravidade sem prazo."""
        prazos = _por_chave(
            marcos_do_caso(
                _caso(status="em_classificacao", validada_em=None, prazo_area_em=None, prazo_conclusivo_em=None),
                AGORA,
                SEM_FERIADO,
            ),
            "prazos",
        )

        assert prazos["area"]["situacao"] == AGUARDANDO_VALIDACAO
        assert prazos["conclusivo"]["situacao"] == AGUARDANDO_VALIDACAO

    def test_caso_critico_validado_fica_sem_prazo_conclusivo(self):
        """A célula conclusiva do crítico é nula de propósito (migration 065).
        Caso validado com a coluna vazia não está esperando nada: ele não tem
        esse prazo, e a tela não inventa um."""
        prazos = _por_chave(
            marcos_do_caso(_caso(gravidade="critico", prazo_conclusivo_em=None), AGORA, SEM_FERIADO),
            "prazos",
        )

        assert prazos["conclusivo"]["situacao"] == SEM_PRAZO
        assert prazos["conclusivo"]["em"] is None
        assert prazos["conclusivo"]["rotulo_prazo"] is None
        assert prazos["area"]["situacao"] == DEFINIDO

    def test_o_prazo_conclusivo_estourado_e_dito_como_estourado(self):
        prazos = _por_chave(
            marcos_do_caso(_caso(prazo_conclusivo_em="2026-08-18T20:00:00+00:00"), AGORA, SEM_FERIADO),
            "prazos",
        )

        assert prazos["conclusivo"]["estourado"] is True
        assert prazos["conclusivo"]["rotulo_prazo"].startswith("vencido há")

    def test_o_prazo_conclusivo_nao_recebe_o_credito_que_a_area_recebeu(self):
        """A divergência das duas fontes, resolvida na tela: o vencimento da
        área está DEPOIS do conclusivo congelado, e a página mostra os dois
        como estão, com a nota que diz o que se vê. Recalcular o conclusivo
        aqui mudaria o compromisso assumido com quem manifestou, que é
        justamente o que a coluna congelada existe para impedir."""
        prazos = _por_chave(
            marcos_do_caso(
                _caso(
                    respondida_em=None,
                    encerrada_em=None,
                    status="aguardando_area",
                    prazo_area_em="2026-08-27T20:00:00+00:00",
                    prazo_conclusivo_em="2026-08-25T20:00:00+00:00",
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "prazos",
        )

        assert prazos["conclusivo"]["em"] == "2026-08-25T20:00:00+00:00"
        assert prazos["conclusivo"]["nota"] == NOTA_AREA_VENCE_DEPOIS

    def test_a_nota_nao_culpa_a_prorrogacao_por_um_caso_que_so_demorou_na_triagem(self):
        """Os dois prazos têm origens diferentes: o conclusivo conta da
        entrada, o da área conta da validação. Com a tabela de prazos vigente
        (médio: 7 dias úteis de conclusiva contra 4 de área), qualquer caso que
        demore mais de 3 dias úteis na triagem nasce com o vencimento da área
        depois do conclusivo, SEM prorrogação e SEM pausa. A nota não pode
        afirmar uma causa que não aconteceu: quem demorou foi a Ouvidoria, e é
        isso que o PRD existe para expor."""
        prazos = _por_chave(
            marcos_do_caso(
                _caso(
                    respondida_em=None,
                    encerrada_em=None,
                    status="aguardando_area",
                    prazo_area_em="2026-08-27T20:00:00+00:00",
                    prazo_conclusivo_em="2026-08-25T20:00:00+00:00",
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "prazos",
        )

        assert "prorrogação e a espera" not in (prazos["conclusivo"]["nota"] or "")

    def test_caso_que_passou_da_conclusiva_ainda_na_triagem_diz_isso(self):
        """A terceira situação do comentário do PRD #468: o caso que ficou na
        fila além da conclusiva nasce validado com o prazo já no passado. O
        número está certo (conta de T0), e a tela nomeia o que houve, em vez de
        deixar o ouvidor concluir que a área atrasou."""
        prazos = _por_chave(
            marcos_do_caso(
                _caso(
                    respondida_em=None,
                    encerrada_em=None,
                    status="aguardando_area",
                    # Validado em 17/08, com o conclusivo vencido em 14/08.
                    prazo_conclusivo_em="2026-08-14T20:00:00+00:00",
                    prazo_area_em="2026-08-21T20:00:00+00:00",
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "prazos",
        )

        assert prazos["conclusivo"]["estourado"] is True
        assert prazos["conclusivo"]["nota"] == NOTA_VENCIDO_NA_TRIAGEM

    def test_caso_reaberto_diz_que_o_prazo_conclusivo_e_da_primeira_tramitacao(self):
        """A reabertura dá prazo novo à área e não move o conclusivo: sem esta
        nota, todo caso recém-reaberto abre com o relógio do manifestante
        estourado sem ninguém ter atrasado nada neste ciclo."""
        prazos = _por_chave(
            marcos_do_caso(
                _caso(
                    status="aguardando_area",
                    reincidencia=True,
                    reaberta_em="2026-08-21T12:00:00+00:00",
                    prazo_area_em="2026-08-27T20:00:00+00:00",
                    prazo_conclusivo_em="2026-08-18T20:00:00+00:00",
                ),
                AGORA,
                SEM_FERIADO,
            ),
            "prazos",
        )

        assert prazos["conclusivo"]["estourado"] is True
        assert prazos["conclusivo"]["nota"] == NOTA_REABERTURA

    def test_caso_comum_nao_carrega_nota_nenhuma(self):
        prazos = _por_chave(marcos_do_caso(_caso(), AGORA, SEM_FERIADO), "prazos")

        assert prazos["conclusivo"]["nota"] is None
        assert prazos["area"]["nota"] is None

    def test_a_contagem_do_prazo_da_area_congela_na_pausa_e_a_do_conclusivo_nao(self):
        """As duas medidas divergem de propósito. O vencimento da área é
        empurrado na retomada, então medi-lo contra o relógio de parede o faria
        aparecer estourado sem ter estourado. O conclusivo nunca é empurrado:
        congelar a medida dele daria ao caso um crédito que ninguém concedeu, e
        a promessa feita a quem manifestou segue correndo."""
        pausado = _caso(
            status="aguardando_manifestante",
            respondida_em=None,
            encerrada_em=None,
            pausada_em="2026-08-17T13:00:00+00:00",  # segunda, 10h
            prazo_area_em="2026-08-19T20:00:00+00:00",
            prazo_conclusivo_em="2026-08-19T20:00:00+00:00",
        )
        prazos = _por_chave(marcos_do_caso(pausado, AGORA, SEM_FERIADO), "prazos")

        assert prazos["area"]["estourado"] is False
        assert prazos["conclusivo"]["estourado"] is True
