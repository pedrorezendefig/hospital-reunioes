"use client";

import { FormEvent, useEffect, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { AdminModal } from "./AdminModal";

export type TaxonomyItem = {
  id: string;
  nome: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
};

interface Props {
  title: string;
  initial?: TaxonomyItem | null;
  onClose: () => void;
  onSubmit: (payload: {
    nome: string;
    ativo?: boolean;
  }) => Promise<boolean | void>;
}

/**
 * Modal compartilhado para CRUD de taxonomia (setores, cargos, tipos_reuniao).
 *
 * Em modo "criar", so pede nome (ativo=true implicito no backend).
 * Em modo "editar", inclui toggle de ativo.
 */
export function TaxonomyFormModal({ title, initial, onClose, onSubmit }: Props) {
  const [nome, setNome] = useState(initial?.nome ?? "");
  const [ativo, setAtivo] = useState(initial?.ativo ?? true);
  const [submitting, setSubmitting] = useState(false);
  const formId = useId();

  useEffect(() => {
    setNome(initial?.nome ?? "");
    setAtivo(initial?.ativo ?? true);
  }, [initial]);

  const isEdit = !!initial;
  const canSubmit = nome.trim().length > 0 && !submitting;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const payload: { nome: string; ativo?: boolean } = { nome: nome.trim() };
      if (isEdit) payload.ativo = ativo;
      await onSubmit(payload);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AdminModal
      open
      onClose={onClose}
      title={title}
      size="md"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm rounded-lg border border-slate-200 bg-white text-text hover:bg-slate-50 disabled:opacity-60"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form={formId}
            disabled={!canSubmit}
            className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-primary to-primary-light text-white font-semibold shadow-md hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEdit ? "Salvar" : "Criar"}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-text mb-1.5">
            Nome
          </label>
          <input
            type="text"
            autoFocus
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            placeholder="Ex: Administrativo"
            maxLength={200}
            required
          />
        </div>

        {isEdit && (
          <label className="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={ativo}
              onChange={(e) => setAtivo(e.target.checked)}
              className="rounded border-slate-300 text-primary focus:ring-primary"
            />
            Ativo
          </label>
        )}
      </form>
    </AdminModal>
  );
}
