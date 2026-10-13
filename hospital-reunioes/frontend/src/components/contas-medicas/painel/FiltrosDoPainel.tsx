"use client";

import { Select } from "@/components/ui/Select";
import {
  ROTULO_TIPO,
  type FiltrosDoPainel as Filtros,
  type Painel,
  type TipoDeConta,
} from "@/lib/contas-medicas/painel";

const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";

const OPCOES_DE_TIPO = [
  { value: "", label: "Todos" },
  ...(Object.entries(ROTULO_TIPO) as [TipoDeConta, string][]).map(([value, label]) => ({ value, label })),
];

/**
 * Os três filtros do Painel: a semana (qualquer dia dela; o servidor acha a
 * segunda), a operadora e o tipo de conta. Cada mudança pede o Painel de novo.
 */
export function FiltrosDoPainel({
  filtros,
  operadoras,
  aoMudar,
}: {
  filtros: Filtros;
  operadoras: Painel["filtros"]["operadoras"];
  aoMudar: (filtros: Filtros) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="block text-xs font-medium text-slate-600">
        <span className="mb-1 block">Semana</span>
        <input
          type="date"
          aria-label="Semana"
          className={CAMPO}
          value={filtros.semana}
          onChange={(e) => aoMudar({ ...filtros, semana: e.target.value })}
        />
      </label>
      <Select
        label="Operadora"
        value={filtros.operadora}
        options={[{ value: "", label: "Todas" }, ...operadoras.map((o) => ({ value: o.id, label: o.sigla }))]}
        onChange={(operadora) => aoMudar({ ...filtros, operadora })}
      />
      <Select
        label="Tipo de conta"
        value={filtros.tipo}
        options={OPCOES_DE_TIPO}
        onChange={(tipo) => aoMudar({ ...filtros, tipo: tipo as Filtros["tipo"] })}
      />
    </div>
  );
}
