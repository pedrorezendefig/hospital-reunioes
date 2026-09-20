import { AlertTriangle, ArrowDown, ArrowUp, Camera, PlugZap } from "lucide-react";
import Link from "next/link";

import { formatarInteiro, formatarPercentual } from "@/lib/central-de-comando/formato";

import { CAMINHO_INSTAGRAM } from "./Instagram";

type NumeroDeFluxo = { atual: number; variacao: number | null };

/**
 * O bloco `instagram` do payload da Visão Geral (issue #821): o Instagram num
 * relance, quatro números, por estado. `ok` traz Seguidores (estoque, com o
 * crescimento do período), Alcance, Visualizações e Interações; `nao-configurado`
 * e `sem-dado` degradam sozinhos, sem derrubar a tela.
 */
export type InstagramDeRelance =
  | {
      estado: "ok";
      seguidores: { total: number; crescimento: number };
      alcance: NumeroDeFluxo;
      visualizacoes: NumeroDeFluxo;
      interacoes: NumeroDeFluxo;
    }
  | { estado: "nao-configurado" | "sem-dado"; motivo: string };

/**
 * O Instagram num relance: quatro números na linguagem nativa da rede (na
 * interface diz-se sempre "Instagram", nunca a empresa dona). A tela cheia fica
 * a um clique, no atalho e no título.
 */
export function InstagramNumRelance({ instagram }: { instagram: InstagramDeRelance }) {
  if (instagram.estado === "nao-configurado") {
    return (
      <BlocoDeAviso
        icone={PlugZap}
        tom="calmo"
        titulo="Conta do Instagram ainda não configurada"
        mensagem={instagram.motivo}
      />
    );
  }
  if (instagram.estado === "sem-dado") {
    return (
      <BlocoDeAviso
        icone={AlertTriangle}
        tom="erro"
        titulo="Não foi possível buscar o Instagram agora."
        mensagem={instagram.motivo}
      />
    );
  }

  return (
    <section
      aria-labelledby="central-instagram-relance"
      className="space-y-4 rounded-2xl border border-border bg-white p-6 shadow-premium"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="central-instagram-relance" className="flex items-center gap-2 text-lg font-bold text-text">
          <Camera aria-hidden className="h-5 w-5 text-primary" />O Instagram num relance
        </h2>
        <Link href={CAMINHO_INSTAGRAM} className="text-sm font-medium text-primary hover:underline">
          Ver o Instagram
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CartaoDeSeguidores total={instagram.seguidores.total} crescimento={instagram.seguidores.crescimento} />
        <CartaoDeFluxo rotulo="Alcance" numero={instagram.alcance} />
        <CartaoDeFluxo rotulo="Visualizações" numero={instagram.visualizacoes} />
        <CartaoDeFluxo rotulo="Interações" numero={instagram.interacoes} />
      </div>
    </section>
  );
}

function CartaoDeSeguidores({ total, crescimento }: { total: number; crescimento: number }) {
  const sinal = crescimento >= 0 ? "+" : "";
  return (
    <div role="group" aria-label="Seguidores" className="space-y-1 rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-text-secondary">Seguidores</p>
      <p className="text-2xl font-bold tabular-nums text-text">{formatarInteiro(total)}</p>
      <p className="text-xs font-medium text-text-secondary">
        {sinal}
        {formatarInteiro(crescimento)} no período
      </p>
    </div>
  );
}

function CartaoDeFluxo({ rotulo, numero }: { rotulo: string; numero: NumeroDeFluxo }) {
  return (
    <div role="group" aria-label={rotulo} className="space-y-1 rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-text-secondary">{rotulo}</p>
      <p className="text-2xl font-bold tabular-nums text-text">{formatarInteiro(numero.atual)}</p>
      <Seta variacao={numero.variacao} />
    </div>
  );
}

function Seta({ variacao }: { variacao: number | null }) {
  if (variacao === null) return <p className="text-xs text-text-secondary">sem base de comparação</p>;
  if (variacao === 0) return <p className="text-xs text-text-secondary">sem mudança</p>;
  const subiu = variacao > 0;
  const Icone = subiu ? ArrowUp : ArrowDown;
  return (
    <p className={`flex items-center gap-1 text-xs font-medium ${subiu ? "text-emerald-600" : "text-red-600"}`}>
      <Icone className="h-3.5 w-3.5" aria-hidden />
      {formatarPercentual(Math.abs(variacao))}
    </p>
  );
}

function BlocoDeAviso({
  icone: Icone,
  tom,
  titulo,
  mensagem,
}: {
  icone: typeof PlugZap;
  tom: "calmo" | "erro";
  titulo: string;
  mensagem: string;
}) {
  const cores = tom === "calmo" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-red-200 bg-red-50 text-red-900";
  return (
    <section aria-labelledby="central-instagram-relance" className={`flex gap-3 rounded-2xl border p-6 ${cores}`}>
      <Icone className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <div className="space-y-1">
        <h2 id="central-instagram-relance" className="font-semibold">
          {titulo}
        </h2>
        <p className="text-sm">{mensagem}</p>
      </div>
    </section>
  );
}
