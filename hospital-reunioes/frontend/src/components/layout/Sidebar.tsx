"use client";

import { useId, useState } from "react";
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
  HeartPulse,
  Users,
  FileText,
  GraduationCap,
  CalendarClock,
  ClipboardCheck,
  ShieldAlert,
  Landmark,
  Siren,
  Inbox,
  Repeat,
  Scale,
  type LucideIcon,
} from "lucide-react";
import {
  useCurrentParticipante,
  type CurrentParticipante,
} from "@/hooks/useCurrentParticipante";
import {
  isSecretaria,
  isSuperAdmin,
  temAcessoContasMedicas,
  temPapelNaOuvidoria,
  temAcessoReunioes,
  temAcessoSegurancaDoPaciente,
  temPerfilPop,
} from "@/lib/auth";
import { Home, CalendarPlus, ScrollText } from "lucide-react";
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

const HREF_DA_OUVIDORIA = "/ouvidoria";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  // Quando presente, o item vira um grupo colapsável (não navega: o href só
  // identifica o estado de expansão). Suporta aninhamento recursivo: hoje o
  // grupo "Reuniões e metas" contém Pendências, que por sua vez tem o seu
  // próprio submenu Lista/Kanban (dois níveis).
  subItems?: NavItem[];
  // Item previsto para depois, que já aparece no menu desabilitado, com o selo
  // "Em breve" e esta explicação (Segurança do Paciente, seção 14 da
  // especificação). Não navega: o href só identifica o item.
  emBreve?: string;
};

const HREF_DA_SEGURANCA_DO_PACIENTE = "/seguranca-do-paciente";
const GRUPO_DA_SEGURANCA_DO_PACIENTE = "grupo:seguranca-do-paciente";
const GRUPO_DO_NUCLEO = "grupo:seguranca-do-paciente/nucleo";
// O botão "Notificar incidente" (issue #1987): fora de /seguranca-do-paciente
// porque todo usuário logado o abre, mesmo sem acesso ao resto do módulo.
const HREF_DE_NOTIFICAR = "/notificar/modulo";

/**
 * O que a Diretoria quer que já apareça no menu, desabilitado (seção 14 da
 * especificação do Núcleo de Segurança do Paciente). Os textos são os dela.
 */
export const ITENS_EM_BREVE_DO_NSP: readonly NavItem[] = [
  {
    href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/auditorias-de-adesao`,
    label: "Auditorias de adesão",
    icon: ClipboardCheck,
    emBreve:
      "Em breve: auditorias rápidas pelo celular. Um membro da equipe observa uma amostra de pacientes ou de procedimentos (pulseira de identificação, lista de verificação cirúrgica, higiene das mãos, risco de queda) e marca o que encontrou. Os resultados alimentam os indicadores dos protocolos sem digitação.",
  },
  {
    href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/gestao-de-riscos`,
    label: "Gestão de riscos",
    icon: ShieldAlert,
    emBreve:
      "Em breve: mapa de riscos por setor e análise preventiva de processos críticos, antes que o incidente aconteça.",
  },
  {
    href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/comissoes`,
    label: "Comissões",
    icon: Landmark,
    emBreve:
      "Em breve: as demais comissões do hospital (prontuário, óbito, ética) com a mesma estrutura de membros, documentos, reuniões e atas.",
  },
];

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
  const isSec = isSecretaria(participante);
  const dentroDaSegurancaDoPaciente =
    pathname.startsWith(HREF_DA_SEGURANCA_DO_PACIENTE) || pathname.startsWith(HREF_DE_NOTIFICAR);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({
    "/reunioes-metas": true,
    "/pendencias": pathname.startsWith("/pendencias"),
    [GRUPO_DA_SEGURANCA_DO_PACIENTE]: dentroDaSegurancaDoPaciente,
    [GRUPO_DO_NUCLEO]: dentroDaSegurancaDoPaciente,
  });
  // A explicação do item "Em breve" aberta no toque (o celular não tem hover).
  const [emBreveAberto, setEmBreveAberto] = useState<string | null>(null);
  const idDoMenu = useId();

  const toggleExpand = (href: string) => {
    setExpandedItems((prev) => ({ ...prev, [href]: !prev[href] }));
  };

  const navItems = itensDoMenu(participante);

  // Renderiza um nó de navegação. `depth` controla o estilo do submenu:
  // 0 = topo, >= 1 = submenu aninhado (reaproveita a indentação e o border-left
  // do submenu de Pendências em todos os níveis).
  const renderItem = (item: NavItem, depth: number) => {
    const hasSubItems = Boolean(item.subItems && item.subItems.length > 0);
    const isExpanded = expandedItems[item.href];
    const Icon = item.icon;

    if (item.emBreve) {
      const aberto = emBreveAberto === item.href;
      const idDaExplicacao = `${idDoMenu}-${item.href}`;
      return (
        <div key={item.href} className="flex flex-col">
          <button
            type="button"
            aria-disabled="true"
            aria-expanded={aberto}
            aria-describedby={idDaExplicacao}
            onClick={() => setEmBreveAberto(aberto ? null : item.href)}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium text-text-secondary/60 cursor-default text-left"
          >
            <Icon className="w-4 h-4 shrink-0" strokeWidth={1.5} />
            <span className="flex-1">{item.label}</span>
            <span className="etiqueta shrink-0 rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[10px] font-semibold">
              Em breve
            </span>
          </button>
          <p
            id={idDaExplicacao}
            hidden={!aberto}
            className="px-3 pb-2 text-xs leading-relaxed text-text-secondary"
          >
            {item.emBreve}
          </p>
        </div>
      );
    }

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
            {item.href === HREF_DA_OUVIDORIA && (
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
        {item.href === HREF_DA_OUVIDORIA && (
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
            href={isSec ? "/secretaria" : "/inicio"}
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

/**
 * Os itens do menu de cada pessoa: o corte de acesso que o menu faz. O manual
 * (issue #1718, ADR 0094, decisão 2) mostra a página de um módulo só a quem
 * tem o módulo aqui, e por isso lê esta mesma lista em vez de refazer a conta.
 */
export function itensDoMenu(participante: CurrentParticipante | null): NavItem[] {
  // O Admin é só do Super admin (ADR 0101): Dados do Atendimento era o único
  // módulo de lá aberto à secretária e ao facilitador, e fechou.
  const showAdmin = isSuperAdmin(participante);
  const isSec = isSecretaria(participante);
  // Contextos ortogonais (ADR 0007): quem só tem perfil POP não vê
  // Reuniões/Pendências; quem não tem perfil POP não vê /pops.
  const showPops = temPerfilPop(participante);
  const popsOnly = showPops && participante != null && !temAcessoReunioes(participante);

  const popsItem: NavItem = { href: "/pops", label: "POPs", icon: BookOpenCheck };
  // A Ouvidoria só para quem tem papel nela (issue #1884, ADR 0099): o
  // Perfil da Ouvidoria, a Secretária, o Super admin e o responsável do setor.
  const ouvidoriaItens: NavItem[] = temPapelNaOuvidoria(participante)
    ? [{ href: HREF_DA_OUVIDORIA, label: "Ouvidoria", icon: Megaphone }]
    : [];
  // Contas médicas (ADR 0070): eixo próprio, entra em toda montagem do menu
  // para quem tem perfil no módulo ou é super admin.
  const contasMedicasItens: NavItem[] = temAcessoContasMedicas(participante)
    ? [{ href: "/contas-medicas", label: "Contas médicas", icon: ReceiptText }]
    : [];
  // Segurança do Paciente (ADR 0095): o grupo aparece para todo usuário logado,
  // com o botão "Notificar incidente" (issue #1987, Ajuste do plano #2045).
  // O resto do módulo, quem entra o servidor diz; o super admin sem Acesso
  // pleno fica só com o botão. As telas da Fase 1 e os três itens "Em breve"
  // já ficam aqui: as fatias seguintes só preenchem as páginas.
  const notificarIncidente: NavItem = { href: HREF_DE_NOTIFICAR, label: "Notificar incidente", icon: Siren };
  const notificacoesItem: NavItem[] = participante?.recursos_nsp?.includes("casos")
    ? [{ href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/notificacoes`, label: "Notificações", icon: Inbox }]
    : [];
  const segurancaDoPacienteItens: NavItem[] = !participante
    ? []
    : !temAcessoSegurancaDoPaciente(participante)
    ? [
        {
          href: GRUPO_DA_SEGURANCA_DO_PACIENTE,
          label: "Segurança do Paciente",
          icon: HeartPulse,
          subItems: [notificarIncidente],
        },
      ]
    : [
        {
          href: GRUPO_DA_SEGURANCA_DO_PACIENTE,
          label: "Segurança do Paciente",
          icon: HeartPulse,
          subItems: [
            notificarIncidente,
            { href: HREF_DA_SEGURANCA_DO_PACIENTE, label: "Visão geral", icon: Home },
            ...notificacoesItem,
            {
              href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/reunioes`,
              label: "Reuniões",
              icon: CalendarDays,
            },
            {
              href: GRUPO_DO_NUCLEO,
              label: "Núcleo",
              icon: Users,
              subItems: [
                { href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/membros`, label: "Membros", icon: Users },
                { href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/documentos`, label: "Documentos", icon: FileText },
                {
                  href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/capacitacoes`,
                  label: "Capacitações",
                  icon: GraduationCap,
                },
                {
                  href: `${HREF_DA_SEGURANCA_DO_PACIENTE}/agenda`,
                  label: "Agenda regulatória",
                  icon: CalendarClock,
                },
              ],
            },
            ...ITENS_EM_BREVE_DO_NSP,
          ],
        },
      ];

  // Comitê de Conduta (issue #1822): a tela Membros, para quem está no
  // Comitê hoje ou tem o perfil de cadastro. Quem decide é o servidor.
  const comiteDeCondutaItens: NavItem[] = participante?.ve_membros_do_comite
    ? [{ href: "/comite-de-conduta/membros", label: "Comitê de Conduta", icon: Scale }]
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
      // As Definições de processo do setor (issue #1875, ADR 0098, decisão 9).
      { href: "/reunioes/processos", label: "Definições de processo", icon: ScrollText },
      {
        href: "/pendencias",
        label: "Pendências",
        icon: Clock,
        subItems: [
          { href: "/pendencias", label: "Lista", icon: ListTodo },
          { href: "/pendencias/kanban", label: "Kanban", icon: KanbanSquare },
        ],
      },
      // A Rotina e a Verificação por ciclo (issue #1874, ADR 0098, decisão 9).
      { href: "/rotinas", label: "Rotinas", icon: Repeat },
    ],
  };

  // O Início (ADR 0104, decisão 1): primeiro item de todos menos a
  // Secretária, que segue com a tela dela.
  const inicioItem: NavItem = { href: "/inicio", label: "Início", icon: Home };

  return popsOnly
    ? [
        inicioItem,
        popsItem,
        ...ouvidoriaItens,
        ...contasMedicasItens,
        ...segurancaDoPacienteItens,
        ...comiteDeCondutaItens,
      ]
    : isSec
    ? [
        { href: "/secretaria", label: "Início", icon: Home },
        { href: "/secretaria/nova", label: "Nova reunião", icon: CalendarPlus },
        { href: "/reunioes/calendario", label: "Calendário", icon: CalendarDays },
        ...ouvidoriaItens,
        ...(showPops ? [popsItem] : []),
        ...contasMedicasItens,
        ...segurancaDoPacienteItens,
        ...comiteDeCondutaItens,
        ...(showAdmin
          ? [{ href: "/admin", label: "Admin", icon: ShieldCheck }]
          : []),
      ]
    : [
        inicioItem,
        reunioesMetasGroup,
        ...ouvidoriaItens,
        ...(showPops ? [popsItem] : []),
        ...contasMedicasItens,
        ...segurancaDoPacienteItens,
        ...comiteDeCondutaItens,
        ...(showAdmin
          ? [{ href: "/admin", label: "Admin", icon: ShieldCheck }]
          : []),
      ];
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
  // O item "Em breve" não navega: recolhido, ele não vira ícone.
  if (item.emBreve) return [];
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
