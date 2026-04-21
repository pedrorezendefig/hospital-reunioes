"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Users,
  Loader2,
  Plus,
  Search,
  Pencil,
  Trash2,
  KeyRound,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import {
  AdminUsuario,
  AdminUsuarioPayload,
  ROLE_OPTIONS,
} from "@/components/admin/types";
import { UsuarioFormModal } from "@/components/admin/UsuarioFormModal";
import { ReasonModal } from "@/components/admin/ReasonModal";
import { NewPasswordModal } from "@/components/admin/NewPasswordModal";
import { MultiSelectFilter } from "@/components/admin/MultiSelectFilter";

export default function AdminUsuariosPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<AdminUsuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [setor, setSetor] = useState<string[]>([]);
  const [setoresDisponiveis, setSetoresDisponiveis] = useState<string[]>([]);
  const [ativo, setAtivo] = useState<"" | "true" | "false">("");
  const [onlySuperAdmin, setOnlySuperAdmin] = useState<"" | "true" | "false">(
    ""
  );
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);

  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminUsuario | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUsuario | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUsuario | null>(null);
  const [generatedPwd, setGeneratedPwd] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (setor.length > 0) params.set("setor", setor.join(","));
      if (ativo) params.set("ativo", ativo);
      if (onlySuperAdmin) params.set("is_super_admin", onlySuperAdmin);
      params.set("limit", String(limit));
      params.set("offset", String(offset));

      const res = await fetch(`/api/admin/usuarios?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setRows(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar usuários", "error");
    } finally {
      setLoading(false);
    }
  }, [token, q, setor, ativo, onlySuperAdmin, limit, offset, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  // Carrega lista canonica de setores (independente dos filtros aplicados).
  useEffect(() => {
    if (authLoading || !token) return;
    fetch("/api/participantes/setores", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: string[]) =>
        setSetoresDisponiveis(Array.isArray(data) ? data : []),
      )
      .catch(() => setSetoresDisponiveis([]));
  }, [authLoading, token]);

  // ─── Handlers ───────────────────────────────────────────────────────────

  async function handleCreate(data: AdminUsuarioPayload) {
    if (!token) return;
    const res = await fetch("/api/admin/usuarios", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const msg = await res.text();
      toast(`Erro ao criar usuário: ${msg}`, "error");
      return false;
    }
    toast("Usuário criado com sucesso", "success");
    setShowCreate(false);
    fetchRows();
    return true;
  }

  async function handleEdit(data: AdminUsuarioPayload) {
    if (!token || !editTarget) return false;
    const res = await fetch(`/api/admin/usuarios/${editTarget.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      toast(`Erro ao atualizar: ${await res.text()}`, "error");
      return false;
    }
    toast("Usuário atualizado", "success");
    setEditTarget(null);
    fetchRows();
    return true;
  }

  async function handleDelete(reason: string) {
    if (!token || !deleteTarget) return false;
    const res = await fetch(`/api/admin/usuarios/${deleteTarget.id}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      toast(`Erro ao deletar: ${await res.text()}`, "error");
      return false;
    }
    toast("Usuário deletado", "success");
    setDeleteTarget(null);
    fetchRows();
    return true;
  }

  async function handleResetPassword(reason: string) {
    if (!token || !resetTarget) return false;
    const res = await fetch(
      `/api/admin/usuarios/${resetTarget.id}/reset-password`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reason }),
      }
    );
    if (!res.ok) {
      toast(`Erro ao resetar senha: ${await res.text()}`, "error");
      return false;
    }
    const data = await res.json();
    setGeneratedPwd({ email: data.email, password: data.new_password });
    setResetTarget(null);
    return true;
  }

  return (
    <div className="animate-fade-in-up space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10">
            <Users className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Usuários</h1>
            <p className="text-sm text-text-secondary">
              Gerenciamento administrativo de participantes
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" />
          Novo Usuário
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl border border-border shadow-premium p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Buscar por nome ou email…"
            value={q}
            onChange={(e) => {
              setOffset(0);
              setQ(e.target.value);
            }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <MultiSelectFilter
          allLabel="Todos os setores"
          value={setor}
          onChange={(next) => {
            setOffset(0);
            setSetor(next);
          }}
          options={setoresDisponiveis.map((s) => ({ value: s, label: s }))}
        />
        <select
          value={ativo}
          onChange={(e) => {
            setOffset(0);
            setAtivo(e.target.value as "" | "true" | "false");
          }}
          className="px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          aria-label="Filtrar por ativo"
        >
          <option value="">Ativo: todos</option>
          <option value="true">Apenas ativos</option>
          <option value="false">Apenas inativos</option>
        </select>
        <select
          value={onlySuperAdmin}
          onChange={(e) => {
            setOffset(0);
            setOnlySuperAdmin(e.target.value as "" | "true" | "false");
          }}
          className="px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          aria-label="Filtrar super admin"
        >
          <option value="">Super Admin: todos</option>
          <option value="true">Apenas super admins</option>
          <option value="false">Sem super admins</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando usuários…
          </div>
        ) : rows.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-slate-500 font-medium">
              Nenhum usuário encontrado
            </p>
            <p className="text-slate-400 text-sm mt-1">
              Ajuste os filtros ou crie um novo.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {[
                    "Nome",
                    "Email",
                    "Cargo",
                    "Setor",
                    "Role",
                    "Ativo",
                    "Super Admin",
                    "Ações",
                  ].map((h) => (
                    <th
                      key={h}
                      className="px-5 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {rows.map((u) => (
                  <tr
                    key={u.id}
                    className="hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/admin/usuarios/${u.id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {u.nome_completo}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{u.email}</td>
                    <td className="px-5 py-3 text-slate-600">
                      {u.cargo || "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {u.setor || "—"}
                    </td>
                    <td className="px-5 py-3">
                      <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 capitalize">
                        {u.role || "—"}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                          u.ativo
                            ? "bg-emerald-50 text-emerald-600"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {u.ativo ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {u.is_super_admin ? (
                        <span
                          className="inline-flex items-center gap-1 text-primary"
                          title="Super Admin"
                        >
                          <ShieldCheck className="w-4 h-4" />
                          <span className="text-xs font-medium">Super</span>
                        </span>
                      ) : (
                        <span className="text-slate-300 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditTarget(u)}
                          title="Editar"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setResetTarget(u)}
                          title="Resetar senha"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                        >
                          <KeyRound className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setDeleteTarget(u)}
                          title="Deletar"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
          <span className="text-xs text-slate-500">
            Exibindo {rows.length} — offset {offset}
          </span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
              className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            >
              Anterior
            </button>
            <button
              disabled={rows.length < limit}
              onClick={() => setOffset(offset + limit)}
              className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            >
              Próxima
            </button>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showCreate && (
        <UsuarioFormModal
          mode="create"
          roleOptions={ROLE_OPTIONS}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        />
      )}
      {editTarget && (
        <UsuarioFormModal
          mode="edit"
          initial={editTarget}
          roleOptions={ROLE_OPTIONS}
          onClose={() => setEditTarget(null)}
          onSubmit={handleEdit}
        />
      )}
      {deleteTarget && (
        <ReasonModal
          title="Deletar usuário"
          description={`Esta ação é irreversível. Informe o motivo para excluir ${deleteTarget.nome_completo}.`}
          confirmLabel="Deletar"
          confirmVariant="danger"
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
      {resetTarget && (
        <ReasonModal
          title="Resetar senha"
          description={`Uma nova senha aleatória será gerada para ${resetTarget.email}. Informe o motivo.`}
          confirmLabel="Resetar senha"
          confirmVariant="warning"
          onClose={() => setResetTarget(null)}
          onConfirm={handleResetPassword}
        />
      )}
      {generatedPwd && (
        <NewPasswordModal
          email={generatedPwd.email}
          password={generatedPwd.password}
          onClose={() => setGeneratedPwd(null)}
        />
      )}
    </div>
  );
}
