"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, KeyRound, Search, UserMinus, UserPlus, Users, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { PERFIL_POP_LABELS, type PerfilPop } from "@/types";
import type { PopsSetor } from "@/components/pops/SetoresManager";

type PopsUsuario = {
  id: string;
  nome_completo: string | null;
  email: string | null;
  perfil_pop: PerfilPop | null;
  auth_user_id: string | null;
  ativo: boolean;
};

const PERFIS: PerfilPop[] = ["superadmin", "gestor_qualidade", "gerente", "coordenador"];

/**
 * Acesso ao contexto POPs (Superadmin): conceder/revogar perfil POP e gerir
 * os vínculos pessoa↔Setor. Conceder a quem não loga provisiona o login —
 * a senha gerada é exibida uma única vez.
 */
export function UsuariosPopsManager() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<PopsUsuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [showConceder, setShowConceder] = useState(false);
  const [setoresAlvo, setSetoresAlvo] = useState<PopsUsuario | null>(null);
  const [senhaGerada, setSenhaGerada] = useState<{ email: string; senha: string } | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch("/api/pops/admin/usuarios?com_perfil=true", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setRows(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar usuários do POPs", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function definirPerfil(
    participanteId: string,
    perfil: PerfilPop | null,
    email?: string | null,
  ): Promise<boolean> {
    if (!token) return false;
    const res = await fetch(`/api/pops/admin/usuarios/${participanteId}/perfil-pop`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ perfil_pop: perfil }),
    });
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro: ${msg}`, "error");
      return false;
    }
    const body = (await res.json()) as { new_password: string | null };
    if (body.new_password) {
      setSenhaGerada({ email: email ?? "", senha: body.new_password });
    }
    toast(perfil ? "Perfil POP atualizado" : "Perfil POP revogado", "success");
    await fetchRows();
    return true;
  }

  async function revogar(u: PopsUsuario) {
    if (
      !confirm(
        `Revogar o perfil POP de "${u.nome_completo}"? A pessoa perde o acesso ao contexto POPs.`,
      )
    )
      return;
    await definirPerfil(u.id, null);
  }

  const columns: Column<PopsUsuario>[] = [
    {
      key: "nome_completo",
      header: "Nome",
      render: (r) => (
        <div>
          <span className="font-medium text-text">{r.nome_completo}</span>
          <div className="text-xs text-slate-500">{r.email}</div>
        </div>
      ),
    },
    {
      key: "perfil_pop",
      header: "Perfil POP",
      width: "200px",
      render: (r) => (
        <select
          value={r.perfil_pop ?? ""}
          onChange={(e) => definirPerfil(r.id, e.target.value as PerfilPop, r.email)}
          className="px-2 py-1 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary bg-white"
          aria-label={`Perfil POP de ${r.nome_completo}`}
        >
          {PERFIS.map((p) => (
            <option key={p} value={p}>
              {PERFIL_POP_LABELS[p]}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: "auth_user_id",
      header: "Login",
      width: "110px",
      render: (r) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
            r.auth_user_id ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600"
          }`}
        >
          {r.auth_user_id ? "Ativo" : "Sem login"}
        </span>
      ),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-5 h-5 text-primary" />
          <div>
            <h2 className="text-lg font-bold text-text">Acesso ao POPs</h2>
            <p className="text-xs text-text-secondary">
              Perfis do contexto POPs e vínculos de Setor. Conceder a quem não loga cria o acesso.
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowConceder(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <UserPlus className="w-4 h-4" />
          Conceder perfil
        </button>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id}
        emptyState={{
          title: "Ninguém tem perfil POP ainda",
          hint: "Use “Conceder perfil” para dar acesso ao contexto POPs.",
        }}
        rowActions={(r) => (
          <>
            <button
              onClick={() => setSetoresAlvo(r)}
              title="Setores da pessoa"
              className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
            >
              <Building2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => revogar(r)}
              title="Revogar perfil POP"
              className="p-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 transition-colors"
            >
              <UserMinus className="w-4 h-4" />
            </button>
          </>
        )}
      />

      {showConceder && (
        <ConcederPerfilModal
          token={token}
          onClose={() => setShowConceder(false)}
          onConceder={async (pessoa, perfil) => {
            const ok = await definirPerfil(pessoa.id, perfil, pessoa.email);
            if (ok) setShowConceder(false);
          }}
        />
      )}

      {setoresAlvo && (
        <VinculosSetorModal
          token={token}
          usuario={setoresAlvo}
          onClose={() => setSetoresAlvo(null)}
        />
      )}

      {senhaGerada && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-bold text-text">Login provisionado</h3>
            </div>
            <p className="text-sm text-text-secondary">
              A pessoa agora pode entrar com <strong>{senhaGerada.email}</strong> e a senha
              abaixo. Anote: ela é exibida <strong>uma única vez</strong>.
            </p>
            <code className="block bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono break-all">
              {senhaGerada.senha}
            </code>
            <div className="flex justify-end">
              <button
                onClick={() => setSenhaGerada(null)}
                className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold"
              >
                Entendi
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ConcederPerfilModal({
  token,
  onClose,
  onConceder,
}: {
  token: string | null;
  onClose: () => void;
  onConceder: (pessoa: PopsUsuario, perfil: PerfilPop) => Promise<void>;
}) {
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<PopsUsuario[]>([]);
  const [pessoa, setPessoa] = useState<PopsUsuario | null>(null);
  const [perfil, setPerfil] = useState<PerfilPop>("coordenador");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!token || q.trim().length < 2) {
      setResultados([]);
      return;
    }
    const handle = setTimeout(async () => {
      const res = await fetch(
        `/api/pops/admin/usuarios?q=${encodeURIComponent(q.trim())}&com_perfil=false`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.ok) setResultados(await res.json());
    }, 300);
    return () => clearTimeout(handle);
  }, [q, token]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-text">Conceder perfil POP</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {!pessoa ? (
          <div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar pessoa por nome ou email…"
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                autoFocus
              />
            </div>
            <div className="mt-2 max-h-56 overflow-y-auto divide-y divide-slate-100">
              {resultados.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setPessoa(r)}
                  className="w-full text-left px-3 py-2 hover:bg-primary/5 rounded-lg"
                >
                  <div className="text-sm font-medium text-text">{r.nome_completo}</div>
                  <div className="text-xs text-slate-500">
                    {r.email ?? "sem email"} · {r.auth_user_id ? "já loga" : "sem login (será provisionado)"}
                  </div>
                </button>
              ))}
              {q.trim().length >= 2 && resultados.length === 0 && (
                <p className="text-sm text-slate-400 px-3 py-2">Ninguém encontrado.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-slate-50 rounded-lg px-3 py-2">
              <div className="text-sm font-medium text-text">{pessoa.nome_completo}</div>
              <div className="text-xs text-slate-500">{pessoa.email}</div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Perfil</label>
              <select
                value={perfil}
                onChange={(e) => setPerfil(e.target.value as PerfilPop)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary bg-white"
              >
                {PERFIS.map((p) => (
                  <option key={p} value={p}>
                    {PERFIL_POP_LABELS[p]}
                  </option>
                ))}
              </select>
            </div>
            {!pessoa.auth_user_id && (
              <p className="text-xs text-amber-600">
                Esta pessoa não loga hoje. O login será provisionado automaticamente e a
                senha, exibida uma única vez.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setPessoa(null)}
                className="px-4 py-2 rounded-xl text-sm font-medium text-text-secondary hover:bg-slate-100"
              >
                Voltar
              </button>
              <button
                disabled={saving}
                onClick={async () => {
                  setSaving(true);
                  await onConceder(pessoa, perfil);
                  setSaving(false);
                }}
                className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
              >
                {saving ? "Concedendo…" : "Conceder"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function VinculosSetorModal({
  token,
  usuario,
  onClose,
}: {
  token: string | null;
  usuario: PopsUsuario;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const [setores, setSetores] = useState<PopsSetor[]>([]);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const [resSetores, resVinculos] = await Promise.all([
          fetch("/api/pops/setores", {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`/api/pops/admin/usuarios/${usuario.id}/setores`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);
        if (resSetores.ok) setSetores(await resSetores.json());
        if (resVinculos.ok) {
          const vinculados = (await resVinculos.json()) as PopsSetor[];
          setSelecionados(new Set(vinculados.map((s) => s.id)));
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [token, usuario.id]);

  function toggle(id: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function salvar() {
    if (!token) return;
    setSaving(true);
    const res = await fetch(`/api/pops/admin/usuarios/${usuario.id}/setores`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ setor_ids: Array.from(selecionados) }),
    });
    setSaving(false);
    if (!res.ok) {
      toast("Erro ao salvar vínculos de Setor", "error");
      return;
    }
    toast("Vínculos de Setor atualizados", "success");
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-text">Setores da pessoa</h3>
            <p className="text-xs text-text-secondary">{usuario.nome_completo}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-400">Carregando…</p>
        ) : setores.length === 0 ? (
          <p className="text-sm text-slate-400">
            Nenhum Setor cadastrado ainda. Crie os Setores primeiro.
          </p>
        ) : (
          <div className="max-h-64 overflow-y-auto space-y-1">
            {setores.map((s) => (
              <label
                key={s.id}
                className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-primary/5 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selecionados.has(s.id)}
                  onChange={() => toggle(s.id)}
                  className="accent-primary"
                />
                <span className="text-sm text-text">{s.nome}</span>
                <span className="ml-auto text-xs font-semibold text-primary">{s.sigla}</span>
              </label>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium text-text-secondary hover:bg-slate-100"
          >
            Cancelar
          </button>
          <button
            disabled={saving || loading}
            onClick={salvar}
            className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
          >
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
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
