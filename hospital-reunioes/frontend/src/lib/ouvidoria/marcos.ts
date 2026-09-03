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
  /**
   * O nome do trecho que este marco fecha, e que já diz de quem é aquele
   * tempo. Nulo no T0, que não fecha nada.
   */
  trecho: string | null;
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

/**
 * O acuse de recebimento ao manifestante (issue #493, RN-56, ADR 0042).
 *
 * Fica FORA da lista de marcos de propósito, e a razão é o encadeamento: cada
 * marco de lá fecha o trecho que o anterior abriu, e enfiar o acuse entre a
 * entrada e a validação faria a "Triagem da Ouvidoria" passar a medir do acuse
 * em diante, ou seja, o gargalo da própria Ouvidoria encolheria na tela por
 * causa de um email.
 */
export interface AcuseDoCaso {
  rotulo: string;
  /** Quando o aviso foi gerado, ou quando o caso foi marcado como sem canal. */
  em: string | null;
  situacao: "enviado" | "em_envio" | "falha_no_envio" | "sem_contato" | "pendente";
  /** Por que ninguém foi avisado, quando foi esse o caso. */
  nota: string | null;
}

export const MARCO_PENDENTE = "Ainda não aconteceu";

/**
 * O que a linha do acuse diz antes da data.
 *
 * As cinco situações precisam ser distintas na tela, e cada distinção paga o
 * próprio aluguel:
 *
 * - "enviado" só aparece quando o servidor viu a notificação ENTREGUE. O
 *   carimbo do caso sozinho não basta: ele é gravado antes de o provedor
 *   responder, e afirmar entrega a partir dele faria a página garantir ao
 *   ouvidor um aviso que pode ter esgotado as tentativas (é o precedente da
 *   issue #373, onde o carimbo só valia com a entrega confirmada);
 * - "não entregue" é o envio que falhou, e é ele que pede reenvio;
 * - "não enviado" é a marcação própria de quem não tinha canal. Juntá-la com a
 *   falha faria a escolha de quem manifestou anônimo parecer erro do hospital.
 */
export const SITUACAO_DO_ACUSE: Record<AcuseDoCaso["situacao"], string> = {
  enviado: "Enviado ao manifestante",
  em_envio: "Na fila de envio",
  falha_no_envio: "Não entregue",
  sem_contato: "Não enviado",
  pendente: MARCO_PENDENTE,
};

/**
 * O aviso de encerramento ao manifestante (issue #494, RN-80, ADR 0042).
 *
 * Mesmo formato do acuse, e o mesmo motivo para ficar fora da lista de marcos:
 * o T3 continua sendo o ato do ouvidor, e amarrá-lo ao provedor de email faria
 * o trecho "Desfecho pela Ouvidoria" crescer por causa de uma retentativa.
 */
export type AvisoDeEncerramento = AcuseDoCaso;

/**
 * O que a linha do aviso diz antes da data.
 *
 * As cinco situações são as do acuse, e o texto muda porque o assunto muda: o
 * que fica pendente aqui não é uma promessa em atraso, é um caso que ainda não
 * foi encerrado.
 */
export const SITUACAO_DO_AVISO_DE_ENCERRAMENTO: Record<AvisoDeEncerramento["situacao"], string> = {
  enviado: "Enviado ao manifestante",
  em_envio: "Na fila de envio",
  falha_no_envio: "Não entregue",
  sem_contato: "Não enviado",
  pendente: MARCO_PENDENTE,
};

/** O prazo que nasce no despacho e ainda não foi despachado. */
export const PRAZO_NO_ACIONAMENTO = "Definido no acionamento";

/**
 * O que a tela diz no lugar do número quando o calendário útil não pôde ser
 * lido (issue #449). É a mesma marca do painel, palavra por palavra.
 *
 * "Sem confirmação", e não "sem o calendário": a marca cobre dois estados, o de
 * saber que os feriados falharam e o de não ter como saber (resposta que nem
 * declara o `degradado`). Afirmar a causa no segundo seria a mesma presunção
 * que a marca existe para evitar.
 */
export const SEM_CONFIRMACAO_DO_CALENDARIO = "sem confirmação do calendário";

/**
 * O tempo do trecho que este marco fecha, em linguagem de gente.
 *
 * Nulo quando o trecho nem começou, e é isso que a tela mostra: nada, e não
 * "menos de uma hora útil". Zero ali diria que a área respondeu na hora quando
 * ela nem foi acionada.
 *
 * `calendarioConfiavel` é obrigatório de propósito: sem calendário, o número
 * sai da tela em vez de sair errado. Feriado que não pôde ser lido conta como
 * dia trabalhado, e a conta erra sem denunciar a si mesma, então avisar e
 * afirmar o número ao lado seria avisar por educação.
 */
export function descreverTrecho(marco: MarcoDoCaso, calendarioConfiavel: boolean): string | null {
  if (marco.trecho === null || marco.minutos_uteis === null) return null;
  if (!calendarioConfiavel) return `${marco.trecho}: ${SEM_CONFIRMACAO_DO_CALENDARIO}`;
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

/**
 * A frase de estado do prazo: a contagem do motor, ou o que falta acontecer.
 *
 * A DATA do vencimento é dado persistido e a tela a mostra sempre; a contagem
 * ("vence em 2 dias úteis") é conta feita no calendário útil, e sem ele
 * confirmado ela sai da tela, como no painel. "Definido no acionamento" não é
 * conta nenhuma, e por isso continua valendo com o calendário fora do ar.
 */
export function descreverPrazo(prazo: PrazoDoCaso, calendarioConfiavel: boolean): string {
  if (prazo.rotulo_prazo === null) return PRAZO_NO_ACIONAMENTO;
  return calendarioConfiavel ? prazo.rotulo_prazo : SEM_CONFIRMACAO_DO_CALENDARIO;
}
