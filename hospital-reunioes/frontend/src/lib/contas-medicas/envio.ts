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

export interface ItemDaFila {
  id: string;
  numero_atendimento: string | null;
  numero_conta: string | null;
  situacao: SituacaoDaConta;
  falta: "prontuario" | "conta" | null;
  periodo_inicio: string | null;
  periodo_fim: string | null;
  nota_entrada: number | null;
  /** A nota depois do reenvio da conta corrigida (issue #1136); nula sem reenvio. */
  nota_saida?: number | null;
  valor_apontado: number | null;
  itens_feitos: number;
  itens_total: number;
  pendencias: number;
  erro_motivo: string | null;
}

export interface Fila {
  fila: ItemDaFila[];
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
  PROCESSANDO: "Pronta em instantes",
  A_FAZER: "A fazer",
  EM_CORRECAO: "Em correção",
  CONCLUIDA: "Concluída",
  CONCLUIDA_COM_PENDENCIA: "Concluída com pendência",
  RETORNO: "Retorno",
  ERRO: "Erro",
};

export function rotuloDaSituacao(conta: ItemDaFila): string {
  if (conta.situacao === "AGUARDANDO_ARQUIVO") {
    if (conta.falta === "conta") return "Falta a conta";
    if (conta.falta === "prontuario") return "Falta o prontuário";
  }
  return ROTULO[conta.situacao] ?? conta.situacao;
}

const DINHEIRO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
