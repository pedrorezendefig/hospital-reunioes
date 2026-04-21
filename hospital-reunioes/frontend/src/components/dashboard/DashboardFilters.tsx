"use client";

import { Filter } from "lucide-react";
import { MultiSelect } from "@/components/ui/MultiSelect";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DashboardFiltersProps {
  filtroSetores: string[];
  filtroResponsaveis: string[];
  filtroPrazoDe: string;
  filtroPrazoAte: string;
  userRole: string;
  setoresOptions: { value: string; label: string }[];
  responsavelOptions: { value: string; label: string }[];
  onSetFiltroSetores: (v: string[]) => void;
  onSetFiltroResponsaveis: (v: string[]) => void;
  onSetFiltroPrazoDe: (v: string) => void;
  onSetFiltroPrazoAte: (v: string) => void;
  onReset: () => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function DashboardFilters({
  filtroSetores,
  filtroResponsaveis,
  filtroPrazoDe,
  filtroPrazoAte,
  setoresOptions,
  responsavelOptions,
  onSetFiltroSetores,
  onSetFiltroResponsaveis,
  onSetFiltroPrazoDe,
  onSetFiltroPrazoAte,
  onReset,
}: DashboardFiltersProps) {
  const hasActiveFilters =
    filtroSetores.length > 0 ||
    filtroResponsaveis.length > 0 ||
    filtroPrazoDe !== "" ||
    filtroPrazoAte !== "";

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col gap-4 mb-8">
      <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm">
        <Filter className="w-4 h-4" />
        <span>Filtros Dinâmicos de Desempenho</span>
        {hasActiveFilters && (
          <span className="ml-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">
            Ativos
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 items-end">
        {/* Setor — MultiSelect */}
        <MultiSelect
          id="filtro-setor"
          label="Setor"
          options={setoresOptions}
          selected={filtroSetores}
          onChange={(v) => {
            onSetFiltroSetores(v);
            onSetFiltroResponsaveis([]);
          }}
          placeholder="Todos os Setores"
          allLabel="Todos os Setores"
        />

        {/* Responsável — MultiSelect */}
        <MultiSelect
          id="filtro-responsavel"
          label="Responsável"
          options={responsavelOptions}
          selected={filtroResponsaveis}
          onChange={onSetFiltroResponsaveis}
          placeholder={
            filtroSetores.length > 0
              ? "Todos (dos Setores)"
              : "Equipe Inteira"
          }
          allLabel={
            filtroSetores.length > 0
              ? "Todos (dos Setores)"
              : "Equipe Inteira"
          }
        />

        {/* Prazo De */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="filtro-prazo-de"
            className="text-xs font-medium text-slate-500 uppercase"
          >
            A partir de
          </label>
          <input
            id="filtro-prazo-de"
            title="Prazo início"
            type="date"
            className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            value={filtroPrazoDe}
            onChange={(e) => onSetFiltroPrazoDe(e.target.value)}
          />
        </div>

        {/* Prazo Ate */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="filtro-prazo-ate"
            className="text-xs font-medium text-slate-500 uppercase"
          >
            Até
          </label>
          <input
            id="filtro-prazo-ate"
            title="Prazo limite"
            type="date"
            className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            value={filtroPrazoAte}
            onChange={(e) => onSetFiltroPrazoAte(e.target.value)}
          />
        </div>

        {/* Restaurar */}
        <div className="flex flex-col justify-end">
          <button
            id="btn-restaurar-filtros"
            onClick={onReset}
            className="text-sm font-medium text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 transition-colors py-2 px-3 rounded-lg w-full text-center"
          >
            Restaurar
          </button>
        </div>
      </div>
    </div>
  );
}
