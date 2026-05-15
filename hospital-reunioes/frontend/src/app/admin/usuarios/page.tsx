"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Users,
  Loader2,
  Plus,
  Search,
  Pencil,
  Trash2,
  KeyRound,
  ShieldCheck,
  ShieldOff,
  GitMerge,
  AlertTriangle,
  LogIn,
  WifiOff,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { createClient } from "@/lib/supabase/client";
import { getErrorMessage } from "@/lib/errors";
import {
  AdminUsuario,
  AdminUsuarioPayload,
  ROLE_OPTIONS,
} from "@/components/admin/types";
import { UsuarioFormModal } from "@/components/admin/UsuarioFormModal";
import { ReasonModal } from "@/components/admin/ReasonModal";
import { NewPasswordModal } from "@/components/admin/NewPasswordModal";
import { MultiSelectFilter } from "@/components/admin/MultiSelectFilter";
import { ResolverExternoModal } from "@/components/admin/ResolverExternoModal";

type FetchError =
  | { kind: "unauthorized" }
  | { kind: "forbidden" }
  | { kind: "server"; status: number; message: string }
  | { kind: "network"; message: string };

export default function AdminUsuariosPage() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const router = useRouter();

  const [rows, setRows] = useState<AdminUsuario[]>([]);
  const [error, setError] = useState<FetchError | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [setor, setSetor] = useState<string[]>([]);
  const [setoresDisponiveis, setSetoresDisponiveis] = useState<string[]>([]);
  const [cargosDisponiveis, setCargosDisponiveis] = useState<string[]>([]);
  const [ativo, setAtivo] = useState<"" | "true" | "false">("");
  const [onlySuperAdmin, setOnlySuperAdmin] = useState<"" | "true" | "false">(
    ""
  );
  const [tipoFilter, setTipoFilter] = useState<"" | "internos" | "externos">(
    ""
  );
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);

  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminUsuario | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUsuario | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUsuario | null>(null);
  const [resolverTarget, setResolverTarget] = useState<AdminUsuario | null>(
    null
  );
  const [grantSuperTarget, setGrantSuperTarget] = useState<AdminUsuario | null>(
    null
  );
  const [revokeSuperTarget, setRevokeSuperTarget] = useState<AdminUsuario | null>(
    null
  );
  const [generatedPwd, setGeneratedPwd] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (setor.length > 0) params.set("setor", setor.join(","));
    if (ativo) params.set("ativo", ativo);
    if (onlySuperAdmin) params.set("is_super_admin", onlySuperAdmin);
    if (tipoFilter === "externos") params.set("is_externo", "true");
    else if (tipoFilter === "internos") params.set("is_externo", "false");
    params.set("limit", String(limit));
    params.set("offset", String(offset));

    const url = `/api/admin/usuarios?${params.toString()}`;
    const filtersSnapshot = {
      q,
      setor,
      ativo,
      is_super_admin: onlySuperAdmin,
      tipo: tipoFilter,
      limit,
      offset,
    };

    let res: Response;
    try {
      res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      const message = getErrorMessage(e);
      console.error("[admin/usuarios] network error", { url, message });
      setError({ kind: "network", message });
      setRows([]);
      setLoading(false);
      return;
    }

    let raw = "";
    try {
      raw = await res.text();
    } catch {
      raw = "";
    }

    if (!res.ok) {
      console.error("[admin/usuarios] fetch failed", {
        status: res.status,
        url,
        body: raw.slice(0, 500),
      });
      if (res.status === 401) {
        setError({ kind: "unauthorized" });
      } else if (res.status === 403) {
        setError({ kind: "forbidden" });
      } else {
        setError({
          kind: "server",
          status: res.status,
          message: raw.slice(0, 500) || res.statusText,
        });
      }
      setRows([]);
      setLoading(false);
      return;
    }

    try {
      const parsed: AdminUsuario[] = JSON.parse(raw);
      setRows(parsed);
      console.debug("[admin/usuarios] fetch ok", {
        status: res.status,
        count: parsed.length,
        filters: filtersSnapshot,
      });
    } catch (e) {
      const message = getErrorMessage(e);
      console.error("[admin/usuarios] parse failed", { message, raw: raw.slice(0, 500) });
      setError({
        kind: "server",
        status: res.status,
        message: `Resposta inválida: ${message}`,
      });
      setRows([]);
    }
    setLoading(false);
  }, [token, q, setor, ativo, onlySuperAdmin, tipoFilter, limit, offset]);

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

  // Carrega lista canonica de cargos (tabela cargos, Fase 1 super-admin CRUD).
  useEffect(() => {
    if (authLoading || !token) return;
    fetch("/api/admin/cargos?ativo=ativos&limit=200", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : { data: [] }))
      .then((body: { data?: { nome: string }[] }) => {
        const nomes = (body?.data ?? []).map((c) => c.nome);
        setCargosDisponiveis(nomes);
      })
      .catch(() => setCargosDisponiveis([]));
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

  async function handleGrantSuper(reason: string) {
    if (!token || !grantSuperTarget) return false;
    const res = await fetch(
      `/api/admin/usuarios/${grantSuperTarget.id}/grant-super-admin`,
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
      toast(`Erro ao conceder super admin: ${await res.text()}`, "error");
      return false;
    }
    toast("Super admin concedido", "success");
    setGrantSuperTarget(null);
    fetchRows();
    return true;
  }

  async function handleRevokeSuper(reason: string) {
    if (!token || !revokeSuperTarget) return false;
    const res = await fetch(
      `/api/admin/usuarios/${revokeSuperTarget.id}/revoke-super-admin`,
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
      toast(`Erro ao revogar super admin: ${await res.text()}`, "error");
      return false;
    }
    toast("Super admin revogado", "success");
    setRevokeSuperTarget(null);
    fetchRows();
    return true;
  }

  async function handleRelogin() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.refresh();
    router.push("/login");
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
      <div className="bg-white rounded-2xl border border-border shadow-premium p-4 grid grid-cols-1 md:grid-cols-5 gap-3">
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
          value={tipoFilter}
          onChange={(e) => {
            setOffset(0);
            setTipoFilter(e.target.value as "" | "internos" | "externos");
          }}
          className="px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          aria-label="Filtrar por tipo"
        >
          <option value="">Tipo: todos</option>
          <option value="internos">Apenas internos</option>
          <option value="externos">Apenas externos</option>
        </select>
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
        ) : error ? (
          <ErrorBanner
            error={error}
            onRetry={fetchRows}
            onRelogin={handleRelogin}
          />
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
                    "Perfil",
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
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/admin/usuarios/${u.id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {u.nome_completo || "—"}
                        </Link>
                        {u.is_externo && (
                          <span
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200"
                            title="Participante externo (criado pelo resolver STT)"
                          >
                            EXTERNO
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{u.email || "—"}</td>
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
                      {(() => {
                        const ap = u.access_profile
                          || (u.is_super_admin ? "super_admin" : "regular");
                        if (ap === "super_admin") {
                          return (
                            <span
                              className="inline-flex items-center gap-1 text-primary"
                              title="Super Admin"
                            >
                              <ShieldCheck className="w-4 h-4" />
                              <span className="text-xs font-medium">Super Admin</span>
                            </span>
                          );
                        }
                        if (ap === "secretaria") {
                          return (
                            <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700">
                              Secretária
                            </span>
                          );
                        }
                        return (
                          <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                            Regular
                          </span>
                        );
                      })()}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1">
                        {u.is_externo && (
                          <button
                            onClick={() => setResolverTarget(u)}
                            title="Resolver externo (mesclar ou promover)"
                            className="p-1.5 rounded-lg text-amber-600 hover:text-amber-700 hover:bg-amber-50 transition-colors"
                          >
                            <GitMerge className="w-4 h-4" />
                          </button>
                        )}
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
                        {u.is_super_admin ? (
                          <button
                            onClick={() => setRevokeSuperTarget(u)}
                            title="Revogar super admin"
                            className="p-1.5 rounded-lg text-primary hover:text-red-600 hover:bg-red-50 transition-colors"
                          >
                            <ShieldOff className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => setGrantSuperTarget(u)}
                            title="Tornar super admin"
                            className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
                          >
                            <ShieldCheck className="w-4 h-4" />
                          </button>
                        )}
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
          setoresDisponiveis={setoresDisponiveis}
          cargosDisponiveis={cargosDisponiveis}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        />
      )}
      {editTarget && (
        <UsuarioFormModal
          mode="edit"
          initial={editTarget}
          roleOptions={ROLE_OPTIONS}
          setoresDisponiveis={setoresDisponiveis}
          cargosDisponiveis={cargosDisponiveis}
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
      {resolverTarget && (
        <ResolverExternoModal
          externo={resolverTarget}
          setoresDisponiveis={setoresDisponiveis}
          cargosDisponiveis={cargosDisponiveis}
          onClose={() => setResolverTarget(null)}
          onResolved={() => {
            setResolverTarget(null);
            fetchRows();
          }}
        />
      )}
      {grantSuperTarget && (
        <ReasonModal
          title="Tornar super admin"
          description={`Conceder permissões de super admin a ${grantSuperTarget.nome_completo}? Informe o motivo.`}
          confirmLabel="Conceder"
          confirmVariant="primary"
          onClose={() => setGrantSuperTarget(null)}
          onConfirm={handleGrantSuper}
        />
      )}
      {revokeSuperTarget && (
        <ReasonModal
          title="Revogar super admin"
          description={`Revogar permissões de super admin de ${revokeSuperTarget.nome_completo}? Informe o motivo.`}
          confirmLabel="Revogar"
          confirmVariant="danger"
          onClose={() => setRevokeSuperTarget(null)}
          onConfirm={handleRevokeSuper}
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

function ErrorBanner({
  error,
  onRetry,
  onRelogin,
}: {
  error: FetchError;
  onRetry: () => void;
  onRelogin: () => void;
}) {
  if (error.kind === "unauthorized") {
    return (
      <div className="p-8 text-center space-y-4">
        <div className="inline-flex p-3 rounded-2xl bg-red-50">
          <LogIn className="w-6 h-6 text-red-500" />
        </div>
        <div>
          <p className="text-base font-semibold text-text">Sessão expirada</p>
          <p className="text-sm text-slate-500 mt-1">
            Seu token de acesso expirou. Faça login novamente para continuar.
          </p>
        </div>
        <button
          onClick={onRelogin}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <LogIn className="w-4 h-4" />
          Fazer login
        </button>
      </div>
    );
  }

  if (error.kind === "forbidden") {
    return (
      <div className="p-8 text-center space-y-4">
        <div className="inline-flex p-3 rounded-2xl bg-amber-50">
          <AlertTriangle className="w-6 h-6 text-amber-600" />
        </div>
        <div>
          <p className="text-base font-semibold text-text">Acesso negado</p>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            Sua conta não tem permissão de super admin para acessar este recurso.
            Fale com um administrador para verificar a flag <code className="px-1 py-0.5 rounded bg-slate-100 text-slate-700 text-xs">is_super_admin</code>.
          </p>
        </div>
      </div>
    );
  }

  if (error.kind === "network") {
    return (
      <div className="p-8 text-center space-y-4">
        <div className="inline-flex p-3 rounded-2xl bg-slate-100">
          <WifiOff className="w-6 h-6 text-slate-500" />
        </div>
        <div>
          <p className="text-base font-semibold text-text">Sem conexão com o servidor</p>
          <p className="text-sm text-slate-500 mt-1">
            Não foi possível alcançar o backend. Verifique sua conexão e tente novamente.
          </p>
          <p className="text-xs text-slate-400 mt-2 font-mono">{error.message}</p>
        </div>
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-text text-sm font-medium hover:bg-slate-50"
        >
          <RefreshCw className="w-4 h-4" />
          Tentar novamente
        </button>
      </div>
    );
  }

  // error.kind === "server"
  return (
    <div className="p-8 text-center space-y-4">
      <div className="inline-flex p-3 rounded-2xl bg-red-50">
        <AlertTriangle className="w-6 h-6 text-red-500" />
      </div>
      <div>
        <p className="text-base font-semibold text-text">
          Erro do servidor ({error.status})
        </p>
        <p className="text-sm text-slate-500 mt-1 max-w-lg mx-auto">
          {error.message.slice(0, 200) || "Erro sem detalhes do backend."}
        </p>
      </div>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-text text-sm font-medium hover:bg-slate-50"
      >
        <RefreshCw className="w-4 h-4" />
        Tentar novamente
      </button>
      {error.message.length > 200 && (
        <details className="text-xs text-slate-500 max-w-lg mx-auto">
          <summary className="cursor-pointer select-none">
            Ver resposta completa
          </summary>
          <pre className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded-lg text-left overflow-auto font-mono whitespace-pre-wrap break-all">
            {error.message}
          </pre>
        </details>
      )}
    </div>
  );
}
