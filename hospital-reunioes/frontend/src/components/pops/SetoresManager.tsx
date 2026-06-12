"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Pencil, Plus, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";

export type PopsSetor = { id: string; nome: string; sigla: string };

/**
 * CRUD de Setores do contexto POPs (Superadmin).
 *
 * Setor: unidade do organograma do HSM, com nome e sigla únicos — a sigla é
 * a base do Código travado HSM_[SIGLA]-[NNN]. Não confundir com o campo
 * livre "setor" do cadastro de participantes das Reuniões.
 */
export function SetoresManager() {
  const { token, loading: authLoading } = useAuth();
  const { toast } = useToast();

  const [rows, setRows] = useState<PopsSetor[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ alvo: PopsSetor | null } | null>(null);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch("/api/pops/setores", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setRows(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar Setores", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    if (!authLoading && token) fetchRows();
  }, [authLoading, token, fetchRows]);

  async function handleSubmit(payload: { nome: string; sigla: string }) {
    if (!token) return false;
    const editando = modal?.alvo;
    const res = await fetch(
      editando ? `/api/pops/setores/${editando.id}` : "/api/pops/setores",
      {
        method: editando ? "PATCH" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      },
    );
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro ao salvar Setor: ${msg}`, "error");
      return false;
    }
    toast(editando ? "Setor atualizado" : "Setor criado", "success");
    setModal(null);
    await fetchRows();
    return true;
  }

  const columns: Column<PopsSetor>[] = [
    {
      key: "nome",
      header: "Nome",
      render: (r) => <span className="font-medium text-text">{r.nome}</span>,
    },
    {
      key: "sigla",
      header: "Sigla",
      width: "140px",
      render: (r) => (
        <span className="inline-flex px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-semibold">
          {r.sigla}
        </span>
      ),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 className="w-5 h-5 text-primary" />
          <div>
            <h2 className="text-lg font-bold text-text">Setores</h2>
            <p className="text-xs text-text-secondary">
              Unidades do organograma — a sigla trava o código dos POPs (HSM_SIGLA-NNN)
            </p>
          </div>
        </div>
        <button
          onClick={() => setModal({ alvo: null })}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" />
          Novo Setor
        </button>
      </div>

      <DataTable
        data={rows}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id}
        emptyState={{
          title: "Nenhum Setor cadastrado",
          hint: "Cadastre os Setores do organograma para vincular os usuários do POPs.",
        }}
        rowActions={(r) => (
          <button
            onClick={() => setModal({ alvo: r })}
            title="Editar"
            className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
          >
            <Pencil className="w-4 h-4" />
          </button>
        )}
      />

      {modal && (
        <SetorFormModal
          initial={modal.alvo}
          onClose={() => setModal(null)}
          onSubmit={handleSubmit}
        />
      )}
    </section>
  );
}

function SetorFormModal({
  initial,
  onClose,
  onSubmit,
}: {
  initial: PopsSetor | null;
  onClose: () => void;
  onSubmit: (payload: { nome: string; sigla: string }) => Promise<boolean>;
}) {
  const [nome, setNome] = useState(initial?.nome ?? "");
  const [sigla, setSigla] = useState(initial?.sigla ?? "");
  const [saving, setSaving] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !sigla.trim()) return;
    setSaving(true);
    const ok = await onSubmit({ nome: nome.trim(), sigla: sigla.trim() });
    if (!ok) setSaving(false);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-text">
            {initial ? "Editar Setor" : "Novo Setor"}
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Nome
            </label>
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Centro de Terapia Intensiva"
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Sigla
            </label>
            <input
              value={sigla}
              onChange={(e) => setSigla(e.target.value.toUpperCase())}
              placeholder="Ex.: CTI"
              maxLength={20}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary uppercase"
            />
            <p className="text-xs text-text-secondary mt-1">
              Base do código travado dos POPs deste Setor (HSM_SIGLA-NNN).
            </p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-sm font-medium text-text-secondary hover:bg-slate-100"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving || !nome.trim() || !sigla.trim()}
              className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
            >
              {saving ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </form>
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
