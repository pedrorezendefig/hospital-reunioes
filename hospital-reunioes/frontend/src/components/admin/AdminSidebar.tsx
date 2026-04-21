"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import {
  Users,
  ScrollText,
  Layers,
  ArrowLeft,
  Building2,
  BadgeCheck,
  CalendarRange,
  Inbox,
  LucideIcon,
} from "lucide-react";

type Item = { href: string; label: string; icon: LucideIcon };
type Section = { label: string; items: Item[] };

const SECTIONS: Section[] = [
  {
    label: "Pessoas",
    items: [
      { href: "/admin/usuarios", label: "Usuários", icon: Users },
      { href: "/admin/solicitacoes", label: "Solicitações", icon: Inbox },
    ],
  },
  {
    label: "Taxonomia",
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
    label: "Operações",
    items: [{ href: "/admin/bulk", label: "Ações em Massa", icon: Layers }],
  },
  {
    label: "Auditoria",
    items: [{ href: "/admin/logs", label: "Logs", icon: ScrollText }],
  },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 min-h-screen bg-gradient-to-b from-surface to-bg border-r border-border flex flex-col">
      <div className="px-4 py-3 border-b border-border flex justify-center">
        <Link
          href="/dashboard"
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
        {SECTIONS.map((section) => (
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
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-primary/5 hover:text-text transition-colors"
        >
          <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
          Voltar ao app
        </Link>
      </div>
    </aside>
  );
}
