"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { dataCurta } from "@/lib/contas-medicas/guia";
import { textoDaNota, type Painel } from "@/lib/contas-medicas/painel";

import { COR_DA_GRADE, COR_DO_EIXO, COR_PRIMARIA } from "./cores";
import { Moldura } from "./Moldura";

/** A nota média de entrada de cada semana, até a escolhida. Semana sem conta fica sem ponto. */
export function BlocoNotaPorSemana({ pontos }: { pontos: NonNullable<Painel["nota_por_semana"]> }) {
  const comNota = pontos.filter((p) => p.nota_media !== null);
  return (
    <Moldura titulo="Nota média por semana" subtitulo="De segunda a domingo, pelo dia em que a conta foi concluída">
      {comNota.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">Nenhuma conta concluída nessas semanas.</p>
      ) : (
        <div
          role="img"
          aria-label={`Nota média de entrada por semana: ${comNota
            .map((p) => `semana de ${dataCurta(p.semana)}, ${textoDaNota(p.nota_media)}`)
            .join("; ")}.`}
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={pontos} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={COR_DA_GRADE} />
              <XAxis
                dataKey="semana"
                tickFormatter={(semana: string) => dataCurta(semana)}
                tick={{ fontSize: 12, fill: COR_DO_EIXO }}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
              />
              <YAxis
                domain={[0, 100]}
                width={36}
                tick={{ fontSize: 12, fill: COR_DO_EIXO }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                formatter={(valor: number) => [textoDaNota(valor), "Nota média"]}
                labelFormatter={(semana: string) => `Semana de ${dataCurta(semana)}`}
                isAnimationActive={false}
              />
              <Line
                type="linear"
                dataKey="nota_media"
                stroke={COR_PRIMARIA}
                strokeWidth={2.5}
                dot={{ r: 3, fill: COR_PRIMARIA }}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Moldura>
  );
}
