"""Motor de prazos da Ouvidoria em calendário útil (issue #322, ADR 0034 decisão 6).

O motor é função pura: recebe o instante de início, o prazo da gravidade e a
lista de feriados, e devolve vencimento e rótulo. Não lê banco, não olha o
relógio por conta própria. Estes testes exercitam esse seam direto, como pede
a seção "Decisões de teste" do PRD #317.

Datas escritas no fuso America/Sao_Paulo, que é o do expediente; o motor
devolve em UTC, que é como o prazo é persistido.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

FUSO = ZoneInfo("America/Sao_Paulo")

SEM_FERIADO: frozenset[date] = frozenset()


def _sp(ano: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    return datetime(ano, mes, dia, hora, minuto, tzinfo=FUSO)


class TestContagemEmDiasUteis:
    """Dia útil não conta o dia do fato: a contagem abre no expediente
    seguinte e o prazo vence no fim do expediente do enésimo dia."""

    def test_dois_dias_uteis_a_partir_de_sexta_16h50_vencem_terca_as_17h(self):
        """Critério de aceite da #322, na letra: caso validado sexta 16h50 com
        prazo de 2 dias úteis vence terça às 17h, porque a contagem só abre
        segunda às 08h."""
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 21, 16, 50), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 17, 0)

    @pytest.mark.parametrize(
        "entrada",
        [
            _sp(2026, 8, 21, 16, 50),  # sexta, dentro do expediente
            _sp(2026, 8, 21, 17, 30),  # sexta, depois do fechamento
            _sp(2026, 8, 22, 22, 0),  # sábado à noite
            _sp(2026, 8, 23, 7, 0),  # domingo de manhã
        ],
        ids=["sexta-no-expediente", "sexta-a-noite", "sabado", "domingo"],
    )
    def test_tudo_que_chega_depois_da_sexta_de_manha_conta_da_segunda(self, entrada):
        """Quarenta minutos a mais na entrada não podem custar um dia útil de
        prazo: sexta 16h50 e sexta 17h30 abrem a contagem na mesma segunda, e
        o prazo combinado com a Diretoria continua sendo de 2 dias úteis."""
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(entrada, Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 17, 0)


class TestFeriadoAdministravel:
    """Feriado cadastrado sai do calendário útil; tirado da tabela, o dia volta
    a contar. O motor não tem feriado embutido: recebe o conjunto pronto."""

    # Quinta, 23/04/2026: São Jorge, feriado estadual do Rio de Janeiro.
    SAO_JORGE = date(2026, 4, 23)

    def test_feriado_cadastrado_empurra_o_vencimento(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        # Quarta-feira: a contagem abriria na quinta, mas ela é feriado.
        vencimento = calcular_vencimento(_sp(2026, 4, 22, 10, 0), Prazo(2, "dias_uteis"), frozenset({self.SAO_JORGE}))

        assert vencimento == _sp(2026, 4, 27, 17, 0), "Feriado do RJ contou como dia útil"

    def test_feriado_removido_volta_a_contar(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 4, 22, 10, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 4, 24, 17, 0)


class TestContagemEmHorasUteis:
    """Gravidade crítica trabalha em horas úteis (4h para a área responder):
    o relógio anda dentro do expediente e para às 17h."""

    def test_quatro_horas_uteis_no_meio_da_tarde_viram_a_manha_seguinte(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        # Segunda 15h: sobram 2h de expediente, as outras 2h caem na terça.
        vencimento = calcular_vencimento(_sp(2026, 8, 24, 15, 0), Prazo(4, "horas_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 10, 0)

    def test_entrada_fora_do_expediente_conta_da_proxima_abertura(self):
        """RN-23: manifestação de sábado à noite não consome prazo de
        madrugada; a contagem abre segunda às 08h."""
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 22, 22, 0), Prazo(4, "horas_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 24, 12, 0)


class TestPrazoImediato:
    """Triagem de caso crítico é "imediato" na spec, ou seja, prazo zero. A
    tela deixa a Diretoria digitar zero em qualquer unidade, e zero significa
    a mesma coisa nas duas."""

    @pytest.mark.parametrize("unidade", ["horas_uteis", "dias_uteis"])
    def test_prazo_zero_vence_na_abertura_da_contagem(self, unidade):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 24, 15, 0), Prazo(0, unidade), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 24, 15, 0)


class TestViradaDeMes:
    """A contagem atravessa a virada de mês sem tropeçar no calendário."""

    def test_dois_dias_uteis_na_ultima_segunda_de_agosto_vencem_em_setembro(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 31, 9, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 9, 2, 17, 0)


class TestRotuloEmLinguagemNatural:
    """O que o painel e o email do setor exibem (RN-35): contagem regressiva
    em português, na mesma unidade em que o prazo foi combinado."""

    def test_logo_apos_a_validacao_o_rotulo_repete_o_prazo_combinado(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        # Validada sexta 16h50 com 2 dias úteis: o vencimento é terça 17h.
        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 21, 16, 50), SEM_FERIADO)

        assert rotulo == "vence em 2 dias úteis"

    def test_ultimo_dia_fala_no_singular(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 24, 9, 0), SEM_FERIADO)

        assert rotulo == "vence em 1 dia útil"

    def test_prazo_curto_de_critico_e_dito_em_horas(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        rotulo = rotular_vencimento(_sp(2026, 8, 24, 13, 0), _sp(2026, 8, 24, 9, 0), SEM_FERIADO)

        assert rotulo == "vence em 4 horas úteis"

    def test_prazo_estourado_diz_ha_quanto_tempo(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        # Vencia terça 17h; agora é quarta 10h, ou seja, 2h de expediente depois.
        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 26, 10, 0), SEM_FERIADO)

        assert rotulo == "vencido há 2 horas úteis"

    def test_gravidade_sem_prazo_nao_finge_contagem(self):
        """Crítico não tem prazo conclusivo fixo e baixo não passa pela área:
        nesses casos o motor devolve vencimento None e o rótulo diz isso."""
        from app.services.ouvidoria_prazos import rotular_vencimento

        assert rotular_vencimento(None, _sp(2026, 8, 24, 9, 0), SEM_FERIADO) == "sem prazo definido"


class TestEstouro:
    """O que o job de cobrança (#327) e o destaque do painel perguntam."""

    def test_antes_do_vencimento_nao_esta_estourado(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 25, 16, 59)) is False

    def test_no_instante_do_vencimento_ja_esta_estourado(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 25, 17, 0)) is True

    def test_caso_sem_prazo_nunca_estoura(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(None, _sp(2027, 1, 1, 12, 0)) is False


class TestPausaAguardandoManifestante:
    """Governança do PRD #318 (issue #331): o tempo em que o caso espera o
    manifestante não conta contra a área. Pausar e retomar acumula."""

    def test_pausar_e_retomar_acumula_o_tempo_parado_em_minutos_uteis(self):
        from app.services.ouvidoria_prazos import minutos_uteis_pausados

        # Primeira pausa: segunda 15h a terça 15h = 2h + 7h = 9h úteis.
        # Segunda pausa: quarta 16h a quinta 9h = 1h + 1h = 2h úteis.
        pausas = [
            (_sp(2026, 8, 24, 15, 0), _sp(2026, 8, 25, 15, 0)),
            (_sp(2026, 8, 26, 16, 0), _sp(2026, 8, 27, 9, 0)),
        ]

        assert minutos_uteis_pausados(pausas, SEM_FERIADO) == 11 * 60

    def test_tempo_pausado_e_descontado_do_tempo_da_area(self):
        """História 9: a área não é cobrada pela espera que não é dela. De
        segunda 9h a quarta 9h correm 18h úteis; com 9h pausadas aguardando o
        manifestante, o tempo da área é 9h."""
        from app.services.ouvidoria_prazos import minutos_uteis_da_area

        pausas = [(_sp(2026, 8, 24, 15, 0), _sp(2026, 8, 25, 15, 0))]

        minutos = minutos_uteis_da_area(_sp(2026, 8, 24, 9, 0), _sp(2026, 8, 26, 9, 0), pausas, SEM_FERIADO)

        assert minutos == 9 * 60

    def test_caso_ainda_pausado_so_desconta_ate_o_momento_da_medicao(self):
        """Medição feita com o caso ainda aguardando o manifestante: só o
        trecho da pausa dentro da janela é descontado. De segunda 9h a terça
        12h correm 12h úteis; a pausa aberta segunda 15h vale 6h até ali."""
        from app.services.ouvidoria_prazos import minutos_uteis_da_area

        pausas = [(_sp(2026, 8, 24, 15, 0), _sp(2026, 8, 26, 10, 0))]

        minutos = minutos_uteis_da_area(_sp(2026, 8, 24, 9, 0), _sp(2026, 8, 25, 12, 0), pausas, SEM_FERIADO)

        assert minutos == 6 * 60

    def test_pausas_sobrepostas_nao_descontam_o_mesmo_tempo_duas_vezes(self):
        """Pausar duas vezes sem registrar a retomada do meio (retentativa do
        ouvidor) grava intervalos sobrepostos. O tempo parado real é o que a
        união deles cobre: 9h a 16h = 7h úteis, não 7h + 4h."""
        from app.services.ouvidoria_prazos import minutos_uteis_pausados

        pausas = [
            (_sp(2026, 8, 24, 9, 0), _sp(2026, 8, 24, 16, 0)),
            (_sp(2026, 8, 24, 10, 0), _sp(2026, 8, 24, 14, 0)),
        ]

        assert minutos_uteis_pausados(pausas, SEM_FERIADO) == 7 * 60


class TestCreditoQueNaoEmpurraNada:
    """O ramo de crédito não positivo de `adiar_vencimento`, direto.

    Ele existe para o vencimento sair INTACTO, e não recalculado: sem a guarda,
    a mesma chamada passaria por `inicio_da_contagem`, que empurra todo instante
    fora do expediente para a próxima abertura. Como o crédito nulo é o caso
    comum (todo caso sem prorrogação e sem pausa), esse desvio silencioso
    valeria para a fila inteira, e o ramo roda em toda chamada de `/metricas`
    desde a extração do prazo conclusivo (issue #433)."""

    def test_credito_zero_devolve_o_mesmo_instante(self):
        """Quarta às 18h, fora do expediente: com crédito zero o vencimento é o
        que já era. Recalculado, ele viraria quinta às 08h."""
        from app.services.ouvidoria_prazos import adiar_vencimento

        vencimento = _sp(2026, 8, 26, 18, 0)

        assert adiar_vencimento(vencimento, 0, SEM_FERIADO) == vencimento

    def test_vencimento_de_sexta_as_17h_nao_pula_para_a_segunda(self):
        """O instante mais caro do calendário: 17h de sexta é o fechamento, e
        `inicio_da_contagem` o joga para segunda às 08h. Crédito negativo (o que
        uma prorrogação que ENCURTOU o prazo produz) não pode empurrar o
        vencimento para frente, muito menos três dias."""
        from app.services.ouvidoria_prazos import adiar_vencimento

        vencimento = _sp(2026, 8, 28, 17, 0)

        assert adiar_vencimento(vencimento, -120, SEM_FERIADO) == vencimento


class TestMeioPrazoDeDevolucao:
    """História 7 do PRD #318: devolução por insuficiência reabre o caso com
    metade do prazo original da gravidade, somada ao tempo já corrido. O
    relógio não zera: da devolução em diante resta só a metade."""

    def test_devolucao_da_metade_do_prazo_original_a_partir_da_devolucao(self):
        """Gravidade alta tem 2 dias úteis. Devolvida terça 10h, a área ganha
        1 dia útil (9h de expediente): vence quarta 10h, não quinta 17h como
        seria se o relógio zerasse."""
        from app.services.ouvidoria_prazos import Prazo, vencimento_apos_devolucao

        vencimento = vencimento_apos_devolucao(_sp(2026, 8, 25, 10, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 26, 10, 0)

    def test_devolucao_fora_do_expediente_conta_da_proxima_abertura(self):
        """Devolvida sexta à noite, a metade só começa a correr segunda às 08h.
        Metade de 2 dias úteis = 9h úteis, o expediente inteiro de segunda:
        vence segunda às 17h."""
        from app.services.ouvidoria_prazos import Prazo, vencimento_apos_devolucao

        vencimento = vencimento_apos_devolucao(_sp(2026, 8, 21, 19, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 24, 17, 0)

    def test_metade_de_prazo_impar_vale_meio_dia_util(self):
        """Metade de 3 dias úteis é 13h30 de expediente, não um arredondamento
        para dia cheio: devolvida segunda 9h, vence terça 13h30."""
        from app.services.ouvidoria_prazos import Prazo, vencimento_apos_devolucao

        vencimento = vencimento_apos_devolucao(_sp(2026, 8, 24, 9, 0), Prazo(3, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 13, 30)

    def test_gravidade_sem_prazo_devolvida_segue_sem_prazo(self):
        from app.services.ouvidoria_prazos import Prazo, vencimento_apos_devolucao

        assert vencimento_apos_devolucao(_sp(2026, 8, 25, 10, 0), Prazo(None), SEM_FERIADO) is None


class TestTetoDeProrrogacao:
    """PRD #318: prorrogação tem teto de 30 dias úteis contados da entrada da
    manifestação. Além do teto, o cálculo recusa sozinho."""

    # Entrada sexta 21/08/2026 16h: o dia útil 1 é segunda 24/08 e o trigésimo
    # é sexta 02/10 (6 semanas cheias sem feriado).
    ENTRADA = _sp(2026, 8, 21, 16, 0)

    def test_vencimento_ate_o_trigesimo_dia_util_e_permitido(self):
        from app.services.ouvidoria_prazos import prorrogacao_dentro_do_teto

        assert prorrogacao_dentro_do_teto(self.ENTRADA, _sp(2026, 10, 2, 17, 0), SEM_FERIADO) is True

    def test_vencimento_alem_do_trigesimo_dia_util_e_recusado(self):
        from app.services.ouvidoria_prazos import prorrogacao_dentro_do_teto

        assert prorrogacao_dentro_do_teto(self.ENTRADA, _sp(2026, 10, 5, 17, 0), SEM_FERIADO) is False

    def test_feriado_no_meio_empurra_o_teto(self):
        """Com a Independência (07/09) fora do calendário útil, o trigésimo
        dia útil vira segunda 05/10: a mesma data recusada acima passa."""
        from app.services.ouvidoria_prazos import prorrogacao_dentro_do_teto

        independencia = frozenset({date(2026, 9, 7)})

        assert prorrogacao_dentro_do_teto(self.ENTRADA, _sp(2026, 10, 5, 17, 0), independencia) is True


class TestVencimentoProrrogado:
    """Issue #333: o prazo novo de uma prorrogação sai do motor já limitado ao
    teto de 30 dias úteis da entrada. A rota não decide teto na mão."""

    # Entrada sexta 21/08/2026 16h: o dia útil 1 é segunda 24/08 e o trigésimo
    # é sexta 02/10 (as mesmas âncoras do teste do teto, acima).
    ENTRADA = _sp(2026, 8, 21, 16, 0)

    def test_soma_dias_uteis_ao_prazo_atual_pulando_o_fim_de_semana(self):
        """Prazo vencendo quinta 27/08 às 17h mais 3 dias úteis vence terça
        01/09 às 17h: sábado e domingo não contam."""
        from app.services.ouvidoria_prazos import vencimento_prorrogado

        novo = vencimento_prorrogado(self.ENTRADA, _sp(2026, 8, 27, 17, 0), 3, SEM_FERIADO)

        assert novo == _sp(2026, 9, 1, 17, 0)

    def test_pedido_alem_do_teto_para_no_teto_em_vez_de_passar(self):
        """Vinte dias úteis a mais sobre um prazo já adiantado passariam de
        02/10. O motor devolve o teto, não o pedido."""
        from app.services.ouvidoria_prazos import vencimento_prorrogado

        novo = vencimento_prorrogado(self.ENTRADA, _sp(2026, 9, 24, 17, 0), 20, SEM_FERIADO)

        assert novo == _sp(2026, 10, 2, 17, 0)

    def test_feriado_no_meio_empurra_o_teto_e_o_pedido_ganha_o_dia(self):
        from app.services.ouvidoria_prazos import vencimento_prorrogado

        independencia = frozenset({date(2026, 9, 7)})

        novo = vencimento_prorrogado(self.ENTRADA, _sp(2026, 9, 24, 17, 0), 20, independencia)

        assert novo == _sp(2026, 10, 5, 17, 0)

    def test_teto_ja_esgotado_nao_devolve_prazo(self):
        """Caso cujo prazo atual já alcançou o teto não tem o que prorrogar:
        devolver o teto encolheria ou repetiria o vencimento."""
        from app.services.ouvidoria_prazos import vencimento_prorrogado

        assert vencimento_prorrogado(self.ENTRADA, _sp(2026, 10, 2, 17, 0), 5, SEM_FERIADO) is None

    def test_pedido_sem_dias_e_erro_de_programacao(self):
        from app.services.ouvidoria_prazos import vencimento_prorrogado

        with pytest.raises(ValueError):
            vencimento_prorrogado(self.ENTRADA, _sp(2026, 8, 27, 17, 0), 0, SEM_FERIADO)


class TestCumprimentoDaArea:
    """Issue #333, indicador: prorrogação aprovada conta como cumprido; caso
    vencido em silêncio conta como estouro. A régua é o vencimento VIGENTE, o
    que faz a prorrogação aprovada valer sozinha, sem caso especial."""

    def test_resposta_dentro_do_prazo_e_cumprido(self):
        from app.services.ouvidoria_prazos import CUMPRIDO, cumprimento_da_area

        assert cumprimento_da_area(_sp(2026, 8, 27, 17, 0), _sp(2026, 8, 26, 10, 0), _sp(2026, 8, 28, 9, 0)) == CUMPRIDO

    def test_resposta_depois_do_prazo_e_estouro(self):
        from app.services.ouvidoria_prazos import ESTOURADO, cumprimento_da_area

        assert (
            cumprimento_da_area(_sp(2026, 8, 27, 17, 0), _sp(2026, 8, 28, 10, 0), _sp(2026, 8, 28, 11, 0)) == ESTOURADO
        )

    def test_prorrogacao_aprovada_faz_a_mesma_resposta_contar_cumprida(self):
        """A resposta chegou 28/08 e o prazo original era 27/08. Com o
        vencimento prorrogado para 01/09, o caso conta como cumprido."""
        from app.services.ouvidoria_prazos import CUMPRIDO, cumprimento_da_area

        assert cumprimento_da_area(_sp(2026, 9, 1, 17, 0), _sp(2026, 8, 28, 10, 0), _sp(2026, 9, 2, 9, 0)) == CUMPRIDO

    def test_vencido_em_silencio_e_estouro(self):
        from app.services.ouvidoria_prazos import ESTOURADO, cumprimento_da_area

        assert cumprimento_da_area(_sp(2026, 8, 27, 17, 0), None, _sp(2026, 8, 28, 9, 0)) == ESTOURADO

    def test_prazo_correndo_ainda_nao_e_nem_um_nem_outro(self):
        from app.services.ouvidoria_prazos import EM_PRAZO, cumprimento_da_area

        assert cumprimento_da_area(_sp(2026, 8, 27, 17, 0), None, _sp(2026, 8, 26, 9, 0)) == EM_PRAZO

    def test_gravidade_sem_prazo_nao_entra_no_indicador(self):
        from app.services.ouvidoria_prazos import SEM_PRAZO, cumprimento_da_area

        assert cumprimento_da_area(None, None, _sp(2026, 8, 26, 9, 0)) == SEM_PRAZO


class TestEstouroConsumadoSobreviveADevolucao:
    """Issue #374: a devolução por insuficiência apaga o marco T2 e empurra o
    vencimento, e com isso apagava o estouro que a área JÁ tinha consumado.
    Responder atrasado e mal limpava a ficha, o contrário da história 5 do
    PRD #318 ("o número refletir comportamento, não sorte")."""

    # O ciclo novo da devolução: prazo lá na frente, sem resposta ainda.
    VENCIMENTO_NOVO = _sp(2026, 9, 4, 17, 0)
    AGORA = _sp(2026, 9, 2, 9, 0)

    def test_area_que_ja_estourou_continua_estourada_no_ciclo_novo(self):
        """A área respondeu 28/08, depois do vencimento de 27/08, e o ouvidor
        devolveu. Sem a memória do estouro, este caso leria `em_prazo`."""
        from app.services.ouvidoria_prazos import ESTOURADO, cumprimento_da_area

        assert (
            cumprimento_da_area(self.VENCIMENTO_NOVO, None, self.AGORA, estouro_consumado_em=_sp(2026, 8, 28, 10, 0))
            == ESTOURADO
        )

    def test_area_que_respondeu_no_prazo_nao_e_punida_pela_devolucao(self):
        from app.services.ouvidoria_prazos import EM_PRAZO, cumprimento_da_area

        assert cumprimento_da_area(self.VENCIMENTO_NOVO, None, self.AGORA, estouro_consumado_em=None) == EM_PRAZO

    def test_estouro_antigo_manda_mesmo_com_resposta_nova_no_prazo(self):
        """A segunda resposta chegou dentro do prazo novo. O caso NÃO volta a
        contar como cumprido: o estouro do primeiro ciclo é fato consumado."""
        from app.services.ouvidoria_prazos import ESTOURADO, cumprimento_da_area

        assert (
            cumprimento_da_area(
                self.VENCIMENTO_NOVO,
                _sp(2026, 9, 3, 10, 0),
                self.AGORA,
                estouro_consumado_em=_sp(2026, 8, 28, 10, 0),
            )
            == ESTOURADO
        )

    def test_gravidade_sem_prazo_segue_fora_do_indicador(self):
        """Sem vencimento não há régua. Um estouro herdado não pode arrastar
        para dentro do indicador um caso que nunca teve prazo."""
        from app.services.ouvidoria_prazos import SEM_PRAZO, cumprimento_da_area

        assert cumprimento_da_area(None, None, self.AGORA, estouro_consumado_em=_sp(2026, 8, 28, 10, 0)) == SEM_PRAZO


class TestGatilhosDeEscalonamento:
    """A escada de cobrança do PRD #318 (histórias 14 a 17): véspera avisa o
    titular; vencimento, titular + substituto; +24h, gestor; +48h, Diretoria.
    Todos os degraus andam pelo calendário útil."""

    def test_degraus_sobre_fim_de_semana_caem_no_dia_util_certo(self):
        """Vencimento sexta 17h: a véspera é quinta, e os degraus seguintes
        pulam o fim de semana, caindo segunda e terça às 17h."""
        from app.services.ouvidoria_prazos import gatilhos_de_escalonamento

        gatilhos = gatilhos_de_escalonamento(_sp(2026, 8, 19, 9, 0), _sp(2026, 8, 21, 17, 0), SEM_FERIADO)

        assert gatilhos.vespera == _sp(2026, 8, 20, 17, 0)
        assert gatilhos.vencimento == _sp(2026, 8, 21, 17, 0)
        assert gatilhos.mais_24h == _sp(2026, 8, 24, 17, 0)
        assert gatilhos.mais_48h == _sp(2026, 8, 25, 17, 0)

    def test_feriado_desloca_vespera_e_degraus(self):
        """Vencimento terça 17h com a segunda de feriado: a véspera recua até
        sexta. Feriado na quarta empurra +24h para quinta e +48h para sexta."""
        from app.services.ouvidoria_prazos import gatilhos_de_escalonamento

        feriados = frozenset({date(2026, 8, 24), date(2026, 8, 26)})

        gatilhos = gatilhos_de_escalonamento(_sp(2026, 8, 20, 9, 0), _sp(2026, 8, 25, 17, 0), feriados)

        assert gatilhos.vespera == _sp(2026, 8, 21, 17, 0)
        assert gatilhos.mais_24h == _sp(2026, 8, 27, 17, 0)
        assert gatilhos.mais_48h == _sp(2026, 8, 28, 17, 0)

    def test_vencimento_no_meio_do_expediente_mantem_a_hora(self):
        """Caso crítico vence em hora cheia (ex.: terça 10h): cada degrau cai
        no dia útil vizinho na mesma hora, não no fechamento."""
        from app.services.ouvidoria_prazos import gatilhos_de_escalonamento

        gatilhos = gatilhos_de_escalonamento(_sp(2026, 8, 24, 9, 0), _sp(2026, 8, 25, 10, 0), SEM_FERIADO)

        assert gatilhos.vespera == _sp(2026, 8, 24, 10, 0)
        assert gatilhos.mais_24h == _sp(2026, 8, 26, 10, 0)
        assert gatilhos.mais_48h == _sp(2026, 8, 27, 10, 0)

    def test_prazo_curto_nao_tem_vespera(self):
        """Crítico responde em 4 horas úteis: validado segunda 10h, vence
        segunda 14h. A véspera cairia sexta, antes do caso existir, e avisar
        "vence amanhã" numa data anterior à entrada não é aviso nenhum."""
        from app.services.ouvidoria_prazos import gatilhos_de_escalonamento

        gatilhos = gatilhos_de_escalonamento(_sp(2026, 8, 24, 10, 0), _sp(2026, 8, 24, 14, 0), SEM_FERIADO)

        assert gatilhos.vespera is None
        assert gatilhos.vencimento == _sp(2026, 8, 24, 14, 0)
        assert gatilhos.mais_24h == _sp(2026, 8, 25, 14, 0)

    def test_gravidade_sem_prazo_nao_tem_escada(self):
        """Mesmo contrato do resto do motor: sem vencimento, não há degrau
        nenhum para o job de cobrança disparar."""
        from app.services.ouvidoria_prazos import gatilhos_de_escalonamento

        assert gatilhos_de_escalonamento(_sp(2026, 8, 24, 9, 0), None, SEM_FERIADO) is None


import os  # noqa: E402
import sys  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

# Recorte da tabela da especificação da Diretoria (seção 7.2) que o motor usa.
SEED_DA_SPEC = [
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _TabelaFake:
    """Fake do PostgREST no que importa: filtros, projeção do select, insert,
    update e delete. Mesmo espírito do fake de test_ouvidoria_manifestacao."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def _projetar(self, row: dict) -> dict:
        return dict(row) if self._colunas is None else {c: row.get(c) for c in self._colunas}

    def insert(self, payload):
        self._insert = payload
        return self

    def upsert(self, payload, **_kw):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        # `.get`: colunas preenchidas por default do banco (ocorrido_em) não
        # existem na linha que a aplicação inseriu, e ordenar por elas aqui
        # não pode explodir.
        self.rows = sorted(self.rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        return self

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            self.rows.extend(dict(n) for n in novos)
            return type("R", (), {"data": [dict(n) for n in novos]})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._delete:
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TabelaFake(self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, _params: dict):
        """Efeito da função `ouvidoria_ultimo_movimento` (migration 092, issue
        #484): o instante do movimento mais recente de cada caso, agregado da
        trilha. É o outro lado da comparação que acende o ponto de novidade na
        fila do ouvidor."""
        assert nome == "ouvidoria_ultimo_movimento", f"RPC inesperada: {nome}"
        ultimo: dict[str, str] = {}
        for mov in self.tabelas.get("ouvidoria_movimentos", []):
            quando = mov.get("ocorrido_em")
            if quando is None:
                continue
            caso = str(mov["manifestacao_id"])
            ultimo[caso] = max(str(quando), ultimo.get(caso, ""))
        agregado = [{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()]
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": agregado})()})()


def _prazos_semeados() -> list[dict]:
    return [dict(linha) for linha in SEED_DA_SPEC]


def _client(monkeypatch, participante: dict | None, **tabelas):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = _SupabaseFake(
        {
            "ouvidoria_prazos": tabelas.get("prazos", _prazos_semeados()),
            "ouvidoria_prazos_historico": tabelas.get("historico", []),
            "ouvidoria_feriados": tabelas.get("feriados", []),
            "ouvidoria_protocolos": tabelas.get("protocolos", []),
            "ouvidoria_acessos": [],
        }
    )

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestLeituraDaTabelaDePrazos:
    """A tabela de prazos é a fonte do motor: quem trabalha na Ouvidoria
    precisa vê-la para saber o prazo de cada gravidade."""

    @pytest.mark.parametrize("perfil", [OUVIDOR, DIRETORIA])
    def test_perfil_da_ouvidoria_le_a_tabela(self, monkeypatch, perfil):
        client, _ = _client(monkeypatch, perfil)

        r = client.get("/api/ouvidoria/prazos")

        assert r.status_code == 200
        celulas = {(p["gravidade"], p["marco"]): p for p in r.json()["prazos"]}
        assert celulas[("alto", "area_resposta")]["valor"] == 2
        assert celulas[("alto", "area_resposta")]["unidade"] == "dias_uteis"

    def test_papel_de_reunioes_nao_le_a_tabela(self, monkeypatch):
        client, _ = _client(monkeypatch, SECRETARIA)

        assert client.get("/api/ouvidoria/prazos").status_code == 403


class TestEdicaoPelaDiretoria:
    """RN-21: só a diretoria executiva edita, e toda edição deixa histórico."""

    def test_diretoria_edita_um_prazo_e_a_mudanca_vale(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 3, "unidade": "dias_uteis"})

        assert r.status_code == 200
        assert r.json()["valor"] == 3
        vigente = next(
            p for p in supabase.tabelas["ouvidoria_prazos"] if (p["gravidade"], p["marco"]) == ("alto", "area_resposta")
        )
        assert vigente["valor"] == 3, "A edição não passou a valer para validação nova"

    def test_edicao_registra_de_que_para_que_e_quem_mudou(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA)

        client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 3, "unidade": "dias_uteis"})

        historico = supabase.tabelas["ouvidoria_prazos_historico"]
        assert len(historico) == 1
        registro = historico[0]
        assert registro["valor_anterior"] == 2
        assert registro["valor_novo"] == 3
        assert registro["autor_id"] == DIRETORIA["id"]
        assert registro["autor_nome"] == DIRETORIA["nome_completo"]

    def test_salvar_o_mesmo_valor_nao_polui_o_historico(self, monkeypatch):
        """O histórico é append-only e não pode ser limpo depois: passar pelas
        células sem mudar nada não pode deixar 12 registros de "mudou de 2 para
        2" no que a Diretoria vai ler amanhã."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 2, "unidade": "dias_uteis"})

        assert r.status_code == 200
        assert supabase.tabelas["ouvidoria_prazos_historico"] == []

    def test_prazo_absurdo_e_recusado(self, monkeypatch):
        """Prazo tem teto: o motor caminha dia a dia pelo calendário, e um
        valor sem limite viraria um request travado quando alguém validasse
        a manifestação."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 10_000_000, "unidade": "dias_uteis"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_prazos_historico"] == []

    @pytest.mark.parametrize("papel", [OUVIDOR, SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_diretoria_nao_edita(self, monkeypatch, papel):
        """O ouvidor entra nesta lista de propósito: ele usa o prazo, quem
        define é a Diretoria (RN-21)."""
        client, supabase = _client(monkeypatch, papel)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 9, "unidade": "dias_uteis"})

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_prazos_historico"] == []

    def test_historico_lido_de_volta_traz_quem_mudou_e_de_quanto_para_quanto(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA)
        client.put("/api/ouvidoria/prazos/medio/area_resposta", json={"valor": 6, "unidade": "dias_uteis"})

        r = client.get("/api/ouvidoria/prazos/historico")

        assert r.status_code == 200
        registro = r.json()["historico"][0]
        assert (registro["gravidade"], registro["marco"]) == ("medio", "area_resposta")
        assert registro["valor_anterior"] == 4
        assert registro["valor_novo"] == 6
        assert registro["autor_nome"] == DIRETORIA["nome_completo"]
        # Contrato fechado: coluna nova na tabela não vira campo novo na
        # resposta sem alguém decidir isso (padrão do módulo).
        assert "autor_id" not in registro

    def test_caso_ja_despachado_mantem_o_prazo_que_o_setor_recebeu(self, monkeypatch):
        """Critério de aceite da #322: a edição vale para validação nova; caso
        já despachado não é recalculado."""
        despachada = {
            "id": "uuid-7",
            "status": "aguardando_area",
            "gravidade": "alto",
            "prazo_area_em": "2026-08-25T20:00:00+00:00",
        }
        client, supabase = _client(monkeypatch, DIRETORIA, protocolos=[despachada])

        client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 9, "unidade": "dias_uteis"})

        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == "2026-08-25T20:00:00+00:00"


class TestFeriadosAdministraveis:
    """RN-22: a lista de feriados é tabela, não constante do código. Quem
    administra é a Diretoria Executiva, como na tabela de prazos."""

    SAO_JORGE = {"data": "2026-04-23", "nome": "Sao Jorge", "abrangencia": "estadual_rj"}

    def test_perfil_da_ouvidoria_le_os_feriados(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, feriados=[dict(self.SAO_JORGE)])

        r = client.get("/api/ouvidoria/feriados")

        assert r.status_code == 200
        assert r.json()["feriados"][0]["data"] == "2026-04-23"

    def test_diretoria_cadastra_feriado(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA, feriados=[])

        r = client.post("/api/ouvidoria/feriados", json=self.SAO_JORGE)

        assert r.status_code == 201
        assert supabase.tabelas["ouvidoria_feriados"][0]["nome"] == "Sao Jorge"

    def test_diretoria_remove_feriado(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA, feriados=[dict(self.SAO_JORGE)])

        r = client.delete("/api/ouvidoria/feriados/2026-04-23")

        assert r.status_code == 204
        assert supabase.tabelas["ouvidoria_feriados"] == []

    @pytest.mark.parametrize("papel", [OUVIDOR, SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_diretoria_nao_mexe_no_calendario(self, monkeypatch, papel):
        client, supabase = _client(monkeypatch, papel, feriados=[dict(self.SAO_JORGE)])

        assert client.post("/api/ouvidoria/feriados", json={**self.SAO_JORGE, "data": "2026-05-05"}).status_code == 403
        assert client.delete("/api/ouvidoria/feriados/2026-04-23").status_code == 403
        assert len(supabase.tabelas["ouvidoria_feriados"]) == 1


def _indice(protocolo: str, **overrides) -> dict:
    row = {
        "id": f"uuid-{protocolo}",
        "numero": 7,
        "protocolo": protocolo,
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "aguardando_area",
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas.",
        "conversa_id": "conv-4711",
        "sigilo_reforcado": False,
        "gravidade": "alto",
        "prazo_area_em": None,
    }
    row.update(overrides)
    return row


class TestPainelUsaOMotorNovo:
    """Critério de aceite da #322: o painel mostra o prazo calculado e o
    rótulo "vence em X", em vez do prazo de 7 dias corridos da fundação."""

    def test_caso_com_prazo_vencido_vem_marcado_como_estourado(self, monkeypatch):
        vencida = _indice("2026-0007", prazo_area_em="2020-01-06T20:00:00+00:00")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[vencida])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["prazo_estourado"] is True
        assert item["rotulo_prazo"].startswith("vencido há"), item["rotulo_prazo"]

    def test_caso_dentro_do_prazo_traz_a_contagem_regressiva(self, monkeypatch):
        no_prazo = _indice("2026-0008", prazo_area_em="2099-01-06T20:00:00+00:00")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[no_prazo])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["prazo_estourado"] is False
        assert item["rotulo_prazo"].startswith("vence em"), item["rotulo_prazo"]

    def test_caso_ainda_sem_gravidade_nao_finge_prazo(self, monkeypatch):
        """Enquanto o ouvidor não classifica, não existe prazo da área: o
        painel diz isso em vez de inventar uma data."""
        sem_classificacao = _indice("2026-0009", gravidade=None, status="em_classificacao")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[sem_classificacao])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["gravidade"] is None
        assert item["prazo_area_em"] is None
        assert item["prazo_estourado"] is False
        assert item["rotulo_prazo"] == "sem prazo definido"
        assert item["minutos_uteis_restantes"] is None

    def test_painel_manda_a_folga_em_tempo_util_para_o_destaque(self, monkeypatch):
        """O destaque de "vence logo" mede na mesma régua do rótulo. Medir em
        dias corridos no navegador apagaria o alerta justo quando o vencimento
        atravessa fim de semana, que é quando ele mais importa."""
        no_prazo = _indice("2026-0011", prazo_area_em="2099-01-06T20:00:00+00:00")
        vencida = _indice("2026-0012", prazo_area_em="2020-01-06T20:00:00+00:00")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[no_prazo, vencida])

        itens = {p["protocolo"]: p for p in client.get("/api/ouvidoria/protocolos").json()["protocolos"]}

        assert itens["2026-0011"]["minutos_uteis_restantes"] > 0
        assert itens["2026-0012"]["minutos_uteis_restantes"] == 0

    def test_indice_do_painel_nao_vaza_campo_do_dossie(self, monkeypatch):
        """O prazo novo entra no índice; relato e identificação continuam
        atrás do perfil da Ouvidoria (ADR 0034, decisão 8).

        `sigilo_reforcado` saiu desta lista na issue #372: ele passou a entrar
        no índice porque a tela de validação abre a partir dele e precisa
        mostrar a marca de sigilo no estado real. Não conta como vazamento
        porque a linha sigilosa não chega a quem está fora da Ouvidoria: para
        este público o campo é sempre falso, e a asserção abaixo prova isso."""
        com_dossie = _indice("2026-0010", relato_integral="Relato inteiro", manifestante_nome="Joana")
        client, _ = _client(monkeypatch, SECRETARIA, protocolos=[com_dossie])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["gravidade"] == "alto"
        assert item["sigilo_reforcado"] is False
        for campo in ("relato_integral", "manifestante_nome"):
            assert campo not in item, f"Campo do Dossiê vazou no índice: {campo}"


class TestRegistroNoApp:
    """Os testes acima montam um FastAPI próprio: este prova que as rotas
    existem no app de verdade (mesmo padrão de test_painel_ouvidoria)."""

    def test_rotas_do_motor_existem_no_app_real(self):
        from app.main import app as app_real

        paths = app_real.openapi()["paths"]
        assert "get" in paths["/api/ouvidoria/prazos"]
        assert "put" in paths["/api/ouvidoria/prazos/{gravidade}/{marco}"]
        assert "get" in paths["/api/ouvidoria/prazos/historico"]
        assert {"get", "post"} <= set(paths["/api/ouvidoria/feriados"])
        assert "delete" in paths["/api/ouvidoria/feriados/{data}"]


class TestMigracaoDoMotorDePrazos:
    """A migration é o contrato de dados do motor: seed da spec, histórico
    append-only e RLS default-deny (padrão da casa)."""

    MIGRATION = "065_ouvidoria_prazos_calendario.sql"

    def _ddl(self) -> str:
        caminho = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations", self.MIGRATION)
        with open(caminho, encoding="utf-8") as f:
            return f.read()

    @pytest.mark.parametrize("celula", SEED_DA_SPEC)
    def test_seed_traz_os_valores_da_especificacao_da_diretoria(self, celula):
        """Seção 7.2 da especificação de 19/08/2026, coluna "Área responde"."""
        ddl = self._ddl()
        valor = "NULL" if celula["valor"] is None else str(celula["valor"])
        esperado = f"('{celula['gravidade']}', '{celula['marco']}', {valor},"
        linha = next((ln for ln in (" ".join(bruta.split()) for bruta in ddl.splitlines()) if esperado in ln), None)
        assert linha is not None, f"Seed ausente ou diferente da spec: {celula}"
        assert celula["unidade"] in linha, f"Unidade do seed diverge da spec: {celula}"

    def test_historico_de_prazo_e_append_only(self):
        ddl = self._ddl().lower()
        assert "trg_ouvidoria_prazos_historico_sem_update" in ddl
        assert "trg_ouvidoria_prazos_historico_sem_delete" in ddl

    @pytest.mark.parametrize("tabela", ["ouvidoria_prazos", "ouvidoria_prazos_historico", "ouvidoria_feriados"])
    def test_tabela_nova_nasce_com_rls(self, tabela):
        ddl = self._ddl().lower()
        assert f"alter table {tabela} enable row level security" in ddl, (
            f"Tabela {tabela} sem RLS default-deny (padrão da casa: 009/041/051/063/064)"
        )

    def test_migration_e_idempotente(self):
        ddl = self._ddl().lower()
        assert ddl.count("create table if not exists") == 3
        assert "on conflict" in ddl, "Rodar a migration duas vezes duplicaria o seed"
