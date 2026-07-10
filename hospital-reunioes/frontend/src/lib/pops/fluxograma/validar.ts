/**
 * Validação da gramática do Fluxograma no cliente (ADR 0024, issue #221),
 * espelho de `validar_fluxograma` do backend.
 *
 * O backend já recusa objeto fora da gramática (persiste como string JSON, não
 * como objeto), então o `conteudo` que chega como objeto normalmente é válido.
 * Esta guarda protege o renderer de qualquer objeto malformado que escape: o
 * componente cai no aviso de regeração em vez de desenhar lixo ou quebrar.
 */

import type { FluxogramaEstrutura, FluxogramaNo } from "./tipos";

function textoNaoVazio(v: unknown): v is string {
  return typeof v === "string" && v.trim().length > 0;
}

function validarNo(no: unknown, ids: Set<string>): no is FluxogramaNo {
  if (!no || typeof no !== "object") return false;
  const n = no as Record<string, unknown>;
  if (!textoNaoVazio(n.id)) return false;
  if (n.tipo !== "passo" && n.tipo !== "decisao") return false;
  if (!textoNaoVazio(n.texto)) return false;

  if (n.tipo === "passo") {
    return n.ramos == null || (Array.isArray(n.ramos) && n.ramos.length === 0);
  }

  // decisao: exatamente 2 ramos nesta fatia (3+ ramos sao a fatia #222).
  if (!Array.isArray(n.ramos) || n.ramos.length !== 2) return false;
  let comDesvio = 0;
  for (const ramo of n.ramos) {
    if (!ramo || typeof ramo !== "object") return false;
    const r = ramo as Record<string, unknown>;
    if (!textoNaoVazio(r.rotulo)) return false;
    if (r.desvio != null) {
      if (typeof r.desvio !== "object") return false;
      const d = r.desvio as Record<string, unknown>;
      if (!textoNaoVazio(d.texto)) return false;
      if (d.retorna_para != null && !ids.has(d.retorna_para as string)) return false;
      comDesvio += 1;
    }
  }
  // Layout fechado (coluna principal + desvio lateral): no maximo um desvio.
  return comDesvio <= 1;
}

/** Coleta os ids validos primeiro (para checar `retorna_para`), depois valida
 * cada no. Ids duplicados invalidam a estrutura (como no backend). */
export function fluxogramaValido(obj: unknown): obj is FluxogramaEstrutura {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return false;
  const nos = (obj as Record<string, unknown>).nos;
  if (!Array.isArray(nos) || nos.length === 0) return false;

  const ids = new Set<string>();
  for (const no of nos) {
    const id = (no as Record<string, unknown>)?.id;
    if (typeof id !== "string") return false;
    if (ids.has(id)) return false;
    ids.add(id);
  }
  return nos.every((no) => validarNo(no, ids));
}
