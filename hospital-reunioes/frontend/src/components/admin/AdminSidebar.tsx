"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import {
  Users,
  ShieldCheck,
  ScrollText,
  Layers,
  ArrowLeft,
} from "lucide-react";

const items = [
  { href: "/admin/usuarios", label: "Usuários", icon: Users },
  { href: "/admin/super-admins", label: "Super Admins", icon: ShieldCheck },
  { href: "/admin/logs", label: "Logs", icon: ScrollText },
  { href: "/admin/bulk", label: "Ações em Massa", icon: Layers },
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

      <nav className="flex-1 px-4 pb-4 space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
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
