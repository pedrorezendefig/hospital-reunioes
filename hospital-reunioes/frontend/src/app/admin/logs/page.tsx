"use client";

/**
 * /admin/logs — visualizador de audit_log.
 *
 * Proteção de rota é feita pelo layout `/admin/layout.tsx` (Agent 3A).
 * Esta página apenas consome:
 *   GET /api/admin/logs?actor_id=&actor_email=&action=&target_type=&target_id=&from=&to=&limit=&offset=
 *   GET /api/admin/logs/actions
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Loader2,
  ScrollText,
  Filter,
  ChevronLeft,
  ChevronRight,
  X,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
  Download,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { MultiSelectFilter } from "@/components/admin/MultiSelectFilter";
import { actionLabel, targetTypeLabel } from "@/lib/admin-labels";

// ─── Types ────────────────────────────────────────────────────────────────

interface AuditLogRow {
  id: string;
  timestamp: string;
  actor_id: string | null;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  reason: string | null;
}

interface AuditLogPage {
  total: number;
  rows: AuditLogRow[];
  limit: number;
  offset: number;
}

const TARGET_TYPES = [
  "reuniao",
  "ata",
  "pendencia",
  "participante",
  "super_admin",
  "bulk",
];

const PAGE_SIZE = 50;

// ─── Page ─────────────────────────────────────────────────────────────────

export default function AdminLogsPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  // Filtros (action e targetType sao multi-select: arrays de valores)
  const [actorEmail, setActorEmail] = useState("");
  const [action, setAction] = useState<string[]>([]);
  const [targetType, setTargetType] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Paginação
  const [offset, setOffset] = useState(0);

  // Dados
  const [actionsOptions, setActionsOptions] = useState<string[]>([]);
  const [page, setPage] = useState<AuditLogPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Carrega lista de actions disponiveis
  useEffect(() => {
    if (authLoading || !token) return;
    fetch("/api/admin/logs/actions", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: string[]) => setActionsOptions(Array.isArray(data) ? data : []))
      .catch(() => setActionsOptions([]));
  }, [authLoading, token]);

  const fetchLogs = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      if (actorEmail.trim()) params.set("actor_email", actorEmail.trim());
      if (action.length > 0) params.set("action", action.join(","));
      if (targetType.length > 0) params.set("target_type", targetType.join(","));
      if (dateFrom) params.set("from", dateFrom);
      if (dateTo) {
        // inclui todo o dia "Até"
        params.set("to", `${dateTo}T23:59:59`);
      }
      const res = await fetch(`/api/admin/logs?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: AuditLogPage = await res.json();
        setPage(data);
      } else if (res.status === 400) {
        toast("Filtros de data inválidos.", "warning");
      } else {
        toast("Falha ao carregar logs", "error");
      }
    } catch {
      toast("Erro de rede ao carregar logs", "error");
    } finally {
      setLoading(false);
    }
  }, [token, offset, actorEmail, action, targetType, dateFrom, dateTo, toast]);

  // Quando filtros mudam, volta pra pagina 0 (se nao ja estiver).
  // Quando offset muda, refetcha.
  useEffect(() => {
    if (authLoading || !token) return;
    if (offset !== 0) {
      setOffset(0);
      return; // o outro efeito vai disparar o fetch apos setOffset
    }
    fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, token, actorEmail, action, targetType, dateFrom, dateTo]);

  useEffect(() => {
    if (authLoading || !token) return;
    // Evita refetch duplicado no mount (offset=0, ja coberto pelo efeito acima).
    if (offset === 0) return;
    fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const total = page?.total ?? 0;
  const currentPageIdx = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function clearFilters() {
    setActorEmail("");
    setAction([]);
    setTargetType([]);
    setDateFrom("");
    setDateTo("");
    setOffset(0);
  }

  // Monta querystring usada tanto pela listagem quanto pelo export.
  const buildFiltersQuery = useCallback(() => {
    const params = new URLSearchParams();
    if (actorEmail.trim()) params.set("actor_email", actorEmail.trim());
    if (action.length > 0) params.set("action", action.join(","));
    if (targetType.length > 0) params.set("target_type", targetType.join(","));
    if (dateFrom) params.set("from", dateFrom);
    if (dateTo) params.set("to", `${dateTo}T23:59:59`);
    return params;
  }, [actorEmail, action, targetType, dateFrom, dateTo]);

  const exportCsv = useCallback(async () => {
    if (!token || exporting) return;
    setExporting(true);
    try {
      const params = buildFiltersQuery();
      const url = `/api/admin/logs/export.csv${
        params.toString() ? `?${params.toString()}` : ""
      }`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 413) {
          toast(
            "Resultado excede o limite de seguranca. Refine os filtros.",
            "warning",
          );
        } else if (res.status === 403) {
          toast("Voce nao tem permissao para exportar logs.", "error");
        } else {
          toast("Falha ao exportar CSV.", "error");
        }
        return;
      }
      const blob = await res.blob();
      let filename = `audit_log_${new Date().toISOString().slice(0, 10)}.csv`;
      const disp = res.headers.get("Content-Disposition");
      if (disp) {
        const match = /filename="?([^"]+)"?/.exec(disp);
        if (match?.[1]) filename = match[1];
      }
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      toast("Erro de rede ao exportar CSV.", "error");
    } finally {
      setExporting(false);
    }
  }, [token, exporting, buildFiltersQuery, toast]);

  const hasActiveFilter =
    !!actorEmail ||
    action.length > 0 ||
    targetType.length > 0 ||
    !!dateFrom ||
    !!dateTo;

  return (
    <div className="space-y-6 animate-fade-in-up pb-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ScrollText className="w-6 h-6 text-primary" />
            Logs de Auditoria
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Histórico de ações administrativas e destrutivas.
          </p>
        </div>
        <button
          onClick={exportCsv}
          disabled={exporting || loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          title="Exportar logs filtrados para CSV"
        >
          {exporting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          Exportar CSV
        </button>
      </div>

      {/* Filtros */}
      <div className="bg-white p-4 rounded-xl border border-border shadow-premium">
        <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm mb-3">
          <Filter className="w-4 h-4" />
          <span>Filtros</span>
          {hasActiveFilter && (
            <span className="ml-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">
              Ativos
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-3 items-end">
          <div className="flex flex-col gap-1 lg:col-span-2">
            <label className="text-xs font-medium text-slate-500 uppercase">
              Ator (email)
            </label>
            <input
              type="text"
              placeholder="email@hospitalsaomatheus.com.br"
              value={actorEmail}
              onChange={(e) => setActorEmail(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>

          <MultiSelectFilter
            label="Ação"
            allLabel="Todas"
            value={action}
            onChange={setAction}
            options={actionsOptions.map((a) => ({
              value: a,
              label: actionLabel(a),
            }))}
          />

          <MultiSelectFilter
            label="Tipo de alvo"
            allLabel="Todos"
            value={targetType}
            onChange={setTargetType}
            options={TARGET_TYPES.map((t) => ({
              value: t,
              label: targetTypeLabel(t),
            }))}
          />

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500 uppercase">De</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500 uppercase">Até</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg p-2 outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {hasActiveFilter && (
          <div className="mt-3 flex justify-end">
            <button
              onClick={clearFilters}
              className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800"
            >
              <X className="w-3 h-3" />
              Limpar filtros
            </button>
          </div>
        )}
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[400px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando logs...
          </div>
        ) : !page || page.rows.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <ScrollText className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhum log encontrado</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {[
                    "",
                    "Timestamp",
                    "Ator",
                    "Ação",
                    "Alvo",
                    "Motivo",
                    "IP",
                  ].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {page.rows.map((row) => (
                  <LogRow
                    key={row.id}
                    row={row}
                    expanded={expanded === row.id}
                    onToggle={() =>
                      setExpanded((prev) => (prev === row.id ? null : row.id))
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Paginação */}
      {page && page.total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total} registros
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
              Anterior
            </button>
            <span className="text-xs text-slate-500">
              Página {currentPageIdx} de {totalPages}
            </span>
            <button
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Próximo
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────

function LogRow({
  row,
  expanded,
  onToggle,
}: {
  row: AuditLogRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  const timestamp = useMemo(() => {
    try {
      const d = new Date(row.timestamp);
      return d.toLocaleString("pt-BR");
    } catch {
      return row.timestamp;
    }
  }, [row.timestamp]);

  const hasMetadata =
    row.metadata && Object.keys(row.metadata || {}).length > 0;

  return (
    <>
      <tr
        className="hover:bg-slate-50/50 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-4 py-3 text-slate-400 w-6">
          {expanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRightIcon className="w-4 h-4" />
          )}
        </td>
        <td className="px-4 py-3 text-slate-600 font-mono text-xs whitespace-nowrap">
          {timestamp}
        </td>
        <td className="px-4 py-3 text-slate-700">
          {row.actor_email}
          {row.actor_id && (
            <span className="block text-[10px] text-slate-400 font-mono">
              {row.actor_id}
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-primary">
            {actionLabel(row.action)}
          </span>
        </td>
        <td className="px-4 py-3 text-slate-600">
          <span className="text-[11px] uppercase tracking-wide text-slate-400">
            {targetTypeLabel(row.target_type)}
          </span>
          <span className="block font-mono text-xs">{row.target_id}</span>
        </td>
        <td className="px-4 py-3 text-slate-600 max-w-[220px]">
          <p className="line-clamp-2 text-xs">{row.reason || "—"}</p>
        </td>
        <td className="px-4 py-3 text-slate-500 text-xs font-mono">
          {row.ip_address || "—"}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50/60">
          <td colSpan={7} className="px-6 py-4">
            <div className="space-y-2">
              <p className="text-[11px] font-semibold text-slate-500 uppercase">
                Metadata
              </p>
              {hasMetadata ? (
                <pre className="bg-white border border-slate-200 rounded-lg p-3 text-xs text-slate-700 overflow-x-auto">
                  {JSON.stringify(row.metadata, null, 2)}
                </pre>
              ) : (
                <p className="text-xs text-slate-400 italic">
                  Nenhum metadata registrado.
                </p>
              )}
              {row.reason && (
                <>
                  <p className="text-[11px] font-semibold text-slate-500 uppercase mt-3">
                    Motivo completo
                  </p>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">
                    {row.reason}
                  </p>
                </>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
