"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";
import {
  Shield,
  Bell,
  Mail,
  Palette,
  Users,
  Send,
  Link,
  Loader2,
  Settings,
} from "lucide-react";

import SecuritySection from "@/components/configuracoes/SecuritySection";
import NotificationsSection from "@/components/configuracoes/NotificationsSection";
import EmailSection from "@/components/configuracoes/EmailSection";
import AppearanceSection from "@/components/configuracoes/AppearanceSection";
import UsersSection from "@/components/configuracoes/UsersSection";
import SystemEmailSection from "@/components/configuracoes/SystemEmailSection";
import IntegrationsSection from "@/components/configuracoes/IntegrationsSection";

// ─── Types ────────────────────────────────────────────────────────────────────

type SectionId =
  | "seguranca"
  | "notificacoes"
  | "email"
  | "aparencia"
  | "usuarios"
  | "email_sistema"
  | "integracoes";

interface SectionItem {
  id: SectionId;
  label: string;
  icon: React.ElementType;
  adminOnly?: boolean;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const PERSONAL_SECTIONS: SectionItem[] = [
  { id: "seguranca", label: "Segurança", icon: Shield },
  { id: "notificacoes", label: "Notificações", icon: Bell },
  { id: "email", label: "Email", icon: Mail },
  { id: "aparencia", label: "Aparência", icon: Palette },
];

const ADMIN_SECTIONS: SectionItem[] = [
  { id: "usuarios", label: "Usuários", icon: Users, adminOnly: true },
  { id: "email_sistema", label: "Email Sistema", icon: Send, adminOnly: true },
  { id: "integracoes", label: "Integrações", icon: Link, adminOnly: true },
];

// ─── Main Component ──────────────────────────────────────────────────────────

export default function ConfiguracoesPage() {
  const { token, loading: authLoading } = useAuth();
  const { participante, loading: loadingMe } = useCurrentParticipante();
  const [activeSection, setActiveSection] = useState<SectionId>("seguranca");

  // Admin = super admin (flag dedicada em participantes.is_super_admin).
  // Diretores/presidentes sem a flag NAO tem acesso administrativo.
  const isAdmin = isSuperAdmin(participante);

  // ─── Loading state ────────────────────────────────────────────────────────

  if (authLoading || loadingMe) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <p className="text-text-secondary text-sm">Carregando configurações...</p>
        </div>
      </div>
    );
  }

  // ─── Section rendering ────────────────────────────────────────────────────

  function renderSection() {
    switch (activeSection) {
      case "seguranca":
        return <SecuritySection />;
      case "notificacoes":
        return <NotificationsSection token={token} />;
      case "email":
        return <EmailSection token={token} />;
      case "aparencia":
        return <AppearanceSection />;
      case "usuarios":
        return isAdmin ? <UsersSection token={token} /> : null;
      case "email_sistema":
        return isAdmin ? <SystemEmailSection token={token} /> : null;
      case "integracoes":
        return isAdmin ? <IntegrationsSection token={token} /> : null;
      default:
        return null;
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in-up">
      {/* Page header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="p-2 rounded-xl bg-primary/10">
            <Settings className="w-6 h-6 text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-text">Configurações</h1>
        </div>
        <p className="text-text-secondary text-sm ml-[52px]">
          Gerencie suas preferências e configurações do sistema
        </p>
      </div>

      {/* Content layout */}
      <div className="flex gap-6">
        {/* Internal sidebar */}
        <aside className="w-[220px] flex-shrink-0">
          <div className="bg-white rounded-2xl border border-border shadow-premium p-3 sticky top-8">
            {/* Personal sections */}
            <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider px-3 mb-2">
              Pessoal
            </p>
            <nav className="space-y-1 mb-3">
              {PERSONAL_SECTIONS.map((section) => (
                <SidebarButton
                  key={section.id}
                  section={section}
                  isActive={activeSection === section.id}
                  onClick={() => setActiveSection(section.id)}
                />
              ))}
            </nav>

            {/* Admin sections */}
            {isAdmin && (
              <>
                <div className="border-t border-border my-3" />
                <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider px-3 mb-2">
                  Administração
                </p>
                <nav className="space-y-1">
                  {ADMIN_SECTIONS.map((section) => (
                    <SidebarButton
                      key={section.id}
                      section={section}
                      isActive={activeSection === section.id}
                      onClick={() => setActiveSection(section.id)}
                    />
                  ))}
                </nav>
              </>
            )}
          </div>
        </aside>

        {/* Main content area */}
        <div className="flex-1 min-w-0">{renderSection()}</div>
      </div>
    </div>
  );
}

// ─── Sidebar Button ──────────────────────────────────────────────────────────

function SidebarButton({
  section,
  isActive,
  onClick,
}: {
  section: SectionItem;
  isActive: boolean;
  onClick: () => void;
}) {
  const Icon = section.icon;

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
        isActive
          ? "bg-gradient-to-r from-primary to-primary-light text-white shadow-md"
          : "text-slate-600 hover:bg-slate-50"
      }`}
    >
      <Icon className="w-[18px] h-[18px]" strokeWidth={isActive ? 2 : 1.5} />
      {section.label}
    </button>
  );
}
