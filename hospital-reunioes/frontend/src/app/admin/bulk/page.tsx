"use client";

/**
 * /admin/bulk — Painel de acoes em massa (super admin).
 *
 * 3 secoes em abas:
 *   1. Reenviar ClickSign       → POST /admin/bulk/reenviar-clicksign
 *   2. Reprocessar IA           → POST /admin/bulk/reprocessar-ia
 *   3. Enviar Email em Massa    → POST /admin/bulk/reenviar-email
 *
 * Cada POST retorna 202 com {job_id}. O componente faz polling em
 * GET /admin/bulk/jobs/{job_id} a cada 2s ate status in ('completed','failed').
 *
 * Este arquivo e SO o page.tsx — o layout vem de /admin/layout.tsx.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { jobStatusLabel, statusAtaLabel } from "@/lib/admin-labels";
import {
  Send,
  Cpu,
  Mail,
  Loader2,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Search,
  Filter,
  Clock,
  History,
} from "lucide-react";

// ─── Tipos ──────────────────────────────────────────────────────────────────

type StatusAta =
  | "PROGRAMADA"
  | "PROCESSANDO"
  | "AGUARDANDO_RESOLUCAO"
  | "AGUARDANDO_VALIDACAO"
  | "AGUARDANDO_ASSINATURA"
  | "ASSINADA"
  | "CANCELADA"
  | "ERRO"
  | "ERRO_TRANSCRICAO"
  | "ERRO_IA"
  | "ERRO_CLICKSIGN"
  | "MIGRADA";

interface Reuniao {
  id_reuniao: string;
  data: string;
  tipo: string | null;
  objetivo: string | null;
  status_ata: StatusAta;
}

interface Participante {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string | null;
  setor?: string | null;
  ativo?: boolean;
}

interface BulkFailure {
  id: string;
  erro: string;
}

interface BulkJobAccepted {
  job_id: string;
  status: string;
  total: number;
}

type JobStatus = "pending" | "running" | "completed" | "failed";

interface BulkJob {
  id: string;
  created_at: string;
  updated_at: string;
  actor_id: string | null;
  actor_email: string;
  job_type: string;
  status: JobStatus;
  target_ids: string[];
  total: number;
  sucessos: number;
  falhas: BulkFailure[];
  metadata: Record<string, unknown>;
  reason: string | null;
  started_at: string | null;
  finished_at: string | null;
}

interface BulkJobList {
  total: number;
  rows: BulkJob[];
  limit: number;
  offset: number;
}

type Tab = "clicksign" | "ia" | "email";

const STATUS_OPTIONS: StatusAta[] = [
  "PROGRAMADA",
  "PROCESSANDO",
  "AGUARDANDO_RESOLUCAO",
  "AGUARDANDO_VALIDACAO",
  "AGUARDANDO_ASSINATURA",
  "ASSINADA",
  "CANCELADA",
  "ERRO",
  "ERRO_TRANSCRICAO",
  "ERRO_IA",
  "ERRO_CLICKSIGN",
  "MIGRADA",
];

const POLL_INTERVAL_MS = 2000;

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso + "T12:00:00").toLocaleDateString("pt-BR");
  } catch {
    return iso;
  }
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

function jobTypeLabel(t: string): string {
  if (t === "reenviar_clicksign") return "ClickSign";
  if (t === "reprocessar_ia") return "Reprocessar IA";
  if (t === "reenviar_email") return "Email";
  return t;
}

// ─── Hook: polling de um job ────────────────────────────────────────────────

function useJobPolling(token: string, jobId: string | null) {
  const [job, setJob] = useState<BulkJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setError(null);
      return;
    }

    let cancelled = false;

    async function fetchOnce() {
      try {
        const res = await fetch(`/api/admin/bulk/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as BulkJob;
        if (cancelled) return;
        setJob(data);
        if (data.status === "completed" || data.status === "failed") {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Erro no polling");
        }
      }
    }

    fetchOnce();
    timerRef.current = setInterval(fetchOnce, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [jobId, token]);

  return { job, error };
}

// ─── Componente principal ───────────────────────────────────────────────────

export default function BulkPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>("clicksign");
  const [token, setToken] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      setToken(session?.access_token ?? null);
      setTokenLoading(false);
    })();
  }, []);

  if (tokenLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!token) {
    return (
      <div className="max-w-xl mx-auto mt-10 p-6 border border-red-200 bg-red-50 rounded-xl text-red-800 text-sm">
        Sessao nao encontrada. Faca login novamente.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Acoes em Massa</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          Operacoes administrativas sobre multiplas reunioes ou participantes.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        <TabButton active={tab === "clicksign"} onClick={() => setTab("clicksign")} icon={<Send className="w-4 h-4" />} label="Reenviar ClickSign" />
        <TabButton active={tab === "ia"} onClick={() => setTab("ia")} icon={<Cpu className="w-4 h-4" />} label="Reprocessar IA" />
        <TabButton active={tab === "email"} onClick={() => setTab("email")} icon={<Mail className="w-4 h-4" />} label="Email em Massa" />
      </div>

      {/* Section */}
      <div>
        {tab === "clicksign" && <ReuniaoSection token={token} kind="clicksign" />}
        {tab === "ia" && <ReuniaoSection token={token} kind="ia" />}
        {tab === "email" && <EmailSection token={token} />}
      </div>

      {/* Recent jobs */}
      <RecentJobs token={token} />
    </div>
  );
}

// ─── Tabs ───────────────────────────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors cursor-pointer ${
        active
          ? "border-primary text-primary"
          : "border-transparent text-slate-500 hover:text-slate-700"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

// ─── Secao: Reunioes (ClickSign ou IA) ─────────────────────────────────────

function ReuniaoSection({
  token,
  kind,
}: {
  token: string;
  kind: "clicksign" | "ia";
}) {
  const { toast } = useToast();
  const endpoint =
    kind === "clicksign"
      ? "/api/admin/bulk/reenviar-clicksign"
      : "/api/admin/bulk/reprocessar-ia";
  const actionLabel = kind === "clicksign" ? "Reenviar" : "Reprocessar";
  const defaultStatus: StatusAta[] =
    kind === "clicksign" ? ["AGUARDANDO_ASSINATURA"] : ["ERRO", "ERRO_IA"];

  const [reunioes, setReunioes] = useState<Reuniao[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusAta[]>(defaultStatus);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const { job, error: pollError } = useJobPolling(token, jobId);

  const loadReunioes = useCallback(async () => {
    setLoadingList(true);
    setLoadError(null);
    try {
      const res = await fetch(`/api/reunioes?limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as Reuniao[];
      setReunioes(Array.isArray(data) ? data : []);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Erro ao carregar reunioes");
    } finally {
      setLoadingList(false);
    }
  }, [token]);

  useEffect(() => {
    loadReunioes();
  }, [loadReunioes]);

  const filtered = useMemo(() => {
    return reunioes.filter((r) => {
      if (statusFilter.length > 0 && !statusFilter.includes(r.status_ata)) return false;
      if (search) {
        const hay = `${r.id_reuniao} ${r.objetivo ?? ""} ${r.tipo ?? ""}`.toLowerCase();
        if (!hay.includes(search.toLowerCase())) return false;
      }
      return true;
    });
  }, [reunioes, statusFilter, search]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected((prev) => {
      const allSelected = filtered.every((r) => prev.has(r.id_reuniao));
      const next = new Set(prev);
      if (allSelected) filtered.forEach((r) => next.delete(r.id_reuniao));
      else filtered.forEach((r) => next.add(r.id_reuniao));
      return next;
    });
  }

  function toggleStatus(s: StatusAta) {
    setStatusFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  }

  async function submit(ids: string[]) {
    setSubmitting(true);
    setJobId(null);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          reuniao_ids: ids,
          reason: reason.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const data = (await res.json()) as BulkJobAccepted;
      setJobId(data.job_id);
    } catch (err) {
      setJobId(null);
      toast(
        err instanceof Error ? err.message : "Erro desconhecido ao agendar job", "error"
      );
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  }

  const selectedIds = Array.from(selected);

  // Quando job termina com falhas, oferece retry mantendo selecao
  useEffect(() => {
    if (job && (job.status === "completed" || job.status === "failed")) {
      const failedIds = new Set(job.falhas.map((f) => f.id));
      if (failedIds.size > 0) {
        setSelected(failedIds);
      }
    }
  }, [job]);

  return (
    <div className="space-y-4">
      {/* Filtros */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase">
          <Filter className="w-3.5 h-3.5" />
          Filtros
        </div>
        <div className="flex flex-wrap gap-2">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer ${
                statusFilter.includes(s)
                  ? "bg-primary text-white border-primary"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {statusAtaLabel(s)}
            </button>
          ))}
          {statusFilter.length > 0 && (
            <button
              onClick={() => setStatusFilter([])}
              className="px-2.5 py-1 text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
            >
              Limpar ×
            </button>
          )}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Buscar por id, tipo ou objetivo"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>
      </div>

      {/* Lista */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <div className="text-sm text-slate-600">
            {loadingList ? (
              "Carregando..."
            ) : (
              <>
                <strong>{filtered.length}</strong> reunioes visiveis —{" "}
                <strong className="text-primary">{selected.size}</strong> selecionadas
              </>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={loadReunioes}
              className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 cursor-pointer"
              title="Recarregar"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={toggleAllVisible}
              disabled={filtered.length === 0}
              className="text-xs text-primary hover:underline disabled:opacity-50 cursor-pointer"
            >
              {filtered.every((r) => selected.has(r.id_reuniao)) && filtered.length > 0
                ? "Desmarcar visiveis"
                : "Selecionar visiveis"}
            </button>
          </div>
        </div>

        {loadError ? (
          <div className="p-6 text-sm text-red-600">{loadError}</div>
        ) : loadingList ? (
          <div className="p-6 text-center text-sm text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-primary/40" />
            Carregando reunioes...
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-400">
            Nenhuma reuniao corresponde aos filtros.
          </div>
        ) : (
          <div className="max-h-[420px] overflow-y-auto divide-y divide-slate-50">
            {filtered.map((r) => {
              const checked = selected.has(r.id_reuniao);
              return (
                <label
                  key={r.id_reuniao}
                  className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50/60 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(r.id_reuniao)}
                    className="mt-1 w-4 h-4 accent-primary cursor-pointer"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs text-slate-500">{r.id_reuniao}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                        {statusAtaLabel(r.status_ata)}
                      </span>
                      {r.tipo && (
                        <span className="text-xs text-slate-500">{r.tipo}</span>
                      )}
                      <span className="text-xs text-slate-400">{formatDate(r.data)}</span>
                    </div>
                    {r.objetivo && (
                      <p className="text-sm text-slate-600 mt-0.5 truncate">
                        {r.objetivo}
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Motivo + acao */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">
            Motivo (opcional)
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex: reenvio apos queda do provedor de email"
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>
        <button
          onClick={() => setConfirmOpen(true)}
          disabled={submitting || selected.size === 0 || (job?.status === "running" || job?.status === "pending")}
          className="px-4 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl text-sm font-medium hover:shadow-premium-strong transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {actionLabel} ({selected.size})
        </button>
      </div>

      {/* Confirmacao */}
      {confirmOpen && (
        <ConfirmDialog
          title={`${actionLabel} ${selected.size} reuniao(es)?`}
          description={`Esta operacao executara "${actionLabel}" em ${selected.size} item(ns). Deseja continuar?`}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={() => submit(selectedIds)}
          confirmLabel={actionLabel}
          busy={submitting}
        />
      )}

      {/* Progresso / resultado */}
      {pollError && (
        <div className="text-sm text-red-600">Erro ao consultar status: {pollError}</div>
      )}
      {job && (
        <JobProgress
          job={job}
          onRetry={
            (job.status === "completed" || job.status === "failed") && job.falhas.length > 0
              ? () => submit(job.falhas.map((f) => f.id))
              : undefined
          }
          busy={submitting}
        />
      )}
    </div>
  );
}

// ─── Secao: Email em Massa ─────────────────────────────────────────────────

function EmailSection({ token }: { token: string }) {
  const { toast } = useToast();
  const [participantes, setParticipantes] = useState<Participante[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [assunto, setAssunto] = useState("");
  const [corpo, setCorpo] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const { job, error: pollError } = useJobPolling(token, jobId);

  const loadParticipantes = useCallback(async () => {
    setLoadingList(true);
    setLoadError(null);
    try {
      const res = await fetch(`/api/participantes?limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as Participante[];
      setParticipantes(Array.isArray(data) ? data : []);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Erro ao carregar participantes");
    } finally {
      setLoadingList(false);
    }
  }, [token]);

  useEffect(() => {
    loadParticipantes();
  }, [loadParticipantes]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return participantes.filter((p) => {
      if (!s) return true;
      return (
        p.nome_completo.toLowerCase().includes(s) ||
        p.email.toLowerCase().includes(s) ||
        (p.setor ?? "").toLowerCase().includes(s)
      );
    });
  }, [participantes, search]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected((prev) => {
      const allSelected = filtered.every((p) => prev.has(p.id));
      const next = new Set(prev);
      if (allSelected) filtered.forEach((p) => next.delete(p.id));
      else filtered.forEach((p) => next.add(p.id));
      return next;
    });
  }

  async function submit(ids: string[]) {
    setSubmitting(true);
    setJobId(null);
    try {
      const res = await fetch(`/api/admin/bulk/reenviar-email`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          participante_ids: ids,
          assunto: assunto.trim(),
          corpo: corpo,
          reason: reason.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const data = (await res.json()) as BulkJobAccepted;
      setJobId(data.job_id);
    } catch (err) {
      setJobId(null);
      toast(
        err instanceof Error ? err.message : "Erro desconhecido ao agendar job", "error"
      );
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  }

  useEffect(() => {
    if (job && (job.status === "completed" || job.status === "failed")) {
      const failedIds = new Set(job.falhas.map((f) => f.id));
      if (failedIds.size > 0) {
        setSelected(failedIds);
      }
    }
  }, [job]);

  const canSubmit =
    selected.size > 0 && assunto.trim().length > 0 && corpo.trim().length > 0;
  const selectedIds = Array.from(selected);
  const jobPending = job?.status === "running" || job?.status === "pending";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Lista de participantes */}
      <div className="space-y-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="relative mb-3">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar por nome, email ou setor"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
            <span>
              <strong>{filtered.length}</strong> visiveis —{" "}
              <strong className="text-primary">{selected.size}</strong> selecionados
            </span>
            <div className="flex gap-3">
              <button
                onClick={loadParticipantes}
                className="hover:text-slate-700 cursor-pointer flex items-center gap-1"
              >
                <RefreshCw className="w-3 h-3" /> Recarregar
              </button>
              <button
                onClick={toggleAllVisible}
                disabled={filtered.length === 0}
                className="text-primary hover:underline disabled:opacity-50 cursor-pointer"
              >
                {filtered.every((p) => selected.has(p.id)) && filtered.length > 0
                  ? "Desmarcar visiveis"
                  : "Selecionar visiveis"}
              </button>
            </div>
          </div>

          {loadError ? (
            <div className="p-4 text-sm text-red-600">{loadError}</div>
          ) : loadingList ? (
            <div className="p-6 text-center text-sm text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-primary/40" />
              Carregando...
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">
              Nenhum participante encontrado.
            </div>
          ) : (
            <div className="max-h-[420px] overflow-y-auto divide-y divide-slate-50 -mx-2">
              {filtered.map((p) => {
                const checked = selected.has(p.id);
                return (
                  <label
                    key={p.id}
                    className="flex items-start gap-3 px-2 py-2 hover:bg-slate-50/60 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(p.id)}
                      className="mt-1 w-4 h-4 accent-primary cursor-pointer"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-slate-800 font-medium truncate">
                        {p.nome_completo}
                      </div>
                      <div className="text-xs text-slate-500 truncate">
                        {p.email}
                        {p.setor && (
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                            {p.setor}
                          </span>
                        )}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Formulario de email */}
      <div className="space-y-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">
              Assunto <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={assunto}
              onChange={(e) => setAssunto(e.target.value)}
              maxLength={300}
              placeholder="Ex: Aviso importante - reuniao do comite"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">
              Corpo (HTML aceito) <span className="text-red-500">*</span>
            </label>
            <textarea
              value={corpo}
              onChange={(e) => setCorpo(e.target.value)}
              maxLength={20000}
              rows={10}
              placeholder="Texto ou HTML simples — suporta tags como <p>, <strong>, <br>, <a>..."
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
            <p className="text-xs text-slate-400 mt-1">
              {corpo.length} / 20000 caracteres
            </p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase mb-1">
              Motivo (opcional)
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ex: comunicado mensal"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <button
            onClick={() => setConfirmOpen(true)}
            disabled={!canSubmit || submitting || jobPending}
            className="w-full px-4 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl text-sm font-medium hover:shadow-premium-strong transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Enviar para {selected.size} participante(s)
          </button>
          {!canSubmit && selected.size > 0 && (
            <p className="text-xs text-amber-600">
              Preencha assunto e corpo para habilitar o envio.
            </p>
          )}
        </div>

        {confirmOpen && (
          <ConfirmDialog
            title={`Enviar email para ${selected.size} participante(s)?`}
            description={`Assunto: "${assunto}". Esta acao vai disparar um email imediatamente.`}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={() => submit(selectedIds)}
            confirmLabel="Enviar"
            busy={submitting}
          />
        )}

        {pollError && (
          <div className="text-sm text-red-600">
            Erro ao consultar status: {pollError}
          </div>
        )}
        {job && (
          <JobProgress
            job={job}
            onRetry={
              (job.status === "completed" || job.status === "failed") &&
              job.falhas.length > 0
                ? () => submit(job.falhas.map((f) => f.id))
                : undefined
            }
            busy={submitting}
          />
        )}
      </div>
    </div>
  );
}

// ─── Confirmacao ────────────────────────────────────────────────────────────

function ConfirmDialog({
  title,
  description,
  onCancel,
  onConfirm,
  confirmLabel,
  busy,
}: {
  title: string;
  description: string;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  busy: boolean;
}) {
  return (
    <div className="modal-backdrop z-[100] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-premium w-full max-w-md p-6 animate-fade-in-up">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <p className="text-sm text-slate-600 mt-2">{description}</p>
        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 disabled:opacity-50 cursor-pointer"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark disabled:opacity-50 cursor-pointer flex items-center gap-2"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Progresso do job ───────────────────────────────────────────────────────

function JobProgress({
  job,
  onRetry,
  busy,
}: {
  job: BulkJob;
  onRetry?: () => void;
  busy: boolean;
}) {
  const processed = job.sucessos + job.falhas.length;
  const percent = job.total > 0 ? Math.min(100, Math.round((processed / job.total) * 100)) : 0;
  const isFinal = job.status === "completed" || job.status === "failed";

  let statusIcon: React.ReactNode;
  let statusColor: string;

  if (job.status === "pending") {
    statusIcon = <Clock className="w-4 h-4" />;
    statusColor = "text-slate-500";
  } else if (job.status === "running") {
    statusIcon = <Loader2 className="w-4 h-4 animate-spin" />;
    statusColor = "text-primary";
  } else if (job.status === "completed") {
    statusIcon = <CheckCircle2 className="w-4 h-4" />;
    statusColor = "text-emerald-700";
  } else {
    statusIcon = <AlertCircle className="w-4 h-4" />;
    statusColor = "text-red-600";
  }
  const statusLabel = jobStatusLabel(job.status);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className={`flex items-center gap-2 ${statusColor}`}>
          {statusIcon}
          <span className="text-sm font-medium">{statusLabel}</span>
          <span className="text-xs text-slate-400 font-mono">#{job.id.slice(0, 8)}</span>
        </div>
        <div className="text-xs text-slate-500">
          {processed} / {job.total}
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full transition-all duration-500 ${
            job.status === "failed"
              ? "bg-red-500"
              : isFinal
                ? "bg-emerald-500"
                : "bg-primary"
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-emerald-700">
            <CheckCircle2 className="w-4 h-4" />
            <span className="text-sm font-medium">{job.sucessos} sucesso(s)</span>
          </div>
          <div className="flex items-center gap-2 text-red-600">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm font-medium">{job.falhas.length} falha(s)</span>
          </div>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            disabled={busy}
            className="px-3 py-1.5 text-xs font-medium border border-primary/20 text-primary bg-primary/5 rounded-lg hover:bg-primary/10 transition-colors disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
          >
            {busy ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RefreshCw className="w-3 h-3" />
            )}
            Tentar novamente ({job.falhas.length})
          </button>
        )}
      </div>

      {job.falhas.length > 0 && (
        <div className="max-h-64 overflow-y-auto border border-slate-100 rounded-lg">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">
                  ID
                </th>
                <th className="text-left px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">
                  Erro
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {job.falhas.map((f, i) => (
                <tr key={`${f.id}-${i}`}>
                  <td className="px-3 py-2 font-mono text-slate-500">{f.id}</td>
                  <td className="px-3 py-2 text-red-600">{f.erro}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Jobs recentes ──────────────────────────────────────────────────────────

function RecentJobs({ token }: { token: string }) {
  const [jobs, setJobs] = useState<BulkJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/bulk/jobs?limit=10&offset=0`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as BulkJobList;
      setJobs(data.rows || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar jobs");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <History className="w-4 h-4" />
          Jobs recentes
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 cursor-pointer"
          title="Recarregar"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      {error ? (
        <div className="p-4 text-sm text-red-600">{error}</div>
      ) : loading && jobs.length === 0 ? (
        <div className="p-6 text-center text-sm text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-primary/40" />
          Carregando...
        </div>
      ) : jobs.length === 0 ? (
        <div className="p-6 text-center text-sm text-slate-400">
          Nenhum job executado ainda.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left">
              <tr>
                <th className="px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">Quando</th>
                <th className="px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">Tipo</th>
                <th className="px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">Progresso</th>
                <th className="px-3 py-2 font-semibold text-slate-500 uppercase tracking-wide">Autor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {jobs.map((j) => {
                const processed = j.sucessos + j.falhas.length;
                return (
                  <tr key={j.id}>
                    <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                      {formatTimestamp(j.created_at)}
                    </td>
                    <td className="px-3 py-2 text-slate-700 whitespace-nowrap">
                      {jobTypeLabel(j.job_type)}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                          j.status === "completed"
                            ? "bg-emerald-100 text-emerald-700"
                            : j.status === "failed"
                              ? "bg-red-100 text-red-700"
                              : j.status === "running"
                                ? "bg-blue-100 text-blue-700"
                                : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {jobStatusLabel(j.status)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                      {processed}/{j.total}
                      {j.falhas.length > 0 && (
                        <span className="ml-1 text-red-600">({j.falhas.length} erro)</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-500 truncate max-w-[180px]">
                      {j.actor_email}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
