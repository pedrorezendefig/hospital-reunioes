"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Clock,
  User,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";

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

export function BottomNav() {
  const pathname = usePathname();
  const { participante } = useCurrentParticipante();
  const showAdmin = isSuperAdmin(participante);

  const items = showAdmin ? [...baseItems, adminItem] : baseItems;

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
                className={`flex flex-col items-center justify-center gap-0.5 h-full transition-colors duration-150 ${
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
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
