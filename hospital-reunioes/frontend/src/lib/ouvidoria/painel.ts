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
import {
  diaNoHospital,
  EM_ANDAMENTO,
  hojeNoHospital,
  type StatusManifestacao,
} from "./prazo";

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
 * O dia civil no fuso do hospital mora com a classificação do prazo (issue
 * #488): a fila precisa da mesma leitura para saber o que vence hoje, e duas
 * cópias da régua acabariam divergindo. Segue exportado daqui porque é por este
 * módulo que o painel o consome.
 */
export { diaNoHospital, hojeNoHospital };

/**
 * A hora civil de um instante, no fuso do hospital, em 24h ("09:00"). Serve ao
 * desempate dentro do mesmo dia, e é lida no mesmo fuso pelo mesmo motivo do
 * dia: comparar o texto ISO cru misturaria vencimentos com offsets diferentes.
 */
function horaNoHospital(instante: string): string {
  return new Date(instante).toLocaleTimeString("en-GB", {
    timeZone: FUSO_HOSPITAL,
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * O dia civil seguinte a um dia civil, em texto ISO.
 *
 * A conta é feita em UTC de propósito, e a variante local
 * (`new Date(ano, mes - 1, dia + 1)`) é o erro natural aqui: ela monta a data à
 * meia-noite do fuso da MÁQUINA, e o `toISOString` logo depois traz tudo de
 * volta para UTC. Num navegador a leste de Greenwich isso volta um dia, e o dia
 * seguinte a 31/12 sairia 31/12. Este módulo já decide o fuso onde o dia civil
 * é lido (o do hospital, no `diaNoHospital`); depois disso a aritmética é sobre
 * o texto, e não pode voltar a depender de onde a tela está aberta.
 */
export function diaSeguinte(dia: string): string {
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

/**
 * O fim do expediente, como hora de desempate. O prazo do caso ainda em triagem
 * é data civil, sem hora: ele vale até o fim daquele dia, e não desde o começo.
 */
const FIM_DO_EXPEDIENTE = "23:59";

/**
 * A hora pela qual o caso é cobrado dentro do dia dele.
 *
 * O caso de triagem não tem hora, e tratar o nulo como texto vazio o punha na
 * frente de todo caso com hora do mesmo dia. Enquanto a lista era inteira isso
 * só embaralhava a ordem; com o corte em N do bloco de próximos vencimentos,
 * passou a decidir quem some da tela, e quem sumia era o mais urgente do dia.
 */
function horaDaCobranca(caso: CasoDoPainel): string {
  return caso.prazo_area_em ? horaNoHospital(caso.prazo_area_em) : FIM_DO_EXPEDIENTE;
}

/** A ordem da urgência, uma só, para os dois blocos que listam casos a vencer. */
function porVencimento(a: CasoDoPainel, b: CasoDoPainel): number {
  return (
    String(diaDaCobranca(a) ?? "").localeCompare(String(diaDaCobranca(b) ?? "")) ||
    horaDaCobranca(a).localeCompare(horaDaCobranca(b))
  );
}

/** As janelas que ainda não chegaram. Vencido e "vence hoje" têm bloco próprio. */
const JANELAS_FUTURAS: JanelaDeVencimento[] = ["amanha", "depois"];

/** Quantos casos o bloco dos próximos vencimentos mostra. */
export const LIMITE_DE_PROXIMOS_VENCIMENTOS = 5;

/** A lista que cabe no bloco, e quantos existem ao todo por trás dela. */
export interface ProximosVencimentos<T> {
  casos: T[];
  total: number;
}

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
): ProximosVencimentos<T> {
  const futuros = casos
    .filter((caso) => JANELAS_FUTURAS.includes(classificarJanela(caso, hoje)))
    .sort(porVencimento);
  return { casos: futuros.slice(0, limite), total: futuros.length };
}

/**
 * O que vai entre parênteses no título de um bloco que corta a lista.
 *
 * Nos blocos vizinhos o parêntese é o total, e é assim que o leitor aprendeu a
 * lê-lo. Repetir só o tamanho da lista cortada faria "Próximos vencimentos (5)"
 * afirmar que existem 5 casos a vencer quando existem 15, e ficaria preso nesse
 * 5 para sempre, porque numa Ouvidoria de prazo em dias quase sempre há mais de
 * 5 casos futuros. Este painel é projetado em sala de reunião.
 */
export function rotuloDaContagemParcial(mostrados: number, total: number): string {
  return mostrados < total ? `${mostrados} de ${total}` : String(total);
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
 * `degradado` vem do módulo de métricas e da listagem com o nome da leitura que
 * não pôde ser feita, ou que saiu incompleta. Cada entrada daqui diz o que a
 * tela perdeu com aquela leitura específica; quem não tem entrada aqui e não
 * está em `SILENCIADAS` sai com o texto genérico, nunca calado.
 *
 * A linha dos feriados é a perigosa, e o estrago dela atravessa as duas
 * leituras: a listagem calcula o rótulo em dias úteis de cada caso com a MESMA
 * tabela de feriados, e desde a issue #449 declara o `degradado` dela também.
 * Quando esta lista acusa `feriados`, venha da listagem ou das métricas, todo
 * número em dias úteis da tela está sob suspeita.
 */
const AVISOS: Record<string, string> = {
  feriados:
    "O calendário de feriados não pôde ser lido: todo prazo em dias úteis desta tela saiu contado como se todo dia útil fosse trabalhado, tanto o atraso das áreas quanto o de cada caso.",
  responsaveis:
    "O cadastro de responsáveis por setor não pôde ser lido: as pendências estão sem o nome de quem responde.",
  // A trilha de movimentos (issue #484). Ela alimenta um sinal cuja ausência é
  // igualzinha ao sinal desligado: fila sem ponto nenhum desenha a mesma tela
  // de fila sem novidade. Sem esta frase o ouvidor leria "nada mexeu" quando a
  // verdade é "não deu para olhar".
  movimentos:
    "A trilha de movimentos não pôde ser lida: nenhum caso está marcado como novidade nesta carga, mesmo que tenha mexido.",
  // A própria lista de casos, cortada no teto de linhas da paginação (issue
  // #448). É o pior dos carimbos, porque tudo desta tela é derivado dela: a
  // lista curta some com casos e ainda encolhe crítico, vencido, vence hoje,
  // próximos e a fila por status, todos com cara de contados direito.
  casos:
    "A lista de manifestações não pôde ser lida por inteiro: faltam casos nesta carga, e todos os números tirados dela estão por baixo.",
  // O registro do aviso ao manifestante (issue #493). Mesma armadilha da
  // trilha: a leitura que falhou desenha a linha de "na fila de envio", que é
  // o que um caso já entregue também deixaria de mostrar. Sem a frase, o
  // ouvidor lê um estado de envio que ninguém confirmou.
  acuse:
    "O registro do aviso ao manifestante não pôde ser lido: o estado de envio do acuse desta página não está confirmado.",
  // O registro do aviso de encerramento (issue #494), pela mesma razão: sem a
  // frase, a página do caso mostra "na fila de envio" num desfecho que pode já
  // ter sido entregue, ou que pode ter falhado.
  aviso_encerramento:
    "O registro do aviso de encerramento não pôde ser lido: o estado de envio do desfecho desta página não está confirmado.",
};

/**
 * As leituras que degradam de propósito EM SILÊNCIO, e o porquê de cada uma.
 *
 * `prazos` e `prorrogacoes` mexem nos trechos de prazo e na taxa de
 * prorrogação, que são do relatório e não desta tela: avisar sobre elas seria
 * ruído sobre número que ninguém está vendo aqui.
 *
 * A lista existe escrita porque o silêncio precisa ser uma DECISÃO, e não o
 * default. Antes, quem não estava em `AVISOS` sumia, e leitura silenciada de
 * propósito ficava indistinguível de carimbo novo que o backend passou a emitir
 * sem par aqui: foi assim que o carimbo `casos` chegou à tela e desapareceu.
 */
const SILENCIADAS = new Set(["prazos", "prorrogacoes"]);

/**
 * O texto de quem chegou sem par. Vago porque é o que se sabe: o nome da
 * leitura veio do backend e esta versão da tela não conhece o estrago dela.
 *
 * Vago e visível é melhor que preciso e ausente. Um aviso genérico manda o
 * ouvidor desconfiar do número e alguém abrir a issue; o silêncio manda ele
 * acreditar.
 */
function avisoGenerico(leitura: string): string {
  return `Uma leitura de apoio (${leitura}) não pôde ser feita por inteiro: parte dos números desta tela pode estar por baixo.`;
}

export function avisosDeDegradacao(degradado: string[]): AvisoDeDegradacao[] {
  return degradado
    .filter((leitura) => !SILENCIADAS.has(leitura))
    .map((leitura) => ({ leitura, texto: AVISOS[leitura] ?? avisoGenerico(leitura) }));
}

/**
 * O calendário útil foi lido inteiro. Enquanto não foi, nenhum número em dias
 * úteis da tela vale, nem o das áreas nem o rótulo de cada caso.
 *
 * `null` é a leitura que nem chegou (issue #437), ou a que veio de um backend
 * uma versão atrás e não declarou nada. Sem a declaração, a lista vazia virava
 * "nada degradou" e a tela voltava a afirmar a frase em dias úteis de cada caso
 * como se soubesse que os feriados foram lidos. Não saber não é saber que está
 * bom.
 *
 * A tela aplica isto às DUAS leituras do calendário, a das métricas e a da
 * listagem (issue #449): basta uma acusar para a frase sair da tela.
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
