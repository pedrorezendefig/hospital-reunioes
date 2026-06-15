"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  AlertTriangle,
  ListChecks,
  Loader2,
  ChevronDown,
  ExternalLink,
  Search,
  CalendarDays,
  Filter,
  LayoutGrid,
  MessageSquare,
  User,
  Target,
} from "lucide-react";
import { Pendencia, StatusPendencia } from "@/types";
import { MultiSelect } from "@/components/ui/MultiSelect";
import { PENDENCIA_STATUS_CONFIG, ALL_STATUSES } from "@/constants/pendencias";
import { StatusBadge } from "@/components/pendencias/StatusBadge";
import { PendenciaDetailModal } from "@/components/pendencias/PendenciaDetailModal";
import { isSuperAdmin } from "@/lib/auth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { useFacilitadores } from "@/hooks/useFacilitadores";

// ─── Indicador de prazo ───────────────────────────────────────────────────────

function PrazoCell({ prazo, status, mounted }: { prazo?: string; status: StatusPendencia; mounted: boolean }) {
  if (!prazo || !mounted) {
    if (status === "REPACTUADA") {
        return (
            <span className="inline-flex items-center gap-1 text-purple-600 text-sm font-semibold">
                <AlertCircle className="w-3.5 h-3.5" />
                A repactuar
            </span>
        );
    }
    return <span className="text-slate-300 text-sm">{!prazo ? "A definir" : "Carregando..."}</span>;
  }

  const dt = new Date(prazo + "T12:00:00");
  const diff = Math.ceil((dt.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  const label = dt.toLocaleDateString("pt-BR");

  if (status === "CONCLUIDO" || status === "CANCELADO") {
    return <span className="text-slate-400 text-sm">{label}</span>;
  }

  if (diff < 0) {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 text-sm font-semibold">
        <AlertCircle className="w-3.5 h-3.5" />
        {label}
      </span>
    );
  }
  if (diff <= 3) {
    return (
      <span className="inline-flex items-center gap-1 text-amber-600 text-sm font-medium">
        <CalendarDays className="w-3.5 h-3.5" />
        {label}
        <span className="text-xs font-normal">({diff}d)</span>
      </span>
    );
  }
  return <span className="text-slate-600 text-sm">{label}</span>;
}

// ─── Dropdown de mudança de status ────────────────────────────────────────────

function StatusDropdown({
  id_acao,
  current,
  token,
  onUpdated,
}: {
  id_acao: string;
  current: StatusPendencia;
  token: string | null;
  onUpdated: (id: string, status: StatusPendencia) => void;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function changeStatus(novo: StatusPendencia) {
    if (novo === current) return setOpen(false);
    setLoading(true);
    setOpen(false);
    try {
      const payload: Record<string, string | null> = { status: novo };
      if (novo === "REPACTUADA") {
        payload.prazo = null;
      }
      const res = await fetch(`/api/pendencias/${id_acao}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) onUpdated(id_acao, novo);
    } catch (e) {
      console.error("Erro ao atualizar status:", e);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <Loader2 className="w-4 h-4 animate-spin text-slate-400" />;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-slate-400 hover:text-slate-600 transition-colors"
        aria-label="Alterar status"
      >
        <StatusBadge status={current} />
        <ChevronDown className="w-3.5 h-3.5" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 w-44 bg-white border border-slate-200 rounded-xl shadow-lg z-20 overflow-hidden">
            {ALL_STATUSES.map((s) => {
              const cfg = PENDENCIA_STATUS_CONFIG[s];
              const Icon = cfg.icon;
              return (
                <button
                  key={s}
                  onClick={() => changeStatus(s)}
                  className={`flex items-center gap-2 w-full px-3 py-2.5 text-sm text-left hover:bg-slate-50 transition-colors ${
                    s === current ? "font-semibold bg-slate-50" : ""
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${cfg.color}`} strokeWidth={2} />
                  <span className={cfg.color}>{cfg.label}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Linha da pendência (hover tooltip estilo calendário) ─────────────────────

type ParticipanteOpt = { id: string; nome_completo: string; setor?: string; email?: string; is_super_admin?: boolean };

function PendenciaRow({
  p,
  participantes,
  token,
  mounted,
  onStatusUpdated,
  onOpenDetail,
}: {
  p: Pendencia;
  participantes: ParticipanteOpt[];
  token: string | null;
  mounted: boolean;
  onStatusUpdated: (id_acao: string, novo: StatusPendencia) => void;
  onOpenDetail: (p: Pendencia) => void;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPos, setTooltipPos] = useState<{ top: number; left: number } | null>(null);
  const [portalReady, setPortalReady] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setPortalReady(true);
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []);

  const totalComentarios = p.total_comentarios ?? 0;
  const setor = participantes.find((pt) => pt.id === p.responsavel_id)?.setor || "Geral";
  const prazoFormatted = p.prazo
    ? new Date(p.prazo + "T12:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })
    : null;

  function calcPos(): { top: number; left: number } | null {
    if (!buttonRef.current) return null;
    const rect = buttonRef.current.getBoundingClientRect();
    const TW = 360;
    const TH_EST = 340;
    const OFFSET = 10;

    // Preferência: tooltip à esquerda do botão (botão fica no canto direito da tabela),
    // alinhado verticalmente com o centro do botão.
    let left = rect.left - TW - OFFSET;
    let top = rect.top + rect.height / 2 - TH_EST / 2;

    // Se não couber à esquerda, tenta à direita do botão.
    if (left < 8) {
      left = rect.right + OFFSET;
      // Se também não couber à direita, encosta à esquerda da viewport.
      if (left + TW > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - TW - 8);
      }
    }

    // Garante que não saia do topo nem do fundo.
    if (top < 8) top = 8;
    if (top + TH_EST > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - TH_EST - 8);
    }
    return { top, left };
  }

  function openTooltip() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    const pos = calcPos();
    if (pos) setTooltipPos(pos);
    setShowTooltip(true);
  }

  function scheduleClose() {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    closeTimerRef.current = setTimeout(() => setShowTooltip(false), 120);
  }

  function cancelClose() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  return (
    <>
      <tr className="hover:bg-slate-50/40 transition-colors">
        <td className="px-5 py-4 align-top min-w-[320px]">
          <p className="font-medium text-slate-800 leading-snug break-words hyphens-auto">
            {p.descricao_acao}
          </p>
          {p.meta_entregavel && (
            <p className="text-xs text-emerald-700 mt-1 font-medium leading-relaxed break-words hyphens-auto">
              {p.meta_entregavel}
            </p>
          )}
        </td>
        <td className="px-5 py-4 align-top">
          <p className="text-slate-700 font-medium">{p.responsavel_nome || "-"}</p>
          {p.cargo && <p className="text-xs text-slate-400">{p.cargo}</p>}
        </td>
        <td className="px-5 py-4 align-top">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 whitespace-nowrap">
            {setor}
          </span>
        </td>
        <td className="px-5 py-4 w-12 align-top">
          {p.id_reuniao && (
            <Link
              href={`/reunioes/${p.id_reuniao}`}
              title={`Abrir reunião ${p.id_reuniao}`}
              aria-label={`Abrir reunião ${p.id_reuniao}`}
              className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/5 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
            </Link>
          )}
        </td>
        <td className="px-5 py-4 whitespace-nowrap align-top">
          <PrazoCell prazo={p.prazo} status={p.status} mounted={mounted} />
        </td>
        <td className="px-5 py-4 whitespace-nowrap align-top">
          <StatusDropdown
            id_acao={p.id_acao}
            current={p.status}
            token={token}
            onUpdated={onStatusUpdated}
          />
        </td>
        <td className="px-5 py-4 whitespace-nowrap align-top">
          <div className="flex items-center justify-end gap-2">
            {totalComentarios > 0 && (
              <span
                className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full"
                aria-label={`${totalComentarios} comentário${totalComentarios === 1 ? "" : "s"}`}
                title={`${totalComentarios} comentário${totalComentarios === 1 ? "" : "s"}`}
              >
                <MessageSquare className="w-3 h-3" />
                {totalComentarios}
              </span>
            )}
            <button
              ref={buttonRef}
              type="button"
              onClick={() => onOpenDetail(p)}
              onMouseEnter={openTooltip}
              onMouseLeave={scheduleClose}
              onFocus={openTooltip}
              onBlur={scheduleClose}
              className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              aria-label="Abrir detalhes da pendência"
              aria-describedby={showTooltip ? `tooltip-${p.id_acao}` : undefined}
            >
              <Search className="w-4 h-4" />
            </button>
          </div>
        </td>
      </tr>

      {portalReady && showTooltip && tooltipPos && createPortal(
        <div
          role="tooltip"
          id={`tooltip-${p.id_acao}`}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
          style={{ top: tooltipPos.top, left: tooltipPos.left }}
          className="fixed z-[60] w-[360px] max-h-[80vh] overflow-y-auto bg-white rounded-2xl shadow-2xl border border-slate-100 p-4 animate-fade-in-up"
        >
          {/* Header — id mono + status badge */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <span className="text-[10px] font-mono text-slate-400 bg-slate-50 px-2 py-1 rounded-md tracking-wide">
              {p.id_acao}
            </span>
            <StatusBadge status={p.status} />
          </div>

          {/* Bloco Ação / Tarefa */}
          <div className="mb-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-1.5">
              Ação · Tarefa
            </p>
            <p className="text-sm font-semibold text-slate-900 leading-relaxed whitespace-pre-wrap">
              {p.descricao_acao}
            </p>
          </div>

          {/* Bloco Meta · Entregável — destaque verde */}
          {p.meta_entregavel ? (
            <div className="mb-3 rounded-lg border-l-[3px] border-emerald-400 bg-emerald-50/50 px-3 py-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700 mb-1 flex items-center gap-1">
                <Target className="w-3 h-3" />
                Meta · Entregável
              </p>
              <p className="text-xs text-emerald-900/90 leading-relaxed whitespace-pre-wrap font-medium">
                {p.meta_entregavel}
              </p>
            </div>
          ) : (
            <div className="mb-3 rounded-lg border border-dashed border-slate-200 px-3 py-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-1 flex items-center gap-1">
                <Target className="w-3 h-3" />
                Meta · Entregável
              </p>
              <p className="text-xs text-slate-400 italic">Não definido</p>
            </div>
          )}

          {/* Meta-info: responsável · prazo · setor · comentários */}
          <div className="space-y-1.5 pt-3 border-t border-slate-100">
            {p.responsavel_nome && (
              <p className="text-xs text-slate-600 flex items-center gap-1.5 leading-snug">
                <User className="w-3 h-3 text-slate-400 shrink-0" />
                <span className="font-medium">{p.responsavel_nome}</span>
                {p.cargo && <span className="text-slate-400">· {p.cargo}</span>}
              </p>
            )}
            <p className="text-xs text-slate-600 flex items-center gap-1.5 leading-snug">
              <span className="inline-flex w-3 h-3 items-center justify-center rounded-sm bg-slate-100 text-[8px] font-bold text-slate-500 shrink-0">
                S
              </span>
              <span>{setor}</span>
            </p>
            {prazoFormatted && (
              <p className="text-xs text-slate-600 flex items-center gap-1.5 leading-snug">
                <CalendarDays className="w-3 h-3 text-slate-400 shrink-0" />
                Prazo {prazoFormatted}
              </p>
            )}
            <p className="text-xs text-slate-600 flex items-center gap-1.5 leading-snug">
              <MessageSquare className="w-3 h-3 text-slate-400 shrink-0" />
              {totalComentarios === 0
                ? "Sem comentários"
                : `${totalComentarios} comentário${totalComentarios === 1 ? "" : "s"}`}
            </p>
          </div>

          {/* Footer — botão pra abrir modal completo */}
          <button
            type="button"
            onClick={() => {
              onOpenDetail(p);
              setShowTooltip(false);
            }}
            className="mt-3 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary/90 transition-colors shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <Search className="w-3.5 h-3.5" />
            Abrir detalhes / chat
          </button>
        </div>,
        document.body
      )}
    </>
  );
}

// ─── Página Principal ─────────────────────────────────────────────────────────

export default function PendenciasPage() {
  return (
    <Suspense fallback={
      <div className="flex justify-center items-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    }>
      <PendenciasContent />
    </Suspense>
  );
}

function PendenciasContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [pendencias, setPendencias] = useState<Pendencia[]>([]);
  const [total, setTotal] = useState(0);
  const [participantes, setParticipantes] = useState<ParticipanteOpt[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string>("");
  const [mounted, setMounted] = useState(false);
  const { participante: currentUser } = useCurrentParticipante();
  const { facilitadores } = useFacilitadores();

  const canSuperAdmin = isSuperAdmin(currentUser);

  const [filtroStatus, setFiltroStatus] = useState<StatusPendencia[]>(
    searchParams.get("status") ? searchParams.get("status")!.split(",").filter(Boolean) as StatusPendencia[] : []
  );
  const [filtroResponsaveis, setFiltroResponsaveis] = useState<string[]>(
    searchParams.get("responsavel") ? searchParams.get("responsavel")!.split(",").filter(Boolean) : []
  );
  const [filtroSetores, setFiltroSetores] = useState<string[]>(
    searchParams.get("setor") ? searchParams.get("setor")!.split(",").filter(Boolean) : []
  );
  const [filtroFacilitadores, setFiltroFacilitadores] = useState<string[]>(
    searchParams.get("facilitador") ? searchParams.get("facilitador")!.split(",").filter(Boolean) : []
  );
  const [filtroPrazoDe, setFiltroPrazoDe] = useState<string>(searchParams.get("prazo_de") || "");
  const [filtroPrazoAte, setFiltroPrazoAte] = useState<string>(searchParams.get("prazo_ate") || "");
  const [filtroCriticas, setFiltroCriticas] = useState<boolean>(searchParams.get("criticas") === "true");

  const [selectedPendencia, setSelectedPendencia] = useState<Pendencia | null>(null);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      setUserRole(session?.user?.user_metadata?.role || "coordenador");

      if (sessionToken) {
        // Fetch Participantes Options (para MultiSelect de responsaveis).
        // O user atual (is_super_admin etc.) vem via useCurrentParticipante.
        fetch(`/api/participantes`, {
          headers: { Authorization: `Bearer ${sessionToken}` }
        })
          .then(res => res.ok ? res.json() : Promise.reject(res.status))
          .then(data => {
            if (Array.isArray(data)) {
              setParticipantes(data);
            }
          })
          .catch(console.error);

        return sessionToken;
      }
      return null;
    }

    init().then((tk) => {
      setMounted(true);
      if (tk) fetchPendencias(tk);
    });
  }, []); // Mount only

  const FETCH_LIMIT = 500;

  const fetchPendencias = useCallback(async (tk?: string) => {
    setLoading(true);
    try {
      const accessToken = tk ?? token;
      if (!accessToken) return;

      const params = new URLSearchParams();
      params.append("limit", String(FETCH_LIMIT));
      // Não enviar filtroStatus para o backend para podermos contar os outros status localmente
      if (filtroResponsaveis.length > 0) params.append("responsavel_id", filtroResponsaveis.join(","));
      if (filtroPrazoDe) params.append("prazo_de", filtroPrazoDe);
      if (filtroPrazoAte) params.append("prazo_ate", filtroPrazoAte);
      if (filtroSetores.length > 0)
        params.append("setor", filtroSetores.join(","));
      if (filtroFacilitadores.length > 0)
        params.append("facilitador_id", filtroFacilitadores.join(","));

      const queryStr = `?${params.toString()}`;

      const res = await fetch(`/api/pendencias${queryStr}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const totalHeader = res.headers.get("X-Total-Count");
        setTotal(totalHeader ? parseInt(totalHeader, 10) : 0);
        setPendencias(await res.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filtroResponsaveis, filtroPrazoDe, filtroPrazoAte, filtroSetores, filtroFacilitadores, token, userRole]);

  // Refetch when filters change (except on mount handled by init)
  useEffect(() => {
    if (token) fetchPendencias();
  }, [filtroResponsaveis, filtroPrazoDe, filtroPrazoAte, filtroSetores, filtroFacilitadores, token, fetchPendencias]);

  function handleStatusUpdated(id_acao: string, novoStatus: StatusPendencia) {
    setPendencias((prev) =>
      prev.map((p) => (p.id_acao === id_acao ? { ...p, status: novoStatus, ...(novoStatus === "REPACTUADA" ? { prazo: undefined } : {}) } : p))
    );
    setSelectedPendencia((prev) =>
      prev && prev.id_acao === id_acao
        ? { ...prev, status: novoStatus, ...(novoStatus === "REPACTUADA" ? { prazo: undefined } : {}) }
        : prev
    );
  }

  function handlePendenciaUpdated(updated: Pendencia) {
    setPendencias((prev) =>
      prev.map((p) =>
        p.id_acao === updated.id_acao
          ? { ...updated, total_comentarios: p.total_comentarios }
          : p
      )
    );
    setSelectedPendencia((prev) =>
      prev && prev.id_acao === updated.id_acao
        ? { ...updated, total_comentarios: prev.total_comentarios }
        : prev
    );
  }

  function handlePendenciaDeleted(id_acao: string) {
    setPendencias((prev) => prev.filter((p) => p.id_acao !== id_acao));
    setSelectedPendencia(null);
  }

  // Filtragem extra no frontend para Setor(es)
  const pendenciasFiltradas = pendencias.filter(p => {
    if (filtroSetores.length === 0) return true;
    const part = participantes.find(pt => pt.id === p.responsavel_id);
    return part?.setor !== undefined && filtroSetores.includes(part.setor);
  });

  // Contadores para os badges baseados apenas no status das filtradas
  const contagemPorStatus = ALL_STATUSES.reduce((acc, s) => {
    acc[s] = pendenciasFiltradas.filter((p) => p.status === s).length;
    return acc;
  }, {} as Record<StatusPendencia, number>);

  // Aplicar filtro de status localmente para a tabela
  const pendenciasVisiveis = pendenciasFiltradas.filter(p => {
    if (filtroCriticas) {
      if (p.status === "ATRASADO") return true;
      if (p.status === "PENDENTE" && p.prazo) {
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const prazoDate = new Date(p.prazo + "T00:00:00");
        const diffDays = Math.ceil((prazoDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
        return diffDays >= 0 && diffDays <= 3;
      }
      return false;
    }
    return filtroStatus.length === 0 || filtroStatus.includes(p.status);
  });

  return (
    <div className="space-y-6 animate-fade-in-up pb-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pendências</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Acompanhamento dinâmico hierárquico e por setor
          </p>
        </div>

        {/* View Toggle */}
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-primary/10 text-primary"
            disabled
          >
            <ListChecks className="w-4 h-4" />
            Lista
          </button>
          <Link
            href="/pendencias/kanban"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-500 hover:bg-slate-50 transition-colors"
          >
            <LayoutGrid className="w-4 h-4" />
            Kanban
          </Link>
        </div>
      </div>

      {/* Aviso de truncamento — total > limite carregado */}
      {total > FETCH_LIMIT && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            Mostrando {pendencias.length} de <strong>{total}</strong> pendências. Use os filtros (setor, responsável, prazo) para refinar a busca e garantir que pendências críticas não fiquem fora.
          </span>
        </div>
      )}

      {/* Barra de Filtros Avançados */}
      <div className="bg-white p-4 rounded-xl border border-border shadow-premium flex flex-col gap-4">
        <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm mb-1">
          <Filter className="w-4 h-4" />
          <span>Filtros Dinâmicos</span>
          {(filtroStatus.length > 0 || filtroCriticas || filtroSetores.length > 0 || filtroResponsaveis.length > 0 || filtroFacilitadores.length > 0 || filtroPrazoDe || filtroPrazoAte) && (
            <span className="ml-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">Ativos</span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4 items-end">

          {/* Setor — MultiSelect (só super admin) */}
          {canSuperAdmin && (
            <MultiSelect
              id="filtro-setor-pendencias"
              label="Setor"
              options={Array.from(new Set(participantes.map(p => p.setor).filter((s): s is string => Boolean(s)))).sort().map(s => ({ value: s, label: s }))}
              selected={filtroSetores}
              onChange={(v) => {
                setFiltroSetores(v);
                setFiltroResponsaveis([]);
              }}
              placeholder="Todos os Setores"
              allLabel="Todos os Setores"
            />
          )}

          {/* Responsável — MultiSelect (só super admin) */}
          {canSuperAdmin && (
            <MultiSelect
              id="filtro-resp"
              label="Responsável"
              options={participantes
                .filter(p => filtroSetores.length === 0 || (p.setor && filtroSetores.includes(p.setor)))
                .map(p => ({ value: p.id, label: p.nome_completo || "Sem nome" }))}
              selected={filtroResponsaveis}
              onChange={setFiltroResponsaveis}
              placeholder={filtroSetores.length > 0 ? "Todos (dos Setores)" : "Equipe Inteira"}
              allLabel={filtroSetores.length > 0 ? "Todos (dos Setores)" : "Equipe Inteira"}
            />
          )}

          {/* Facilitador — MultiSelect (visível para qualquer usuário) */}
          <MultiSelect
            id="filtro-facilitador"
            label="Facilitador"
            options={facilitadores.map(f => ({ value: f.id, label: f.nome_completo }))}
            selected={filtroFacilitadores}
            onChange={setFiltroFacilitadores}
            placeholder="Todos os Facilitadores"
            allLabel="Todos os Facilitadores"
          />

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filtro-prazo-de" className="text-xs font-medium text-slate-500 uppercase">A partir de</label>
            <input
              id="filtro-prazo-de"
              title="Prazo inicio"
              type="date"
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              value={filtroPrazoDe}
              onChange={(e) => setFiltroPrazoDe(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filtro-prazo-ate" className="text-xs font-medium text-slate-500 uppercase">Até</label>
            <input
              id="filtro-prazo-ate"
              title="Prazo limite"
              type="date"
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              value={filtroPrazoAte}
              onChange={(e) => setFiltroPrazoAte(e.target.value)}
            />
          </div>

          {/* Botão limpar */}
          <div className="flex flex-col justify-end">
             <button
                id="btn-limpar-filtros"
                onClick={() => {
                  setFiltroSetores([]);
                  setFiltroResponsaveis([]);
                  setFiltroFacilitadores([]);
                  setFiltroPrazoDe("");
                  setFiltroPrazoAte("");
                  setFiltroStatus([]);
                  setFiltroCriticas(false);
                  router.replace('/pendencias');
                }}
                className="text-sm font-medium text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 transition-colors py-2 px-3 rounded-lg w-full text-center"
             >
                Limpar Filtros
             </button>
          </div>
        </div>
      </div>

      {/* Filtros rápidos por status */}
      <div className="flex flex-wrap gap-2 mt-4 items-end">
        <MultiSelect
          label="Status"
          options={ALL_STATUSES.map((s) => ({
            value: s,
            label: `${PENDENCIA_STATUS_CONFIG[s].label} (${contagemPorStatus[s] ?? 0})`,
          }))}
          selected={filtroStatus}
          onChange={(v) => {
            setFiltroCriticas(false);
            setFiltroStatus(v as StatusPendencia[]);
          }}
          placeholder={`Todos os status (${pendenciasFiltradas.length})`}
          allLabel={`Todos os status (${pendenciasFiltradas.length})`}
        />
        {filtroCriticas && (
          <button
            onClick={() => setFiltroCriticas(false)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-sm font-medium transition-all border bg-rose-100 text-rose-600 border-transparent hover:bg-rose-200"
          >
            <AlertCircle className="w-4 h-4" />
            Críticas
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-white/50">
              {pendenciasVisiveis.length}
            </span>
          </button>
        )}
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[400px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando pendências de forma dinâmica...
          </div>
        ) : pendenciasVisiveis.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <ListChecks className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhuma pendência encontrada</p>
            <p className="text-slate-400 text-sm mt-1">
              Refaça os filtros ou conclua aprovações pendentes em atas.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Ação / Tarefa", "Responsável", "Setor", "Reunião", "Prazo", "Status"].map((h) => (
                    <th
                      key={h}
                      className="px-5 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                  <th className="px-5 py-3 text-right">
                    <span className="sr-only">Ações</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {pendenciasVisiveis.map((p) => (
                  <PendenciaRow
                    key={p.id_acao}
                    p={p}
                    participantes={participantes}
                    token={token}
                    mounted={mounted}
                    onStatusUpdated={handleStatusUpdated}
                    onOpenDetail={setSelectedPendencia}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedPendencia && (
        <PendenciaDetailModal
          pendencia={selectedPendencia}
          token={token}
          participantes={participantes}
          userRole={userRole}
          currentUser={currentUser}
          onClose={() => setSelectedPendencia(null)}
          onStatusUpdated={handleStatusUpdated}
          onPendenciaUpdated={handlePendenciaUpdated}
          onPendenciaDeleted={handlePendenciaDeleted}
        />
      )}
    </div>
  );
}
