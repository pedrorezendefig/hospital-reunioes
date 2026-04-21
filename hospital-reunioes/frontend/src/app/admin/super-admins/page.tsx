"use client";

/**
 * /admin/super-admins — lista de super admins + promover/rebaixar.
 *
 * Proteção de rota é feita pelo layout `/admin/layout.tsx` (Agent 3A).
 * Esta página apenas consome os endpoints:
 *   GET  /api/admin/super-admins
 *   POST /api/admin/super-admins/{id}/promote   body: { reason }
 *   POST /api/admin/super-admins/{id}/demote    body: { reason }
 *   GET  /api/admin/usuarios?q=...              (busca para promover)
 */
import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  ShieldCheck,
  UserPlus,
  UserMinus,
  Search,
  X,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";

// ─── Types ────────────────────────────────────────────────────────────────

interface SuperAdmin {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string | null;
  setor?: string | null;
  role?: string | null;
}

interface UsuarioSearchResult {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string | null;
  setor?: string | null;
  is_super_admin?: boolean;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // ignore
  }
  return fallback;
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function SuperAdminsPage() {
  const { token, userEmail, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [superAdmins, setSuperAdmins] = useState<SuperAdmin[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal state
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [demoteTarget, setDemoteTarget] = useState<SuperAdmin | null>(null);

  const fetchSuperAdmins = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch("/api/admin/super-admins", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setSuperAdmins(await res.json());
      } else {
        toast(await parseErrorDetail(res, "Falha ao carregar super admins"), "error");
      }
    } catch {
      toast("Erro de rede ao carregar super admins", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchSuperAdmins();
  }, [authLoading, token, fetchSuperAdmins]);

  if (authLoading || (loading && superAdmins.length === 0)) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in-up pb-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-primary" />
            Super Admins
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Usuários com acesso administrativo total ao sistema.
          </p>
        </div>
        <button
          onClick={() => setPromoteOpen(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary/90 transition-colors shadow-sm"
        >
          <UserPlus className="w-4 h-4" />
          Promover usuário
        </button>
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[300px]">
        {superAdmins.length === 0 && !loading ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <ShieldCheck className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhum super admin encontrado</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Nome", "Email", "Cargo", "Setor", "Role", ""].map((h) => (
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
                {superAdmins.map((sa) => {
                  const isSelf =
                    !!userEmail && sa.email?.toLowerCase() === userEmail.toLowerCase();
                  return (
                    <tr key={sa.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-4">
                        <p className="font-medium text-slate-800">{sa.nome_completo}</p>
                        {isSelf && (
                          <p className="text-[11px] text-primary font-medium">você</p>
                        )}
                      </td>
                      <td className="px-5 py-4 text-slate-600">{sa.email}</td>
                      <td className="px-5 py-4 text-slate-600">{sa.cargo || "—"}</td>
                      <td className="px-5 py-4 text-slate-600">{sa.setor || "—"}</td>
                      <td className="px-5 py-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                          {sa.role || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <button
                          onClick={() => setDemoteTarget(sa)}
                          disabled={isSelf}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          title={
                            isSelf
                              ? "Você não pode rebaixar a si mesmo"
                              : "Rebaixar super admin"
                          }
                        >
                          <UserMinus className="w-3.5 h-3.5" />
                          Rebaixar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {promoteOpen && (
        <PromoteModal
          token={token}
          onClose={() => setPromoteOpen(false)}
          onSuccess={() => {
            setPromoteOpen(false);
            fetchSuperAdmins();
          }}
        />
      )}

      {demoteTarget && (
        <DemoteModal
          token={token}
          target={demoteTarget}
          onClose={() => setDemoteTarget(null)}
          onSuccess={() => {
            setDemoteTarget(null);
            fetchSuperAdmins();
          }}
        />
      )}
    </div>
  );
}

// ─── Promote Modal ────────────────────────────────────────────────────────

function PromoteModal({
  token,
  onClose,
  onSuccess,
}: {
  token: string | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UsuarioSearchResult[]>([]);
  const [selected, setSelected] = useState<UsuarioSearchResult | null>(null);
  const [reason, setReason] = useState("");
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const doSearch = useCallback(
    async (q: string) => {
      if (!token) return;
      const trimmed = q.trim();
      if (trimmed.length < 2) {
        setResults([]);
        return;
      }
      setSearching(true);
      try {
        const res = await fetch(
          `/api/admin/usuarios?q=${encodeURIComponent(trimmed)}&limit=15`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (res.ok) {
          const data: UsuarioSearchResult[] = await res.json();
          // Esconde quem já é super admin
          setResults(data.filter((u) => !u.is_super_admin));
        } else {
          setResults([]);
        }
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    },
    [token],
  );

  const debouncedSearch = useDebouncedCallback((q: string) => {
    doSearch(q);
  }, 300);

  useEffect(() => {
    debouncedSearch(query);
  }, [query, debouncedSearch]);

  const canSubmit = !!selected && reason.trim().length > 0 && !submitting;

  async function submit() {
    if (!selected || !token) return;
    setSubmitting(true);
    try {
      const res = await fetch(
        `/api/admin/super-admins/${selected.id}/promote`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ reason: reason.trim() }),
        },
      );
      if (res.ok) {
        toast(`${selected.nome_completo} promovido a super admin.`, "success");
        onSuccess();
      } else if (res.status === 400) {
        toast(await parseErrorDetail(res, "Não foi possível promover"), "warning");
      } else if (res.status === 404) {
        toast("Usuário não encontrado.", "error");
      } else {
        toast(await parseErrorDetail(res, "Falha ao promover"), "error");
      }
    } catch {
      toast("Erro de rede ao promover", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell onClose={onClose} title="Promover usuário a super admin">
      <div className="space-y-4">
        {/* Busca */}
        <div>
          <label className="text-xs font-medium text-slate-500 uppercase block mb-1.5">
            Usuário
          </label>
          {selected ? (
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-200">
              <div>
                <p className="font-medium text-slate-800">{selected.nome_completo}</p>
                <p className="text-xs text-slate-500">{selected.email}</p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="p-1 hover:bg-slate-200 rounded"
                aria-label="Trocar usuário"
              >
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>
          ) : (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                autoFocus
                placeholder="Digite nome ou email (mín. 2 caracteres)..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              />
              {(searching || results.length > 0) && query.trim().length >= 2 && (
                <div className="mt-1 max-h-64 overflow-y-auto border border-slate-200 rounded-lg bg-white shadow-lg">
                  {searching && (
                    <div className="px-3 py-2 text-xs text-slate-400 flex items-center gap-2">
                      <Loader2 className="w-3 h-3 animate-spin" /> Buscando...
                    </div>
                  )}
                  {!searching && results.length === 0 && (
                    <div className="px-3 py-2 text-xs text-slate-400">
                      Nenhum usuário encontrado.
                    </div>
                  )}
                  {results.map((u) => (
                    <button
                      key={u.id}
                      onClick={() => {
                        setSelected(u);
                        setResults([]);
                        setQuery("");
                      }}
                      className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b border-slate-100 last:border-b-0"
                    >
                      <p className="text-sm font-medium text-slate-800">
                        {u.nome_completo}
                      </p>
                      <p className="text-xs text-slate-500">
                        {u.email}
                        {u.setor ? ` • ${u.setor}` : ""}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Motivo */}
        <div>
          <label className="text-xs font-medium text-slate-500 uppercase block mb-1.5">
            Motivo <span className="text-red-500">*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Por que essa pessoa precisa ser super admin?"
            rows={3}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary resize-none"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Obrigatório. Será gravado no audit log.
          </p>
        </div>

        <ModalActions
          onCancel={onClose}
          onConfirm={submit}
          confirmLabel="Promover"
          disabled={!canSubmit}
          submitting={submitting}
        />
      </div>
    </ModalShell>
  );
}

// ─── Demote Modal ─────────────────────────────────────────────────────────

function DemoteModal({
  token,
  target,
  onClose,
  onSuccess,
}: {
  token: string | null;
  target: SuperAdmin;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { toast } = useToast();
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = reason.trim().length > 0 && !submitting;

  async function submit() {
    if (!token) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/admin/super-admins/${target.id}/demote`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ reason: reason.trim() }),
      });
      if (res.ok) {
        toast(`${target.nome_completo} rebaixado.`, "success");
        onSuccess();
      } else if (res.status === 400) {
        toast(
          await parseErrorDetail(res, "Não foi possível rebaixar"),
          "warning",
        );
      } else if (res.status === 404) {
        toast("Usuário não encontrado.", "error");
      } else {
        toast(await parseErrorDetail(res, "Falha ao rebaixar"), "error");
      }
    } catch {
      toast("Erro de rede ao rebaixar", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell onClose={onClose} title="Rebaixar super admin">
      <div className="space-y-4">
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
          <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-700">
            <p className="font-medium">
              {target.nome_completo} perderá acesso administrativo.
            </p>
            <p className="mt-0.5">
              Visibilidade global, CRUD admin, audit logs e ações destrutivas
              deixarão de funcionar.
            </p>
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-slate-500 uppercase block mb-1.5">
            Motivo <span className="text-red-500">*</span>
          </label>
          <textarea
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Por que remover o acesso?"
            rows={3}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary resize-none"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Obrigatório. Será gravado no audit log.
          </p>
        </div>

        <ModalActions
          onCancel={onClose}
          onConfirm={submit}
          confirmLabel="Rebaixar"
          destructive
          disabled={!canSubmit}
          submitting={submitting}
        />
      </div>
    </ModalShell>
  );
}

// ─── Modal primitives ─────────────────────────────────────────────────────

function ModalShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="modal-backdrop z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-100 rounded-lg"
            aria-label="Fechar"
          >
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function ModalActions({
  onCancel,
  onConfirm,
  confirmLabel,
  disabled,
  submitting,
  destructive,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  disabled?: boolean;
  submitting?: boolean;
  destructive?: boolean;
}) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
      >
        Cancelar
      </button>
      <button
        type="button"
        onClick={onConfirm}
        disabled={disabled}
        className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
          destructive
            ? "bg-red-600 hover:bg-red-700"
            : "bg-primary hover:bg-primary/90"
        }`}
      >
        {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {confirmLabel}
      </button>
    </div>
  );
}
