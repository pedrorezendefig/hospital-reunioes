"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Plus,
  Search,
  Pencil,
  Archive,
  ArchiveRestore,
  LucideIcon,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { Select } from "@/components/ui/Select";
import { DataTable, type Column } from "@/components/admin/DataTable";
import {
  TaxonomyFormModal,
  type TaxonomyItem,
} from "@/components/admin/TaxonomyFormModal";

type AtivoFilter = "ativos" | "arquivados" | "todos";

interface Props {
  title: string;
  subtitle?: string;
  /** Endpoint base, ex: "/api/admin/setores". Sem trailing slash. */
  endpoint: string;
  /** Substantivo masculino/feminino para mensagens: "setor", "cargo", "tipo de reunião". */
  itemNoun: string;
  /** Concorda com itemNoun para mensagens femininas ("a" vs "o"). */
  itemNounArticle?: "o" | "a";
  icon?: LucideIcon;
  iconComponent?: React.ReactNode;
}

type ListResponse = {
  data: TaxonomyItem[];
  total: number;
  page: number;
  limit: number;
};

const PAGE_SIZE = 50;

export function TaxonomyPage({
  title,
  subtitle,
  endpoint,
  itemNoun,
  itemNounArticle = "o",
  icon: Icon,
  iconComponent,
}: Props) {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<TaxonomyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [ativoFilter, setAtivoFilter] = useState<AtivoFilter>("ativos");
  const [page, setPage] = useState(1);

  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<TaxonomyItem | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        ativo: ativoFilter,
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (q) params.set("q", q);
      const res = await fetch(`${endpoint}?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const body: ListResponse = await res.json();
      setRows(body.data);
      setTotal(body.total);
    } catch (e) {
      console.error(e);
      toast(`Erro ao carregar ${itemNoun}s`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, endpoint, q, ativoFilter, page, toast, itemNoun]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function handleCreate(payload: { nome: string }) {
    if (!token) return false;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro ao criar: ${msg}`, "error");
      return false;
    }
    toast(
      `${itemNounArticle === "a" ? "Nova" : "Novo"} ${itemNoun} ${
        itemNounArticle === "a" ? "criada" : "criado"
      }`,
      "success",
    );
    setShowCreate(false);
    setPage(1);
    await fetchRows();
    return true;
  }

  async function handleEdit(payload: { nome: string; ativo?: boolean }) {
    if (!token || !editTarget) return false;
    const res = await fetch(`${endpoint}/${editTarget.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro ao atualizar: ${msg}`, "error");
      return false;
    }
    toast(
      `${itemNoun.charAt(0).toUpperCase() + itemNoun.slice(1)} ${
        itemNounArticle === "a" ? "atualizada" : "atualizado"
      }`,
      "success",
    );
    setEditTarget(null);
    await fetchRows();
    return true;
  }

  async function handleArchive(item: TaxonomyItem) {
    if (!token) return;
    const acao = item.ativo ? "arquivar" : "reativar";
    if (!confirm(`Tem certeza que deseja ${acao} "${item.nome}"?`)) return;

    const method = item.ativo ? "DELETE" : "PATCH";
    const body = item.ativo ? undefined : JSON.stringify({ ativo: true });
    const res = await fetch(`${endpoint}/${item.id}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body,
    });
    if (!res.ok) {
      toast(`Erro ao ${acao}`, "error");
      return;
    }
    toast(
      item.ativo
        ? `${itemNoun.charAt(0).toUpperCase() + itemNoun.slice(1)} arquivad${
            itemNounArticle === "a" ? "a" : "o"
          }`
        : `${itemNoun.charAt(0).toUpperCase() + itemNoun.slice(1)} reativad${
            itemNounArticle === "a" ? "a" : "o"
          }`,
      "success",
    );
    await fetchRows();
  }

  const columns: Column<TaxonomyItem>[] = [
    {
      key: "nome",
      header: "Nome",
      render: (r) => <span className="font-medium text-text">{r.nome}</span>,
    },
    {
      key: "ativo",
      header: "Status",
      width: "130px",
      render: (r) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
            r.ativo
              ? "bg-emerald-50 text-emerald-600"
              : "bg-slate-100 text-slate-500"
          }`}
        >
          {r.ativo ? "Ativo" : "Arquivado"}
        </span>
      ),
    },
    {
      key: "updated_at",
      header: "Atualizado",
      width: "200px",
      render: (r) => (
        <span className="text-slate-500 text-xs">
          {new Date(r.updated_at).toLocaleString("pt-BR")}
        </span>
      ),
    },
  ];

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {(Icon || iconComponent) && (
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              {Icon ? <Icon className="w-6 h-6" /> : iconComponent}
            </div>
          )}
          <div>
            <h1 className="text-2xl font-bold text-text">{title}</h1>
            {subtitle && (
              <p className="text-sm text-text-secondary">{subtitle}</p>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" />
          {itemNounArticle === "a" ? "Nova" : "Novo"} {itemNoun}
        </button>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id}
        emptyState={{
          title: `Nenhum ${itemNoun} encontrado`,
          hint: "Ajuste os filtros ou crie um novo.",
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
                placeholder={`Buscar ${itemNoun}...`}
                value={q}
                onChange={(e) => {
                  setPage(1);
                  setQ(e.target.value);
                }}
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
            <Select
              value={ativoFilter}
              onChange={(v) => {
                setPage(1);
                setAtivoFilter(v as AtivoFilter);
              }}
              options={[
                { value: "ativos", label: "Apenas ativos" },
                { value: "arquivados", label: "Apenas arquivados" },
                { value: "todos", label: "Todos" },
              ]}
            />
          </div>
        }
        rowActions={(r) => (
          <>
            <button
              onClick={() => setEditTarget(r)}
              title="Editar"
              className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleArchive(r)}
              title={r.ativo ? "Arquivar" : "Reativar"}
              className={`p-1.5 rounded-lg transition-colors ${
                r.ativo
                  ? "text-slate-500 hover:text-red-600 hover:bg-red-50"
                  : "text-slate-500 hover:text-emerald-600 hover:bg-emerald-50"
              }`}
            >
              {r.ativo ? (
                <Archive className="w-4 h-4" />
              ) : (
                <ArchiveRestore className="w-4 h-4" />
              )}
            </button>
          </>
        )}
      />

      {showCreate && (
        <TaxonomyFormModal
          title={`${itemNounArticle === "a" ? "Nova" : "Novo"} ${itemNoun}`}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        />
      )}
      {editTarget && (
        <TaxonomyFormModal
          title={`Editar ${itemNoun}`}
          initial={editTarget}
          onClose={() => setEditTarget(null)}
          onSubmit={handleEdit}
        />
      )}
    </div>
  );
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
    return res.statusText;
  } catch {
    return res.statusText;
  }
}
