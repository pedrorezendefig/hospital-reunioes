"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { dataCurta, reais } from "@/lib/contas-medicas/guia";
import { NIVEIS, ROTULO_NIVEL, textoEmReais, type Painel } from "@/lib/contas-medicas/painel";

import { COR_DA_GRADE, COR_DO_EIXO, COR_DO_NIVEL } from "./cores";
import { Moldura } from "./Moldura";

/**
 * O R$ incluído por nível de evidência, por semana, em barras empilhadas
 * (adendo v1.1, item 4): quanto do valor incluído depende só de prescrição.
 */
export function BlocoNivelEvidencia({ semanas }: { semanas: NonNullable<Painel["nivel_evidencia"]> }) {
  const total = (s: (typeof semanas)[number]) => NIVEIS.reduce((soma, nivel) => soma + s[nivel], 0);
  const comValor = semanas.filter((s) => total(s) > 0);
  return (
    <Moldura titulo="R$ incluído por nível de evidência" subtitulo="Linhas Feito, por semana">
      {comValor.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">Nada incluído nessas semanas.</p>
      ) : (
        <div
          role="img"
          aria-label={`R$ incluído por nível de evidência: ${comValor
            .map((s) => `semana de ${dataCurta(s.semana)}, ${textoEmReais(total(s))}`)
            .join("; ")}.`}
        >
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={semanas} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
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
                width={56}
                tickFormatter={(valor: number) => reais(valor).replace(/,00$/, "")}
                tick={{ fontSize: 12, fill: COR_DO_EIXO }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                formatter={(valor: number, nivel: string) => [textoEmReais(valor), nivel]}
                labelFormatter={(semana: string) => `Semana de ${dataCurta(semana)}`}
                isAnimationActive={false}
              />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              {NIVEIS.map((nivel) => (
                <Bar
                  key={nivel}
                  dataKey={nivel}
                  name={ROTULO_NIVEL[nivel]}
                  stackId="nivel"
                  fill={COR_DO_NIVEL[nivel]}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Moldura>
  );
}
