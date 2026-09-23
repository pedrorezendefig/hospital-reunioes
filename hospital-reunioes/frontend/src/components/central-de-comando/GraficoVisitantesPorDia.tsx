"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import {
  formatarDiaCurto,
  formatarDiaLongo,
  formatarInteiro,
  formatarInteiroCompacto,
  formatarPercentual,
} from "@/lib/central-de-comando/formato";
import {
  COR_ANTERIOR,
  COR_ATUAL,
  COR_DA_GRADE,
  COR_DO_EIXO,
  marcasDoEixo,
  temAnterior,
} from "@/lib/central-de-comando/graficos";

/**
 * Um dia do bloco `movimento` do payload de Dados do Google: os Visitantes do
 * dia, o dia correspondente do período anterior com os Visitantes dele, e a
 * variação de um para o outro, já calculada no backend.
 */
export type PontoDoMovimento = {
  data: string;
  visitantes: number;
  data_anterior: string;
  visitantes_anterior: number;
  variacao: number | null;
};

// Altura fixa e largura da tela: no celular o gráfico ocupa a largura toda e
// continua com altura de gráfico, sem virar uma tira.
const ALTURA = 240;

// O dia do hospital, e não o do navegador: é o fuso em que o backend fecha o
// período (issue #857).
const DIA_NO_HOSPITAL = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "numeric",
  month: "numeric",
  year: "numeric",
});

/**
 * O "ontem" do hospital visto de `agora` (epoch em ms), como data ISO
 * (`2026-09-17`), a mesma forma das datas do payload. Das 21h à meia-noite de
 * Brasília o dia em UTC já virou, e o ontem de UTC é o hoje do hospital.
 */
function ontemNoHospital(agora: number): string {
  const partes = DIA_NO_HOSPITAL.formatToParts(agora);
  const parte = (tipo: Intl.DateTimeFormatPartTypes) => Number(partes.find((p) => p.type === tipo)?.value);
  return new Date(Date.UTC(parte("year"), parte("month") - 1, parte("day") - 1)).toISOString().slice(0, 10);
}

/**
 * O gráfico de Visitantes por dia de Dados do Google (issue #817, ADR 0058).
 *
 * Porte do `VisitorsChart` do repositório antigo em `recharts`, no molde dos
 * gráficos do dashboard, com as cores dos tokens do app: a linha do período
 * escolhido em azul e a do período anterior em cinza tracejado, atrás, só
 * quando ele teve visita. No eixo, no máximo 4 dias, para caber no celular; o
 * dia que é mesmo ontem no hospital aparece como "ontem" (o período termina
 * ontem, mas o número pode ter vindo de antes da meia-noite). Passar o dedo ou o
 * mouse mostra o dia, os Visitantes e a comparação com o dia correspondente
 * do anterior; a conta dessa comparação vem pronta do backend.
 */
export function GraficoVisitantesPorDia({ pontos }: { pontos: PontoDoMovimento[] }) {
  if (pontos.length === 0) {
    return <p className="py-10 text-center text-sm text-text-secondary">Sem dados de visitantes para este período.</p>;
  }

  const comAnterior = temAnterior(pontos);
  const ontem = ontemNoHospital(Date.now());
  const marcas = marcasDoEixo(pontos.length).map((i) => pontos[i].data);
  const rotulo =
    `Visitantes por dia nos últimos ${pontos.length} dias.` +
    (comAnterior ? " Período anterior mostrado para comparação." : "");

  return (
    <div className="space-y-3">
      <ul aria-label="Legenda" className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-secondary">
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="h-0.5 w-5 rounded-full" style={{ backgroundColor: COR_ATUAL }} />
          Período escolhido
        </li>
        {comAnterior && (
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="w-5 border-t-2 border-dashed" style={{ borderColor: COR_ANTERIOR }} />
            Período anterior
          </li>
        )}
      </ul>
      <div role="img" aria-label={rotulo}>
        <ResponsiveContainer width="100%" height={ALTURA}>
          <LineChart data={pontos} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={COR_DA_GRADE} />
            <XAxis
              dataKey="data"
              ticks={marcas}
              interval={0}
              tickFormatter={(data: string) => (data === ontem ? "ontem" : formatarDiaCurto(data))}
              tick={{ fontSize: 12, fill: COR_DO_EIXO }}
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <YAxis
              width={48}
              allowDecimals={false}
              tickFormatter={(valor: number) => formatarInteiroCompacto(valor)}
              tick={{ fontSize: 12, fill: COR_DO_EIXO }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={<DicaDoDia ontem={ontem} comAnterior={comAnterior} />}
              cursor={{ stroke: COR_DA_GRADE }}
              isAnimationActive={false}
            />
            {comAnterior && (
              <Line
                type="linear"
                dataKey="visitantes_anterior"
                stroke={COR_ANTERIOR}
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            )}
            <Line
              type="linear"
              dataKey="visitantes"
              stroke={COR_ATUAL}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4, fill: COR_ATUAL }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * A dica do dia sob o dedo ou o mouse: o dia (com "ontem" na frente quando é
 * o `ontem` do hospital), os Visitantes, e, com o período anterior no gráfico,
 * os Visitantes do dia correspondente e a variação, com a seta do sentido e sem
 * sinal de menos (molde do número-manchete da Visão Geral).
 */
export function DicaDoDia({
  active,
  payload,
  ontem,
  comAnterior,
}: TooltipProps<number, string> & { ontem: string; comAnterior: boolean }) {
  const ponto = payload?.[0]?.payload as PontoDoMovimento | undefined;
  if (!active || !ponto) return null;

  return (
    <div className="space-y-1 rounded-lg border border-border bg-white px-3 py-2 text-sm shadow-premium">
      <p className="text-xs text-text-secondary">
        {ponto.data === ontem ? `ontem · ${formatarDiaLongo(ponto.data)}` : formatarDiaLongo(ponto.data)}
      </p>
      <p className="font-semibold tabular-nums text-text">
        {formatarInteiro(ponto.visitantes)} {ponto.visitantes === 1 ? "visitante" : "visitantes"}
      </p>
      {comAnterior && (
        <p className="flex flex-wrap gap-x-2 text-xs tabular-nums text-text-secondary">
          <span>Anterior: {formatarInteiro(ponto.visitantes_anterior)}</span>
          {ponto.variacao !== null && (
            <span className={`font-semibold ${ponto.variacao >= 0 ? "text-emerald-700" : "text-amber-700"}`}>
              {ponto.variacao >= 0 ? "↑" : "↓"} {formatarPercentual(Math.abs(ponto.variacao))}
            </span>
          )}
        </p>
      )}
    </div>
  );
}
