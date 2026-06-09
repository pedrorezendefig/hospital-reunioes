"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import {
  LayoutDashboard,
  Clock,
  ChevronDown,
  ChevronRight,
  ListTodo,
  KanbanSquare,
  CalendarDays,
  ShieldCheck,
  FileUp,
  StickyNote,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSecretaria, isSuperAdmin } from "@/lib/auth";
import { Home, CalendarPlus } from "lucide-react";

interface SidebarProps {
  variant?: "desktop" | "drawer";
  onNavigate?: () => void;
}

export function Sidebar({ variant = "desktop", onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const { participante } = useCurrentParticipante();
  const showAdmin = isSuperAdmin(participante);
  const isSec = isSecretaria(participante);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({
    "/pendencias": pathname.startsWith("/pendencias"),
  });

  const toggleExpand = (href: string) => {
    setExpandedItems((prev) => ({ ...prev, [href]: !prev[href] }));
  };

  const navItems = isSec
    ? [
        { href: "/secretaria", label: "Início", icon: Home },
        { href: "/secretaria/nova", label: "Nova reunião", icon: CalendarPlus },
        { href: "/reunioes/calendario", label: "Calendário", icon: CalendarDays },
      ]
    : [
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { href: "/reunioes/calendario", label: "Calendário", icon: CalendarDays },
        { href: "/notas", label: "Notas", icon: StickyNote },
        {
          href: "/pendencias",
          label: "Pendências",
          icon: Clock,
          subItems: [
            { href: "/pendencias", label: "Lista", icon: ListTodo },
            { href: "/pendencias/kanban", label: "Kanban", icon: KanbanSquare },
          ],
        },
        ...(showAdmin
          ? [
              { href: "/admin", label: "Admin", icon: ShieldCheck },
              { href: "/reunioes/importar", label: "Importar ATA", icon: FileUp },
            ]
          : []),
      ];

  const content = (
    <>
      <div className="px-4 py-3 border-b border-border flex justify-center">
        <Link
          href={isSec ? "/secretaria" : "/dashboard"}
          onClick={onNavigate}
          className="block hover:opacity-80 transition-opacity"
        >
          <Logo layout="vertical" size="md" />
        </Link>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const hasSubItems = Boolean(item.subItems && item.subItems.length > 0);
          const isItemActive =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : !hasSubItems
              ? pathname.startsWith(item.href)
              : pathname === item.href;

          const isExpanded = expandedItems[item.href];

          const Icon = item.icon;

          return (
            <div key={item.href} className="flex flex-col">
              {hasSubItems ? (
                <button
                  onClick={() => toggleExpand(item.href)}
                  className={`flex items-center justify-between w-full px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
                    pathname.startsWith(item.href) && !isItemActive
                      ? "bg-primary/5 text-primary"
                      : isItemActive
                      ? "bg-primary/10 text-primary border-l-[3px] border-primary pl-2.5"
                      : "text-text-secondary hover:bg-primary/5 hover:text-text"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon
                      className="w-[18px] h-[18px]"
                      strokeWidth={pathname.startsWith(item.href) ? 2 : 1.5}
                    />
                    {item.label}
                  </div>
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 opacity-50" />
                  ) : (
                    <ChevronRight className="w-4 h-4 opacity-50" />
                  )}
                </button>
              ) : (
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
                    isItemActive
                      ? "bg-primary/10 text-primary border-l-[3px] border-primary pl-2.5"
                      : "text-text-secondary hover:bg-primary/5 hover:text-text"
                  }`}
                >
                  <Icon
                    className="w-[18px] h-[18px]"
                    strokeWidth={isItemActive ? 2 : 1.5}
                  />
                  {item.label}
                </Link>
              )}

              {hasSubItems && isExpanded && (
                <div className="mt-1 ml-4 pl-3 border-l-2 border-border/50 space-y-1">
                  {item.subItems!.map((sub) => {
                    const isSubActive = pathname === sub.href;
                    const SubIcon = sub.icon;
                    return (
                      <Link
                        key={sub.href}
                        href={sub.href}
                        onClick={onNavigate}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
                          isSubActive
                            ? "bg-primary/10 text-primary"
                            : "text-text-secondary hover:bg-primary/5 hover:text-text"
                        }`}
                      >
                        <SubIcon
                          className="w-4 h-4"
                          strokeWidth={isSubActive ? 2 : 1.5}
                        />
                        {sub.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
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
