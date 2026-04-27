"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CalendarDays,
  Search,
  Pencil,
  Archive,
  ArchiveRestore,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { ReasonModal } from "@/components/admin/ReasonModal";
import { ReuniaoEditModal } from "@/components/admin/ReuniaoEditModal";

const PAGE_SIZE = 50;

interface Reuniao {
  id_reuniao: string;
  data: string | null;
  titulo: string | null;
  tipo: string | null;
  setor: string | null;
  facilitador_id: string | null;
  objetivo: string | null;
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
                placeholder="Buscar por título, ID ou pauta..."
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
