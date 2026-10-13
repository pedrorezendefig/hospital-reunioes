/**
 * A fila de Validação: tipos, textos e as chamadas da tela (issue #1142, PRD #1129).
 *
 * O servidor manda os temas abertos já em ordem (do maior R$ em jogo para o
 * menor) e os três números do topo prontos; aqui só se escreve o que a tela
 * mostra e se fala com as rotas de decisão.
 */

import { detalheDoErro } from "@/lib/contas-medicas/operadoras";

export type TipoDeTema = "REGRA_PENDENTE" | "BLOQUEADO" | "OBSERVACAO" | "DICIONARIO";

export type Decisao =
  | "VALIDAR_REGRA"
  | "DEIXAR_PENDENTE"
  | "DESCARTAR"
  | "MANTER_REGRA"
  | "EDITAR_REGRA"
  | "RESPONDER"
  | "CONFIRMAR"
  | "REJEITAR";

export interface RegraDoTema {
  texto: string;
  tipo: "CONTRATUAL" | "OPERACIONAL" | null;
  origem: string | null;
  status: "VIGENTE" | "PENDENTE";
}

export interface Tema {
  id: string;
  tipo: TipoDeTema;
  titulo: string;
  operadora: string | null;
  regra_codigo: string | null;
  regra: RegraDoTema | null;
  codigo_item: string | null;
  contas: number;
  desde: string | null;
  valor: number;
  leitura_ia: string | null;
  observacoes: string[];
  dicionario: { termo: string; codigo_conta: string | null; descricao_conta: string | null } | null;
}

export interface FilaDeValidacao {
  numeros: { aguardando_decisao: number; contas_afetadas: number; valor_em_jogo: number };
  temas: Tema[];
}

export const ROTULO_DO_TIPO: Record<TipoDeTema, string> = {
  REGRA_PENDENTE: "Regra pendente",
  BLOQUEADO: "Código bloqueado",
  OBSERVACAO: "Observação do time",
  DICIONARIO: "Termo do dicionário",
};

export const ROTA_DA_FILA = "/api/contas-medicas/validacao";

function rotaDoTema(tema: Tema, acao: "decisao" | "cadastro" | "leitura"): string {
  return `${ROTA_DA_FILA}/temas/${encodeURIComponent(tema.id)}/${acao}`;
}

/** Grava a decisão. Devolve a mensagem de erro, ou `null` quando deu certo. */
export async function decidir(
  token: string,
  tema: Tema,
  decisao: Decisao,
  corpo: { texto?: string; tipo?: string | null; origem?: string | null } = {},
): Promise<string | null> {
  const res = await fetch(rotaDoTema(tema, "decisao"), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ decisao, ...corpo }),
  });
  return res.ok ? null : detalheDoErro(res, "Não foi possível gravar a decisão.");
}

/** "Enviar ao cadastro": fecha o tema e baixa a lista em CSV. */
export async function enviarAoCadastro(token: string, tema: Tema): Promise<string | null> {
  const res = await fetch(rotaDoTema(tema, "cadastro"), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return detalheDoErro(res, "Não foi possível gerar a lista do cadastro.");
  const nome = res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "cadastro.csv";
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.click();
  URL.revokeObjectURL(url);
  return null;
}

/** A leitura da IA sobre as observações: a guardada ou uma nova. */
export async function lerObservacao(token: string, tema: Tema): Promise<{ leitura?: string; erro?: string }> {
  const res = await fetch(rotaDoTema(tema, "leitura"), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { erro: await detalheDoErro(res, "Não foi possível ler a observação.") };
  const corpo = await res.json();
  return { leitura: corpo.leitura_ia };
}
