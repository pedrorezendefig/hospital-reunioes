"use client";

import { Loader2 } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PieEntry {
  name: string;
  value: number;
  color: string;
}

export interface StatusPieChartProps {
  data: PieEntry[];
  loading: boolean;
  onSliceClick: (statusEnum: string) => void;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STATUS_ENUM_MAP: Record<string, string> = {
  Pendente: "PENDENTE",
  "Em Progresso": "EM_PROGRESSO",
  "Concluido": "CONCLUIDO",
  Concluído: "CONCLUIDO",
  Atrasado: "ATRASADO",
  Repactuada: "REPACTUADA",
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function StatusPieChart({
  data,
  loading,
  onSliceClick,
}: StatusPieChartProps) {
  const total = data.reduce((acc, e) => acc + e.value, 0);

  return (
    <div className="bg-surface rounded-xl p-6 border border-border shadow-premium flex flex-col">
      <h2 className="text-lg font-bold text-text mb-1">
        Status das Pendências
      </h2>
      <p className="text-text-secondary text-xs mb-4">
        Visão geral por situação
      </p>

      {loading ? (
        <div className="flex-1 flex items-center justify-center h-64">
          <Loader2 className="w-10 h-10 animate-spin text-slate-300" />
        </div>
      ) : data.length === 0 ? (
        <div className="flex-1 flex items-center justify-center h-64 text-text-secondary text-sm">
          Sem pendências para os filtros aplicados.
        </div>
      ) : (
        <>
          <div className="relative">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={75}
                  outerRadius={115}
                  paddingAngle={3}
                  stroke="#fff"
                  strokeWidth={2}
                  cursor="pointer"
                  animationBegin={100}
                  animationDuration={800}
                  onClick={(entry) => {
                    const name = entry?.name || entry?.payload?.name;
                    if (name && STATUS_ENUM_MAP[name]) {
                      onSliceClick(STATUS_ENUM_MAP[name]);
                    }
                  }}
                >
                  {data.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip
                  contentStyle={{
                    borderRadius: "6px",
                    border: "none",
                    boxShadow: "0 4px 20px rgb(0 0 0 / 0.1)",
                  }}
                  formatter={(value: number, name: string) => [
                    `${value} (${total > 0 ? ((value / total) * 100).toFixed(0) : 0}%)`,
                    name,
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            {/* Label central sobreposta via CSS */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <div className="text-3xl font-bold text-slate-900">{total}</div>
                <div className="text-xs text-slate-400 mt-0.5">pendências</div>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3 justify-center">
            {data.map((entry) => (
              <button
                key={entry.name}
                onClick={() => {
                  if (STATUS_ENUM_MAP[entry.name]) {
                    onSliceClick(STATUS_ENUM_MAP[entry.name]);
                  }
                }}
                className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
              >
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                {entry.name}
                <span className="text-slate-400 font-normal">
                  ({entry.value})
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
