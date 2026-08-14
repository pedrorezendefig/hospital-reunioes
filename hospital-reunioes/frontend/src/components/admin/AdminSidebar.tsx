"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";
import {
  Users,
  ArrowLeft,
  Building2,
  BadgeCheck,
  CalendarRange,
  HeartPulse,
  LucideIcon,
  Wrench,
} from "lucide-react";

type Item = { href: string; label: string; icon: LucideIcon };
// somenteSuperAdmin: secoes que a sidebar esconde de secretaria/facilitador
// (o backend segue sendo o gate real, com 403 nas rotas de super admin).
type Section = { label: string; items: Item[]; somenteSuperAdmin?: boolean };

const SECTIONS: Section[] = [
  {
    label: "Pessoas",
    somenteSuperAdmin: true,
    items: [{ href: "/admin/usuarios", label: "Usuários", icon: Users }],
  },
  {
    label: "Taxonomia",
    somenteSuperAdmin: true,
    items: [
      { href: "/admin/setores", label: "Setores", icon: Building2 },
      { href: "/admin/cargos", label: "Cargos", icon: BadgeCheck },
      {
        href: "/admin/tipos-reuniao",
        label: "Tipos de Reunião",
        icon: CalendarRange,
      },
    ],
  },
  {
    label: "Atendimento",
    items: [
      {
        href: "/admin/dados-atendimento",
        label: "Dados do Atendimento",
        icon: HeartPulse,
      },
    ],
  },
  {
    label: "Ferramentas",
    somenteSuperAdmin: true,
    items: [{ href: "/admin/utilitarios", label: "Utilitários", icon: Wrench }],
  },
];

interface AdminSidebarProps {
  variant?: "desktop" | "drawer";
  onNavigate?: () => void;
}

export function AdminSidebar({
  variant = "desktop",
  onNavigate,
}: AdminSidebarProps) {
  const pathname = usePathname();
  const { participante } = useCurrentParticipante();
  const superAdmin = isSuperAdmin(participante);
  const sections = SECTIONS.filter(
    (s) => superAdmin || !s.somenteSuperAdmin,
  );

  const content = (
    <>
      <div className="px-4 py-3 border-b border-border flex justify-center">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className="block hover:opacity-80 transition-opacity"
        >
          <Logo layout="vertical" size="md" />
        </Link>
      </div>

      <div className="px-4 pt-4 pb-2">
        <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
          Administração
        </span>
      </div>

      <nav className="flex-1 px-4 pb-4 space-y-3 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.label} className="space-y-1">
            <div className="px-3 pt-2 pb-1 text-[10px] font-semibold text-text-secondary/70 uppercase tracking-wider">
              {section.label}
            </div>
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className={`flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
                    isActive
                      ? "bg-primary/10 text-primary border-l-[3px] border-primary pl-2.5"
                      : "text-text-secondary hover:bg-primary/5 hover:text-text"
                  }`}
                >
                  <Icon
                    className="w-[18px] h-[18px]"
                    strokeWidth={isActive ? 2 : 1.5}
                  />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="p-4 border-t border-border">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-primary/5 hover:text-text transition-colors"
        >
          <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
          Voltar ao app
        </Link>
      </div>
    </>
  );

  if (variant === "desktop") {
    return (
      <aside className="hidden md:flex w-64 min-h-screen bg-gradient-to-b from-surface to-bg border-r border-border flex-col">
        {content}
      </aside>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-surface to-bg">
      {content}
    </div>
  );
}
