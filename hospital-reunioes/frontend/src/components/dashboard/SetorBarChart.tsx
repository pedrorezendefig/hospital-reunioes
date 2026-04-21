"use client";

import { Loader2 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SetorBarEntry {
  setor: string;
  Pendente: number;
  "Em Progresso": number;
  "Concluído": number;
  Atrasado: number;
  Repactuada: number;
}

export interface SetorBarChartProps {
  data: SetorBarEntry[];
  loading: boolean;
  onBarClick: (statusEnum: string, setor: string) => void;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Pendente: "#FFC067",
  "Em Progresso": "#7CC2F2",
  "Concluído": "#88D7A4",
  Atrasado: "#FC9D9D",
  Repactuada: "#C4B5FD",
};

const STATUS_ENUM_MAP: Record<string, string> = {
  Pendente: "PENDENTE",
  "Em Progresso": "EM_PROGRESSO",
  "Concluído": "CONCLUIDO",
  Atrasado: "ATRASADO",
  Repactuada: "REPACTUADA",
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function SetorBarChart({
  data,
  loading,
  onBarClick,
}: SetorBarChartProps) {
  return (
    <div className="bg-surface rounded-xl p-6 border border-border shadow-premium flex flex-col">
      <h2 className="text-lg font-bold text-text mb-1">
        Pendências por Setor
      </h2>
      <p className="text-text-secondary text-xs mb-4">
        Distribuição de status por departamento
      </p>

      {loading ? (
        <div className="flex-1 flex items-center justify-center h-64">
          <Loader2 className="w-10 h-10 animate-spin text-slate-300" />
        </div>
      ) : data.length === 0 ? (
        <div className="flex-1 flex items-center justify-center h-64 text-text-secondary text-sm">
          Nenhum dado disponível.
        </div>
      ) : (
        <ResponsiveContainer
          width="100%"
          height={Math.max(250, data.length * 40 + 80)}
        >
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 16, left: 4, bottom: 0 }}
            barSize={32}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              horizontal={false}
              stroke="#f1f5f9"
            />
            <XAxis type="number" tick={{ fontSize: 11, fill: "#94a3b8" }} />
            <YAxis
              type="category"
              dataKey="setor"
              width={140}
              tick={{ fontSize: 10, fill: "#64748b" }}
              interval={0}
            />
            <RechartsTooltip
              contentStyle={{
                borderRadius: "12px",
                border: "none",
                boxShadow: "0 4px 20px rgb(0 0 0 / 0.1)",
                fontSize: 12,
              }}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            />
            {Object.entries(STATUS_COLORS).map(([name, color]) => (
              <Bar
                key={name}
                dataKey={name}
                stackId="a"
                fill={color}
                cursor="pointer"
                onClick={(barData) => {
                  if (STATUS_ENUM_MAP[name]) {
                    onBarClick(STATUS_ENUM_MAP[name], barData.setor);
                  }
                }}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
