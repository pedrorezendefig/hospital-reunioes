"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

interface Props {
  recolhido: boolean;
  onAlternar: () => void;
}

/** O botão que recolhe e expande o menu lateral do computador (issue #1550). */
export function BotaoRecolherMenu({ recolhido, onAlternar }: Props) {
  const rotulo = recolhido ? "Expandir menu" : "Recolher menu";
  const Icone = recolhido ? PanelLeftOpen : PanelLeftClose;
  return (
    <button
      type="button"
      onClick={onAlternar}
      aria-label={rotulo}
      title={rotulo}
      aria-expanded={!recolhido}
      className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-primary/5 hover:text-text transition-colors cursor-pointer ${
        recolhido ? "justify-center" : ""
      }`}
    >
      <Icone className="w-[18px] h-[18px] shrink-0" strokeWidth={1.5} />
      {!recolhido && <span>Recolher menu</span>}
    </button>
  );
}
