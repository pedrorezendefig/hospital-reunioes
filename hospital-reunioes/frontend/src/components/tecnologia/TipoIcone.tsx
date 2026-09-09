"use client";

/**
 * O símbolo do tipo da Demanda (issue #637, PRD #634, ADR 0050).
 *
 * Um componente só, com o mapa dos sete tipos: o card, o modal e a lista de
 * escolha desenham o mesmo símbolo porque leem daqui. Sete ícones do lucide,
 * o traço que o app inteiro já usa, sem desenho próprio.
 *
 * O `aria-label` é o rótulo do tipo: para quem lê a tela por leitor, "Decisão"
 * é a informação, e não "ícone".
 */

import { Bug, Info, Lightbulb, Scale, SlidersHorizontal, Sparkles, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { TIPO_ROTULO, TipoDemanda } from "./demandas";

const ICONE_DO_TIPO: Record<TipoDemanda, LucideIcon> = {
  // A Vitta precisa que o hospital escolha: a balança de quem pesa e decide.
  decisao: Scale,
  informacao: Info,
  // Depende de gente de fora (Global Health, analista de TI, MV).
  terceiro: Users,
  // Mudar algo que já existe: os controles que se movem sem trocar a peça.
  ajuste: SlidersHorizontal,
  novo: Sparkles,
  defeito: Bug,
  // Opinião ou estudo da Vitta, sem código.
  consultoria: Lightbulb,
};

export function TipoIcone({ tipo, className = "w-4 h-4" }: { tipo: TipoDemanda; className?: string }) {
  const Icone = ICONE_DO_TIPO[tipo] ?? Info;
  return <Icone className={className} role="img" aria-label={TIPO_ROTULO[tipo] ?? tipo} />;
}
