"""Os quatro marcos do caso e o tempo decorrido em cada trecho (issue #480,
PRD #468, RN-55, diagnóstico da Diretoria D-05 e D-10).

Módulo fundo e **puro**, no molde do motor de prazos de onde ele tira a régua:
recebe o caso, o instante da medição e os feriados, e devolve o que a página do
caso mostra. Não lê banco, não consulta o relógio e não conhece HTTP.

A pergunta que a página responde é "onde este caso emperrou": entrada (T0),
validação (T1), resposta da área (T2) e conclusão (T3), com o tempo de
EXPEDIENTE que separa cada par. Dias corridos serviriam para nada aqui, porque
o prazo que a Diretoria cobra corre no Calendário útil: dizer "o setor levou 3
dias" onde a área teve 1 dia de mesa acusaria de lentidão quem respondeu na
segunda um caso de sexta.

QUAL PRAZO CONCLUSIVO MANDA NESTA TELA (a decisão que a fatia #479 deixou em
aberto). Existem duas fontes, e elas divergem de propósito:

1. `ouvidoria_protocolos.prazo_conclusivo_em`, congelado na validação e sem
   nenhum crédito de prorrogação ou de pausa (migration 091);
2. o conclusivo recalculado em `ouvidoria_metricas._vencimento_do_trecho`, que
   soma ao vencimento o crédito já concedido ao prazo da área.

**Esta tela lê a coluna congelada (1).** Três motivos, nesta ordem:

* o PRD #468 crava. A história 11 pede o conclusivo "congelado na validação,
  para mudança futura na tabela de prazos não recalcular caso já despachado", e
  a história 12 pede que gravidade sem célula conclusiva "simplesmente não
  exiba esse prazo". A coluna nasceu na fatia #479 para esta página ler;
* a página do caso e o relatório respondem perguntas diferentes. Aqui a
  pergunta é "o que foi prometido a ESTE manifestante", e a resposta é o
  compromisso assumido no despacho. No relatório a pergunta é "quanto o
  hospital cumpre", e ali dar ao conclusivo o mesmo crédito do prazo da área é
  o que impede o PDF de acusar de atraso uma prorrogação que a própria
  Diretoria concedeu. As duas leituras estão certas, cada uma no seu lugar;
* recalcular na leitura faria editar a tabela de prazos mudar o passado, que é
  exatamente o que o Motor de prazos proíbe (CONTEXT.md).

O preço da escolha é que o número pode ficar visualmente incoerente: em caso
prorrogado, o conclusivo congelado cai ANTES do prazo da área, e em caso
reaberto ele já nasce vencido. A tela não conserta nem esconde o número, ela o
NOMEIA: as duas notas abaixo dizem, em português, por que o relógio do
manifestante e o da área estão onde estão.
"""

from __future__ import annotations

import datetime as dt

from app.services.ouvidoria_prazos import (
    FUSO,
    esta_vencido,
    minutos_uteis_entre,
    rotular_vencimento,
)
from app.services.ouvidoria_prorrogacao import entrada_da_manifestacao

ENCERRADO = "encerrado"

# Os quatro marcos, na ordem em que o caso os atravessa (RN-55). Cada um a
# partir do T1 fecha o trecho que o anterior abriu, e o NOME do trecho já diz
# de quem é aquele tempo: é o que responde "onde emperrou, e com quem". Um
# campo separado com o dono do trecho não entra aqui porque a tela não teria o
# que fazer com ele, e código que ninguém consome não tem quem o corrija.
#
# O T2 ao T3 é da Ouvidoria, e não da área: depois que o setor responde, quem
# fecha o caso com quem manifestou é a Ouvidoria. Sem esse trecho separado, o
# gargalo da própria Ouvidoria ficaria escondido dentro do total (D-05).
#
# O T0 não sai de coluna própria: a entrada é o instante REAL do contato
# (`contato_em`), com `data_abertura` de fallback nos casos antigos. Quem sabe
# ler os dois é `entrada_da_manifestacao`, o mesmo T0 que o teto da prorrogação
# usa: dois T0 diferentes no mesmo caso seriam dois processos diferentes.
MARCOS = (
    {"chave": "T0", "rotulo": "Entrada", "coluna": None, "trecho": None},
    {"chave": "T1", "rotulo": "Validação", "coluna": "validada_em", "trecho": "Triagem da Ouvidoria"},
    {"chave": "T2", "rotulo": "Resposta da área", "coluna": "respondida_em", "trecho": "Resposta da área"},
    {"chave": "T3", "rotulo": "Conclusão", "coluna": "encerrada_em", "trecho": "Desfecho pela Ouvidoria"},
)

# Os dois prazos que andam junto dos marcos: o da área (T1 ate T2) e o do caso
# inteiro (T0 ate T3, o compromisso com quem manifestou, D-10).
PRAZOS = (
    {"chave": "area", "rotulo": "Prazo da área", "coluna": "prazo_area_em"},
    {"chave": "conclusivo", "rotulo": "Prazo conclusivo", "coluna": "prazo_conclusivo_em"},
)

# As três situações de um prazo, que a coluna nula sozinha não separa.
DEFINIDO = "definido"
# Nulo porque o despacho ainda não aconteceu: o prazo sai da validação.
AGUARDANDO_VALIDACAO = "aguardando_validacao"
# Nulo porque a gravidade não tem aquela célula na tabela (o crítico não tem
# conclusiva fixa; o baixo não passa pela área). Aqui não existe prazo, e a
# tela não mostra linha nenhuma em vez de inventar data (PRD #468, história 12).
SEM_PRAZO = "sem_prazo"

# As notas afirmam o FATO que a tela mostra, nunca a causa dele. A causa não
# está toda na linha do caso: a prorrogação vive em outra tabela, e os dois
# prazos têm origens diferentes (o conclusivo conta da entrada, o da área conta
# da validação). Com os valores da tabela de prazos, QUALQUER caso que demore
# mais do que a diferença entre os dois na triagem nasce com o vencimento da
# área depois do conclusivo, sem prorrogação nenhuma e sem pausa nenhuma. Dizer
# ali "a prorrogação moveu o prazo" inocentaria a demora da própria Ouvidoria,
# que é justamente o que este PRD existe para expor (D-05).
NOTA_AREA_VENCE_DEPOIS = (
    "O vencimento da área está depois deste prazo. O prazo conclusivo conta da entrada da "
    "manifestação e não se move: nem a prorrogação da área nem a espera pelo manifestante o empurram."
)

# A terceira situação que o comentário do PRD #468 deixou em aberto: o caso que
# passou da conclusiva ainda na fila de triagem nasce validado com o prazo já
# no passado. O número está certo (é contado de T0, como a spec pede), e o que
# faltava decidir era como a tela mostra isso sem mentir. Ela nomeia: o tempo
# foi consumido antes do despacho, e não pela área.
NOTA_VENCIDO_NA_TRIAGEM = (
    "Este prazo já estava vencido quando o caso foi validado: ele conta da entrada da "
    "manifestação, e o tempo foi consumido antes de a área ser acionada."
)

NOTA_REABERTURA = (
    "Prazo da primeira tramitação: a reabertura por reincidência dá prazo novo à área, "
    "e não compra prazo novo com quem manifestou."
)


# O acuse de recebimento (issue #493, ADR 0042). Ele NÃO entra na lista MARCOS
# acima, e a razão é o encadeamento: cada marco de lá fecha o trecho que o
# anterior abriu, e enfiar o acuse entre T0 e T1 faria "Triagem da Ouvidoria"
# passar a medir do acuse até a validação, ou seja, o gargalo da própria
# Ouvidoria encolheria na tela por causa de um email. Ele é um fato do caso ao
# lado da linha do tempo, e não um degrau dela.
ACUSE_ENVIADO = "enviado"
ACUSE_EM_ENVIO = "em_envio"
ACUSE_FALHA_NO_ENVIO = "falha_no_envio"
ACUSE_SEM_CONTATO = "sem_contato"
ACUSE_PENDENTE = "pendente"

ROTULO_ACUSE = "Acuse de recebimento"

NOTA_ACUSE_SEM_CONTATO = (
    "Sem canal para avisar: o caso é anônimo ou o contato informado não tem email. "
    "O aviso de recebimento não foi enviado, e este caso não conta como falha de retorno."
)
NOTA_ACUSE_PENDENTE = "Este caso foi aberto antes de o aviso automático de recebimento existir."
NOTA_ACUSE_FALHA = (
    "O provedor de email recusou a mensagem nas tentativas previstas. Reenvie pelo registro de notificações deste caso."
)

# Como o status da linha em `ouvidoria_notificacoes` vira a frase da tela. É
# ele que manda, e não o carimbo do caso: o carimbo diz que o acuse foi GERADO
# (é gravado antes de o provedor responder, de propósito), e a tela não pode
# afirmar entrega sem olhar a entrega. Sem esta tradução, o caso cujo email
# esgotou as tentativas continuaria dizendo "enviado ao manifestante", que é
# justamente a mentira que o precedente da issue #373 mandou não contar.
_SITUACAO_POR_STATUS = {
    "enviada": ACUSE_ENVIADO,
    "falha": ACUSE_FALHA_NO_ENVIO,
    "agendada": ACUSE_EM_ENVIO,
    "enviando": ACUSE_EM_ENVIO,
}


def acuse_do_caso(caso: dict, status_do_envio: str | None = None) -> dict:
    """O que a página do caso diz sobre o aviso de recebimento (RN-56).

    Cinco situações, e cada uma precisa ser distinta na tela: entregue, ainda
    saindo, envio que falhou, caso que não tinha para onde ser avisado
    (marcação própria da decisão 4 do ADR 0042) e caso que simplesmente não
    passou por aqui, que são os anteriores a esta fatia.

    `status_do_envio` é o status da notificação do acuse daquele caso, lido por
    quem monta o Dossiê, e ele MANDA sobre o carimbo. Duas razões, e as duas
    são a tela não mentir:

    * o carimbo diz que o acuse foi GERADO, e é gravado antes de o provedor
      responder. Traduzi-lo direto em "enviado" faria a página garantir ao
      ouvidor um aviso que pode ter esgotado as tentativas;
    * existir notificação sem carimbo é possível, porque o carimbo tem guarda
      própria e engole a própria falha. Concluir "pendente" ali diria, para um
      caso aberto hoje, que ele é anterior ao aviso automático.

    Status nulo com carimbo presente cai em "em envio", que é o que se pode
    afirmar com honestidade: o acuse foi gerado, e daqui não dá para dizer que
    chegou."""
    enviado = _instante(caso.get("acuse_recebimento_em"))
    if status_do_envio is not None or enviado is not None:
        situacao = _SITUACAO_POR_STATUS.get(status_do_envio or "", ACUSE_EM_ENVIO)
        return {
            "rotulo": ROTULO_ACUSE,
            "em": enviado.isoformat() if enviado else None,
            "situacao": situacao,
            "nota": NOTA_ACUSE_FALHA if situacao == ACUSE_FALHA_NO_ENVIO else None,
        }
    sem_contato = _instante(caso.get("acuse_sem_contato_em"))
    if sem_contato is not None:
        return {
            "rotulo": ROTULO_ACUSE,
            "em": sem_contato.isoformat(),
            "situacao": ACUSE_SEM_CONTATO,
            "nota": NOTA_ACUSE_SEM_CONTATO,
        }
    return {"rotulo": ROTULO_ACUSE, "em": None, "situacao": ACUSE_PENDENTE, "nota": NOTA_ACUSE_PENDENTE}


# O aviso de encerramento ao manifestante (issue #494, ADR 0042, decisão 3).
# Mesmo desenho do acuse, e pelo mesmo motivo: é um fato do caso ao lado da
# linha do tempo, e não um degrau dela. O marco T3 continua sendo `encerrada_em`
# (o ato do ouvidor), e não a hora em que o email saiu: amarrar o T3 ao provedor
# de email faria o tempo do trecho "Desfecho pela Ouvidoria" crescer por causa
# de uma retentativa.
AVISO_ENVIADO = "enviado"
AVISO_EM_ENVIO = "em_envio"
AVISO_FALHA_NO_ENVIO = "falha_no_envio"
AVISO_SEM_CONTATO = "sem_contato"
AVISO_PENDENTE = "pendente"

ROTULO_AVISO_ENCERRAMENTO = "Aviso de encerramento"

NOTA_AVISO_SEM_CONTATO = (
    "Sem canal para avisar: o caso é anônimo ou o contato informado não tem email. "
    "O desfecho não foi enviado, e este caso fica fora do indicador de resposta conclusiva."
)
NOTA_AVISO_PENDENTE = "O caso ainda não foi encerrado, ou foi encerrado antes de o aviso automático existir."
NOTA_AVISO_FALHA = (
    "O provedor de email recusou a mensagem nas tentativas previstas. Reenvie pelo registro de notificações deste caso."
)


def aviso_do_encerramento(caso: dict, status_do_envio: str | None = None) -> dict:
    """O que a página do caso diz sobre o aviso de encerramento (RN-80).

    Cinco situações, as mesmas do acuse e pela mesma razão: entregue, ainda
    saindo, envio que falhou, caso que não tinha para onde ser avisado (marcação
    própria da decisão 4 do ADR 0042) e caso que simplesmente não passou por
    aqui, que são os encerrados antes desta fatia e os que ainda estão abertos.

    `status_do_envio` MANDA sobre o carimbo, e essa é a regra que importa: o
    carimbo diz que o aviso foi GERADO, e é gravado antes de o provedor
    responder. Traduzi-lo direto em "enviado" faria a página garantir ao ouvidor
    um desfecho entregue que pode ter esgotado as tentativas, que é justamente a
    mentira que o precedente da issue #373 mandou não contar."""
    avisado = _instante(caso.get("encerramento_avisado_em"))
    if status_do_envio is not None or avisado is not None:
        situacao = _SITUACAO_POR_STATUS.get(status_do_envio or "", AVISO_EM_ENVIO)
        return {
            "rotulo": ROTULO_AVISO_ENCERRAMENTO,
            "em": avisado.isoformat() if avisado else None,
            "situacao": situacao,
            "nota": NOTA_AVISO_FALHA if situacao == AVISO_FALHA_NO_ENVIO else None,
        }
    sem_contato = _instante(caso.get("encerramento_sem_contato_em"))
    if sem_contato is not None:
        return {
            "rotulo": ROTULO_AVISO_ENCERRAMENTO,
            "em": sem_contato.isoformat(),
            "situacao": AVISO_SEM_CONTATO,
            "nota": NOTA_AVISO_SEM_CONTATO,
        }
    return {"rotulo": ROTULO_AVISO_ENCERRAMENTO, "em": None, "situacao": AVISO_PENDENTE, "nota": NOTA_AVISO_PENDENTE}


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto, ou None quando vazio.

    Valor sem fuso vale como hora de parede do hospital, a mesma leitura que
    `entrada_da_manifestacao` já faz com `contato_em`. As colunas são
    `timestamptz` e chegam com fuso, então isto é cinto de segurança: o motor
    recusa instante ingênuo de propósito, e um `ValueError` subindo daqui
    derrubaria a página inteira do caso por causa de um dado torto."""
    if not bruto:
        return None
    momento = dt.datetime.fromisoformat(str(bruto))
    return momento if momento.tzinfo else momento.replace(tzinfo=FUSO)


def _medido_em(caso: dict, agora: dt.datetime) -> dt.datetime:
    """O instante contra o qual o que ainda está aberto é medido.

    Caso parado aguardando o manifestante mede no instante em que parou, a
    mesma régua do painel (`_projetar_prazo`) e das métricas: medir contra o
    relógio de parede cobraria da área uma espera que não é dela."""
    return _instante(caso.get("pausada_em")) or agora


def _marco_em(caso: dict, marco: dict) -> dt.datetime | None:
    """Quando aquele marco aconteceu NESTE caso, ou None se ainda não aconteceu.

    O T3 só vale enquanto o caso está encerrado. A reabertura por reincidência
    preserva `encerrada_em` de propósito (é o marco da tramitação anterior, que
    os relatórios leem), mas o caso voltou a tramitar: lido cru, aquele carimbo
    apresentaria como concluído um caso que está aberto agora. É a mesma guarda
    de `ouvidoria_metricas._marco_que_fecha`."""
    if marco["coluna"] is None:
        return entrada_da_manifestacao(caso)
    if marco["chave"] == "T3" and caso.get("status") != ENCERRADO:
        return None
    return _instante(caso.get(marco["coluna"]))


def _nota_do_prazo(
    caso: dict, chave: str, vencimento: dt.datetime | None, prazo_area: dt.datetime | None
) -> str | None:
    """Por que o relógio do manifestante está onde está.

    Só o conclusivo tem nota, e só nos dois casos em que o número congelado
    contraria a leitura ingênua da tela. Fora deles a nota seria ruído.

    Cada nota afirma o FATO, e não a causa dele: a causa não está toda na linha
    do caso (a prorrogação vive em outra tabela) e chutá-la é pior do que
    calar. A ordem importa: vencido já na validação explica melhor do que
    "vence depois", e engloba esse caso."""
    if chave != "conclusivo" or vencimento is None:
        return None
    if caso.get("reaberta_em"):
        return NOTA_REABERTURA
    validada_em = _instante(caso.get("validada_em"))
    if validada_em is not None and vencimento <= validada_em:
        return NOTA_VENCIDO_NA_TRIAGEM
    if prazo_area is not None and prazo_area > vencimento:
        return NOTA_AREA_VENCE_DEPOIS
    return None


def marcos_do_caso(caso: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> dict:
    """Os quatro marcos com o tempo decorrido, e os dois prazos ao lado deles.

    Devolve as duas listas na ordem em que a página as mostra. Marco que não
    aconteceu vem `pendente`, com `em` nulo: preencher com o marco anterior ou
    com o relógio faria a tela inventar um fato do caso.

    Trecho cujo marco de ABERTURA ainda não aconteceu não tem tempo, e não tem
    zero: zero diria que a área respondeu na hora quando ela nem foi acionada.
    Trecho aberto conta até a medição e se declara `em_curso`, que é como o
    caso parado na fila mostra o tempo que já queimou."""
    instantes = {marco["chave"]: _marco_em(caso, marco) for marco in MARCOS}
    medido_em = _medido_em(caso, agora)

    linhas = []
    abertura: dt.datetime | None = None
    for marco in MARCOS:
        em = instantes[marco["chave"]]
        if marco["coluna"] is None or abertura is None:
            minutos, em_curso = None, False
        elif em is not None:
            minutos, em_curso = minutos_uteis_entre(abertura, em, feriados), False
        else:
            minutos, em_curso = minutos_uteis_entre(abertura, medido_em, feriados), True
        linhas.append(
            {
                "chave": marco["chave"],
                "rotulo": marco["rotulo"],
                "em": em.isoformat() if em else None,
                "pendente": em is None,
                "trecho": marco["trecho"],
                "minutos_uteis": minutos,
                "em_curso": em_curso,
                # O encerramento que a reabertura preservou. Fica dito pelo que
                # é, em vez de sumir da tela ou passar por conclusão do ciclo
                # corrente.
                "tramitacao_anterior_em": (
                    _instante(caso.get("encerrada_em")).isoformat()
                    if marco["chave"] == "T3" and em is None and caso.get("encerrada_em")
                    else None
                ),
            }
        )
        abertura = em

    prazo_area = _instante(caso.get("prazo_area_em"))
    prazos = []
    for prazo in PRAZOS:
        vencimento = _instante(caso.get(prazo["coluna"]))
        # O prazo da área congela a medida na pausa porque o vencimento dele é
        # empurrado na retomada; o conclusivo nunca é empurrado, e congelar a
        # medida dele daria ao caso um crédito que ninguém concedeu.
        medida = medido_em if prazo["chave"] == "area" else agora
        prazos.append(
            {
                "chave": prazo["chave"],
                "rotulo": prazo["rotulo"],
                "em": vencimento.isoformat() if vencimento else None,
                "situacao": (
                    DEFINIDO if vencimento else (AGUARDANDO_VALIDACAO if not caso.get("validada_em") else SEM_PRAZO)
                ),
                # A mesma frase do painel e do email do setor: painel, email e
                # página do caso nunca dizem prazos diferentes.
                "rotulo_prazo": rotular_vencimento(vencimento, medida, feriados) if vencimento else None,
                "estourado": esta_vencido(vencimento, medida),
                "nota": _nota_do_prazo(caso, prazo["chave"], vencimento, prazo_area),
            }
        )

    return {"marcos": linhas, "prazos": prazos}
