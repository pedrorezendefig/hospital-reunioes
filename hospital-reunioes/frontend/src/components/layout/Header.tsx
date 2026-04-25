"use client";

import { Menu, Search } from "lucide-react";
import { NotificacoesDropdown } from "./NotificacoesDropdown";
import { UserProfileDropdown } from "./UserProfileDropdown";

interface HeaderProps {
  nome: string;
  email?: string;
  onMenuClick?: () => void;
}

export function Header({ nome, email, onMenuClick }: HeaderProps) {
  return (
    <header className="relative z-[100] h-16 bg-slate-50 border-b border-slate-200 flex items-center justify-between px-3 md:px-6 gap-2">
      <div className="flex items-center gap-2 md:gap-3 flex-1 min-w-0">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Abrir menu"
          className="md:hidden inline-flex items-center justify-center w-11 h-11 rounded-xl text-text-secondary hover:bg-primary/5 hover:text-text active:bg-primary/10 transition-colors"
        >
          <Menu className="w-6 h-6" strokeWidth={1.75} />
        </button>

        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/40" />
          <input
            type="text"
            placeholder="Buscar..."
            className="pl-9 pr-4 py-2 rounded-xl bg-bg border border-border text-sm text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all w-64"
          />
        </div>
      </div>

      <div className="flex items-center gap-3 md:gap-6 md:mr-6">
        <NotificacoesDropdown />

        <div className="hidden md:block w-px h-8 bg-border" />

        <UserProfileDropdown nome={nome} email={email} />
      </div>
    </header>
  );
}
