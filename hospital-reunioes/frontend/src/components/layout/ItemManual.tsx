"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen } from "lucide-react";

interface Props {
  recolhido: boolean;
  onNavigate?: () => void;
}

/**
 * O item Manual do rodapé das duas barras laterais, a do app e a do Admin,
 * acima do botão de recolher (issue #1718, ADR 0094, decisão 1).
 */
export function ItemManual({ recolhido, onNavigate }: Props) {
  const ativo = usePathname() === "/manual";
  return (
    <Link
      href="/manual"
      onClick={onNavigate}
      title={recolhido ? "Manual" : undefined}
      aria-current={ativo ? "page" : undefined}
      className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
        recolhido ? "justify-center" : ""
      } ${
        ativo
          ? "bg-primary/10 text-primary"
          : "text-text-secondary hover:bg-primary/5 hover:text-text"
      }`}
    >
      <BookOpen className="w-[18px] h-[18px] shrink-0" strokeWidth={ativo ? 2 : 1.5} />
      <span className={recolhido ? "sr-only" : undefined}>Manual</span>
    </Link>
  );
}
