"use client";

import { useState, useEffect, useCallback, use } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  Pencil,
  KeyRound,
  Trash2,
  ShieldCheck,
  ScrollText,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import {
  AdminUsuario,
  AdminUsuarioDetalhe,
  AdminUsuarioPayload,
  AuditLogRow,
  ROLE_OPTIONS,
} from "@/components/admin/types";
import { UsuarioFormModal } from "@/components/admin/UsuarioFormModal";
import { ReasonModal } from "@/components/admin/ReasonModal";
import { NewPasswordModal } from "@/components/admin/NewPasswordModal";
import { useRouter } from "next/navigation";

export default function AdminUsuarioDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [detalhe, setDetalhe] = useState<AdminUsuarioDetalhe | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [generatedPwd, setGeneratedPwd] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const fetchDetalhe = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/usuarios/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setDetalhe(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar usuário", "error");
    } finally {
      setLoading(false);
    }
  }, [token, id, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchDetalhe();
  }, [authLoading, token, fetchDetalhe]);

  async function handleEdit(data: AdminUsuarioPayload) {
    if (!token) return false;
    const res = await fetch(`/api/admin/usuarios/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      toast(`Erro: ${await res.text()}`, "error");
      return false;
    }
    toast("Usuário atualizado", "success");
    setEditing(false);
    fetchDetalhe();
    return true;
  }

  async function handleDelete(reason: string) {
    if (!token) return false;
    const res = await fetch(`/api/admin/usuarios/${id}`, {
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
    router.push("/admin/usuarios");
    return true;
  }

  async function handleReset(reason: string) {
    if (!token || !detalhe) return false;
    const res = await fetch(`/api/admin/usuarios/${id}/reset-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      toast(`Erro: ${await res.text()}`, "error");
      return false;
    }
    const data = await res.json();
    setGeneratedPwd({ email: data.email, password: data.new_password });
    setResetting(false);
    return true;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  if (!detalhe) {
    return (
      <div className="animate-fade-in-up">
        <Link
          href="/admin/usuarios"
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>
        <p className="text-slate-500">Usuário não encontrado.</p>
      </div>
    );
  }

  const u: AdminUsuario = detalhe.usuario;

  return (
    <div className="animate-fade-in-up space-y-6">
      <Link
        href="/admin/usuarios"
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text"
      >
        <ArrowLeft className="w-4 h-4" />
        Voltar à lista
      </Link>

      {/* Header */}
      <div className="bg-white rounded-2xl border border-border shadow-premium p-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center text-white text-xl font-bold">
            {u.nome_completo.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 className="text-xl font-bold text-text flex items-center gap-2">
              {u.nome_completo}
              {u.is_super_admin && (
                <span
                  className="inline-flex items-center gap-1 text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-full"
                  title="Super Admin"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Super Admin
                </span>
              )}
            </h1>
            <p className="text-sm text-slate-500">{u.email}</p>
            <p className="text-xs text-slate-400 mt-0.5">
              {u.cargo || "—"} · {u.setor || "Sem setor"} · role{" "}
              <span className="capitalize">{u.role || "—"}</span>
              {!u.ativo && " · INATIVO"}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <button
            onClick={() => setEditing(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold hover:opacity-90 transition-all"
          >
            <Pencil className="w-4 h-4" />
            Editar
          </button>
          <button
            onClick={() => setResetting(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm font-semibold hover:bg-amber-100 transition-all"
          >
            <KeyRound className="w-4 h-4" />
            Resetar senha
          </button>
          <button
            onClick={() => setDeleting(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-red-50 text-red-600 text-sm font-semibold hover:bg-red-100 transition-all"
          >
            <Trash2 className="w-4 h-4" />
            Deletar
          </button>
        </div>
      </div>

      {/* Dados */}
      <div className="bg-white rounded-2xl border border-border shadow-premium p-6">
        <h2 className="text-sm font-bold text-text mb-4">Dados cadastrais</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <Info label="ID" value={u.id} mono />
          <Info label="Email" value={u.email} />
          <Info label="Cargo" value={u.cargo || "—"} />
          <Info label="Setor" value={u.setor || "—"} />
          <Info label="Área" value={u.area || "—"} />
          <Info
            label="Role"
            value={
              <span className="capitalize">{u.role || "—"}</span>
            }
          />
          <Info
            label="Externo"
            value={u.is_externo ? "Sim" : "Não"}
          />
          <Info label="Ativo" value={u.ativo ? "Sim" : "Não"} />
          <Info label="Auth user id" value={u.auth_user_id || "—"} mono />
          <Info
            label="Data cadastro"
            value={u.data_cadastro || "—"}
          />
        </div>
      </div>

      {/* Histórico */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center gap-2">
          <ScrollText className="w-4 h-4 text-text-secondary" />
          <h2 className="text-sm font-bold text-text">
            Histórico recente ({detalhe.audit_logs.length})
          </h2>
          <span className="text-xs text-slate-400 ml-auto">
            Últimos 20 registros do audit_log
          </span>
        </div>

        {detalhe.audit_logs.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-400">
            Nenhum evento registrado para este usuário.
          </div>
        ) : (
          <ul className="divide-y divide-slate-50">
            {detalhe.audit_logs.map((log) => (
              <AuditRow key={log.id} log={log} />
            ))}
          </ul>
        )}
      </div>

      {/* Modals */}
      {editing && (
        <UsuarioFormModal
          mode="edit"
          initial={u}
          roleOptions={ROLE_OPTIONS}
          onClose={() => setEditing(false)}
          onSubmit={handleEdit}
        />
      )}
      {deleting && (
        <ReasonModal
          title="Deletar usuário"
          description={`Esta ação é irreversível. Informe o motivo para excluir ${u.nome_completo}.`}
          confirmLabel="Deletar"
          confirmVariant="danger"
          onClose={() => setDeleting(false)}
          onConfirm={handleDelete}
        />
      )}
      {resetting && (
        <ReasonModal
          title="Resetar senha"
          description={`Uma nova senha será gerada para ${u.email}. Informe o motivo.`}
          confirmLabel="Resetar senha"
          confirmVariant="warning"
          onClose={() => setResetting(false)}
          onConfirm={handleReset}
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

function Info({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500 uppercase mb-0.5">
        {label}
      </p>
      <p
        className={`text-sm text-slate-700 ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function AuditRow({ log }: { log: AuditLogRow }) {
  const ts = new Date(log.timestamp);
  const label = isNaN(ts.getTime())
    ? log.timestamp
    : ts.toLocaleString("pt-BR");

  return (
    <li className="px-6 py-3 hover:bg-slate-50/60">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="inline-flex px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 uppercase tracking-wide">
              {log.action}
            </span>
            <span className="text-xs text-slate-500">
              {log.target_type} · {log.target_id}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            por {log.actor_email}
            {log.ip_address && ` · ${log.ip_address}`}
          </p>
          {log.reason && (
            <p className="text-xs text-slate-600 mt-1 italic">
              Motivo: {log.reason}
            </p>
          )}
        </div>
        <time className="text-xs text-slate-400 whitespace-nowrap">
          {label}
        </time>
      </div>
    </li>
  );
}
