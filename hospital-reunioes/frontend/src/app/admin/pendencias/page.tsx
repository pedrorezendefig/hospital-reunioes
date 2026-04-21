"use client";

import { useCallback, useEffect, useState, FormEvent } from "react";
import {
  ListTodo,
  Search,
  Pencil,
  Archive,
  ArchiveRestore,
  X,
  Loader2,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { ReasonModal } from "@/components/admin/ReasonModal";

const PAGE_SIZE = 50;

interface Pendencia {
  id_acao: string;
  id_reuniao: string | null;
  descricao_acao: string | null;
  responsavel_id: string | null;
  responsavel_nome: string | null;
  co_responsavel_id: string | null;
  co_responsavel_nome: string | null;
  cargo: string | null;
  prazo: string | null;
  status: string | null;
  meta_entregavel: string | null;
  deleted_at: string | null;
}

type Arquivadas = "excluir" | "incluir" | "apenas";

const STATUS_OPTIONS = [
  "PENDENTE",
  "EM_PROGRESSO",
  "CONCLUIDO",
  "ATRASADO",
  "CANCELADO",
  "REPACTUADA",
];

export default function PendenciasAdminPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<Pendencia[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [arquivadas, setArquivadas] = useState<Arquivadas>("excluir");
  const [page, setPage] = useState(1);

  const [editTarget, setEditTarget] = useState<Pendencia | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Pendencia | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<Pendencia | null>(null);

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
      if (statusFilter) params.set("status", statusFilter);
      const res = await fetch(`/api/admin/pendencias?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setRows(body.data);
      setTotal(body.total);
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar pendências", "error");
    } finally {
      setLoading(false);
    }
  }, [token, q, statusFilter, arquivadas, page, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function handleArchive(reason: string) {
    if (!token || !archiveTarget) return false;
    const res = await fetch(`/api/admin/pendencias/${archiveTarget.id_acao}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      toast(`Erro ao arquivar: ${await res.text()}`, "error");
      return false;
    }
    toast("Pendência arquivada", "success");
    setArchiveTarget(null);
    await fetchRows();
    return true;
  }

  async function handleRestore(reason: string) {
    if (!token || !restoreTarget) return false;
    const res = await fetch(
      `/api/admin/pendencias/${restoreTarget.id_acao}/restore`,
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
    toast("Pendência restaurada", "success");
    setRestoreTarget(null);
    await fetchRows();
    return true;
  }

  const columns: Column<Pendencia>[] = [
    {
      key: "id_acao",
      header: "ID",
      width: "100px",
      render: (r) => (
        <span className="font-mono text-xs text-slate-500">{r.id_acao}</span>
      ),
    },
    {
      key: "descricao_acao",
      header: "Descrição",
      render: (r) => (
        <div className="max-w-md">
          <div className="text-text truncate">{r.descricao_acao || "—"}</div>
          <div className="text-xs text-slate-400">
            Reunião: {r.id_reuniao || "—"}
          </div>
        </div>
      ),
    },
    {
      key: "responsavel_nome",
      header: "Responsável",
      render: (r) => (
        <span className="text-slate-600">
          {r.responsavel_nome || r.responsavel_id || "—"}
        </span>
      ),
    },
    {
      key: "prazo",
      header: "Prazo",
      width: "120px",
      render: (r) => (
        <span className="text-slate-600 text-xs">{r.prazo || "—"}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "140px",
      render: (r) => (
        <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
          {r.status || "—"}
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
            <ListTodo className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Pendências</h1>
            <p className="text-sm text-text-secondary">
              Edição administrativa de ações e responsáveis
            </p>
          </div>
        </div>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id_acao}
        emptyState={{
          title: "Nenhuma pendência encontrada",
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
                placeholder="Buscar por descrição ou ID..."
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
        <PendenciaEditModal
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
          title="Arquivar pendência"
          description={`Arquivar "${archiveTarget.descricao_acao?.slice(0, 80) || archiveTarget.id_acao}"? Restaurável.`}
          confirmLabel="Arquivar"
          confirmVariant="danger"
          onClose={() => setArchiveTarget(null)}
          onConfirm={handleArchive}
        />
      )}
      {restoreTarget && (
        <ReasonModal
          title="Restaurar pendência"
          description={`Restaurar "${restoreTarget.descricao_acao?.slice(0, 80) || restoreTarget.id_acao}"?`}
          confirmLabel="Restaurar"
          confirmVariant="primary"
          onClose={() => setRestoreTarget(null)}
          onConfirm={handleRestore}
        />
      )}
    </div>
  );
}

function PendenciaEditModal({
  target,
  token,
  onClose,
  onSaved,
}: {
  target: Pendencia;
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();

  const [descricao, setDescricao] = useState(target.descricao_acao ?? "");
  const [statusP, setStatusP] = useState(target.status ?? "PENDENTE");
  const [respId, setRespId] = useState(target.responsavel_id ?? "");
  const [respNome, setRespNome] = useState(target.responsavel_nome ?? "");
  const [coRespId, setCoRespId] = useState(target.co_responsavel_id ?? "");
  const [coRespNome, setCoRespNome] = useState(
    target.co_responsavel_nome ?? "",
  );
  const [prazo, setPrazo] = useState(target.prazo ?? "");
  const [cargo, setCargo] = useState(target.cargo ?? "");
  const [metaEntregavel, setMetaEntregavel] = useState(
    target.meta_entregavel ?? "",
  );
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      const set = (k: string, v: string, orig: string | null) => {
        if (v !== (orig ?? "")) payload[k] = v || null;
      };
      set("descricao_acao", descricao, target.descricao_acao);
      set("status", statusP, target.status);
      set("responsavel_id", respId, target.responsavel_id);
      set("responsavel_nome", respNome, target.responsavel_nome);
      set("co_responsavel_id", coRespId, target.co_responsavel_id);
      set("co_responsavel_nome", coRespNome, target.co_responsavel_nome);
      set("prazo", prazo, target.prazo);
      set("cargo", cargo, target.cargo);
      set("meta_entregavel", metaEntregavel, target.meta_entregavel);
      if (reason.trim()) payload.reason = reason.trim();
      if (Object.keys(payload).length === 0) {
        toast("Nenhuma alteração", "info");
        onClose();
        return;
      }
      const res = await fetch(`/api/admin/pendencias/${target.id_acao}`, {
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
      toast("Pendência atualizada", "success");
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
            <h2 className="text-lg font-bold text-text">Editar pendência</h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">
              {target.id_acao} · Reunião {target.id_reuniao}
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
          <Field label="Descrição">
            <textarea
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              rows={3}
              className="input"
              required
            />
          </Field>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Status">
              <select
                value={statusP}
                onChange={(e) => setStatusP(e.target.value)}
                className="input"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Prazo">
              <input
                type="date"
                value={prazo}
                onChange={(e) => setPrazo(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Responsável (ID)">
              <input
                value={respId}
                onChange={(e) => setRespId(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Responsável (nome cache)">
              <input
                value={respNome}
                onChange={(e) => setRespNome(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Co-responsável (ID)">
              <input
                value={coRespId}
                onChange={(e) => setCoRespId(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Co-responsável (nome cache)">
              <input
                value={coRespNome}
                onChange={(e) => setCoRespNome(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Cargo">
              <input
                value={cargo}
                onChange={(e) => setCargo(e.target.value)}
                className="input"
              />
            </Field>
          </div>
          <Field label="Meta / entregável">
            <textarea
              value={metaEntregavel}
              onChange={(e) => setMetaEntregavel(e.target.value)}
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
              placeholder="Ex: correção de responsável trocado"
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
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate-500 uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}
