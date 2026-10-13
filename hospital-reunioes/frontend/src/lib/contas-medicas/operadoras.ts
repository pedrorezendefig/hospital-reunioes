/**
 * O que as telas Operadoras e Memória da operadora dividem (issues #1119,
 * #1120 e #1140): os rótulos, as datas, as tabelas de preço e o download da
 * memória.
 */

export type Situacao = "PRONTA" | "PARCIAL" | "SEM_MEMORIA";

export interface VersaoDaTabela {
  tabela: string;
  versao: string | null;
  vigencia_inicio: string | null;
  vigencia_fim: string | null;
  /** A versão que a busca de preço escolhe para hoje. */
  em_uso: boolean;
}

export interface TabelaDaCategoria {
  categoria: string;
  tipo: string | null;
  situacao: "CARREGADA" | "NAO_CARREGADA";
  versoes: VersaoDaTabela[];
}

/** Qual coluna do arquivo do convênio é cada campo do item (issue #1146). */
export interface MapeamentoDeColunas {
  codigo: string;
  codigo_alternativo: string | null;
  descricao: string | null;
  unidade: string | null;
  /** `chave` é o nome do preço: "valor" quando é um só, o plano quando são vários. */
  precos: { chave: string; coluna: string }[];
}

export interface ItemDaAmostra {
  codigo: string;
  codigo_alternativo: string | null;
  descricao: string | null;
  unidade: string | null;
  precos: Record<string, number | string | null>;
}

/** A proposta do backend: o mapeamento, 20 itens convertidos e o total. Nada gravado. */
export interface PropostaDeMapeamento {
  cabecalho: string[];
  mapeamento: MapeamentoDeColunas;
  /** IA: a IA propôs; CONFIRMADO: reaproveitado de um arquivo de mesmo cabeçalho; PESSOA: o ajuste. */
  origem: "IA" | "CONFIRMADO" | "PESSOA";
  amostra: ItemDaAmostra[];
  total: number;
  erro: string | null;
}

export const LABEL_SITUACAO: Record<Situacao, string> = {
  PRONTA: "Pronta",
  PARCIAL: "Parcial",
  SEM_MEMORIA: "Sem memória",
};

export const COR_SITUACAO: Record<Situacao, string> = {
  PRONTA: "bg-emerald-50 text-emerald-700",
  PARCIAL: "bg-amber-50 text-amber-700",
  SEM_MEMORIA: "bg-slate-100 text-slate-600",
};

export const LABEL_CATEGORIA: Record<string, string> = {
  MATERIAL: "Materiais",
  MEDICAMENTO: "Medicamentos",
  DIARIA_TAXA: "Diárias e taxas",
  PACOTE: "Pacotes",
  HONORARIO: "Honorários",
  SADT: "SADT",
  PORTE_ANESTESICO: "Porte anestésico",
};

/** As categorias que recebem tabela pela tela. Honorário espera a CBHPM. */
export const CATEGORIAS_DE_ENVIO = ["MATERIAL", "MEDICAMENTO", "DIARIA_TAXA", "PACOTE"];

/** Categoria que só a memória conhece (a próxima operadora inventa) aparece pelo nome. */
export function rotuloDaCategoria(categoria: string): string {
  return LABEL_CATEGORIA[categoria] ?? categoria.replaceAll("_", " ");
}

/** "2026-08-01" (ou o timestamp do banco) vira "01/08/2026". */
export function dataBr(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

export function vigencia(v: VersaoDaTabela): string {
  if (!v.vigencia_inicio) return "";
  return v.vigencia_fim
    ? `${dataBr(v.vigencia_inicio)} a ${dataBr(v.vigencia_fim)}`
    : `desde ${dataBr(v.vigencia_inicio)}`;
}

export function plural(n: number, singular: string, varias: string): string {
  return `${n} ${n === 1 ? singular : varias}`;
}

export async function detalheDoErro(res: Response, padrao: string): Promise<string> {
  try {
    const corpo = await res.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // resposta sem JSON (ex.: 500 do proxy)
  }
  return padrao;
}

/**
 * Baixa a memória vigente da operadora no formato do arquivo, com o nome que o
 * servidor deu. Devolve a mensagem de erro, ou `null` quando baixou.
 */
export async function baixarMemoria(token: string, sigla: string): Promise<string | null> {
  const res = await fetch(`/api/contas-medicas/operadoras/${encodeURIComponent(sigla)}/memoria`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return detalheDoErro(res, "Não foi possível baixar a memória.");
  const nome = res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? `MEMORIA-${sigla}.md`;
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.click();
  URL.revokeObjectURL(url);
  return null;
}
