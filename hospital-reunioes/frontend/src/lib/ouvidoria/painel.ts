/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319, ADR 0034).
 *
 * A régua do que a tela mostra, fora da tela. Duas fontes chegam aqui e não se
 * misturam, porque respondem perguntas diferentes:
 *
 * * a listagem (`/api/ouvidoria/protocolos`) responde "quais casos", e é dela
 *   que saem a fila por status, o que vence hoje e amanhã e os críticos abertos;
 * * o módulo de métricas (`/api/ouvidoria/metricas`) responde "quanto cada área
 *   deve AGORA", pelo bloco `pendencias_por_area`, que tem universo próprio e
 *   nenhum recorte de data (contrato da issue #341).
 *
 * Somar os dois é somar universos diferentes: `pendencias_por_area[].pendentes`
 * é a fila viva e `volume.total` é o que entrou no período. Por isso este
 * módulo nunca cruza contagem de um lado com a do outro.
 *
 * Nenhuma conta de calendário útil acontece aqui. O vencimento chega calculado
 * pelo motor do servidor; o que esta camada faz é ler em que DIA ele cai.
 */

import { LABEL_STATUS, ORDEM_DA_FILA } from "./fila";
import { EM_ANDAMENTO, type StatusManifestacao } from "./prazo";

/** O fuso do hospital. O dia civil de um vencimento é lido nele, não no do navegador. */
const FUSO_HOSPITAL = "America/Sao_Paulo";

/**
 * Quem abre o painel (PRD #319, histórias 11 a 14). Os mesmos dois perfis que o
 * módulo de métricas exige, e pelo mesmo motivo: o painel mostra o caso
 * sigiloso junto dos demais. O gate de verdade é o backend (403 no
 * `/metricas`); a tela só não oferece um caminho que termina lá.
 */
export const PERFIS_DO_PAINEL = ["ouvidor", "diretoria_executiva"];

export function podeVerPainel(perfilOuvidoria: string | null | undefined): boolean {
  return !!perfilOuvidoria && PERFIS_DO_PAINEL.includes(perfilOuvidoria);
}

/** O que o painel precisa saber de um caso da listagem. */
export interface CasoDoPainel {
  status: StatusManifestacao;
  gravidade: string | null;
  prazo_area_em: string | null;
}

/**
 * `parado` é o caso cujo relógio não corre: já respondido, encerrado, ou
 * pausado aguardando o manifestante (issue #335). O vencimento dele existe no
 * dado, mas anunciá-lo cobraria alguém por uma espera que não é dele.
 */
export type JanelaDeVencimento = "vencido" | "hoje" | "amanha" | "depois" | "sem_prazo" | "parado";

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

/** Hoje, na mesma régua. */
export function hojeNoHospital(agora: Date = new Date()): string {
  return agora.toLocaleDateString("en-CA", { timeZone: FUSO_HOSPITAL });
}

function diaSeguinte(dia: string): string {
  const [ano, mes, data] = dia.split("-").map(Number);
  return new Date(Date.UTC(ano, mes - 1, data + 1)).toISOString().slice(0, 10);
}

/**
 * Em que janela um caso cai. A comparação é de DIA CIVIL: "vence amanhã" é
 * pergunta de calendário de parede, e o vencimento que ela lê já saiu do motor
 * contado em dias úteis. A consequência é conhecida e desejada: na sexta a
 * lista de amanhã fica vazia, porque não existe vencimento no sábado.
 */
export function classificarJanela(caso: CasoDoPainel, hoje: string): JanelaDeVencimento {
  if (!EM_ANDAMENTO.has(caso.status)) return "parado";
  if (!caso.prazo_area_em) return "sem_prazo";
  const dia = diaNoHospital(caso.prazo_area_em);
  if (dia < hoje) return "vencido";
  if (dia === hoje) return "hoje";
  if (dia === diaSeguinte(hoje)) return "amanha";
  return "depois";
}

/**
 * Os casos de uma janela, do vencimento mais próximo para o mais distante:
 * dentro do dia, quem vence às 11h precisa da atenção antes de quem vence às 17h.
 */
export function vencendoEm<T extends CasoDoPainel>(
  casos: T[],
  janela: JanelaDeVencimento,
  hoje: string
): T[] {
  return casos
    .filter((caso) => classificarJanela(caso, hoje) === janela)
    .sort((a, b) => String(a.prazo_area_em).localeCompare(String(b.prazo_area_em)));
}

/**
 * Os críticos que ainda não fecharam (PRD #319, história 14). O caso já
 * respondido pela área continua aqui: enquanto a Ouvidoria não encerra, o grave
 * segue aberto, e é justamente ele que não pode se misturar ao comum.
 */
export function criticosAbertos<T extends CasoDoPainel>(casos: T[]): T[] {
  return casos.filter((caso) => caso.gravidade === "critico" && caso.status !== "encerrado");
}

export interface ContagemDeStatus {
  status: StatusManifestacao;
  label: string;
  total: number;
}

/**
 * A fila por status, na ordem do trabalho do ouvidor. Estado sem caso vira zero
 * explícito, e não sumiço: coluna que desaparece esconde que a fila esvaziou.
 */
export function contarPorStatus(casos: CasoDoPainel[]): ContagemDeStatus[] {
  return ORDEM_DA_FILA.map((status) => ({
    status,
    label: LABEL_STATUS[status],
    total: casos.filter((caso) => caso.status === status).length,
  }));
}

/**
 * Uma linha de `pendencias_por_area` do módulo de métricas (contrato da #341).
 * Nenhum caso é identificado aqui: só contagem, o nome de quem responde pelo
 * setor e o atraso do caso mais atrasado. Protocolo não sai desse bloco.
 */
export interface PendenciaDeArea {
  setor: string;
  responsavel: string | null;
  pendentes: number;
  vencidas: number;
  dias_uteis_de_atraso: number;
}

/**
 * As áreas com caso vencido (PRD #319, história 13). A ordem chega pronta do
 * módulo (da mais atrasada para a menos) e é preservada: reordenar aqui faria o
 * painel discordar do relatório sobre onde apertar.
 */
export function areasComVencidas(pendencias: PendenciaDeArea[]): PendenciaDeArea[] {
  return pendencias.filter((linha) => linha.vencidas > 0);
}

export interface AvisoDeDegradacao {
  leitura: string;
  texto: string;
}

/**
 * O que o painel deixa de poder afirmar quando uma leitura de apoio falha.
 *
 * `degradado` vem do módulo de métricas com o nome da leitura que não pôde ser
 * feita. Só entram aqui as que mexem em número que ESTA tela mostra: `prazos` e
 * `prorrogacoes` degradam os trechos de prazo e a taxa de prorrogação, que são
 * do relatório, e avisar sobre eles seria ruído.
 *
 * A linha dos feriados é a perigosa: com ela nada vem nulo, o atraso sai
 * calculado com calendário errado e o número tem cara de bom. Sem este aviso,
 * ninguém teria como desconfiar.
 */
const AVISOS: Record<string, string> = {
  feriados: "O calendário de feriados não pôde ser lido: os dias de atraso saíram contados como se todo dia útil fosse trabalhado, e podem estar maiores do que a realidade.",
  responsaveis: "O cadastro de responsáveis por setor não pôde ser lido: as pendências estão sem o nome de quem responde.",
};

export function avisosDeDegradacao(degradado: string[]): AvisoDeDegradacao[] {
  return degradado.filter((leitura) => leitura in AVISOS).map((leitura) => ({ leitura, texto: AVISOS[leitura] }));
}

/** O atraso em dias úteis só vale se o calendário foi lido inteiro. */
export function atrasoFoiMedidoComCalendarioCerto(degradado: string[]): boolean {
  return !degradado.includes("feriados");
}

/**
 * O nome ao lado da pendência. Nulo tem dois significados no contrato da #341 e
 * eles não podem virar a mesma frase: setor realmente sem titular vigente é
 * cobrança de cadastro, e leitura que falhou não é cobrança de nada.
 */
export function rotuloDoResponsavel(responsavel: string | null, degradado: string[]): string {
  if (responsavel) return responsavel;
  return degradado.includes("responsaveis") ? "Cadastro não lido" : "Sem titular vigente";
}
