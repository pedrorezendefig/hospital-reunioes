"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/ui/Logo";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";
import { BotaoRecolherMenu } from "@/components/layout/BotaoRecolherMenu";
import { ItemManual } from "@/components/layout/ItemManual";
import { useMenuRecolhido } from "@/hooks/useMenuRecolhido";
import {
  Users,
  ArrowLeft,
  Building2,
  BadgeCheck,
  CalendarRange,
  Camera,
  ChartLine,
  Cpu,
  HeartPulse,
  LayoutDashboard,
  LucideIcon,
  Target,
} from "lucide-react";

type Item = { href: string; label: string; icon: LucideIcon };
// somenteSuperAdmin: secoes que a sidebar esconde de secretaria/facilitador
// (o backend segue sendo o gate real, com 403 nas rotas de super admin).
type Section = {
  label: string;
  items: Item[];
  somenteSuperAdmin?: boolean;
};

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
    // Os numeros do Site e do Instagram (ADR 0058). Cada tela no seu endereco:
    // a Visao Geral tem caminho proprio, e nao a raiz da secao, porque o item
    // ativo e decidido por prefixo e a raiz acenderia em todas as telas.
    label: "Central de Comando",
    somenteSuperAdmin: true,
    items: [
      {
        href: "/admin/central-de-comando/visao-geral",
        label: "Visão Geral",
        icon: LayoutDashboard,
      },
      {
        href: "/admin/central-de-comando/objetivos",
        label: "Objetivos",
        icon: Target,
      },
      {
        href: "/admin/central-de-comando/dados-do-google",
        label: "Dados do Google",
        icon: ChartLine,
      },
      {
        href: "/admin/central-de-comando/instagram",
        label: "Instagram",
        icon: Camera,
      },
    ],
  },
  {
    label: "Tecnologia",
    somenteSuperAdmin: true,
    items: [{ href: "/admin/tecnologia", label: "Tecnologia", icon: Cpu }],
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
  const sections = SECTIONS.filter((s) => superAdmin || !s.somenteSuperAdmin);
  // A mesma preferência da barra do app (issue #1550); a gaveta do celular
  // ignora e segue sempre aberta.
  const [preferenciaRecolhido, alternarRecolhido] = useMenuRecolhido();
  const recolhido = variant === "desktop" && preferenciaRecolhido;

  const content = (
    <>
      {!recolhido && (
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
        </>
      )}

      <nav
        className={`flex-1 space-y-3 overflow-y-auto ${recolhido ? "p-2" : "px-4 pb-4"}`}
      >
        {sections.map((section) => (
          <div key={section.label} className="space-y-1">
            {recolhido ? (
              <div className="mx-2 border-t border-border/50" />
            ) : (
              <div className="px-3 pt-2 pb-1 text-[10px] font-semibold text-text-secondary/70 uppercase tracking-wider">
                {section.label}
              </div>
            )}
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  title={recolhido ? item.label : undefined}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
                    recolhido ? "justify-center" : ""
                  } ${
                    isActive
                      ? recolhido
                        ? "bg-primary/10 text-primary"
                        : "bg-primary/10 text-primary border-l-[3px] border-primary pl-2.5"
                      : "text-text-secondary hover:bg-primary/5 hover:text-text"
                  }`}
                >
                  <Icon
                    className="w-[18px] h-[18px] shrink-0"
                    strokeWidth={isActive ? 2 : 1.5}
                  />
                  <span className={recolhido ? "sr-only" : undefined}>
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </div>
        ))}

      </nav>

      <div
        data-rodape-do-menu
        className={`border-t border-border space-y-1 ${recolhido ? "p-2" : "p-4"}`}
      >
        <Link
          href="/dashboard"
          onClick={onNavigate}
          title={recolhido ? "Voltar ao app" : undefined}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-primary/5 hover:text-text transition-colors ${
            recolhido ? "justify-center" : ""
          }`}
        >
          <ArrowLeft className="w-4 h-4 shrink-0" strokeWidth={1.5} />
          <span className={recolhido ? "sr-only" : undefined}>
            Voltar ao app
          </span>
        </Link>
        <ItemManual recolhido={recolhido} onNavigate={onNavigate} />
        {variant === "desktop" && (
          <BotaoRecolherMenu
            recolhido={recolhido}
            onAlternar={alternarRecolhido}
          />
        )}
      </div>
    </>
  );

  if (variant === "desktop") {
    return (
      <aside
        className={`hidden md:flex ${recolhido ? "w-16" : "w-64"} min-h-screen bg-gradient-to-b from-surface to-bg border-r border-border flex-col`}
      >
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
