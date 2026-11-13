"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatarInteiro, formatarInteiroCompacto } from "@/lib/central-de-comando/formato";
import { COR_ANTERIOR, COR_ATUAL, COR_DA_GRADE, COR_DO_EIXO } from "@/lib/central-de-comando/graficos";
import { formatarNota } from "@/lib/ouvidoria/nota-externa";

/** Uma leitura da nota do Google: o instante, a nota e o total acumulado (nulo na digitada). */
export type LeituraDaNota = { lida_em: string; nota: number; total: number | null };

type Tendencia = "melhorou" | "piorou" | "igual";

/** Uma linha do gráfico: o dia do mês e o que cada mês leu nele. */
type Linha = { dia: number; nota?: number; total?: number; nota_anterior?: number; total_anterior?: number };

const ALTURA = 220;

// No eixo, o dia do mês: 5 rótulos cabem no celular, e o eixo vai até o 31
// para o 29 não ficar na borda.
const DIAS_NO_EIXO = [1, 8, 15, 22, 29];

const DIA_NO_HOSPITAL = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "numeric" });

function diaDoMes(iso: string): number {
  return Number(DIA_NO_HOSPITAL.format(new Date(iso)));
}

/**
 * Junta as leituras dos dois meses pelo dia do mês: a leitura do dia 9 deste
 * mês fica na mesma vertical que a do dia 9 do anterior.
 */
function linhasPorDia(doMes: LeituraDaNota[], anterior: LeituraDaNota[]): Linha[] {
  const porDia = new Map<number, Linha>();
  const linha = (dia: number) => porDia.get(dia) ?? porDia.set(dia, { dia }).get(dia)!;
  for (const leitura of anterior) {
    const l = linha(diaDoMes(leitura.lida_em));
    l.nota_anterior = leitura.nota;
    if (leitura.total !== null) l.total_anterior = leitura.total;
  }
  for (const leitura of doMes) {
    const l = linha(diaDoMes(leitura.lida_em));
    l.nota = leitura.nota;
    if (leitura.total !== null) l.total = leitura.total;
  }
  return [...porDia.values()].sort((a, b) => a.dia - b.dia);
}

function frenteAoAnterior(
  tendencia: Tendencia | null,
  nota: number | null,
  notaAnterior: number | null,
  escala: number,
): string | null {
  if (tendencia === null || nota === null || notaAnterior === null) return null;
  const agora = formatarNota(nota, escala);
  const antes = formatarNota(notaAnterior, escala);
  if (tendencia === "igual") return `A nota ficou igual à do fim do mês anterior: ${agora}.`;
  return `A nota ${tendencia}: ${agora} contra ${antes} no fim do mês anterior.`;
}

function formatarNotaNoEixo(valor: number): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/**
 * O gráfico do mês da nota do Google (issue #1699, PRD #1527): as leituras
 * semanais do mês em linha cheia, e as do mês anterior em cinza tracejado,
 * atrás, pelo dia do mês. Dois gráficos, um embaixo do outro no celular: a
 * nota e as avaliações acumuladas (o total que o Google mostra; a leitura
 * digitada não tem total e fica só no da nota). Abaixo da nota, uma frase diz
 * se ela melhorou ou piorou frente ao fim do mês anterior; a conta da
 * tendência é do backend.
 *
 * Sem leitura no mês, nenhum gráfico, e a frase diz por quê.
 */
export function GraficoDoMesDaNota({
  doMes,
  anterior,
  escala,
  nota,
  notaAnterior,
  tendencia,
}: {
  doMes: LeituraDaNota[];
  anterior: LeituraDaNota[];
  escala: number;
  nota: number | null;
  notaAnterior: number | null;
  tendencia: Tendencia | null;
}) {
  if (doMes.length === 0) {
    return (
      <p role="status" className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-secondary">
        O gráfico está vazio porque ainda não houve leitura neste mês. A nota é lida uma vez por semana, e o gráfico
        começa na primeira leitura do mês.
      </p>
    );
  }

  const linhas = linhasPorDia(doMes, anterior);
  const frase = frenteAoAnterior(tendencia, nota, notaAnterior, escala);
  const comNotaAnterior = anterior.length > 0;
  const comTotalAnterior = anterior.some((leitura) => leitura.total !== null);
  const comparacao = (com: boolean) => (com ? " Mês anterior em tracejado, para comparar." : "");

  return (
    <section aria-labelledby="titulo-do-grafico-da-nota" className="space-y-4">
      <div className="space-y-2">
        <h2 id="titulo-do-grafico-da-nota" className="text-lg font-semibold text-text">
          Leituras do mês
        </h2>
        <ul aria-label="Legenda" className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-secondary">
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="h-0.5 w-5 rounded-full" style={{ backgroundColor: COR_ATUAL }} />
            Este mês
          </li>
          {comNotaAnterior && (
            <li className="flex items-center gap-2">
              <span aria-hidden="true" className="w-5 border-t-2 border-dashed" style={{ borderColor: COR_ANTERIOR }} />
              Mês anterior
            </li>
          )}
        </ul>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <figure className="space-y-2 rounded-2xl border border-border bg-white p-4 shadow-premium">
          <figcaption className="text-xs text-text-secondary">Nota no Google</figcaption>
          <div
            role="img"
            aria-label={`Nota no Google em cada leitura do mês.${comparacao(comNotaAnterior)}${frase ? ` ${frase}` : ""}`}
          >
            <ResponsiveContainer width="100%" height={ALTURA}>
              <LineChart data={linhas} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={COR_DA_GRADE} />
                {eixoDosDias()}
                <YAxis
                  width={40}
                  domain={["dataMin - 0.2", "dataMax + 0.2"]}
                  tickFormatter={formatarNotaNoEixo}
                  tick={{ fontSize: 12, fill: COR_DO_EIXO }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  labelFormatter={(dia) => `Dia ${dia}`}
                  formatter={(valor: number) => formatarNota(valor, escala)}
                  isAnimationActive={false}
                />
                {comNotaAnterior && linhaDoAnterior("nota_anterior")}
                {linhaDoMes("nota")}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {frase && <p className="text-sm font-medium text-text">{frase}</p>}
        </figure>
        <figure className="space-y-2 rounded-2xl border border-border bg-white p-4 shadow-premium">
          <figcaption className="text-xs text-text-secondary">Avaliações acumuladas no Google</figcaption>
          <div role="img" aria-label={`Avaliações acumuladas em cada leitura do mês.${comparacao(comTotalAnterior)}`}>
            <ResponsiveContainer width="100%" height={ALTURA}>
              <LineChart data={linhas} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={COR_DA_GRADE} />
                {eixoDosDias()}
                <YAxis
                  width={48}
                  allowDecimals={false}
                  domain={["auto", "auto"]}
                  tickFormatter={(valor: number) => formatarInteiroCompacto(valor)}
                  tick={{ fontSize: 12, fill: COR_DO_EIXO }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  labelFormatter={(dia) => `Dia ${dia}`}
                  formatter={(valor: number) => formatarInteiro(valor)}
                  isAnimationActive={false}
                />
                {comTotalAnterior && linhaDoAnterior("total_anterior")}
                {linhaDoMes("total")}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </figure>
      </div>
    </section>
  );
}

// O `recharts` 2 só desenha filho que ele reconhece pelo tipo: os eixos e as
// linhas saem de funções que devolvem o próprio elemento, chamadas como
// função, e não como componente.
function eixoDosDias() {
  return (
    <XAxis
      dataKey="dia"
      type="number"
      domain={[1, 31]}
      ticks={DIAS_NO_EIXO}
      interval={0}
      tick={{ fontSize: 12, fill: COR_DO_EIXO }}
      tickLine={false}
      axisLine={false}
      tickMargin={8}
    />
  );
}

function linhaDoMes(dataKey: "nota" | "total") {
  return (
    <Line
      type="linear"
      dataKey={dataKey}
      name="Este mês"
      stroke={COR_ATUAL}
      strokeWidth={2.5}
      dot={{ r: 3, fill: COR_ATUAL }}
      activeDot={{ r: 4, fill: COR_ATUAL }}
      connectNulls
      isAnimationActive={false}
    />
  );
}

function linhaDoAnterior(dataKey: "nota_anterior" | "total_anterior") {
  return (
    <Line
      type="linear"
      dataKey={dataKey}
      name="Mês anterior"
      stroke={COR_ANTERIOR}
      strokeWidth={1.5}
      strokeDasharray="4 4"
      dot={{ r: 2, fill: COR_ANTERIOR }}
      activeDot={false}
      connectNulls
      isAnimationActive={false}
    />
  );
}
