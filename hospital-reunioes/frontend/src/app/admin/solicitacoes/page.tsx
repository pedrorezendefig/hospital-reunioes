"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Inbox,
  Search,
  Clock,
  CheckCircle2,
  TimerOff,
  Trash2,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { ReasonModal } from "@/components/admin/ReasonModal";

type StatusFilter = "pendente" | "confirmado" | "expirado" | "todos";

interface SignupRequest {
  id: string;
  nome_completo: string;
  email: string;
  cargo: string | null;
  area: string | null;
  setor: string | null;
  role: string | null;
  confirmado: boolean;
  expires_at: string | null;
  created_at: string;
}

interface ListResponse {
  data: SignupRequest[];
  total: number;
  page: number;
  limit: number;
}

const PAGE_SIZE = 50;

function computedStatus(row: SignupRequest): "pendente" | "confirmado" | "expirado" {
  if (row.confirmado) return "confirmado";
  if (row.expires_at) {
    try {
      if (new Date(row.expires_at).getTime() < Date.now()) return "expirado";
    } catch {
      /* ignore */
    }
  }
  return "pendente";
}

export default function SolicitacoesPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<SignupRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pendente");
  const [page, setPage] = useState(1);

  const [rejectTarget, setRejectTarget] = useState<SignupRequest | null>(null);
  const [expireTarget, setExpireTarget] = useState<SignupRequest | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        status: statusFilter,
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (q) params.set("q", q);
      const res = await fetch(
        `/api/admin/signup-requests?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(await res.text());
      const body: ListResponse = await res.json();
      setRows(body.data);
      setTotal(body.total);
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar solicitações", "error");
    } finally {
      setLoading(false);
    }
  }, [token, q, statusFilter, page, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function handleReject(reason: string) {
    if (!token || !rejectTarget) return false;
    const res = await fetch(`/api/admin/signup-requests/${rejectTarget.id}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      toast(`Erro ao rejeitar: ${await res.text()}`, "error");
      return false;
    }
    toast("Solicitação rejeitada", "success");
    setRejectTarget(null);
    await fetchRows();
    return true;
  }

  async function handleExpire(reason: string) {
    if (!token || !expireTarget) return false;
    const res = await fetch(
      `/api/admin/signup-requests/${expireTarget.id}/expire`,
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
      toast(`Erro ao expirar: ${await res.text()}`, "error");
      return false;
    }
    toast("Solicitação expirada", "success");
    setExpireTarget(null);
    await fetchRows();
    return true;
  }

  const columns: Column<SignupRequest>[] = [
    {
      key: "nome_completo",
      header: "Solicitante",
      render: (r) => (
        <div>
          <div className="font-medium text-text">{r.nome_completo}</div>
          <div className="text-xs text-slate-400">{r.email}</div>
        </div>
      ),
    },
    {
      key: "cargo",
      header: "Cargo",
      render: (r) => (
        <span className="text-slate-600">{r.cargo || "—"}</span>
      ),
    },
    {
      key: "setor",
      header: "Setor",
      render: (r) => (
        <span className="text-slate-600">{r.setor || "—"}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "140px",
      render: (r) => {
        const s = computedStatus(r);
        const config = {
          pendente: {
            label: "Pendente",
            icon: Clock,
            cls: "bg-amber-50 text-amber-700",
          },
          confirmado: {
            label: "Confirmado",
            icon: CheckCircle2,
            cls: "bg-emerald-50 text-emerald-700",
          },
          expirado: {
            label: "Expirado",
            icon: TimerOff,
            cls: "bg-slate-100 text-slate-500",
          },
        }[s];
        const Icon = config.icon;
        return (
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${config.cls}`}
          >
            <Icon className="w-3 h-3" />
            {config.label}
          </span>
        );
      },
    },
    {
      key: "created_at",
      header: "Criada em",
      width: "180px",
      render: (r) => (
        <span className="text-slate-500 text-xs">
          {new Date(r.created_at).toLocaleString("pt-BR")}
        </span>
      ),
    },
  ];

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10 text-primary">
            <Inbox className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Solicitações</h1>
            <p className="text-sm text-text-secondary">
              Cadastros pendentes de confirmação por email
            </p>
          </div>
        </div>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id}
        emptyState={{
          title: "Nenhuma solicitação",
          hint: "Ajuste os filtros para ver outros status.",
        }}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total,
          onPageChange: setPage,
        }}
        toolbar={
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar por nome ou email..."
                value={q}
                onChange={(e) => {
                  setPage(1);
                  setQ(e.target.value);
                }}
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => {
                setPage(1);
                setStatusFilter(e.target.value as StatusFilter);
              }}
              className="px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
            >
              <option value="pendente">Pendentes</option>
              <option value="confirmado">Confirmadas</option>
              <option value="expirado">Expiradas</option>
              <option value="todos">Todas</option>
            </select>
          </div>
        }
        rowActions={(r) => {
          const s = computedStatus(r);
          return (
            <>
              {s === "pendente" && (
                <button
                  onClick={() => setExpireTarget(r)}
                  title="Expirar link agora"
                  className="p-1.5 rounded-lg text-slate-500 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                >
                  <TimerOff className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => setRejectTarget(r)}
                title="Rejeitar / deletar"
                className="p-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          );
        }}
      />

      {rejectTarget && (
        <ReasonModal
          title="Rejeitar solicitação"
          description={`Deletar a solicitação de ${rejectTarget.nome_completo} (${rejectTarget.email})? Ação irreversível. Informe o motivo.`}
          confirmLabel="Rejeitar"
          confirmVariant="danger"
          onClose={() => setRejectTarget(null)}
          onConfirm={handleReject}
        />
      )}
      {expireTarget && (
        <ReasonModal
          title="Expirar solicitação"
          description={`Invalidar o link de confirmação de ${expireTarget.nome_completo}? O usuário precisará solicitar novo cadastro. Informe o motivo.`}
          confirmLabel="Expirar"
          confirmVariant="warning"
          onClose={() => setExpireTarget(null)}
          onConfirm={handleExpire}
        />
      )}
    </div>
  );
}
