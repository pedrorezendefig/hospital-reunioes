import { Heart, type LucideIcon, Target, Users } from "lucide-react";
import Link from "next/link";

import { formatarInteiro } from "@/lib/central-de-comando/formato";

import { CAMINHO_OBJETIVOS } from "./Objetivos";

/** Um Objetivo em foco na Visão Geral: o card, com o número vivo quando a fonte
 * dele respondeu (senão nulo, e o card leva a ver os números). */
export type ObjetivoEmFoco = {
  id: string;
  nome: string;
  descricao: string;
  numero: { rotulo: string; valor: number } | null;
};

// O ícone de cada Objetivo em foco: escolha de tela (o backend não manda ícone).
const ICONE_DO_OBJETIVO: Record<string, LucideIcon> = {
  "site-visitantes": Users,
  "instagram-seguidores": Users,
  "instagram-engajamento": Heart,
};

/**
 * Os três Objetivos em foco: as direções com número vivo no próprio painel. Cada
 * card leva à lente do Objetivo; o número vem reaproveitado do resto da tela, e
 * cai sozinho quando a fonte dele falha, sem derrubar o card.
 */
export function ObjetivosEmFoco({ objetivos }: { objetivos: ObjetivoEmFoco[] }) {
  return (
    <section aria-labelledby="central-objetivos-em-foco" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="central-objetivos-em-foco" className="flex items-center gap-2 text-lg font-bold text-text">
          <Target aria-hidden className="h-5 w-5 text-primary" />
          Objetivos em foco
        </h2>
        <Link href={CAMINHO_OBJETIVOS} className="text-sm font-medium text-primary hover:underline">
          Ver todos
        </Link>
      </div>
      <ul className="grid gap-4 sm:grid-cols-3">
        {objetivos.map((objetivo) => (
          <li key={objetivo.id}>
            <CardDoObjetivo objetivo={objetivo} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function CardDoObjetivo({ objetivo }: { objetivo: ObjetivoEmFoco }) {
  const Icone = ICONE_DO_OBJETIVO[objetivo.id] ?? Target;
  return (
    <Link
      href={`${CAMINHO_OBJETIVOS}/${objetivo.id}`}
      className="flex h-full flex-col rounded-2xl border border-border bg-white p-5 shadow-premium transition-colors hover:border-primary/40 hover:bg-primary/5"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-white"
        >
          <Icone className="h-4 w-4" />
        </span>
        <div className="space-y-1">
          <h3 className="font-semibold text-text">{objetivo.nome}</h3>
          <p className="text-xs text-text-secondary">{objetivo.descricao}</p>
        </div>
      </div>
      {objetivo.numero ? (
        <div className="mt-4">
          <p className="text-3xl font-bold tabular-nums text-text">{formatarInteiro(objetivo.numero.valor)}</p>
          <p className="text-xs text-text-secondary">{objetivo.numero.rotulo}</p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-text-secondary">Ver os números</p>
      )}
    </Link>
  );
}
