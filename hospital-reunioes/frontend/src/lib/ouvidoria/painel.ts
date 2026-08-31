/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319, ADR 0034).
 *
 * A régua do que a tela mostra, fora da tela. Duas fontes chegam aqui e não se
 * misturam, porque respondem perguntas diferentes:
 *
 * * a listagem (`/api/ouvidoria/protocolos`) responde "quais casos", e é dela
 *   que saem a fila por status, o que já venceu, o que vence hoje e amanhã e os
 *   críticos abertos;
 * * o módulo de métricas (`/api/ouvidoria/metricas`) responde "quanto cada área
 *   deve AGORA", pelo bloco `pendencias_por_area`, que tem universo próprio e
 *   nenhum recorte de data (contrato da issue #341).
 *
 * Somar os dois é somar universos diferentes: `pendencias_por_area[].pendentes`
 * conta só o que está com a área, e a fila por status conta todos os estados.
 * Por isso este módulo nunca cruza contagem de um lado com a do outro.
 *
 * Nenhuma conta de calendário útil acontece aqui. O vencimento chega calculado
 * pelo motor do servidor, e o veredito de estouro também: o que esta camada faz
 * é ler em que DIA o vencimento cai.
 */

import { agruparPorStatus, ORDEM_DA_FILA, rotuloDoStatus } from "./fila";
import { EM_ANDAMENTO, type StatusManifestacao } from "./prazo";

/** O fuso do hospital. O dia civil de um vencimento é lido nele, não no do navegador. */
const FUSO_HOSPITAL = "America/Sao_Paulo";

/**
 * Quem abre o painel (PRD #319, histórias 11 a 14). Os mesmos dois perfis que o
 * módulo de métricas exige, e pelo mesmo motivo: o painel mostra o caso
 * sigiloso junto dos demais. Esta função existe para a tela não oferecer um
 * caminho que termina em 403; o enforcement é do servidor, no layout da rota e
 * no gate do `/metricas`.
 */
export const PERFIS_DO_PAINEL: readonly string[] = ["ouvidor", "diretoria_executiva"];

export function podeVerPainel(perfilOuvidoria: string | null | undefined): boolean {
  return PERFIS_DO_PAINEL.includes(String(perfilOuvidoria));
}

/** O que o painel precisa saber de um caso da listagem. */
export interface CasoDoPainel {
  status: StatusManifestacao;
  gravidade: string | null;
  /** O vencimento da área, calculado pelo motor. Nulo enquanto o caso não foi validado. */
  prazo_area_em: string | null;
  /** O prazo de referência da fundação, em data civil. É o que vale na fila de triagem. */
  prazo_resposta: string;
  /** O veredito do motor sobre o vencimento da área, medido em calendário útil. */
  prazo_estourado: boolean;
  /** A marca de sigilo do caso (RN-40). Denúncia é sigilosa por natureza. */
  sigilo_reforcado: boolean;
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

/** Hoje, na mesma régua, e pelo mesmo motivo. */
export function hojeNoHospital(agora: Date = new Date()): string {
  return agora.toLocaleDateString("en-CA", { timeZone: FUSO_HOSPITAL });
}

function diaSeguinte(dia: string): string {
  const [ano, mes, data] = dia.split("-").map(Number);
  return new Date(Date.UTC(ano, mes - 1, data + 1)).toISOString().slice(0, 10);
}

function janelaDoDia(dia: string, hoje: string): JanelaDeVencimento {
  if (dia < hoje) return "vencido";
  if (dia === hoje) return "hoje";
  if (dia === diaSeguinte(hoje)) return "amanha";
  return "depois";
}

/**
 * O dia pelo qual o caso é cobrado, e por onde ele é ordenado. Enquanto não há
 * prazo da área, vale o prazo de referência da fundação, que é o que a fila de
 * triagem tem: sem ele, o caso que a Ouvidoria ainda não triou não seria
 * cobrado por bloco nenhum, e o atraso é dela.
 */
function diaDaCobranca(caso: CasoDoPainel): string | null {
  if (caso.prazo_area_em) return diaNoHospital(caso.prazo_area_em);
  return caso.prazo_resposta || null;
}

/**
 * Em que janela um caso cai.
 *
 * O estouro é lido do motor, nunca deduzido da data: um vencimento de hoje às
 * 11h visto às 16h já estourou, e chamá-lo de "vence hoje" mandaria cobrar até
 * o fim do dia um caso que já está contando contra a área na tabela logo
 * abaixo. Só depois disso a pergunta vira de calendário de parede: em que dia
 * esse vencimento cai. A janela "amanha" continua sendo dia civil, e por isso na
 * sexta ela é sempre vazia: é o `proximosVencimentos` que responde "o que vem
 * agora" em qualquer dia da semana (issue #437).
 */
export function classificarJanela(caso: CasoDoPainel, hoje: string): JanelaDeVencimento {
  // "Parado" é o que esta tela SABE que já saiu da cobrança. Estado que ela não
  // conhece não é sabido, e some da janela se for tratado como parado: um caso
  // já contando contra a área desapareceria da lista de vencidos, que é a
  // primeira coisa que o ouvidor olha (issue #375, item 15). Entre esconder um
  // estourado e mostrar um caso que talvez já tenha fechado, o segundo erro é
  // o barato.
  const conhecido = ORDEM_DA_FILA.includes(caso.status);
  if (conhecido && !EM_ANDAMENTO.has(caso.status)) return "parado";
  if (caso.prazo_area_em && caso.prazo_estourado) return "vencido";
  const dia = diaDaCobranca(caso);
  if (!dia) return "sem_prazo";
  return janelaDoDia(dia, hoje);
}

/**
 * Os casos de uma janela, do vencimento mais próximo para o mais distante:
 * dentro do dia, quem vence às 11h precisa da atenção antes de quem vence às
 * 17h. A chave serve aos dois tipos de prazo, para o caso de triagem não ir
 * parar numa ponta da lista por acaso em vez de por urgência.
 */
export function vencendoEm<T extends CasoDoPainel>(
  casos: T[],
  janela: JanelaDeVencimento,
  hoje: string
): T[] {
  return casos.filter((caso) => classificarJanela(caso, hoje) === janela).sort(porVencimento);
}

/** A ordem da urgência, uma só, para os dois blocos que listam casos a vencer. */
function porVencimento(a: CasoDoPainel, b: CasoDoPainel): number {
  return (
    String(diaDaCobranca(a) ?? "").localeCompare(String(diaDaCobranca(b) ?? "")) ||
    String(a.prazo_area_em ?? "").localeCompare(String(b.prazo_area_em ?? ""))
  );
}

/** As janelas que ainda não chegaram. Vencido e "vence hoje" têm bloco próprio. */
const JANELAS_FUTURAS: JanelaDeVencimento[] = ["amanha", "depois"];

/** Quantos casos o bloco dos próximos vencimentos mostra. */
export const LIMITE_DE_PROXIMOS_VENCIMENTOS = 5;

/**
 * Os casos mais próximos de vencer, em qualquer dia (issue #437).
 *
 * Substitui a lista de "amanhã", que era dia civil de calendário de parede e
 * por isso ficava vazia toda sexta-feira: no sábado não vence nada, e o ouvidor
 * saía para o fim de semana sem ver o que vence na segunda. Aqui a pergunta não
 * é "que dia é amanhã", e sim "quais são os próximos", que é a mesma resposta
 * em qualquer dia da semana e não pede o calendário útil no navegador.
 *
 * Vencido e "vence hoje" ficam de fora porque já têm bloco próprio: repetir o
 * caso faria a mesma cobrança aparecer duas vezes na mesma tela.
 */
export function proximosVencimentos<T extends CasoDoPainel>(
  casos: T[],
  hoje: string,
  limite: number = LIMITE_DE_PROXIMOS_VENCIMENTOS
): T[] {
  return casos
    .filter((caso) => JANELAS_FUTURAS.includes(classificarJanela(caso, hoje)))
    .sort(porVencimento)
    .slice(0, limite);
}

/**
 * Os críticos que ainda não fecharam (PRD #319, história 14). O caso já
 * respondido pela área continua aqui: enquanto a Ouvidoria não encerra, o grave
 * segue aberto, e é justamente ele que não pode se misturar ao comum.
 */
export function criticosAbertos<T extends CasoDoPainel>(casos: T[]): T[] {
  return casos.filter((caso) => caso.gravidade === "critico" && caso.status !== "encerrado");
}

/**
 * A linha precisa da marca de sigilo (RN-40). A denúncia é sigilosa por natureza
 * e é candidata natural a crítica: sem a marca, ela aparece no destaque
 * vermelho visualmente idêntica a uma reclamação de fila, e esta é uma tela
 * feita para ficar aberta e ser projetada numa sala de reunião.
 */
export function precisaDaMarcaDeSigilo(caso: CasoDoPainel): boolean {
  return caso.sigilo_reforcado === true;
}

export interface ContagemDeStatus {
  status: StatusManifestacao;
  label: string;
  total: number;
}

/**
 * A fila por status, na ordem do trabalho do ouvidor. Estado sem caso vira zero
 * explícito, e não sumiço: coluna que desaparece esconde que a fila esvaziou.
 *
 * Estado que esta tela ainda não conhece entra no fim, com o próprio código de
 * rótulo (issue #375, item 15). Sem isso, o caso sumia da contagem e os totais
 * deixavam de fechar com o total de casos: o painel fica aberto e projetado
 * numa sala de reunião, e uma soma que não bate ali é pior que uma linha com
 * nome estranho.
 *
 * A régua é uma só: quem agrupa é o `agruparPorStatus` da fila, e aqui só se
 * conta o que ele agrupou (issue #437). A contagem própria que existia aqui era
 * uma segunda régua com as mesmas duas decisões (a ordem e o estado
 * desconhecido) para manter em dois lugares.
 */
export function contarPorStatus(casos: CasoDoPainel[]): ContagemDeStatus[] {
  return agruparPorStatus(casos).map((grupo) => ({
    status: grupo.status,
    label: rotuloDoStatus(grupo.status),
    total: grupo.itens.length,
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
 * A linha dos feriados é a perigosa, e o estrago dela é maior do que o módulo
 * de métricas consegue declarar: a listagem calcula o rótulo em dias úteis de
 * cada caso com a MESMA tabela de feriados e engole a falha em silêncio, sem
 * `degradado` nenhum na resposta. Quando esta lista acusa `feriados`, todo
 * número em dias úteis da tela está sob suspeita, venha de onde vier.
 */
const AVISOS: Record<string, string> = {
  feriados:
    "O calendário de feriados não pôde ser lido: todo prazo em dias úteis desta tela saiu contado como se todo dia útil fosse trabalhado, tanto o atraso das áreas quanto o de cada caso.",
  responsaveis:
    "O cadastro de responsáveis por setor não pôde ser lido: as pendências estão sem o nome de quem responde.",
};

export function avisosDeDegradacao(degradado: string[]): AvisoDeDegradacao[] {
  return degradado.filter((leitura) => leitura in AVISOS).map((leitura) => ({ leitura, texto: AVISOS[leitura] }));
}

/**
 * O calendário útil foi lido inteiro. Enquanto não foi, nenhum número em dias
 * úteis da tela vale, nem o das áreas nem o rótulo de cada caso.
 *
 * `null` é a leitura de métricas que nem chegou (issue #437). Quem declara o
 * `degradado` é ela: sem a resposta, a lista vazia virava "nada degradou" e a
 * tela voltava a afirmar a frase em dias úteis de cada caso como se soubesse
 * que os feriados foram lidos. Não saber não é saber que está bom.
 */
export function calendarioUtilFoiLido(degradado: string[] | null): boolean {
  if (degradado === null) return false;
  return !degradado.includes("feriados");
}

/**
 * A chave de agrupamento que o módulo de métricas usa para o caso que chegou
 * sem setor (`ouvidoria_metricas.py`). O dado continua assim, porque é chave;
 * quem não pode falar em código de sistema é a tela (issue #437).
 */
const SETOR_NAO_INFORMADO = "nao_informado";

/** O nome do setor para a tela. */
export function rotuloDoSetor(setor: string): string {
  return setor === SETOR_NAO_INFORMADO ? "Não informado" : setor;
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

/**
 * Por que a leitura não chegou.
 *
 * Perder o perfil com o painel aberto não é instabilidade: a tela precisa
 * apagar o que já mostrou, porque o que está na tela é protocolo, setor e
 * resumo de manifestação. Instabilidade pode manter a foto antiga com aviso;
 * perda de acesso, não.
 */
export type FalhaDeCarga = "sem_acesso" | "instavel";

export function classificarFalha(status: number): FalhaDeCarga {
  return status === 401 || status === 403 ? "sem_acesso" : "instavel";
}

/** O passo normal do painel: é o retrato da operação, não um relógio de segundos. */
export const INTERVALO_BASE_MS = 60_000;
/** O teto do recuo. Acima disso a tela deixaria de ser "tempo real" de vez. */
export const INTERVALO_MAXIMO_MS = 10 * 60_000;

/**
 * Quanto esperar até a próxima tentativa. O limite de requisições é por IP e o
 * hospital inteiro divide um balde só (issue #399): insistir de minuto em
 * minuto contra um 429 mantém o balde estourado e o painel em branco junto.
 */
export function intervaloDeAtualizacao(falhasSeguidas: number): number {
  if (falhasSeguidas <= 0) return INTERVALO_BASE_MS;
  return Math.min(INTERVALO_BASE_MS * 2 ** falhasSeguidas, INTERVALO_MAXIMO_MS);
}
