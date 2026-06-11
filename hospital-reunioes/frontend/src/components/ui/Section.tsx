import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface SectionProps {
  title: string;
  icon?: LucideIcon;
  children: ReactNode;
  /** Slot opcional à direita do título (ex.: o alvo ⌖ de "apontar seção"). */
  action?: ReactNode;
}

/**
 * Card de seção da Ata — título com ícone opcional, slot de ação à direita e corpo.
 * Extraído do detalhe da Reunião para que o `AtaEnxutaView` desenhe o resumo e o
 * quadro com o MESMO visual da Ata final, no detalhe e na tela dedicada da Ata Guiada.
 */
export function Section({ title, icon: Icon, children, action }: SectionProps) {
  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          {Icon && <Icon className="w-4.5 h-4.5 text-primary" strokeWidth={1.5} />}
          <h2 className="font-semibold text-slate-900">{title}</h2>
        </div>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

export default Section;
