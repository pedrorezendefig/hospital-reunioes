/**
 * As configurações do Canal de Conduta (issue #1826): os tipos que a API
 * devolve e a chamada autenticada às rotas do Comitê.
 */
import { createClient } from "@/lib/supabase/client";

export interface VersaoDaConfiguracao {
  id: string;
  versao: number;
  texto: string;
  autor: string;
  criado_em: string;
}

export interface ItemDaConfiguracao {
  chave: string;
  rotulo: string;
  grupo: string;
  /** Lido pelas telas públicas, sem login. */
  publico: boolean;
  /** Da mais nova (a vigente) para a mais antiga. */
  versoes: VersaoDaConfiguracao[];
}

export const ROTA_DAS_CONFIGURACOES = "/api/comite-de-conduta/configuracoes";

/** O erro da API com o código, para a tela separar a recusa (403) da falha. */
export class ErroDoCanal extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** "Versão 2, por Fulana em 12/11/2026", com o dia em São Paulo. */
export function linhaDaVersao(v: VersaoDaConfiguracao): string {
  const dia = new Date(v.criado_em).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  return `Versão ${v.versao}, por ${v.autor || "autor sem nome"} em ${dia}`;
}

export async function chamarConduta<T>(caminho: string, opcoes: { method?: string; body?: unknown } = {}): Promise<T> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  const headers: Record<string, string> = { Authorization: `Bearer ${session?.access_token ?? ""}` };
  if (opcoes.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(caminho, {
    method: opcoes.method ?? "GET",
    headers,
    body: opcoes.body !== undefined ? JSON.stringify(opcoes.body) : undefined,
  });
  if (!res.ok) {
    const corpo = await res.json().catch(() => null);
    const detalhe = typeof corpo?.detail === "string" ? corpo.detail : "Não foi possível concluir. Tente de novo.";
    throw new ErroDoCanal(detalhe, res.status);
  }
  return (await res.json()) as T;
}
