"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Clock,
  User,
  ShieldCheck,
  Megaphone,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { temAcessoReunioes, temPerfilOuvidoria } from "@/lib/auth";
import { DistintivoDeNovidades } from "@/components/layout/DistintivoDeNovidades";
import type { ContagemDeNovidades } from "@/lib/ouvidoria/novidades";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (pathname: string) => boolean;
}

const baseItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Início",
    icon: LayoutDashboard,
    match: (p) => p === "/dashboard",
  },
  {
    href: "/reunioes/calendario",
    label: "Reuniões",
    icon: FileText,
    match: (p) => p.startsWith("/reunioes"),
  },
  {
    href: "/pendencias",
    label: "Pendências",
    icon: Clock,
    match: (p) => p.startsWith("/pendencias"),
  },
  {
    href: "/perfil",
    label: "Perfil",
    icon: User,
    match: (p) => p.startsWith("/perfil"),
  },
];

const adminItem: NavItem = {
  href: "/admin",
  label: "Admin",
  icon: ShieldCheck,
  match: (p) => p.startsWith("/admin"),
};

const ouvidoriaItem: NavItem = {
  href: "/ouvidoria",
  label: "Ouvidoria",
  icon: Megaphone,
  match: (p) => p.startsWith("/ouvidoria"),
};

interface BottomNavProps {
  /** O contador de novidades da Ouvidoria (issue #487). Chega pronto de quem
   * monta a casca: a barra e o menu lateral mostram o MESMO número, e cada um
   * buscando por conta seriam duas idas ao servidor pela mesma resposta. */
  novidadesOuvidoria?: ContagemDeNovidades;
}

export function BottomNav({
  novidadesOuvidoria = { estado: "sem_contagem" },
}: BottomNavProps) {
  const pathname = usePathname();
  const { participante } = useCurrentParticipante();
  // Todo papel de Reuniões entra no /admin (ADR 0031): a raiz redireciona
  // por papel e o backend segue 403ando o que não é do papel.
  const showAdmin = participante != null && temAcessoReunioes(participante);
  // Quem é da Ouvidoria alcança a fila pelo celular (issue #478, PRD #468).
  const showOuvidoria = temPerfilOuvidoria(participante);

  // Sobra uma vaga depois dos quatro itens fixos, e o Admin e a Ouvidoria
  // disputam essa vaga. Quem leva é a Ouvidoria: o Admin continua no menu
  // lateral (a gaveta do celular), e a fila da Ouvidoria não tem outro
  // atalho aqui embaixo.
  const items = showOuvidoria
    ? [...baseItems, ouvidoriaItem]
    : showAdmin
    ? [...baseItems, adminItem]
    : baseItems;

  return (
    <nav
      aria-label="Navegação principal"
      className="md:hidden fixed bottom-0 inset-x-0 z-[150] bg-surface/95 backdrop-blur-md border-t border-border"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="flex items-stretch justify-around h-16">
        {items.map((item) => {
          const isActive = item.match(pathname);
          const Icon = item.icon;
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`relative flex flex-col items-center justify-center gap-0.5 h-full transition-colors duration-150 ${
                  isActive
                    ? "text-primary"
                    : "text-text-secondary active:text-primary"
                }`}
              >
                <Icon
                  className="w-6 h-6"
                  strokeWidth={isActive ? 2.25 : 1.75}
                />
                <span className="text-[10px] font-medium leading-none">
                  {item.label}
                </span>
                {item.href === ouvidoriaItem.href && (
                  <DistintivoDeNovidades
                    contagem={novidadesOuvidoria}
                    className="absolute top-1.5 left-1/2 ml-2"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
