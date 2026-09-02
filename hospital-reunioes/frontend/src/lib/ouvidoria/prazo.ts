/**
 * Classificação do prazo de uma manifestação de ouvidoria para o destaque
 * visual do painel (issues #292 e #320). Datas em ISO (YYYY-MM-DD),
 * comparadas como data civil: sem fuso, sem hora.
 */

export type StatusManifestacao =
  | "novo"
  | "em_classificacao"
  | "aguardando_area"
  | "aguardando_manifestante"
  | "respondido"
  | "encerrado";

/**
 * Os quatro degraus do semáforo de prazo, mais o caso de relógio parado
 * (issue #488, RN-58). Vermelho é só o que precisa de resposta hoje, vencido
 * ("estourado") ou vencendo ("vence_hoje"); "perto" é o âmbar de até um dia
 * útil de folga; "normal" não acende cor nenhuma.
 *
 * O vermelho acendia com dois dias de folga (D-13), na mesma intensidade do
 * vencido. Quando tudo é urgente, nada é urgente: a escala perdeu a triagem
 * visual que o ouvidor faz de relance.
 */
export type ClassePrazo = "estourado" | "vence_hoje" | "perto" | "normal" | "respondido";

/**
 * Estados em que o relógio ainda corre. A partir de "respondido" o caso saiu
 * das mãos da ouvidoria e o prazo de resposta deixa de valer.
 *
 * "aguardando_manifestante" fica de fora de propósito (issue #335): é a pausa,
 * e durante ela o relógio da área está parado. Mostrar contagem regressiva ali
 * cobraria o setor por uma espera que não é dele.
 */
export const EM_ANDAMENTO = new Set<StatusManifestacao>([
  "novo",
  "em_classificacao",
  "aguardando_area",
]);

const MS_POR_DIA = 1000 * 60 * 60 * 24;

/**
 * O prazo de referência da fundação é data civil, sem hora e sem calendário
 * útil: o único dia seguinte que existe aqui é o de amanhã, e é ele que carrega
 * o âmbar.
 */
export function classificarPrazo(
  prazo: string,
  status: StatusManifestacao,
  hoje: string
): ClassePrazo {
  if (!EM_ANDAMENTO.has(status)) return "respondido";
  const diffDias = Math.round(
    (Date.parse(`${prazo}T12:00:00`) - Date.parse(`${hoje}T12:00:00`)) / MS_POR_DIA
  );
  if (diffDias < 0) return "estourado";
  if (diffDias === 0) return "vence_hoje";
  if (diffDias === 1) return "perto";
  return "normal";
}

/** O fuso do hospital. O dia civil de um vencimento é lido nele, não no do navegador. */
const FUSO_HOSPITAL = "America/Sao_Paulo";

/**
 * O dia civil de um instante, no fuso do hospital. `en-CA` é o formato ISO
 * (AAAA-MM-DD), que é o que o resto do módulo compara como texto.
 *
 * Ler em UTC erraria a virada: um vencimento das 23h de hoje em Brasília já é
 * amanhã em UTC, e o caso que vence hoje apareceria como "vence amanhã".
 */
export function diaNoHospital(instante: string): string {
  return new Date(instante).toLocaleDateString("en-CA", { timeZone: FUSO_HOSPITAL });
}

/** Hoje, na mesma régua, e pelo mesmo motivo. */
export function hojeNoHospital(agora: Date = new Date()): string {
  return agora.toLocaleDateString("en-CA", { timeZone: FUSO_HOSPITAL });
}

/**
 * O que o painel precisa saber do prazo de uma manifestação (issue #322).
 * Tudo vem calculado do motor no servidor: o navegador não recalcula
 * calendário útil, para painel e email do setor nunca dizerem prazos
 * diferentes.
 */
export interface PrazoDaManifestacao {
  status: StatusManifestacao;
  prazo_resposta: string;
  prazo_area_em: string | null;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  /** Folga em minutos de expediente. Zero quando estourado, nulo sem prazo. */
  minutos_uteis_restantes: number | null;
}

/** Expediente de 08h às 17h: a mesma régua que o motor usa no servidor. */
const MINUTOS_POR_DIA_UTIL = 9 * 60;
/** Até 1 dia útil de folga a linha ganha o âmbar de "vence logo" (RN-58). */
const FOLGA_DE_ALERTA = MINUTOS_POR_DIA_UTIL;

/**
 * Destaque visual da linha. Caso já classificado usa o veredito do motor;
 * caso ainda sem gravidade cai no prazo de 7 dias corridos da fundação, que
 * é o que existe antes de o ouvidor validar.
 *
 * Duas perguntas, nesta ordem, e elas medem coisas diferentes:
 *
 * 1. em que DIA esse vencimento cai. Vencido e vence hoje são o vermelho, e a
 *    resposta é de calendário de parede, no fuso do hospital. É a mesma leitura
 *    que o painel faz por bloco ("Já venceu" e "Vence hoje"), para as duas
 *    telas nunca darem vereditos diferentes do mesmo caso;
 * 2. quanta FOLGA sobrou, em tempo útil, para o âmbar. Um vencimento de segunda
 *    visto na sexta está a 3 dias no calendário e a 1 dia de trabalho, e é o
 *    segundo número que decide se alguém precisa correr.
 */
export function classificarPrazoDaManifestacao(
  m: PrazoDaManifestacao,
  hoje: string
): ClassePrazo {
  if (!EM_ANDAMENTO.has(m.status)) return "respondido";
  if (!m.prazo_area_em) return classificarPrazo(m.prazo_resposta, m.status, hoje);
  const dia = diaNoHospital(m.prazo_area_em);
  // O dia já passado conta como estouro mesmo sem o carimbo do motor: o painel
  // lê assim, e um caso vencido pintado de âmbar num lugar e de vermelho no
  // outro é pior que um vermelho que chega um minuto cedo demais.
  if (m.prazo_estourado || dia < hoje) return "estourado";
  if (dia === hoje) return "vence_hoje";
  if (m.minutos_uteis_restantes === null) return "normal";
  return m.minutos_uteis_restantes <= FOLGA_DE_ALERTA ? "perto" : "normal";
}

/**
 * Quem define os parâmetros do prazo (RN-21). Mais estreito que o perfil da
 * Ouvidoria de propósito: o ouvidor trabalha com o prazo, quem o define é a
 * Diretoria Executiva. Quem não passa aqui não vê a tela de edição.
 */
export function podeEditarPrazos(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "diretoria_executiva";
}

/**
 * Os marcos da tabela de prazos, na ordem em que o caso os atravessa
 * (RN-21, RN-56).
 *
 * O acuse vem primeiro porque é o primeiro compromisso do caso: ele nasce no
 * segundo zero da abertura, antes de qualquer triagem.
 */
export const MARCOS_DE_PRAZO = [
  "acusar_recebimento",
  "triagem",
  "area_resposta",
  "conclusiva",
] as const;

export type MarcoDePrazo = (typeof MARCOS_DE_PRAZO)[number];

export type UnidadeDePrazo = "horas_uteis" | "dias_uteis" | "horas_corridas";

export const LABEL_UNIDADE: Record<UnidadeDePrazo, string> = {
  horas_uteis: "horas úteis",
  dias_uteis: "dias úteis",
  horas_corridas: "horas corridas",
};

/**
 * A unidade que aquele marco é obrigado a usar, ou nula quando a Diretoria
 * escolhe entre horas e dias úteis (RN-56, ADR 0042, decisão 1).
 *
 * O acuse de recebimento é o único marco fora do Calendário útil, e o par é
 * fechado nos dois sentidos: tirá-lo do relógio de parede transformaria a
 * promessa de sábado em terça, e pôr qualquer outro marco nele faria o sistema
 * cobrar o setor de madrugada e no feriado. O backend recusa o contrário, e
 * esta função é o que impede a tela de oferecer o que ele vai recusar.
 */
export function unidadeFixaDoMarco(marco: MarcoDePrazo): UnidadeDePrazo | null {
  return marco === "acusar_recebimento" ? "horas_corridas" : null;
}

/**
 * O valor da célula em linguagem de gente, para a linha do marco cuja unidade
 * a tela não deixa editar.
 *
 * Zero em horas corridas é "mesmo dia", e não "vencido na hora": no relógio de
 * parede não existe janela de expediente a esperar, então o que sobra do dia é
 * o prazo. É a linha do crítico da spec da Diretoria, e sem esta frase ela
 * apareceria na tela como um zero que ninguém sabe ler.
 */
export function descreverCelulaDePrazo(
  valor: number | null,
  unidade: UnidadeDePrazo
): string {
  if (valor === null) return "sem prazo";
  if (unidade === "horas_corridas" && valor === 0) return "mesmo dia";
  if (valor === 0) return "imediato";
  return `${valor} ${LABEL_UNIDADE[unidade]}`;
}

/**
 * O tempo parado aguardando o manifestante em linguagem de gente (issue #335).
 *
 * O número vem em minutos de EXPEDIENTE, e um dia útil do hospital tem nove
 * horas: dizer "2 dias úteis" para 18 horas é o que o ouvidor entende, e
 * "1080 minutos" não é.
 *
 * O arredondamento acontece PRIMEIRO, em horas, e só então os dias são
 * separados. Arredondar o resto por conta própria deixava as horas alcançarem
 * um dia inteiro: 535 min virava "9 horas úteis" e 1074 min virava "1 dia útil
 * e 9 horas úteis".
 */
export function formatarEsperaUtil(minutos: number): string {
  const HORAS_POR_DIA_UTIL = 9;
  const totalHoras = Math.round(minutos / 60);
  const dias = Math.floor(totalHoras / HORAS_POR_DIA_UTIL);
  const horas = totalHoras % HORAS_POR_DIA_UTIL;
  const partes: string[] = [];
  if (dias > 0) partes.push(dias === 1 ? "1 dia útil" : `${dias} dias úteis`);
  if (horas > 0) partes.push(horas === 1 ? "1 hora útil" : `${horas} horas úteis`);
  return partes.length > 0 ? partes.join(" e ") : "menos de uma hora útil";
}
