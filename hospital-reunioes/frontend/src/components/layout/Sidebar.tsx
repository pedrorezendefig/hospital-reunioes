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
  Megaphone,
  ShieldCheck,
  BookOpenCheck,
  Target,
  ReceiptText,
  type LucideIcon,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  isSecretaria,
  temAcessoContasMedicas,
  temAcessoReunioes,
  temPerfilPop,
} from "@/lib/auth";
import { Home, CalendarPlus } from "lucide-react";
import { DistintivoDeNovidades } from "@/components/layout/DistintivoDeNovidades";
import { BotaoRecolherMenu } from "@/components/layout/BotaoRecolherMenu";
import { ItemManual } from "@/components/layout/ItemManual";
import { useMenuRecolhido } from "@/hooks/useMenuRecolhido";
import type { ContagemDeNovidades } from "@/lib/ouvidoria/novidades";

interface SidebarProps {
  variant?: "desktop" | "drawer";
  onNavigate?: () => void;
  /** O contador de novidades da Ouvidoria (issue #487), o mesmo que a barra
   * inferior recebe. Vem pronto de quem monta a casca. */
  novidadesOuvidoria?: ContagemDeNovidades;
}

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  // Quando presente, o item vira um grupo colapsável (não navega: o href só
  // identifica o estado de expansão). Suporta aninhamento recursivo: hoje o
  // grupo "Reuniões e metas" contém Pendências, que por sua vez tem o seu
  // próprio submenu Lista/Kanban (dois níveis).
  subItems?: NavItem[];
};

export function Sidebar({
  variant = "desktop",
  onNavigate,
  novidadesOuvidoria = { estado: "sem_contagem" },
}: SidebarProps) {
  const pathname = usePathname();
  const { participante } = useCurrentParticipante();
  // Só a barra do computador recolhe (issue #1550); a gaveta do celular
  // ignora a preferência e segue sempre aberta.
  const [preferenciaRecolhido, alternarRecolhido] = useMenuRecolhido();
  const recolhido = variant === "desktop" && preferenciaRecolhido;
  // Todo papel de Reuniões entra no /admin: super admin vê tudo, secretária
  // edita e facilitador lê o Dados do Atendimento (ADR 0031). A raiz /admin
  // redireciona por papel; a sidebar de lá esconde o que não é do papel.
  const showAdmin =
    participante != null && temAcessoReunioes(participante);
  const isSec = isSecretaria(participante);
  // Contextos ortogonais (ADR 0007): quem só tem perfil POP não vê
  // Reuniões/Pendências; quem não tem perfil POP não vê /pops.
  const showPops = temPerfilPop(participante);
  const popsOnly = showPops && participante != null && !temAcessoReunioes(participante);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({
    "/reunioes-metas": true,
    "/pendencias": pathname.startsWith("/pendencias"),
  });

  const toggleExpand = (href: string) => {
    setExpandedItems((prev) => ({ ...prev, [href]: !prev[href] }));
  };

  const popsItem: NavItem = { href: "/pops", label: "POPs", icon: BookOpenCheck };
  const ouvidoriaItem: NavItem = {
    href: "/ouvidoria",
    label: "Ouvidoria",
    icon: Megaphone,
  };
  // Contas médicas (ADR 0070): eixo próprio, entra em toda montagem do menu
  // para quem tem perfil no módulo ou é super admin.
  const contasMedicasItens: NavItem[] = temAcessoContasMedicas(participante)
    ? [{ href: "/contas-medicas", label: "Contas médicas", icon: ReceiptText }]
    : [];

  // Grupo colapsável que reúne todo o tema Reuniões (Dashboard, Calendário,
  // Pendências). "Metas" é só o rótulo, não há feature nova.
  const reunioesMetasGroup: NavItem = {
    href: "/reunioes-metas",
    label: "Reuniões e metas",
    icon: Target,
    subItems: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/reunioes/calendario", label: "Calendário", icon: CalendarDays },
      {
        href: "/pendencias",
        label: "Pendências",
        icon: Clock,
        subItems: [
          { href: "/pendencias", label: "Lista", icon: ListTodo },
          { href: "/pendencias/kanban", label: "Kanban", icon: KanbanSquare },
        ],
      },
    ],
  };

  const navItems: NavItem[] = popsOnly
    ? [popsItem, ...contasMedicasItens]
    : isSec
    ? [
        { href: "/secretaria", label: "Início", icon: Home },
        { href: "/secretaria/nova", label: "Nova reunião", icon: CalendarPlus },
        { href: "/reunioes/calendario", label: "Calendário", icon: CalendarDays },
        ouvidoriaItem,
        ...(showPops ? [popsItem] : []),
        ...contasMedicasItens,
        ...(showAdmin
          ? [{ href: "/admin", label: "Admin", icon: ShieldCheck }]
          : []),
      ]
    : [
        reunioesMetasGroup,
        ouvidoriaItem,
        ...(showPops ? [popsItem] : []),
        ...contasMedicasItens,
        ...(showAdmin
          ? [{ href: "/admin", label: "Admin", icon: ShieldCheck }]
          : []),
      ];

  // Renderiza um nó de navegação. `depth` controla o estilo do submenu:
  // 0 = topo, >= 1 = submenu aninhado (reaproveita a indentação e o border-left
  // do submenu de Pendências em todos os níveis).
  const renderItem = (item: NavItem, depth: number) => {
    const hasSubItems = Boolean(item.subItems && item.subItems.length > 0);
    const isExpanded = expandedItems[item.href];
    const Icon = item.icon;

    if (hasSubItems) {
      // Um grupo está "ativo" quando a rota atual está sob algum dos seus
      // filhos navegáveis. O destaque forte (border-left) fica reservado ao
      // link folha de fato ativo; o grupo recebe só o realce suave.
      const isWithinGroup = subtreeMatchesPath(item, pathname);

      const buttonBase =
        depth === 0
          ? "px-3 py-2.5 rounded-xl"
          : "px-3 py-2 rounded-lg";

      return (
        <div key={item.href} className="flex flex-col">
          <button
            onClick={() => toggleExpand(item.href)}
            className={`flex items-center justify-between w-full ${buttonBase} text-sm font-medium transition-all duration-200 cursor-pointer ${
              isWithinGroup
                ? "bg-primary/5 text-primary"
                : "text-text-secondary hover:bg-primary/5 hover:text-text"
            }`}
          >
            <div className="flex items-center gap-3">
              <Icon
                className={depth === 0 ? "w-[18px] h-[18px]" : "w-4 h-4"}
                strokeWidth={isWithinGroup ? 2 : 1.5}
              />
              {item.label}
            </div>
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 opacity-50" />
            ) : (
              <ChevronRight className="w-4 h-4 opacity-50" />
            )}
          </button>

          {isExpanded && (
            <div className="mt-1 ml-4 pl-3 border-l-2 border-border/50 space-y-1">
              {item.subItems!.map((sub) => renderItem(sub, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    // Item folha (link navegável). No topo (depth 0) usa o estilo cheio; em
    // submenu usa o estilo compacto do antigo Lista/Kanban.
    const isLeafActive = folhaAtiva(item, depth, pathname);

    if (depth === 0) {
      return (
        <div key={item.href} className="flex flex-col">
          <Link
            href={item.href}
            onClick={onNavigate}
            aria-current={isLeafActive ? "page" : undefined}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
              isLeafActive
                ? "bg-primary/10 text-primary border-l-[3px] border-primary pl-2.5"
                : "text-text-secondary hover:bg-primary/5 hover:text-text"
            }`}
          >
            <Icon
              className="w-[18px] h-[18px]"
              strokeWidth={isLeafActive ? 2 : 1.5}
            />
            {item.label}
            {item.href === ouvidoriaItem.href && (
              <DistintivoDeNovidades
                contagem={novidadesOuvidoria}
                className="ml-auto"
              />
            )}
          </Link>
        </div>
      );
    }

    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onNavigate}
        aria-current={isLeafActive ? "page" : undefined}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer ${
          isLeafActive
            ? "bg-primary/10 text-primary"
            : "text-text-secondary hover:bg-primary/5 hover:text-text"
        }`}
      >
        <Icon className="w-4 h-4" strokeWidth={isLeafActive ? 2 : 1.5} />
        {item.label}
      </Link>
    );
  };

  // Recolhida, a barra mostra só o ícone de cada link folha, sem os grupos:
  // um grupo não navega e o submenu indentado não cabe na largura dos ícones.
  // O nome vai no `title` (o hover) e no texto só para leitor de tela.
  const renderIcone = ({ item, depth }: { item: NavItem; depth: number }) => {
    const ativo = folhaAtiva(item, depth, pathname);
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        title={item.label}
        aria-current={ativo ? "page" : undefined}
        className={`relative flex items-center justify-center px-3 py-2.5 rounded-xl transition-all duration-200 cursor-pointer ${
          ativo
            ? "bg-primary/10 text-primary"
            : "text-text-secondary hover:bg-primary/5 hover:text-text"
        }`}
      >
        <Icon className="w-[18px] h-[18px]" strokeWidth={ativo ? 2 : 1.5} />
        <span className="sr-only">{item.label}</span>
        {item.href === ouvidoriaItem.href && (
          <DistintivoDeNovidades
            contagem={novidadesOuvidoria}
            className="absolute -top-1 -right-1"
          />
        )}
      </Link>
    );
  };

  const content = (
    <>
      {!recolhido && (
        <div className="px-4 py-3 border-b border-border flex justify-center">
          <Link
            href={popsOnly ? "/pops" : isSec ? "/secretaria" : "/dashboard"}
            onClick={onNavigate}
            className="block hover:opacity-80 transition-opacity"
          >
            <Logo layout="vertical" size="md" />
          </Link>
        </div>
      )}

      <nav
        className={`flex-1 space-y-1 overflow-y-auto ${recolhido ? "p-2" : "p-4"}`}
      >
        {recolhido
          ? navItems.flatMap((item) => folhas(item, 0)).map(renderIcone)
          : navItems.map((item) => renderItem(item, 0))}
      </nav>
    </>
  );

  if (variant === "desktop") {
    return (
      <aside
        className={`hidden md:flex ${recolhido ? "w-16" : "w-64"} min-h-screen bg-gradient-to-b from-surface to-bg border-r border-border flex-col`}
      >
        {content}
        <div
          data-rodape-do-menu
          className={`border-t border-border space-y-1 ${recolhido ? "p-2" : "p-4"}`}
        >
          <ItemManual recolhido={recolhido} />
          <BotaoRecolherMenu
            recolhido={recolhido}
            onAlternar={alternarRecolhido}
          />
        </div>
      </aside>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-surface to-bg">
      {content}
      <div data-rodape-do-menu className="border-t border-border p-4">
        <ItemManual recolhido={false} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

// O critério de "ativo" de um link folha: match exato para Dashboard e para
// os itens de submenu, prefixo para os demais do topo.
function folhaAtiva(item: NavItem, depth: number, pathname: string): boolean {
  if (item.href === "/dashboard") return pathname === "/dashboard";
  return depth === 0 ? pathname.startsWith(item.href) : pathname === item.href;
}

// Os links folha da subárvore, cada um com a profundidade em que mora (é ela
// que decide o critério de "ativo").
function folhas(item: NavItem, depth: number): { item: NavItem; depth: number }[] {
  if (!item.subItems || item.subItems.length === 0) return [{ item, depth }];
  return item.subItems.flatMap((sub) => folhas(sub, depth + 1));
}

// True se a rota atual cai sob algum link folha (recursivamente) da subárvore
// deste grupo. Usa o mesmo critério de "ativo" dos links folha: match exato
// para Dashboard, prefixo para os demais.
function subtreeMatchesPath(item: NavItem, pathname: string): boolean {
  if (!item.subItems || item.subItems.length === 0) {
    if (item.href === "/dashboard") return pathname === "/dashboard";
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }
  return item.subItems.some((sub) => subtreeMatchesPath(sub, pathname));
}
