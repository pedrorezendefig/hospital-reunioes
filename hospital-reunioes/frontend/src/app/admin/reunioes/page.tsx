"use client";

import { useCallback, useEffect, useState, FormEvent } from "react";
import {
  CalendarDays,
  Search,
  Pencil,
  Archive,
  ArchiveRestore,
  X,
  Loader2,
  Lock,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { ReasonModal } from "@/components/admin/ReasonModal";

const PAGE_SIZE = 50;

interface Reuniao {
  id_reuniao: string;
  data: string | null;
  titulo: string | null;
  tipo: string | null;
  setor: string | null;
  facilitador_id: string | null;
  objetivo: string | null;
  local: string | null;
  status_ata: string | null;
  nome_grupo_recorrencia: string | null;
  id_grupo_recorrencia: string | null;
  deleted_at: string | null;
}

type Arquivadas = "excluir" | "incluir" | "apenas";

const STATUS_OPTIONS = [
  "PROGRAMADA",
  "PROCESSANDO",
  "ERRO",
  "ERRO_IA",
  "AGUARDANDO_RESOLUCAO",
  "AGUARDANDO_VALIDACAO",
  "AGUARDANDO_ASSINATURA",
  "ASSINADA",
  "CANCELADA",
  "IMPORTADA",
];

const BLOCKED_WHEN_SIGNED = new Set([
  "status_ata",
  "json_ata",
  "url_pdf_assinado",
  "data_assinatura",
  "envelope_key_clicksign",
]);

export default function ReunioesAdminPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<Reuniao[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [arquivadas, setArquivadas] = useState<Arquivadas>("excluir");
  const [page, setPage] = useState(1);

  const [editTarget, setEditTarget] = useState<Reuniao | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Reuniao | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<Reuniao | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        arquivadas,
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (q) params.set("q", q);
      if (statusFilter) params.set("status_ata", statusFilter);
      const res = await fetch(`/api/admin/reunioes?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setRows(body.data);
      setTotal(body.total);
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar reuniões", "error");
    } finally {
      setLoading(false);
    }
  }, [token, q, statusFilter, arquivadas, page, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function handleArchive(reason: string) {
    if (!token || !archiveTarget) return false;
    const res = await fetch(
      `/api/admin/reunioes/${archiveTarget.id_reuniao}`,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reason }),
      },
    );
    if (!res.ok) {
      toast(`Erro ao arquivar: ${await res.text()}`, "error");
      return false;
    }
    toast("Reunião arquivada", "success");
    setArchiveTarget(null);
    await fetchRows();
    return true;
  }

  async function handleRestore(reason: string) {
    if (!token || !restoreTarget) return false;
    const res = await fetch(
      `/api/admin/reunioes/${restoreTarget.id_reuniao}/restore`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reason }),
      },
    );
    if (!res.ok) {
      toast(`Erro ao restaurar: ${await res.text()}`, "error");
      return false;
    }
    toast("Reunião restaurada", "success");
    setRestoreTarget(null);
    await fetchRows();
    return true;
  }

  const columns: Column<Reuniao>[] = [
    {
      key: "id_reuniao",
      header: "ID",
      width: "200px",
      render: (r) => (
        <span className="font-mono text-xs text-slate-500">{r.id_reuniao}</span>
      ),
    },
    {
      key: "titulo",
      header: "Título",
      render: (r) => (
        <div>
          <div className="font-medium text-text">{r.titulo || "—"}</div>
          <div className="text-xs text-slate-400">
            {r.data} · {r.tipo || "—"} · {r.setor || "—"}
          </div>
        </div>
      ),
    },
    {
      key: "status_ata",
      header: "Status",
      width: "180px",
      render: (r) => (
        <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
          {r.status_ata || "—"}
        </span>
      ),
    },
    {
      key: "deleted_at",
      header: "",
      width: "100px",
      render: (r) =>
        r.deleted_at ? (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
            <Archive className="w-3 h-3" />
            Arquivada
          </span>
        ) : null,
    },
  ];

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10 text-primary">
            <CalendarDays className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Reuniões</h1>
            <p className="text-sm text-text-secondary">
              Edição administrativa — atas ASSINADAS são imutáveis no núcleo
            </p>
          </div>
        </div>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id_reuniao}
        emptyState={{
          title: "Nenhuma reunião encontrada",
          hint: "Ajuste os filtros.",
        }}
        pagination={{ page, pageSize: PAGE_SIZE, total, onPageChange: setPage }}
        toolbar={
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="relative md:col-span-2">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                value={q}
                onChange={(e) => {
                  setPage(1);
                  setQ(e.target.value);
                }}
                placeholder="Buscar por título, ID ou objetivo..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => {
                setPage(1);
                setStatusFilter(e.target.value);
              }}
              className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
            >
              <option value="">Status: todos</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              value={arquivadas}
              onChange={(e) => {
                setPage(1);
                setArquivadas(e.target.value as Arquivadas);
              }}
              className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
            >
              <option value="excluir">Ocultar arquivadas</option>
              <option value="incluir">Incluir arquivadas</option>
              <option value="apenas">Apenas arquivadas</option>
            </select>
          </div>
        }
        rowActions={(r) => (
          <>
            <button
              onClick={() => setEditTarget(r)}
              title="Editar"
              className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5"
            >
              <Pencil className="w-4 h-4" />
            </button>
            {r.deleted_at ? (
              <button
                onClick={() => setRestoreTarget(r)}
                title="Restaurar"
                className="p-1.5 rounded-lg text-slate-500 hover:text-emerald-600 hover:bg-emerald-50"
              >
                <ArchiveRestore className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={() => setArchiveTarget(r)}
                title="Arquivar"
                className="p-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50"
              >
                <Archive className="w-4 h-4" />
              </button>
            )}
          </>
        )}
      />

      {editTarget && (
        <ReuniaoEditModal
          target={editTarget}
          token={token!}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            setEditTarget(null);
            fetchRows();
          }}
        />
      )}
      {archiveTarget && (
        <ReasonModal
          title="Arquivar reunião"
          description={`Arquivar "${archiveTarget.titulo || archiveTarget.id_reuniao}"? A reunião será ocultada das listagens normais. Restaurável.`}
          confirmLabel="Arquivar"
          confirmVariant="danger"
          onClose={() => setArchiveTarget(null)}
          onConfirm={handleArchive}
        />
      )}
      {restoreTarget && (
        <ReasonModal
          title="Restaurar reunião"
          description={`Restaurar "${restoreTarget.titulo || restoreTarget.id_reuniao}"?`}
          confirmLabel="Restaurar"
          confirmVariant="primary"
          onClose={() => setRestoreTarget(null)}
          onConfirm={handleRestore}
        />
      )}
    </div>
  );
}

/* ─── Modal de edição com bloqueio de ata ASSINADA ───────────────────────── */

function ReuniaoEditModal({
  target,
  token,
  onClose,
  onSaved,
}: {
  target: Reuniao;
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const isSigned = target.status_ata === "ASSINADA";

  const [titulo, setTitulo] = useState(target.titulo ?? "");
  const [setor, setSetor] = useState(target.setor ?? "");
  const [tipo, setTipo] = useState(target.tipo ?? "");
  const [facilitador, setFacilitador] = useState(target.facilitador_id ?? "");
  const [objetivo, setObjetivo] = useState(target.objetivo ?? "");
  const [local, setLocal] = useState(target.local ?? "");
  const [statusAta, setStatusAta] = useState(target.status_ata ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      const maybeSet = (k: string, v: string, original: string | null) => {
        if (v !== (original ?? "")) payload[k] = v;
      };
      maybeSet("titulo", titulo, target.titulo);
      maybeSet("setor", setor, target.setor);
      maybeSet("tipo", tipo, target.tipo);
      maybeSet("facilitador_id", facilitador, target.facilitador_id);
      maybeSet("objetivo", objetivo, target.objetivo);
      maybeSet("local", local, target.local);
      if (!isSigned) maybeSet("status_ata", statusAta, target.status_ata);
      if (reason.trim()) payload.reason = reason.trim();
      if (Object.keys(payload).length === 0) {
        toast("Nenhuma alteração", "info");
        onClose();
        return;
      }
      const res = await fetch(`/api/admin/reunioes/${target.id_reuniao}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        toast(`Erro: ${await res.text()}`, "error");
        return;
      }
      toast("Reunião atualizada", "success");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop z-[200] flex items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-premium-strong w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
      >
        <header className="flex items-start justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-lg font-bold text-text">Editar reunião</h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              {target.id_reuniao}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="overflow-auto px-6 py-5 space-y-4 flex-1">
          {isSigned && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg p-3 flex gap-2">
              <Lock className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                Ata <strong>ASSINADA</strong> — conteúdo da ata, status, PDF e
                evidência de assinatura são imutáveis por compliance. Apenas
                metadados periféricos podem ser alterados.
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Título">
              <input
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Setor">
              <input
                value={setor}
                onChange={(e) => setSetor(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Tipo">
              <input
                value={tipo}
                onChange={(e) => setTipo(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Facilitador (ID)">
              <input
                value={facilitador}
                onChange={(e) => setFacilitador(e.target.value)}
                className="input"
                placeholder="P001"
              />
            </Field>
            <Field label="Local">
              <input
                value={local}
                onChange={(e) => setLocal(e.target.value)}
                className="input"
              />
            </Field>
            <Field
              label={`Status ${isSigned ? "(bloqueado)" : ""}`}
              disabled={isSigned}
            >
              <select
                value={statusAta}
                onChange={(e) => setStatusAta(e.target.value)}
                disabled={isSigned}
                className="input disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Objetivo">
            <textarea
              value={objetivo}
              onChange={(e) => setObjetivo(e.target.value)}
              rows={2}
              className="input"
            />
          </Field>
          <Field label="Motivo (opcional)">
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className="input"
              placeholder="Ex: correção de facilitador"
            />
          </Field>
        </div>

        <footer className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border bg-slate-50/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-slate-200 bg-white text-text hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-primary to-primary-light text-white font-semibold shadow-md hover:shadow-lg disabled:opacity-60 inline-flex items-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Salvar
          </button>
        </footer>

        <style jsx>{`
          .input {
            width: 100%;
            padding: 0.5rem 0.75rem;
            border: 1px solid rgb(226 232 240);
            border-radius: 0.5rem;
            font-size: 0.875rem;
            outline: none;
          }
          .input:focus {
            border-color: var(--color-primary, #4f46e5);
            box-shadow: 0 0 0 1px var(--color-primary, #4f46e5);
          }
        `}</style>
      </form>
    </div>
  );
}

function Field({
  label,
  disabled,
  children,
}: {
  label: string;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`flex flex-col gap-1.5 ${disabled ? "opacity-60" : ""}`}>
      <span className="text-xs font-medium text-slate-500 uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}
