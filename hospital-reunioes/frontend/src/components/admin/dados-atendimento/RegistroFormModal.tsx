"use client";

import { FormEvent, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { AdminModal } from "../AdminModal";
import type { Campo, Registro, TabelaSpec } from "./config";

interface Props {
  spec: TabelaSpec;
  initial?: Registro | null;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<boolean | void>;
}

type FormValues = Record<string, string | boolean>;

function valoresIniciais(spec: TabelaSpec, initial?: Registro | null): FormValues {
  const valores: FormValues = {};
  for (const campo of spec.campos) {
    const atual = initial?.[campo.key];
    if (campo.tipo === "boolean") {
      valores[campo.key] = typeof atual === "boolean" ? atual : false;
    } else if (campo.tipo === "number") {
      valores[campo.key] = atual === undefined || atual === null ? "" : String(atual);
    } else {
      valores[campo.key] = typeof atual === "string" ? atual : "";
    }
  }
  return valores;
}

/**
 * Modal genérico de criação/edição de um registro do Dados do Atendimento,
 * dirigido pela spec de campos da tabela (espelho do backend).
 */
export function RegistroFormModal({ spec, initial, onClose, onSubmit }: Props) {
  const [valores, setValores] = useState<FormValues>(() =>
    valoresIniciais(spec, initial),
  );
  const [submitting, setSubmitting] = useState(false);
  const formId = useId();

  const isEdit = !!initial;

  const camposInvalidos = spec.campos.filter((campo) => {
    const valor = valores[campo.key];
    if (campo.tipo === "boolean") return false;
    if (campo.tipo === "number") {
      if (typeof valor !== "string" || valor.trim() === "")
        return !!campo.obrigatorio;
      return Number.isNaN(Number(valor.replace(",", ".")));
    }
    return !!campo.obrigatorio && (typeof valor !== "string" || !valor.trim());
  });
  const canSubmit = camposInvalidos.length === 0 && !submitting;

  function setCampo(key: string, valor: string | boolean) {
    setValores((prev) => ({ ...prev, [key]: valor }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {};
      for (const campo of spec.campos) {
        const valor = valores[campo.key];
        if (campo.tipo === "boolean") {
          payload[campo.key] = valor === true;
        } else if (campo.tipo === "number") {
          const texto = typeof valor === "string" ? valor.trim() : "";
          if (texto === "") continue;
          payload[campo.key] = Number(texto.replace(",", "."));
        } else {
          payload[campo.key] = typeof valor === "string" ? valor.trim() : "";
        }
      }
      await onSubmit(payload);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AdminModal
      open
      onClose={onClose}
      title={
        isEdit
          ? `Editar ${spec.itemNoun}`
          : `${spec.artigo === "a" ? "Nova" : "Novo"} ${spec.itemNoun}`
      }
      size="lg"
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
        {spec.campos.map((campo) => (
          <CampoInput
            key={campo.key}
            campo={campo}
            valor={valores[campo.key]}
            onChange={(v) => setCampo(campo.key, v)}
          />
        ))}
      </form>
    </AdminModal>
  );
}

function CampoInput({
  campo,
  valor,
  onChange,
}: {
  campo: Campo;
  valor: string | boolean;
  onChange: (valor: string | boolean) => void;
}) {
  if (campo.tipo === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={valor === true}
          onChange={(e) => onChange(e.target.checked)}
          className="rounded border-slate-300 text-primary focus:ring-primary"
        />
        {campo.label}
      </label>
    );
  }

  const inputClass =
    "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary";

  return (
    <div>
      <label className="block text-sm font-medium text-text mb-1.5">
        {campo.label}
        {campo.obrigatorio && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {campo.tipo === "textarea" ? (
        <textarea
          value={typeof valor === "string" ? valor : ""}
          onChange={(e) => onChange(e.target.value)}
          rows={2}
          className={inputClass}
          required={campo.obrigatorio}
        />
      ) : (
        <input
          type={campo.tipo === "number" ? "number" : "text"}
          step={campo.tipo === "number" ? "0.01" : undefined}
          min={campo.tipo === "number" ? "0" : undefined}
          value={typeof valor === "string" ? valor : ""}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
          required={campo.obrigatorio}
        />
      )}
    </div>
  );
}
