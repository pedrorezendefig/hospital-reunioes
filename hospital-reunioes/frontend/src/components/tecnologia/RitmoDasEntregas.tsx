"use client";

/**
 * O ritmo no topo da aba Entregas (issue #1701, ADR 0092, decisões 1, 3, 4 e 7).
 *
 * Dois números, pedidos e entregas das últimas 4 semanas com a variação contra
 * as 4 anteriores escrita em texto, e o gráfico das últimas 12 semanas, com a
 * barra de pedidos ao lado da de entregas, empilhada em G, M e P. Quem conta é
 * o servidor; a tela só desenha.
 *
 * O mouse num número abre a composição (bugs e melhorias; G, M e P) pela
 * intenção de hover; o mouse numa semana abre a prévia do que saiu nela, e o
 * clique (no celular, o toque) marca a semana para a lista filtrar (issue
 * #1704); as outras semanas ficam apagadas até desmarcar. Os números sobem contando e as barras crescem escalonadas; para quem pede menos
 * movimento, tudo aparece pronto. Abaixo de 720px, tudo vira uma coluna.
 */

import { useId } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from "recharts";

import { useContagem } from "@/hooks/useContagem";
import { useIntencaoDeHover } from "@/hooks/useIntencaoDeHover";
import { useMovimentoReduzido } from "@/hooks/useMovimentoReduzido";

export type Tamanho = "P" | "M" | "G";

export type TopoDasEntregas = {
  pedidos: { total: number; anteriores: number; bugs: number; melhorias: number };
  entregas: { total: number; anteriores: number; g: number; m: number; p: number };
};

export type SemanaDasEntregas = {
  inicio: string;
  pedidos: number;
  g: number;
  m: number;
  p: number;
  entregas: { titulo: string; tamanho: Tamanho }[];
};

type Serie = "pedidos" | "g" | "m" | "p";

/** Os pedidos em cinza, atrás; as entregas nos azuis da marca, do G (o mais escuro) ao P. */
const COR_DA_SERIE: Record<Serie, string> = {
  pedidos: "var(--color-text-secondary)",
  g: "var(--color-primary-dark)",
  m: "var(--color-primary)",
  p: "var(--color-primary-light)",
};
const COR_DA_GRADE = "var(--color-border)";
const COR_DO_EIXO = "var(--color-text-secondary)";

const ROTULO_DO_TAMANHO: Record<Tamanho, string> = {
  G: "6 partes ou mais",
  M: "de 2 a 5 partes",
  P: "até 1 parte",
};

/** Quanto cada barra espera a da semana anterior para começar a crescer. */
const ESCALONAMENTO_MS = 40;
const ALTURA_DO_GRAFICO = 240;

function plural(n: number, um: string, varios: string): string {
  return `${n} ${n === 1 ? um : varios}`;
}

/** "+6 contra as 4 anteriores", sem seta (ADR 0092, decisão 1). */
export function variacaoEmTexto(total: number, anteriores: number): string {
  const diferenca = total - anteriores;
  if (diferenca === 0) return "Igual às 4 anteriores";
  return `${diferenca > 0 ? "+" : ""}${diferenca} contra as 4 anteriores`;
}

/** O início da semana (AAAA-MM-DD, dia do hospital) como a tela o diz: "09/11", lido como texto. */
export function diaEMes(inicio: string): string {
  const [, mes, dia] = inicio.split("-");
  return `${dia}/${mes}`;
}

function NumeroDoRitmo({
  rotulo,
  total,
  anteriores,
  nomeDaComposicao,
  composicao,
  parado,
}: {
  rotulo: string;
  total: number;
  anteriores: number;
  nomeDaComposicao: string;
  composicao: string[];
  parado: boolean;
}) {
  const valor = useContagem(total, parado);
  const { aberto, alvo } = useIntencaoDeHover();
  const id = useId();
  return (
    <div className="relative">
      <button
        type="button"
        {...alvo}
        aria-expanded={aberto}
        aria-controls={id}
        className={
          "w-full rounded-xl border border-border bg-white px-4 py-3 text-left transition-colors " +
          "hover:border-primary/40"
        }
      >
        <span className="block text-xs text-text-secondary">{rotulo}</span>
        <span className="block text-3xl font-semibold tabular-nums text-text">{valor}</span>
        <span className="block normal-case text-xs text-text-secondary">{variacaoEmTexto(total, anteriores)}</span>
      </button>
      {aberto && (
        <div
          id={id}
          role="region"
          aria-label={nomeDaComposicao}
          className={
            "absolute left-0 right-0 top-full z-10 mt-1 rounded-lg border border-border bg-white px-3 py-2 " +
            "text-sm shadow-premium animate-fade-in"
          }
        >
          <ul className="space-y-0.5 text-text">
            {composicao.map((linha) => (
              <li key={linha}>{linha}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

type PropsDaBarra = {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: { inicio?: string };
};

/** A barra das outras semanas quando uma está marcada. */
const OPACIDADE_DESMARCADA = 0.35;

/**
 * A barra de uma série. Cresce do chão em CSS, uma semana depois da outra,
 * quando há movimento. Com uma semana marcada, a dela fica cheia e as outras
 * apagadas.
 */
function barra(serie: Serie, crescer: boolean, marcada: string | null) {
  function Barra(props: unknown) {
    const { x = 0, y = 0, width = 0, height = 0, index = 0, payload } = props as PropsDaBarra;
    const desta = marcada !== null && payload?.inicio === marcada;
    return (
      <rect
        x={x}
        y={y}
        width={width}
        height={Math.max(0, height)}
        fill={COR_DA_SERIE[serie]}
        fillOpacity={marcada !== null && !desta ? OPACIDADE_DESMARCADA : undefined}
        data-serie={serie}
        data-marcada={desta ? "true" : undefined}
        className={crescer ? "barra-do-ritmo" : undefined}
        style={crescer ? { animationDelay: `${index * ESCALONAMENTO_MS}ms` } : undefined}
      />
    );
  }
  return Barra;
}

/** A prévia da semana sob o mouse: os números e o que saiu, com o tamanho de cada entrega. */
export function PreviaDaSemana({ active, payload }: TooltipProps<number, string>) {
  const semana = payload?.[0]?.payload as SemanaDasEntregas | undefined;
  if (!active || !semana) return null;
  return (
    <div className="max-w-xs space-y-1 rounded-lg border border-border bg-white px-3 py-2 text-sm shadow-premium">
      <p className="text-xs text-text-secondary">Semana de {diaEMes(semana.inicio)}</p>
      <p className="font-semibold tabular-nums text-text">
        {plural(semana.pedidos, "pedido", "pedidos")}, {plural(semana.entregas.length, "entrega", "entregas")}
      </p>
      {semana.entregas.length > 0 && (
        <ul aria-label="O que saiu na semana" className="space-y-0.5 text-text">
          {semana.entregas.map((entrega, i) => (
            <li key={`${i}-${entrega.titulo}`} className="flex gap-2">
              <span className="font-semibold text-primary">{entrega.tamanho}</span>{" "}
              <span className="normal-case">{entrega.titulo}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type CliqueNaSemana = {
  /** O início da semana marcada, que a lista filtra; `null` sem filtro. */
  semanaMarcada?: string | null;
  onClicarNaSemana?: (inicio: string) => void;
};

function GraficoDoRitmo({
  semanas,
  parado,
  semanaMarcada = null,
  onClicarNaSemana,
}: { semanas: SemanaDasEntregas[]; parado: boolean } & CliqueNaSemana) {
  const crescer = !parado;
  return (
    <figure aria-label="Pedidos e entregas das últimas 12 semanas" className="m-0 space-y-2">
      <ul aria-label="Legenda" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        {(
          [
            ["pedidos", "Pedidos"],
            ["g", "G"],
            ["m", "M"],
            ["p", "P"],
          ] as [Serie, string][]
        ).map(([serie, nome]) => (
          <li key={serie} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: COR_DA_SERIE[serie] }}
            />
            {nome}
          </li>
        ))}
      </ul>
      <ResponsiveContainer width="100%" height={ALTURA_DO_GRAFICO}>
        <BarChart
          data={semanas}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          barGap={2}
          className={onClicarNaSemana ? "cursor-pointer" : undefined}
          onClick={(estado) => {
            const inicio = estado?.activeLabel;
            if (onClicarNaSemana && typeof inicio === "string") onClicarNaSemana(inicio);
          }}
        >
          <CartesianGrid vertical={false} stroke={COR_DA_GRADE} />
          <XAxis
            dataKey="inicio"
            tickFormatter={diaEMes}
            tick={{ fontSize: 12, fill: COR_DO_EIXO }}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
          />
          <YAxis
            width={32}
            allowDecimals={false}
            tick={{ fontSize: 12, fill: COR_DO_EIXO }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            content={<PreviaDaSemana />}
            cursor={{ fill: COR_DA_GRADE, opacity: 0.4 }}
            isAnimationActive={false}
          />
          <Bar dataKey="pedidos" name="Pedidos" shape={barra("pedidos", crescer, semanaMarcada)} isAnimationActive={false} />
          <Bar dataKey="g" name="G" stackId="entregas" shape={barra("g", crescer, semanaMarcada)} isAnimationActive={false} />
          <Bar dataKey="m" name="M" stackId="entregas" shape={barra("m", crescer, semanaMarcada)} isAnimationActive={false} />
          <Bar dataKey="p" name="P" stackId="entregas" shape={barra("p", crescer, semanaMarcada)} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function RitmoDasEntregas({
  topo,
  semanas,
  semanaMarcada,
  onClicarNaSemana,
}: { topo: TopoDasEntregas; semanas: SemanaDasEntregas[] } & CliqueNaSemana) {
  const parado = useMovimentoReduzido();
  return (
    <section
      aria-label="Ritmo das entregas"
      className="grid gap-3 min-[720px]:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] min-[720px]:items-start"
    >
      <div className="grid gap-3">
        <NumeroDoRitmo
          rotulo="Pedidos"
          total={topo.pedidos.total}
          anteriores={topo.pedidos.anteriores}
          nomeDaComposicao="Composição dos pedidos"
          composicao={[
            plural(topo.pedidos.bugs, "bug", "bugs"),
            plural(topo.pedidos.melhorias, "melhoria", "melhorias"),
          ]}
          parado={parado}
        />
        <NumeroDoRitmo
          rotulo="Entregas"
          total={topo.entregas.total}
          anteriores={topo.entregas.anteriores}
          nomeDaComposicao="Composição das entregas"
          composicao={[
            `${topo.entregas.g} G (${ROTULO_DO_TAMANHO.G})`,
            `${topo.entregas.m} M (${ROTULO_DO_TAMANHO.M})`,
            `${topo.entregas.p} P (${ROTULO_DO_TAMANHO.P})`,
          ]}
          parado={parado}
        />
        <p className="px-1 text-xs text-text-secondary">Nas últimas 4 semanas, contando esta.</p>
      </div>
      {semanas.length > 0 && (
        <div className="min-w-0 rounded-xl border border-border bg-white px-3 py-3">
          <GraficoDoRitmo
            semanas={semanas}
            parado={parado}
            semanaMarcada={semanaMarcada}
            onClicarNaSemana={onClicarNaSemana}
          />
        </div>
      )}
    </section>
  );
}
