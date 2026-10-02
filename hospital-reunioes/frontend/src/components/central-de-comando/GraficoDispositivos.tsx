"use client";

import { Cell, Pie, PieChart } from "recharts";

import { formatarFatia, formatarInteiro } from "@/lib/central-de-comando/formato";
import { COR_DO_DISPOSITIVO, type Dispositivo } from "@/lib/central-de-comando/graficos";

/**
 * Um dispositivo do bloco `dispositivos` do payload de Dados do Google: as
 * Visitas do período, o rótulo da tela e a fatia em pontos percentuais. O
 * backend manda só os que tiveram Visita, do mais usado ao menos usado, e as
 * fatias somam 100.
 */
export type DispositivoDoPayload = {
  chave: Dispositivo;
  rotulo: string;
  visitas: number;
  percentual: number;
};

// A rosca tem tamanho fixo: cabe inteira na largura de um celular, e não
// depende de medir o espaço em volta.
const LADO = 160;

/**
 * A rosca de dispositivos de Dados do Google (issue #817, ADR 0058).
 *
 * Porte do `DeviceDonut` do repositório antigo em `recharts`, no molde da
 * rosca do dashboard (`StatusPieChart`), com as cores dos tokens do app. O
 * mais usado vai para o centro, com a fatia e o nome; a lista ao lado diz
 * cada dispositivo, a fatia e as Visitas. A rosca é enfeite para o leitor de
 * tela: quem lê o dado é a lista. No celular, a lista desce para baixo da
 * rosca.
 */
export function GraficoDispositivos({ dispositivos }: { dispositivos: DispositivoDoPayload[] }) {
  if (dispositivos.length === 0) {
    return <p className="py-10 text-center text-sm text-text-secondary">Sem dados de dispositivo para este período.</p>;
  }

  const lider = dispositivos[0];

  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row">
      <div data-testid="rosca" aria-hidden="true" className="relative shrink-0" style={{ width: LADO, height: LADO }}>
        <PieChart width={LADO} height={LADO}>
          <Pie
            data={dispositivos}
            dataKey="visitas"
            nameKey="rotulo"
            innerRadius={52}
            outerRadius={76}
            startAngle={90}
            endAngle={-270}
            stroke="var(--color-surface)"
            strokeWidth={2}
            isAnimationActive={false}
          >
            {dispositivos.map((dispositivo) => (
              <Cell key={dispositivo.chave} fill={COR_DO_DISPOSITIVO[dispositivo.chave]} />
            ))}
          </Pie>
        </PieChart>
        <div
          data-testid="centro-da-rosca"
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
        >
          <span className="text-2xl font-bold tabular-nums text-text">{formatarFatia(lider.percentual)}</span>
          <span className="text-xs text-text-secondary">{lider.rotulo.toLowerCase()}</span>
        </div>
      </div>
      <ul aria-label="Visitas por dispositivo" className="w-full space-y-3">
        {dispositivos.map((dispositivo) => (
          <li key={dispositivo.chave} className="flex items-center gap-3 text-sm">
            <span
              aria-hidden="true"
              data-cor={COR_DO_DISPOSITIVO[dispositivo.chave]}
              className="h-3 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: COR_DO_DISPOSITIVO[dispositivo.chave] }}
            />
            <span className="text-text">{dispositivo.rotulo}</span>
            <span className="ml-auto font-semibold tabular-nums text-text">{formatarFatia(dispositivo.percentual)}</span>
            <span className="w-24 text-right text-xs tabular-nums text-text-secondary">
              {formatarInteiro(dispositivo.visitas)} {dispositivo.visitas === 1 ? "visita" : "visitas"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
