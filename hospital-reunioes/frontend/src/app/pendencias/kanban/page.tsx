"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  Loader2,
  User,
  GripVertical,
  LayoutGrid,
  List,
  Filter,
} from "lucide-react";
import { Pendencia, StatusPendencia } from "@/types";
import { PendenciaDetailModal } from "@/components/pendencias/PendenciaDetailModal";
import { MultiSelect } from "@/components/ui/MultiSelect";
import { PENDENCIA_STATUS_CONFIG } from "@/constants/pendencias";
import { isSuperAdmin } from "@/lib/auth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";

// ─── Constantes ──────────────────────────────────────────────────────────────

const COLUMN_ORDER: StatusPendencia[] = [
  "PENDENTE",
  "EM_PROGRESSO",
  "ATRASADO",
  "CONCLUIDO",
  "CANCELADO",
  "REPACTUADA",
];

// ─── Kanban Card ─────────────────────────────────────────────────────────────

function KanbanCard({
  pendencia,
  onOpenDetail,
  isDragging,
}: {
  pendencia: Pendencia;
  onOpenDetail: (p: Pendencia) => void;
  isDragging: boolean;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", pendencia.id_acao);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => onOpenDetail(pendencia)}
      className={`group bg-white rounded-xl border border-slate-100 p-4 cursor-pointer
        shadow-sm hover:shadow-premium hover:-translate-y-0.5
        transition-all duration-200 select-none
        ${isDragging ? "opacity-50 scale-95 rotate-1" : "opacity-100"}
      `}
    >
      {/* Grip + ID */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <GripVertical className="w-3.5 h-3.5 text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab" />
          <span className="text-[10px] font-mono text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded">
            {pendencia.id_acao}
          </span>
        </div>
        {pendencia.id_reuniao && (
          <span className="text-[10px] text-slate-300 font-mono">
            {pendencia.id_reuniao}
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-sm font-medium text-slate-800 line-clamp-2 mb-3 leading-snug">
        {pendencia.descricao_acao}
      </p>

      {/* Meta entregavel */}
      {pendencia.meta_entregavel && (
        <p className="text-xs text-slate-400 line-clamp-1 mb-3">
          → {pendencia.meta_entregavel}
        </p>
      )}

      {/* Footer: Responsavel com nome completo (prazo removido para dar espaco) */}
      {pendencia.responsavel_nome ? (
        <div className="flex items-start gap-1.5 min-w-0">
          <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
            <span className="text-[10px] font-bold text-primary">
              {pendencia.responsavel_nome
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")
                .toUpperCase()}
            </span>
          </div>
          <div className="flex flex-col gap-1 min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span
                className="text-xs font-medium text-slate-700 leading-snug break-words"
                title={pendencia.responsavel_nome}
              >
                {pendencia.responsavel_nome}
              </span>
              {pendencia.responsavel_is_externo && (
                <span
                  className="text-[9px] font-semibold text-amber-700 bg-amber-100 border border-amber-200 px-1.5 py-0.5 rounded-full uppercase tracking-wide"
                  title="Responsável externo (fora do quadro)"
                >
                  Externo
                </span>
              )}
            </div>
            {pendencia.co_responsavel_nome && (
              <span
                className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full self-start break-words"
                title={`Co-resp: ${pendencia.co_responsavel_nome}`}
              >
                co: {pendencia.co_responsavel_nome}
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1">
          <User className="w-3.5 h-3.5 text-slate-300" />
          <span className="text-xs text-slate-300">Sem responsável</span>
        </div>
      )}
    </div>
  );
}

// ─── Kanban Column ───────────────────────────────────────────────────────────

function KanbanColumn({
  status,
  pendencias,
  onDrop,
  onOpenDetail,
  draggingId,
}: {
  status: StatusPendencia;
  pendencias: Pendencia[];
  onDrop: (id_acao: string, newStatus: StatusPendencia) => void;
  onOpenDetail: (p: Pendencia) => void;
  draggingId: string | null;
}) {
  const [isOver, setIsOver] = useState(false);
  const cfg = PENDENCIA_STATUS_CONFIG[status];
  const Icon = cfg.icon;

  return (
    <div
      className={`flex flex-col min-w-[280px] w-[280px] rounded-2xl border transition-all duration-200 ${
        isOver
          ? `${cfg.borderColor} bg-gradient-to-b ${cfg.bgLight} shadow-lg scale-[1.01]`
          : "border-slate-100 bg-slate-50/50"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        const id_acao = e.dataTransfer.getData("text/plain");
        if (id_acao) onDrop(id_acao, status);
      }}
    >
      {/* Column Header */}
      <div
        className={`flex items-center justify-between px-4 py-3 rounded-t-2xl bg-gradient-to-r ${cfg.headerGradient}`}
      >
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-white/90" strokeWidth={2.5} />
          <span className="text-sm font-semibold text-white">{cfg.label}</span>
        </div>
        <span className="text-xs font-bold text-white/80 bg-white/20 px-2 py-0.5 rounded-full">
          {pendencias.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex-1 p-3 space-y-2.5 overflow-y-auto max-h-[calc(100vh-250px)] min-h-[120px]">
        {pendencias.length === 0 ? (
          <div
            className={`flex items-center justify-center h-20 rounded-xl border-2 border-dashed transition-colors ${
              isOver ? cfg.borderColor : "border-slate-200"
            }`}
          >
            <span className="text-xs text-slate-400">Solte aqui</span>
          </div>
        ) : (
          pendencias.map((p) => (
            <KanbanCard
              key={p.id_acao}
              pendencia={p}
              onOpenDetail={onOpenDetail}
              isDragging={draggingId === p.id_acao}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Página Principal ─────────────────────────────────────────────────────────

export default function KanbanPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      }
    >
      <KanbanContent />
    </Suspense>
  );
}

function KanbanContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pendencias, setPendencias] = useState<Pendencia[]>([]);
  const [participantes, setParticipantes] = useState<{ id: string; nome_completo: string; setor?: string; email?: string; is_super_admin?: boolean }[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string>("");
  const { participante: currentUser } = useCurrentParticipante();
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [selectedPendencia, setSelectedPendencia] = useState<Pendencia | null>(null);

  // Filtros
  const [filtroResponsavel, setFiltroResponsavel] = useState<string[]>(
    searchParams.get("responsavel") ? searchParams.get("responsavel")!.split(",").filter(Boolean) : []
  );
  const [filtroSetor, setFiltroSetor] = useState<string[]>(
    searchParams.get("setor") ? searchParams.get("setor")!.split(",").filter(Boolean) : []
  );
  const [filtroPrazoDe, setFiltroPrazoDe] = useState<string>(searchParams.get("prazo_de") || "");
  const [filtroPrazoAte, setFiltroPrazoAte] = useState<string>(searchParams.get("prazo_ate") || "");
  // Init
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
        return { tk: sessionToken };
      }
      return null;
    }
    init().then((res) => {
      if (res) {
        fetchPendencias(res.tk);
        // Fetch participantes para o MultiSelect do modal.
        // O currentUser (is_super_admin etc.) vem via useCurrentParticipante.
        fetch(`/api/participantes`, {
          headers: { Authorization: `Bearer ${res.tk}` },
        })
          .then((r) => r.ok ? r.json() : Promise.reject(r.status))
          .then((data) => {
            if (Array.isArray(data)) {
              setParticipantes(data);
            }
          })
          .catch(console.error);
      }
    });
  }, []); // Mount only

  const canSuperAdmin = isSuperAdmin(currentUser);

  const fetchPendencias = useCallback(
    async (tk?: string) => {
      setLoading(true);
      try {
        const accessToken = tk ?? token;
        if (!accessToken) return;

        const params = new URLSearchParams();
        params.append("limit", "200");
        if (filtroResponsavel.length > 0) params.set("responsavel_id", filtroResponsavel.join(","));
        if (filtroPrazoDe) params.append("prazo_de", filtroPrazoDe);
        if (filtroPrazoAte) params.append("prazo_ate", filtroPrazoAte);
        const queryStr = params.toString() ? `?${params.toString()}` : "";

        const res = await fetch(`/api/pendencias${queryStr}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) setPendencias(await res.json());
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    },
    [filtroResponsavel, filtroPrazoDe, filtroPrazoAte, token, userRole]
  );

  // Refetch when filters change
  useEffect(() => {
    if (token) fetchPendencias();
  }, [filtroResponsavel, filtroPrazoDe, filtroPrazoAte, token, fetchPendencias]);

  // Mapear click da notificação (highlight)
  const highlightId = searchParams.get("highlight");
  useEffect(() => {
    if (highlightId && pendencias.length > 0 && !selectedPendencia) {
      const entry = pendencias.find((item) => item.id_acao === highlightId);
      if (entry) {
        setSelectedPendencia(entry);
        
        // Limpar o highlight da URL para não reabrir o modal em loop
        const newParams = new URLSearchParams(searchParams.toString());
        newParams.delete("highlight");
        const qs = newParams.toString();
        router.replace(qs ? `/pendencias/kanban?${qs}` : `/pendencias/kanban`, { scroll: false });
      }
    }
  }, [highlightId, pendencias, selectedPendencia, searchParams, router]);

  // Filtragem extra no frontend para Setor
  const pendenciasFiltradas = pendencias.filter(p => {
    if (filtroSetor.length === 0) return true;
    const part = participantes.find(pt => pt.id === p.responsavel_id);
    return part?.setor !== undefined && filtroSetor.includes(part.setor);
  });

  // Group by status
  const columns: Record<StatusPendencia, Pendencia[]> = {
    PENDENTE: [],
    EM_PROGRESSO: [],
    ATRASADO: [],
    CONCLUIDO: [],
    CANCELADO: [],
    REPACTUADA: [],
  };

  pendenciasFiltradas.forEach((p) => {
    if (columns[p.status]) columns[p.status].push(p);
  });

  // Handle drag-and-drop status change
  async function handleDrop(id_acao: string, newStatus: StatusPendencia) {
    const card = pendencias.find((p) => p.id_acao === id_acao);
    if (!card || card.status === newStatus) return;

    // Optimistic update
    setPendencias((prev) =>
      prev.map((p) => (p.id_acao === id_acao ? { ...p, status: newStatus, ...(newStatus === "REPACTUADA" ? { prazo: undefined } : {}) } : p))
    );
    setUpdatingId(id_acao);

    try {
      const payload: Record<string, string | null> = { status: newStatus };
      if (newStatus === "REPACTUADA") {
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

      if (!res.ok) {
        // Revert on failure
        setPendencias((prev) =>
          prev.map((p) =>
            p.id_acao === id_acao ? { ...p, status: card.status } : p
          )
        );
      }
    } catch (e) {
      console.error("Erro ao mover card:", e);
      // Revert
      setPendencias((prev) =>
        prev.map((p) =>
          p.id_acao === id_acao ? { ...p, status: card.status } : p
        )
      );
    } finally {
      setUpdatingId(null);
    }
  }

  function handleOpenDetail(p: Pendencia) {
    setSelectedPendencia(p);
  }

  function handleModalStatusUpdated(id_acao: string, newStatus: StatusPendencia) {
    setPendencias((prev) =>
      prev.map((p) => (p.id_acao === id_acao ? { ...p, status: newStatus, ...(newStatus === "REPACTUADA" ? { prazo: undefined } : {}) } : p))
    );
    if (selectedPendencia?.id_acao === id_acao) {
      setSelectedPendencia((prev) => prev ? { ...prev, status: newStatus, ...(newStatus === "REPACTUADA" ? { prazo: undefined } : {}) } : null);
    }
  }

  function handlePendenciaUpdated(updatedObj: Pendencia) {
    setPendencias((prev) =>
      prev.map((p) => (p.id_acao === updatedObj.id_acao ? updatedObj : p))
    );
    if (selectedPendencia?.id_acao === updatedObj.id_acao) {
      setSelectedPendencia(updatedObj);
    }
  }

  // Global drag listeners for styling
  useEffect(() => {
    function onDragStart(e: DragEvent) {
      const id = (e.target as HTMLElement)
        ?.closest("[draggable]")
        ?.querySelector(".font-mono")?.textContent;
      if (id) setDraggingId(id);
    }
    function onDragEnd() {
      setDraggingId(null);
    }
    document.addEventListener("dragstart", onDragStart);
    document.addEventListener("dragend", onDragEnd);
    return () => {
      document.removeEventListener("dragstart", onDragStart);
      document.removeEventListener("dragend", onDragEnd);
    };
  }, []);

  return (
    <div className="space-y-5 animate-fade-in-up pb-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Kanban</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Arraste os cards para alterar o status das pendências
          </p>
        </div>

        {/* View Toggle */}
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
          <Link
            href="/pendencias"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-500 hover:bg-slate-50 transition-colors"
          >
            <List className="w-4 h-4" />
            Tabela
          </Link>
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-primary/10 text-primary"
            disabled
          >
            <LayoutGrid className="w-4 h-4" />
            Kanban
          </button>
        </div>
      </div>

      {/* Barra de Filtros Avançados */}
      <div className="bg-white p-4 rounded-xl border border-border shadow-premium flex flex-col gap-4">
        <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm mb-1">
          <Filter className="w-4 h-4" />
          <span>Filtros Dinâmicos</span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
          {canSuperAdmin && (
            <div className="flex flex-col gap-1.5">
              <MultiSelect
                label="Setor"
                options={Array.from(new Set(participantes.map(p => p.setor).filter(Boolean))).sort().map(s => ({ value: s as string, label: s as string }))}
                selected={filtroSetor}
                onChange={(v) => {
                  setFiltroSetor(v);
                  setFiltroResponsavel([]);
                }}
                placeholder="Todos os Setores"
                allLabel="Todos os Setores"
              />
            </div>
          )}

          {canSuperAdmin && (
            <div className="flex flex-col gap-1.5">
              <MultiSelect
                label="Responsável"
                options={participantes
                  .filter(p => filtroSetor.length === 0 || (p.setor && filtroSetor.includes(p.setor)))
                  .map(p => ({ value: p.id, label: p.nome_completo }))}
                selected={filtroResponsavel}
                onChange={setFiltroResponsavel}
                placeholder={filtroSetor.length > 0 ? "Todos (dos Setores)" : "Equipe Inteira"}
                allLabel={filtroSetor.length > 0 ? "Todos (dos Setores)" : "Equipe Inteira"}
              />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-500 uppercase">A partir de</label>
            <input 
              title="Prazo inicio"
              type="date"
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              value={filtroPrazoDe}
              onChange={(e) => setFiltroPrazoDe(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-500 uppercase">Até</label>
            <input 
              title="Prazo limite"
              type="date"
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              value={filtroPrazoAte}
              onChange={(e) => setFiltroPrazoAte(e.target.value)}
            />
          </div>

          <div className="flex flex-col justify-end">
             <button
                onClick={() => {
                  setFiltroSetor([]);
                  setFiltroResponsavel([]);
                  setFiltroPrazoDe("");
                  setFiltroPrazoAte("");
                  router.replace("/pendencias/kanban");
                }}
                className="text-sm font-medium text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 transition-colors py-2 px-3 rounded-lg w-full text-center"
             >
                Limpar Filtros
             </button>
          </div>
        </div>
      </div>

      {/* Board */}
      {loading ? (
        <div className="flex items-center justify-center h-64 gap-2 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
          Carregando board...
        </div>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {COLUMN_ORDER.map((status) => (
            <KanbanColumn
              key={status}
              status={status}
              pendencias={columns[status]}
              onDrop={handleDrop}
              onOpenDetail={handleOpenDetail}
              draggingId={draggingId}
            />
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedPendencia && (
        <PendenciaDetailModal
          pendencia={selectedPendencia}
          token={token}
          participantes={participantes}
          userRole={userRole}
          currentUser={currentUser}
          onClose={() => setSelectedPendencia(null)}
          onStatusUpdated={handleModalStatusUpdated}
          onPendenciaUpdated={handlePendenciaUpdated}
          onPendenciaDeleted={(id) =>
            setPendencias((prev) => prev.filter((p) => p.id_acao !== id))
          }
        />
      )}
    </div>
  );
}
