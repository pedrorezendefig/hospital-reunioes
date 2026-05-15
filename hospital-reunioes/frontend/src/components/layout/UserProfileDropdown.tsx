"use client";

import { useState, useRef, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { LogOut, User, Settings, ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { SuperAdminBadge } from "@/components/SuperAdminBadge";
import {
  invalidateCurrentParticipante,
  useCurrentParticipante,
} from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";

interface UserProfileDropdownProps {
  nome: string;
  email?: string;
}

export function UserProfileDropdown({ nome, email }: UserProfileDropdownProps) {
  const [open, setOpen] = useState(false);
  const { participante } = useCurrentParticipante();
  const isSuperAdminUser = isSuperAdmin(participante);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const supabase = createClient();

  // Fechar ao clicar fora
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    invalidateCurrentParticipante();
    router.refresh();
    router.push("/login");
  };

  const iniciais = nome.charAt(0).toUpperCase();

  return (
    <div ref={dropdownRef} className="relative">
      {/* Profile Trigger */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-3 hover:bg-slate-100 p-1.5 rounded-xl transition-all duration-200 group"
      >
        <div className="text-right hidden sm:block">
          <div className="text-sm font-semibold text-slate-700 group-hover:text-primary transition-colors inline-flex items-center gap-1.5 justify-end">
            <span>{nome}</span>
            <SuperAdminBadge visible={isSuperAdminUser} size={14} />
          </div>
          {email && (
            <div className="text-xs text-slate-500 truncate max-w-[150px]">
              {email}
            </div>
          )}
        </div>
        <div className="relative">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center text-white font-bold shadow-soft group-hover:shadow-premium transition-all duration-300">
            {iniciais}
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-white rounded-full flex items-center justify-center shadow-sm border border-slate-100">
            <ChevronDown className={`w-3 h-3 text-slate-400 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
          </div>
        </div>
      </button>

      {/* Dropdown Menu */}
      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-2xl shadow-premium-strong z-50 overflow-hidden animate-in fade-in zoom-in duration-200 origin-top-right">
          <div className="p-2 border-b border-slate-50 sm:hidden">
            <div className="px-3 py-2">
              <p className="text-sm font-bold text-slate-800">{nome}</p>
              <p className="text-xs text-slate-500 truncate">{email}</p>
            </div>
          </div>
          
          <div className="p-1.5">
            <button
              onClick={() => {
                setOpen(false);
                router.push("/perfil"); // Exemplo de rota de perfil
              }}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-slate-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-colors group"
            >
              <User className="w-4 h-4 text-slate-400 group-hover:text-primary transition-colors" />
              Meu Perfil
            </button>
            <button
              onClick={() => {
                setOpen(false);
                router.push("/configuracoes"); // Exemplo de rota de config
              }}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-slate-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-colors group"
            >
              <Settings className="w-4 h-4 text-slate-400 group-hover:text-primary transition-colors" />
              Configurações
            </button>
          </div>

          <div className="p-1.5 bg-slate-50/50 border-t border-slate-100">
            <button
              onClick={handleSignOut}
              className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors group"
            >
              <LogOut className="w-4 h-4 text-red-500 group-hover:scale-110 transition-transform" />
              Sair da conta
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
