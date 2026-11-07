/**
 * O envio e a fila de Contas médicas: tipos, limites e textos (issue #1123,
 * PRD #1113, ADR 0070).
 *
 * Quem decide o pareamento, o tipo do arquivo e as recusas é o servidor. Aqui
 * ficam os limites que dá para conferir antes de subir (30 arquivos, 100 MB por
 * arquivo), a divisão em lotes e as frases da fila.
 *
 * Os lotes existem por causa do teto do corpo do backend, de 100 MiB, que não
 * muda: um prontuário sozinho chega perto disso. Cada lote é uma requisição, e
 * todos levam o mesmo `envio_id`, para os limites e o "Último envio" valerem
 * para o envio inteiro.
 */

export const ROTA_ENVIO = "/api/contas-medicas/envios";
export const ROTA_FILA = "/api/contas-medicas/fila";
export const ROTA_MEUS_ENVIOS = "/api/contas-medicas/meus-envios";
export const ROTA_ME = "/api/contas-medicas/me";

/** Descartar a conta em Erro ou Aguardando arquivo (issue #1338). */
export function rotaDoDescarte(contaId: string): string {
  return `/api/contas-medicas/contas/${contaId}/descartar`;
}

/** A pergunta antes de apagar: o atendimento e o aviso de que os arquivos saem. */
export function perguntaDoDescarte(conta: ItemDaFila): string {
  return `Descartar o atendimento ${conta.numero_atendimento}? Os arquivos serão apagados.`;
}

/** A conta em Erro da IA volta para a fila sem anexar o PDF (issue #1339). */
export function rotaAnalisarDeNovo(contaId: string): string {
  return `/api/contas-medicas/contas/${contaId}/analisar-de-novo`;
}

/** A conta parada por folha escaneada ilegível segue mesmo assim (issue #1401). */
export function rotaAnalisarAssimMesmo(contaId: string): string {
  return `/api/contas-medicas/contas/${contaId}/analisar-assim-mesmo`;
}

/** "Enviar contas": o envio e Meus envios (issue #1308, ADR 0073). */
export const ENVIAR_CONTAS = "enviar_contas";
/** "Analisar contas" na tela; a chave guarda o nome antigo (ADR 0073). */
export const ANALISAR_CONTAS = "enviar_corrigir_contas";

export const LIMITE_DE_ARQUIVOS = 30;
/** 100 MB como o computador mostra o tamanho (mil vezes mil), igual ao backend. */
export const LIMITE_POR_ARQUIVO = 100 * 1000 * 1000;
/** A soma de um lote com mais de um arquivo, com folga para o multipart. */
export const TETO_DO_LOTE = 90 * 1000 * 1000;

export const MENSAGEM_ARQUIVOS_DEMAIS = `O envio já tem ${LIMITE_DE_ARQUIVOS} arquivos, o limite. Mande este num próximo envio.`;
export const MENSAGEM_ARQUIVO_GRANDE = "O arquivo passa de 100 MB, o limite por arquivo.";

export interface LinhaDoUltimoEnvio {
  numero_atendimento: string;
  frase: string;
  texto: string;
  aviso: string | null;
}

export interface Recusa {
  arquivo: string;
  numero_atendimento: string | null;
  motivo: string;
}

export interface RespostaDoEnvio {
  envio_id: string | null;
  ultimo_envio: LinhaDoUltimoEnvio[];
  recusas: Recusa[];
}

export type SituacaoDaConta =
  | "AGUARDANDO_ARQUIVO"
  | "NA_FILA"
  | "PROCESSANDO"
  | "A_FAZER"
  | "EM_CORRECAO"
  | "CONCLUIDA"
  | "CONCLUIDA_COM_PENDENCIA"
  | "RETORNO"
  | "ERRO";

/** As cinco Etapas do processamento da tela (issue #1416), na ordem. */
export type EtapaDoProcessamento =
  | "LENDO_CONTA"
  | "LENDO_PRONTUARIO"
  | "IA_LENDO_PRONTUARIO"
  | "CONFERINDO"
  | "IA_MONTANDO_GUIA";

export interface ItemDaFila {
  id: string;
  numero_atendimento: string | null;
  numero_conta: string | null;
  situacao: SituacaoDaConta;
  falta: "prontuario" | "conta" | null;
  periodo_inicio: string | null;
  periodo_fim: string | null;
  /** As páginas do último Prontuário do atendimento (issue #1336); nulas sem prontuário. */
  prontuario_paginas?: number | null;
  nota_entrada: number | null;
  /** A nota depois do reenvio da conta corrigida (issue #1136); nula sem reenvio. */
  nota_saida?: number | null;
  valor_apontado: number | null;
  itens_feitos: number;
  itens_total: number;
  pendencias: number;
  erro_motivo: string | null;
  /**
   * O Código do erro da conta em Erro (issue #1337), nulo fora dele: o código,
   * o detalhe técnico numa linha, a hora do erro, o arquivo em que a análise
   * parou (o quadrado vermelho) e a ação que resolve.
   */
  erro_codigo?: string | null;
  erro_detalhe?: string | null;
  erro_em?: string | null;
  erro_arquivo?: "conta" | "prontuario" | null;
  erro_acao?: "analisar_de_novo" | "enviar_de_novo" | null;
  /**
   * O botão "Analisar assim mesmo" ao lado de "Enviar de novo" (issue #1401):
   * o servidor diz quando cabe (CM-ARQ-DIGITALIZADO com os PDFs guardados).
   */
  pode_analisar_assim_mesmo?: boolean;
  /** O botão Descartar do cartão do envio (issue #1338): o servidor diz quando cabe. */
  pode_descartar?: boolean;
  /**
   * A conta em Processando (issue #1416), nulo fora dele: a Etapa do
   * processamento, a parte do Passo A ("parte 3 de 7"), desde quando a etapa
   * e o processamento começaram e a tentativa (1 a 3).
   */
  etapa?: EtapaDoProcessamento | null;
  parte?: number | null;
  partes?: number | null;
  etapa_desde?: string | null;
  processando_desde?: string | null;
  tentativa?: number | null;
  /** Só para quem tem "painel completo": quem está com a conta (issue #1307). */
  com?: string | null;
}

/**
 * A tela Contas (issue #1307, ADR 0073): a Fila comum das livres, "Minhas"
 * (as que a pessoa puxou e não concluiu), "Meus envios" (as que ela enviou e
 * não ficaram prontas) e as Concluídas. Com `todas`, a pessoa tem o painel
 * completo e as listas trazem as contas de todas.
 */
export interface Fila {
  todas: boolean;
  fila: ItemDaFila[];
  minhas: ItemDaFila[];
  meus_envios: ItemDaFila[];
  concluidas: ItemDaFila[];
}

/** Os arquivos que sobem e os que ficam de fora, com a frase de cada um. */
export function separarArquivos(arquivos: File[]): { aceitos: File[]; recusas: Recusa[] } {
  const aceitos: File[] = [];
  const recusas: Recusa[] = [];
  for (const arquivo of arquivos) {
    let motivo: string | null = null;
    if (arquivo.size > LIMITE_POR_ARQUIVO) motivo = MENSAGEM_ARQUIVO_GRANDE;
    else if (aceitos.length >= LIMITE_DE_ARQUIVOS) motivo = MENSAGEM_ARQUIVOS_DEMAIS;
    if (motivo) recusas.push({ arquivo: arquivo.name, numero_atendimento: null, motivo });
    else aceitos.push(arquivo);
  }
  return { aceitos, recusas };
}

/** Os arquivos em lotes, na ordem em que vieram, cada lote até o teto. */
export function lotes(arquivos: File[], teto = TETO_DO_LOTE): File[][] {
  const resultado: File[][] = [];
  let atual: File[] = [];
  let soma = 0;
  for (const arquivo of arquivos) {
    if (atual.length > 0 && soma + arquivo.size > teto) {
      resultado.push(atual);
      atual = [];
      soma = 0;
    }
    atual.push(arquivo);
    soma += arquivo.size;
  }
  if (atual.length > 0) resultado.push(atual);
  return resultado;
}

async function motivoDoErro(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // resposta sem JSON (ex.: 502 do proxy)
  }
  return "Não consegui enviar este arquivo. Envie de novo.";
}

type Buscar = (url: string, init?: RequestInit) => Promise<Response>;

async function analisarPelaRota(rota: string, token: string, buscar: Buscar): Promise<string | null> {
  let resposta: Response;
  try {
    resposta = await buscar(rota, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    return "Não consegui falar com o servidor. Tente de novo.";
  }
  if (resposta.ok) return null;
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // resposta sem JSON (ex.: 502 do proxy)
  }
  return "Não consegui analisar de novo. Tente de novo.";
}

/**
 * Põe a conta em Erro de volta na fila (issue #1339). Devolve nulo quando deu
 * certo, ou a frase do servidor para mostrar no cartão.
 */
export async function analisarDeNovo(contaId: string, token: string, buscar: Buscar = fetch): Promise<string | null> {
  return analisarPelaRota(rotaAnalisarDeNovo(contaId), token, buscar);
}

/**
 * Põe a conta parada em CM-ARQ-DIGITALIZADO de volta na fila, para a análise
 * seguir com as folhas a conferir à mão (issue #1401). Nulo quando deu certo,
 * ou a frase do servidor.
 */
export async function analisarAssimMesmo(
  contaId: string,
  token: string,
  buscar: Buscar = fetch,
): Promise<string | null> {
  return analisarPelaRota(rotaAnalisarAssimMesmo(contaId), token, buscar);
}

/**
 * Sobe os arquivos lote a lote, no mesmo envio, e devolve o "Último envio"
 * do envio inteiro com as recusas de todos os lotes. Lote que o servidor
 * recusa inteiro vira uma recusa por arquivo, e o envio segue.
 */
export async function enviarEmLotes(arquivos: File[], token: string, buscar: Buscar = fetch): Promise<RespostaDoEnvio> {
  const resultado: RespostaDoEnvio = { envio_id: null, ultimo_envio: [], recusas: [] };
  for (const lote of lotes(arquivos)) {
    const corpo = new FormData();
    if (resultado.envio_id) corpo.append("envio_id", resultado.envio_id);
    for (const arquivo of lote) corpo.append("arquivos", arquivo, arquivo.name);
    let resposta: Response;
    try {
      resposta = await buscar(ROTA_ENVIO, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: corpo,
      });
    } catch {
      resposta = new Response(null, { status: 599 });
    }
    if (!resposta.ok) {
      const motivo = await motivoDoErro(resposta);
      resultado.recusas.push(...lote.map((f) => ({ arquivo: f.name, numero_atendimento: null, motivo })));
      continue;
    }
    const parcial: RespostaDoEnvio = await resposta.json();
    resultado.envio_id = parcial.envio_id;
    resultado.ultimo_envio = parcial.ultimo_envio;
    resultado.recusas.push(...parcial.recusas);
  }
  return resultado;
}

const ROTULO: Record<SituacaoDaConta, string> = {
  AGUARDANDO_ARQUIVO: "Falta arquivo",
  NA_FILA: "Na fila",
  PROCESSANDO: "Processando",
  A_FAZER: "A fazer",
  EM_CORRECAO: "Em correção",
  CONCLUIDA: "Concluída",
  CONCLUIDA_COM_PENDENCIA: "Concluída com pendência",
  RETORNO: "Retorno",
  ERRO: "Erro",
};

const NOME_DA_ETAPA: Record<EtapaDoProcessamento, string> = {
  LENDO_CONTA: "Lendo a conta",
  LENDO_PRONTUARIO: "Lendo o prontuário",
  IA_LENDO_PRONTUARIO: "IA lendo o prontuário",
  CONFERINDO: "Conferindo",
  IA_MONTANDO_GUIA: "IA montando o Guia",
};

/** Quantas tentativas a análise tem antes de virar Erro (o Motor, `MAXIMO_DE_TENTATIVAS`). */
export const MAXIMO_DE_TENTATIVAS = 3;

/** Quanto tempo passou desde `desde`: "há menos de 1 min", "há 4 min", "há 1 h 5 min". */
function tempoDecorrido(desde: string, agora: Date): string {
  const minutos = Math.floor((agora.getTime() - new Date(desde).getTime()) / 60_000);
  if (minutos < 1) return "há menos de 1 min";
  if (minutos < 60) return `há ${minutos} min`;
  const resto = minutos % 60;
  return `há ${Math.floor(minutos / 60)} h` + (resto ? ` ${resto} min` : "");
}

/**
 * A pílula da conta em Processando (issue #1416): "Processando", a Etapa do
 * processamento com a parte do Passo A quando houver, e o tempo decorrido.
 */
function rotuloDoProcessamento(conta: ItemDaFila, agora: Date): string {
  const partes = ["Processando"];
  if (conta.etapa) {
    const parte = conta.parte && conta.partes ? `, parte ${conta.parte} de ${conta.partes}` : "";
    partes.push(NOME_DA_ETAPA[conta.etapa] + parte);
  }
  if (conta.processando_desde) partes.push(tempoDecorrido(conta.processando_desde, agora));
  return partes.join(", ");
}

export function rotuloDaSituacao(conta: ItemDaFila, agora: Date = new Date()): string {
  if (conta.situacao === "AGUARDANDO_ARQUIVO") {
    if (conta.falta === "conta") return "Falta a conta";
    if (conta.falta === "prontuario") return "Falta o prontuário";
  }
  if (conta.situacao === "PROCESSANDO") return rotuloDoProcessamento(conta, agora);
  return ROTULO[conta.situacao] ?? conta.situacao;
}

/**
 * O aviso de cada conta que estava Processando e sumiu da lista de envios
 * (issue #1416): sair de Processando sem ir para Erro nem para a fila é ficar
 * pronta, e a conta pronta sai dos envios e vai para a Fila. Um aviso por
 * atendimento, mesmo com duas parciais prontas juntas.
 */
export function avisosDeProntas(antes: ItemDaFila[], depois: ItemDaFila[]): string[] {
  const ficaram = new Set(depois.map((conta) => conta.id));
  const atendimentos = antes
    .filter((conta) => conta.situacao === "PROCESSANDO" && !ficaram.has(conta.id))
    .map((conta) => conta.numero_atendimento);
  return [...new Set(atendimentos)].map((numero) => `Atendimento ${numero} pronto, foi para a Fila`);
}

const DINHEIRO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** O detalhe do Processamento de uma conta, para o painel lateral (issue #1418). */
export function rotaDoProcessamento(contaId: string): string {
  return `/api/contas-medicas/contas/${contaId}/processamento`;
}

/** Uma das cinco etapas no painel: feita, em curso ou por fazer, com o tempo em segundos. */
export interface EtapaNoPainel {
  etapa: EtapaDoProcessamento;
  estado: "feita" | "atual" | "falta";
  tempo_s: number | null;
}

/**
 * O que a rota do painel devolve. O custo da IA (modelo, chamadas, tokens e
 * dólares) só vem para quem tem "painel completo": para os outros, as chaves
 * não existem.
 */
export interface DetalheDoProcessamento {
  id: string;
  situacao: SituacaoDaConta;
  etapas: EtapaNoPainel[];
  parte: number | null;
  partes: number | null;
  tentativa: number | null;
  posicao_na_fila: number | null;
  modelo?: string | null;
  chamadas?: number;
  tokens_entrada?: number;
  tokens_saida?: number;
  tokens_cache?: number;
  custo_usd?: number;
}

/** O nome da etapa como a tela mostra. */
export function nomeDaEtapa(etapa: EtapaDoProcessamento): string {
  return NOME_DA_ETAPA[etapa];
}

/** Quanto a etapa levou: "3 s", "4 min 5 s", "1 h 2 min". */
export function duracao(segundos: number): string {
  const total = Math.round(segundos);
  if (total < 60) return `${total} s`;
  if (total < 3600) {
    const resto = total % 60;
    return `${Math.floor(total / 60)} min` + (resto ? ` ${resto} s` : "");
  }
  const minutos = Math.floor((total % 3600) / 60);
  return `${Math.floor(total / 3600)} h` + (minutos ? ` ${minutos} min` : "");
}

/** O custo da conta em dólar, com as casas que uma conta barata precisa. */
export function dolares(valor: number): string {
  return `US$ ${valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

/** O que vem ao lado da situação: a nota, o R$ e os itens; o motivo do erro; as pendências. */
export function detalheDaConta(conta: ItemDaFila): string {
  const nota = conta.nota_entrada != null ? `Nota ${conta.nota_entrada}` : null;
  switch (conta.situacao) {
    case "A_FAZER":
    case "EM_CORRECAO":
      return [
        nota,
        conta.valor_apontado != null ? `R$ ${DINHEIRO.format(conta.valor_apontado)}` : null,
        `${conta.itens_feitos} de ${conta.itens_total}`,
      ]
        .filter(Boolean)
        .join(", ");
    case "ERRO":
      return conta.erro_motivo ?? "";
    case "PROCESSANDO":
      // A conta que voltou para a fila por prazo e foi pega de novo (issue #1416).
      return conta.tentativa && conta.tentativa > 1 ? `tentativa ${conta.tentativa} de ${MAXIMO_DE_TENTATIVAS}` : "";
    case "CONCLUIDA":
    case "CONCLUIDA_COM_PENDENCIA": {
      const pendencias =
        conta.pendencias > 0 ? `${conta.pendencias} ${conta.pendencias === 1 ? "pendência" : "pendências"}` : null;
      const notas =
        conta.nota_saida != null && conta.nota_entrada != null
          ? `Nota de entrada ${conta.nota_entrada}, nota de saída ${conta.nota_saida}`
          : nota;
      return [notas, pendencias].filter(Boolean).join(", ");
    }
    default:
      return "";
  }
}

const DATA_E_HORA = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** A data e a hora no fuso do hospital, como "01/11/2026 14:32". */
export function dataEHora(instante: Date): string {
  return DATA_E_HORA.format(instante).replace(",", "");
}

/**
 * O que "Copiar para a TI" leva da conta em Erro (issue #1337): o código, o
 * atendimento, a conta, a data e a hora do erro e o detalhe técnico, uma linha
 * cada, para colar no WhatsApp. A conta marcada pela migration (o erro de
 * antes do código) não tem hora gravada: vale a hora da cópia.
 */
export function textoParaATI(conta: ItemDaFila, agora: Date = new Date()): string {
  return [
    `Código do erro: ${conta.erro_codigo ?? "sem código"}`,
    `Atendimento: ${conta.numero_atendimento ?? "sem número"}`,
    `Conta: ${conta.numero_conta ?? "sem número"}`,
    `Data e hora: ${dataEHora(conta.erro_em ? new Date(conta.erro_em) : agora)}`,
    `Detalhe: ${conta.erro_detalhe ?? "sem detalhe técnico gravado"}`,
  ].join("\n");
}
