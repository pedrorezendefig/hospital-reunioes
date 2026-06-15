"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Loader2,
  GitMerge,
  UserCheck,
  Search,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { AdminUsuario, ROLE_OPTIONS } from "./types";
import { UserRole } from "@/types";
import { AdminModal } from "./AdminModal";
import { AutocompleteInput } from "@/components/ui/AutocompleteInput";

interface Props {
  externo: AdminUsuario;
  setoresDisponiveis?: string[];
  cargosDisponiveis?: string[];
  onClose: () => void;
  /** Chamado apos merge ou promote com sucesso — caller recarrega a lista. */
  onResolved: () => void;
}

type Tab = "merge" | "promote";

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors";

/**
 * Modal do Resolver: duas tabs, cada uma executa uma estrategia
 * distinta de "corrigir um externo".
 *
 * - Merge (M): externo e duplicata de um interno existente — transfere
 *   todas as FKs via RPC e deleta o externo.
 * - Promote (P): externo e pessoa nova que deve virar interno — marca
 *   is_externo=false, ativo=true, preenche dados faltantes. Envio de
 *   senha/convite fica separado (usar Resetar senha depois).
 */
export function ResolverExternoModal({
  externo,
  setoresDisponiveis,
  cargosDisponiveis,
  onClose,
  onResolved,
}: Props) {
  const [tab, setTab] = useState<Tab>("merge");
  const [submitting, setSubmitting] = useState(false);

  return (
    <AdminModal
      open
      onClose={onClose}
      title="Resolver participante externo"
      description={`${externo.nome_completo}${externo.email ? ` · ${externo.email}` : ""}`}
      size="lg"
      scrollable
    >
      <div className="-mx-6 -my-5 flex flex-col">
        <div className="flex border-b border-border bg-slate-50/50">
          <TabButton
            active={tab === "merge"}
            onClick={() => setTab("merge")}
            icon={GitMerge}
            label="Mesclar com interno"
            hint="É a mesma pessoa que outro interno já cadastrado"
          />
          <TabButton
            active={tab === "promote"}
            onClick={() => setTab("promote")}
            icon={UserCheck}
            label="Promover a interno"
            hint="É uma pessoa nova que deve virar interno"
          />
        </div>

        <div className="flex-1">
          {tab === "merge" ? (
            <MergeTab
              externo={externo}
              submitting={submitting}
              setSubmitting={setSubmitting}
              onResolved={onResolved}
            />
          ) : (
            <PromoteTab
              externo={externo}
              setoresDisponiveis={setoresDisponiveis}
              cargosDisponiveis={cargosDisponiveis}
              submitting={submitting}
              setSubmitting={setSubmitting}
              onResolved={onResolved}
            />
          )}
        </div>
      </div>
    </AdminModal>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof GitMerge;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-6 py-4 text-left transition-colors ${
        active
          ? "bg-white border-b-2 border-primary text-primary"
          : "text-text-secondary hover:bg-slate-100 border-b-2 border-transparent"
      }`}
    >
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4" />
        <span className="font-semibold text-sm">{label}</span>
      </div>
      <p className="text-xs text-slate-400 mt-1">{hint}</p>
    </button>
  );
}

/* ─── Merge tab ─────────────────────────────────────────────────────────── */

function MergeTab({
  externo,
  submitting,
  setSubmitting,
  onResolved,
}: {
  externo: AdminUsuario;
  submitting: boolean;
  setSubmitting: (v: boolean) => void;
  onResolved: () => void;
}) {
  const { token } = useAuth();
  const { toast } = useToast();

  const [q, setQ] = useState("");
  const [results, setResults] = useState<AdminUsuario[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<AdminUsuario | null>(null);
  const [reason, setReason] = useState("");

  // Debounced search de internos.
  useEffect(() => {
    if (!token || !q.trim() || q.trim().length < 2) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const params = new URLSearchParams({
          q: q.trim(),
          is_externo: "false",
          limit: "10",
        });
        const res = await fetch(`/api/admin/usuarios?${params}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: ctrl.signal,
        });
        if (res.ok) {
          const body: AdminUsuario[] = await res.json();
          setResults(body.filter((u) => u.id !== externo.id));
        }
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => {
      ctrl.abort();
      clearTimeout(t);
    };
  }, [token, q, externo.id]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !selected || !reason.trim() || submitting) return;
    if (
      !confirm(
        `Mesclar "${externo.nome_completo}" em "${selected.nome_completo}"? ` +
          "Isso transfere todas as referências (reuniões, pendências, menções, notificações) e deleta o externo. Ação irreversível.",
      )
    )
      return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/admin/usuarios/${externo.id}/merge`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          interno_id: selected.id,
          reason: reason.trim(),
        }),
      });
      if (!res.ok) {
        const msg = await parseErrorMessage(res);
        toast(`Erro ao mesclar: ${msg}`, "error");
        return;
      }
      const body = await res.json();
      const totalMoves =
        body.reuniao_participantes_moved +
        body.pendencias_responsavel +
        body.pendencias_co_responsavel +
        body.comentarios_autor +
        body.comentarios_mencoes +
        body.notificacoes;
      toast(
        `Mesclado em ${selected.nome_completo}. ${totalMoves} referências transferidas.`,
        "success",
      );
      onResolved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-6 space-y-4">
      <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg p-3 flex gap-2">
        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          Ao mesclar, todas as reuniões, pendências, comentários, menções e
          notificações do externo serão transferidas para o interno escolhido,
          e o externo será <strong>deletado</strong>. Ação irreversível.
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">
          Buscar interno
        </label>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSelected(null);
            }}
            placeholder="Digite nome ou email (min. 2 chars)"
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          />
          {searching && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-slate-400" />
          )}
        </div>
        {q.trim().length >= 2 && results.length > 0 && !selected && (
          <ul className="mt-2 max-h-40 overflow-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
            {results.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setSelected(r)}
                  className="w-full text-left px-3 py-2 hover:bg-slate-50"
                >
                  <div className="text-sm font-medium text-text">
                    {r.nome_completo}
                  </div>
                  <div className="text-xs text-slate-400">
                    {r.email} · {r.setor || "-"} · {r.cargo || "-"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {q.trim().length >= 2 && !searching && results.length === 0 && !selected && (
          <p className="text-xs text-slate-400 mt-2">
            Nenhum interno encontrado com este termo.
          </p>
        )}
      </div>

      {selected && (
        <div className="border border-primary/30 bg-primary/5 rounded-lg p-3">
          <div className="text-xs text-slate-500 uppercase font-semibold mb-1">
            Será mesclado em
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-text">
                {selected.nome_completo}
              </div>
              <div className="text-xs text-slate-500">
                {selected.email} · {selected.setor || "-"}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-xs text-slate-500 hover:text-primary"
            >
              Trocar
            </button>
          </div>
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">
          Motivo (obrigatório)
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder="Ex: mesma pessoa, variação ortográfica ignorada pelo resolver STT"
          className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          required
        />
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        <button
          type="submit"
          disabled={!selected || !reason.trim() || submitting}
          className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-primary to-primary-light text-white font-semibold shadow-md hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          <GitMerge className="w-4 h-4" />
          Mesclar
        </button>
      </div>
    </form>
  );
}

/* ─── Promote tab ───────────────────────────────────────────────────────── */

function PromoteTab({
  externo,
  setoresDisponiveis,
  cargosDisponiveis,
  submitting,
  setSubmitting,
  onResolved,
}: {
  externo: AdminUsuario;
  setoresDisponiveis?: string[];
  cargosDisponiveis?: string[];
  submitting: boolean;
  setSubmitting: (v: boolean) => void;
  onResolved: () => void;
}) {
  const { token } = useAuth();
  const { toast } = useToast();

  const [email, setEmail] = useState(externo.email ?? "");
  const [cargo, setCargo] = useState(externo.cargo ?? "");
  const [setor, setSetor] = useState(externo.setor ?? "");
  const [role, setRole] = useState<UserRole>(
    (externo.role as UserRole) ?? "coordenador",
  );
  const [reason, setReason] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/admin/usuarios/${externo.id}/promote`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: email.trim() || undefined,
          cargo: cargo.trim() || undefined,
          setor: setor.trim() || undefined,
          role,
          reason: reason.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const msg = await parseErrorMessage(res);
        toast(`Erro ao promover: ${msg}`, "error");
        return;
      }
      toast(
        `${externo.nome_completo} promovido(a) a interno. Use 'Resetar senha' para enviar acesso.`,
        "success",
      );
      onResolved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-6 space-y-4">
      <div className="bg-blue-50 border border-blue-200 text-blue-800 text-xs rounded-lg p-3 flex gap-2">
        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          Promover marca o participante como interno (is_externo=false, ativo).
          Depois, use <strong>Resetar senha</strong> no menu de ações para
          gerar/enviar a senha de acesso.
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Email" required>
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={INPUT_CLASS}
          />
        </Field>
        <Field label="Role">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className={`${INPUT_CLASS} capitalize`}
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Cargo" required>
          <AutocompleteInput
            value={cargo}
            onChange={setCargo}
            options={cargosDisponiveis ?? []}
            placeholder="Selecione ou digite"
            required
            className={INPUT_CLASS}
          />
        </Field>
        <Field label="Setor">
          <AutocompleteInput
            value={setor}
            onChange={setSetor}
            options={setoresDisponiveis ?? []}
            placeholder="Selecione ou digite"
            className={INPUT_CLASS}
          />
        </Field>
      </div>

      <Field label="Motivo (opcional)">
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          className={`${INPUT_CLASS} resize-none`}
          placeholder="Ex: funcionária nova identificada em ata de fev/2026"
        />
      </Field>

      <div className="flex items-center justify-end gap-2 pt-2">
        <button
          type="submit"
          disabled={!email.trim() || !cargo.trim() || submitting}
          className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-primary to-primary-light text-white font-semibold shadow-md hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          <UserCheck className="w-4 h-4" />
          Promover
        </button>
      </div>
    </form>
  );
}

/* ─── Helpers ───────────────────────────────────────────────────────────── */

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate-500 uppercase">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      {children}
    </label>
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
