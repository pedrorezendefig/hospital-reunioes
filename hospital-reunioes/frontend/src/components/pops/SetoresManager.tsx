"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Pencil, Plus, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { AutocompleteInput } from "@/components/ui/AutocompleteInput";
import { sugerirSigla } from "@/lib/pops/sigla";

export type NaturezaSetor = "assistencial" | "administrativa" | "apoio";

/** Rótulos das Naturezas do Setor para exibição (ADR 0018). */
const NATUREZA_LABEL: Record<NaturezaSetor, string> = {
  assistencial: "Assistencial",
  administrativa: "Administrativa",
  apoio: "De apoio",
};

export type PopsSetor = { id: string; nome: string; sigla: string; natureza: NaturezaSetor };

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
  const [setoresSugeridos, setSetoresSugeridos] = useState<string[]>([]);

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

  // Setores já conhecidos das Reuniões, apenas sugestão de UX no autocomplete
  // do Nome. Sem vínculo: pops_setores continua entidade própria e dona da sigla.
  useEffect(() => {
    if (authLoading || !token) return;
    fetch("/api/participantes/setores", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: string[]) =>
        setSetoresSugeridos(Array.isArray(data) ? data : []),
      )
      .catch(() => setSetoresSugeridos([]));
  }, [authLoading, token]);

  async function handleSubmit(payload: { nome: string; sigla: string; natureza: NaturezaSetor }) {
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
    {
      key: "natureza",
      header: "Natureza",
      width: "150px",
      render: (r) => (
        <span className="text-sm text-text-secondary">{NATUREZA_LABEL[r.natureza]}</span>
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
              Unidades do organograma. A sigla trava o código dos POPs (HSM_SIGLA-NNN)
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
          setoresSugeridos={setoresSugeridos}
          onClose={() => setModal(null)}
          onSubmit={handleSubmit}
        />
      )}
    </section>
  );
}

function SetorFormModal({
  initial,
  setoresSugeridos,
  onClose,
  onSubmit,
}: {
  initial: PopsSetor | null;
  setoresSugeridos: string[];
  onClose: () => void;
  onSubmit: (payload: { nome: string; sigla: string; natureza: NaturezaSetor }) => Promise<boolean>;
}) {
  const [nome, setNome] = useState(initial?.nome ?? "");
  const [sigla, setSigla] = useState(initial?.sigla ?? "");
  const [natureza, setNatureza] = useState<NaturezaSetor>(initial?.natureza ?? "assistencial");
  // Na criação, pré-preenche a sigla a partir do nome enquanto o usuário não a
  // edita à mão. Na edição, a sigla existente já entra "travada" (sem auto-sugestão).
  const [siglaTravada, setSiglaTravada] = useState(initial !== null);
  const [saving, setSaving] = useState(false);

  function handleNomeChange(next: string) {
    setNome(next);
    if (!siglaTravada) setSigla(sugerirSigla(next));
  }

  function handleSiglaChange(next: string) {
    setSigla(next.toUpperCase());
    setSiglaTravada(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !sigla.trim()) return;
    setSaving(true);
    const ok = await onSubmit({ nome: nome.trim(), sigla: sigla.trim(), natureza });
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
            <AutocompleteInput
              value={nome}
              onChange={handleNomeChange}
              options={setoresSugeridos}
              placeholder="Selecione ou digite"
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Sigla
            </label>
            <input
              value={sigla}
              onChange={(e) => handleSiglaChange(e.target.value)}
              placeholder="Ex.: CTI"
              maxLength={20}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary uppercase"
            />
            <p className="text-xs text-text-secondary mt-1">
              Base do código travado dos POPs deste Setor (HSM_SIGLA-NNN).
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Natureza
            </label>
            <select
              value={natureza}
              onChange={(e) => setNatureza(e.target.value as NaturezaSetor)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
            >
              <option value="assistencial">Assistencial</option>
              <option value="administrativa">Administrativa</option>
              <option value="apoio">De apoio</option>
            </select>
            <p className="text-xs text-text-secondary mt-1">
              Área do Setor: orienta as normas que o assistente de IA evoca ao redigir os POPs.
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
