"use client";

/**
 * A prévia da importação da Memória (issue #1486, ADR 0081, decisão 10).
 *
 * O arquivo enviado é comparado com a versão vigente da operadora, Regra a
 * Regra pelo código: as incluídas, as alteradas (o texto antes e depois, e o
 * tipo, a origem ou o status que mudou) e as removidas. Nada é gravado antes
 * de "Confirmar e gravar": o `.md` trabalhado fora do app não sobrescreve às
 * cegas o que foi ensinado pela tela.
 */

import { Check, Loader2 } from "lucide-react";
import { plural } from "@/lib/contas-medicas/operadoras";

interface RegraDaPrevia {
  texto: string;
  tipo: string | null;
  origem: string | null;
  status: string;
}

export interface PreviaDaImportacao {
  operadora: string;
  versao: string;
  versao_vigente: string | null;
  regras: { total: number; vigentes: number; pendentes: number };
  incluidas: (RegraDaPrevia & { codigo: string })[];
  alteradas: { codigo: string; antes: RegraDaPrevia; depois: RegraDaPrevia }[];
  removidas: (RegraDaPrevia & { codigo: string })[];
}

const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_SECUNDARIO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm font-medium disabled:opacity-50";

const CAMPOS_ROTULADOS = [
  ["tipo", "Tipo"],
  ["origem", "Origem"],
  ["status", "Status"],
] as const;

/** `PENDENTE` vira "Pendente"; vazio vira "sem". */
function valor(texto: string | null): string {
  return texto ? texto.charAt(0) + texto.slice(1).toLowerCase() : "sem";
}

function Lista({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <ul aria-label={rotulo} className="mt-1 space-y-2">
      {children}
    </ul>
  );
}

export function PreviaDaMemoria({
  previa,
  ocupado,
  aoConfirmar,
  aoCancelar,
}: {
  previa: PreviaDaImportacao;
  ocupado: boolean;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}) {
  const nada = !previa.incluidas.length && !previa.alteradas.length && !previa.removidas.length;
  return (
    <section aria-label="O que muda na memória" className="mt-6 border-t border-slate-100 pt-4 text-sm">
      <h3 className="font-semibold text-slate-900">O que muda na memória</h3>
      <p className="text-slate-600 mt-0.5">
        {previa.versao_vigente
          ? `${previa.operadora}, da versão ${previa.versao_vigente} para a ${previa.versao}. `
          : `A ${previa.operadora} ainda não tem memória: todas as Regras do arquivo entram. `}
        O arquivo tem {plural(previa.regras.vigentes, "regra vigente", "regras vigentes")} e{" "}
        {plural(previa.regras.pendentes, "pendente", "pendentes")}. Nada é gravado antes de confirmar.
      </p>
      {nada && <p className="mt-3 text-slate-700">Nenhuma Regra muda em relação à versão vigente.</p>}

      {previa.incluidas.length > 0 && (
        <div className="mt-4">
          <h4 className="font-medium text-emerald-800">Incluídas ({previa.incluidas.length})</h4>
          <Lista rotulo="Incluídas">
            {previa.incluidas.map((r) => (
              <li key={r.codigo}>
                <span className="font-mono text-slate-600">{r.codigo}</span>{" "}
                <span className="text-slate-800 whitespace-pre-line">{r.texto}</span>
              </li>
            ))}
          </Lista>
        </div>
      )}

      {previa.alteradas.length > 0 && (
        <div className="mt-4">
          <h4 className="font-medium text-amber-800">Alteradas ({previa.alteradas.length})</h4>
          <Lista rotulo="Alteradas">
            {previa.alteradas.map(({ codigo, antes, depois }) => (
              <li key={codigo}>
                <span className="font-mono text-slate-600">{codigo}</span>
                {antes.texto !== depois.texto ? (
                  <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <dt className="text-xs uppercase text-slate-500">Antes</dt>
                    <dd className="text-slate-500 line-through whitespace-pre-line">{antes.texto}</dd>
                    <dt className="text-xs uppercase text-slate-500">Depois</dt>
                    <dd className="text-slate-800 whitespace-pre-line">{depois.texto}</dd>
                  </dl>
                ) : (
                  <span className="text-slate-800 whitespace-pre-line"> {depois.texto}</span>
                )}
                {CAMPOS_ROTULADOS.filter(([campo]) => antes[campo] !== depois[campo]).map(([campo, rotulo]) => (
                  <p key={campo} className="mt-1 text-xs text-slate-600">
                    {rotulo}: {valor(antes[campo])} para {valor(depois[campo])}
                  </p>
                ))}
              </li>
            ))}
          </Lista>
        </div>
      )}

      {previa.removidas.length > 0 && (
        <div className="mt-4">
          <h4 className="font-medium text-red-800">Removidas ({previa.removidas.length})</h4>
          <Lista rotulo="Removidas">
            {previa.removidas.map((r) => (
              <li key={r.codigo}>
                <span className="font-mono text-slate-600">{r.codigo}</span>{" "}
                <span className="text-slate-800 whitespace-pre-line">{r.texto}</span>
              </li>
            ))}
          </Lista>
        </div>
      )}

      <div className="flex flex-wrap gap-3 mt-4">
        <button type="button" onClick={aoConfirmar} disabled={ocupado} className={BOTAO}>
          {ocupado ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Check className="w-4 h-4" aria-hidden="true" />
          )}
          Confirmar e gravar
        </button>
        <button type="button" onClick={aoCancelar} disabled={ocupado} className={BOTAO_SECUNDARIO}>
          Cancelar
        </button>
      </div>
    </section>
  );
}
