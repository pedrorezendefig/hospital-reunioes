/**
 * Os quatro marcos do caso e o tempo decorrido em cada trecho (issue #480,
 * PRD #468, RN-55, diagnóstico D-05 e D-10).
 *
 * Tudo o que é conta vem pronto do servidor: o tempo chega em minutos de
 * EXPEDIENTE, já contado no calendário útil do hospital (feriados inclusos), e
 * a contagem regressiva de cada prazo chega como frase feita, a mesma do
 * painel e do email do setor. O navegador não recalcula calendário útil.
 *
 * O que mora aqui é só a régua do que a tela diz de cada linha, que é onde
 * ficaria fácil mentir: marco que não aconteceu, trecho que nem começou e
 * prazo que não existe.
 */

import { formatarEsperaUtil } from "@/lib/ouvidoria/prazo";

/** Um dos quatro marcos, com o trecho que ele fecha. */
export interface MarcoDoCaso {
  chave: string;
  rotulo: string;
  /** Instante em ISO, ou nulo quando o marco ainda não aconteceu. */
  em: string | null;
  pendente: boolean;
  /** O nome do trecho que este marco fecha. Nulo no T0, que não fecha nada. */
  trecho: string | null;
  responsavel: string | null;
  /** Minutos de expediente do trecho. Nulo quando o trecho nem começou. */
  minutos_uteis: number | null;
  em_curso: boolean;
  /** O encerramento que a reabertura por reincidência preservou. */
  tramitacao_anterior_em: string | null;
}

export type SituacaoDoPrazo = "definido" | "aguardando_validacao" | "sem_prazo";

export interface PrazoDoCaso {
  chave: string;
  rotulo: string;
  em: string | null;
  situacao: SituacaoDoPrazo;
  /** A contagem regressiva do motor ("vence em 2 dias úteis"). */
  rotulo_prazo: string | null;
  estourado: boolean;
  /** Por que o relógio está onde está, quando o número precisa de explicação. */
  nota: string | null;
}

export const MARCO_PENDENTE = "Ainda não aconteceu";

/** O prazo que nasce no despacho e ainda não foi despachado. */
export const PRAZO_NO_ACIONAMENTO = "Definido no acionamento";

/**
 * O tempo do trecho que este marco fecha, em linguagem de gente.
 *
 * Nulo quando o trecho nem começou, e é isso que a tela mostra: um traço, e
 * não "menos de uma hora útil". Zero ali diria que a área respondeu na hora
 * quando ela nem foi acionada.
 */
export function descreverTrecho(marco: MarcoDoCaso): string | null {
  if (marco.trecho === null || marco.minutos_uteis === null) return null;
  const decorrido = formatarEsperaUtil(marco.minutos_uteis);
  return marco.em_curso
    ? `${marco.trecho}: ${decorrido} até agora`
    : `${marco.trecho}: ${decorrido}`;
}

/**
 * Os prazos que a tela mostra.
 *
 * Gravidade sem célula na tabela não tem aquele prazo, e a linha simplesmente
 * não aparece (PRD #468, história 12): o crítico não tem prazo conclusivo
 * fixo, e mostrar a linha vazia convidaria alguém a preencher o número que o
 * sistema não tem. Prazo que ainda vai nascer no acionamento continua na tela,
 * porque ali existe compromisso, ele é que ainda não foi assumido.
 */
export function prazosVisiveis(prazos: PrazoDoCaso[]): PrazoDoCaso[] {
  return prazos.filter((prazo) => prazo.situacao !== "sem_prazo");
}

/** A frase de estado do prazo: a contagem do motor, ou o que falta acontecer. */
export function descreverPrazo(prazo: PrazoDoCaso): string {
  return prazo.rotulo_prazo ?? PRAZO_NO_ACIONAMENTO;
}
