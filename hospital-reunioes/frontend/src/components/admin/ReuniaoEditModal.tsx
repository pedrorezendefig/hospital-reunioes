"use client";

import { FormEvent, useId, useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { AdminModal } from "./AdminModal";

export interface ReuniaoEditable {
  id_reuniao: string;
  data: string | null;
  titulo: string | null;
  tipo: string | null;
  setor: string | null;
  facilitador_id: string | null;
  objetivo: string | null;
  status_ata: string | null;
  deleted_at: string | null;
}

const STATUS_OPTIONS = [
  "PROGRAMADA",
  "PROCESSANDO",
  "ERRO",
  "ERRO_IA",
  "AGUARDANDO_RESOLUCAO",
  "AGUARDANDO_VALIDACAO",
  "AGUARDANDO_ASSINATURA",
  "ASSINADA",
  "CANCELADA",
  "IMPORTADA",
];

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors";

interface Props {
  target: ReuniaoEditable;
  token: string;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Modal de edicao administrativa de reuniao.
 *
 * Atas com status_ata=ASSINADA bloqueiam alteracao de:
 *   status_ata, json_ata, url_pdf_assinado, data_assinatura,
 *   envelope_key_clicksign.
 * Metadados perifericos (titulo, setor, tipo, facilitador, objetivo)
 * continuam editaveis mesmo em ASSINADA.
 */
export function ReuniaoEditModal({ target, token, onClose, onSaved }: Props) {
  const { toast } = useToast();
  const isSigned = target.status_ata === "ASSINADA";
  const formId = useId();

  const [titulo, setTitulo] = useState(target.titulo ?? "");
  const [setor, setSetor] = useState(target.setor ?? "");
  const [tipo, setTipo] = useState(target.tipo ?? "");
  const [facilitador, setFacilitador] = useState(target.facilitador_id ?? "");
  const [objetivo, setObjetivo] = useState(target.objetivo ?? "");
  const [statusAta, setStatusAta] = useState(target.status_ata ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      const maybeSet = (k: string, v: string, original: string | null) => {
        if (v !== (original ?? "")) payload[k] = v;
      };
      maybeSet("titulo", titulo, target.titulo);
      maybeSet("setor", setor, target.setor);
      maybeSet("tipo", tipo, target.tipo);
      maybeSet("facilitador_id", facilitador, target.facilitador_id);
      maybeSet("objetivo", objetivo, target.objetivo);
      if (!isSigned) maybeSet("status_ata", statusAta, target.status_ata);
      if (reason.trim()) payload.reason = reason.trim();
      if (Object.keys(payload).length === 0) {
        toast("Nenhuma alteração", "info");
        onClose();
        return;
      }
      const res = await fetch(`/api/admin/reunioes/${target.id_reuniao}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        toast(`Erro: ${await res.text()}`, "error");
        return;
      }
      toast("Reunião atualizada", "success");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminModal
      open
      onClose={onClose}
      title="Editar reunião"
      description={target.id_reuniao}
      size="lg"
      scrollable
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-slate-200 bg-white text-text hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form={formId}
            disabled={saving}
            className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-primary to-primary-light text-white font-semibold shadow-md hover:shadow-lg disabled:opacity-60 inline-flex items-center gap-2"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Salvar
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit} className="space-y-4">
        {isSigned && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg p-3 flex gap-2">
            <Lock className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              Ata <strong>ASSINADA</strong> — conteúdo da ata, status, PDF e
              evidência de assinatura são imutáveis por compliance. Apenas
              metadados periféricos podem ser alterados.
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Título">
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Setor">
            <input
              value={setor}
              onChange={(e) => setSetor(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Tipo">
            <input
              value={tipo}
              onChange={(e) => setTipo(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Facilitador (ID)">
            <input
              value={facilitador}
              onChange={(e) => setFacilitador(e.target.value)}
              className={INPUT_CLASS}
              placeholder="P001"
            />
          </Field>
          <Field
            label={`Status ${isSigned ? "(bloqueado)" : ""}`}
            disabled={isSigned}
          >
            <select
              value={statusAta}
              onChange={(e) => setStatusAta(e.target.value)}
              disabled={isSigned}
              className={`${INPUT_CLASS} disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed`}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Pauta">
          <textarea
            value={objetivo}
            onChange={(e) => setObjetivo(e.target.value)}
            rows={2}
            className={`${INPUT_CLASS} resize-none`}
          />
        </Field>
        <Field label="Motivo (opcional)">
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className={`${INPUT_CLASS} resize-none`}
            placeholder="Ex: correção de facilitador"
          />
        </Field>
      </form>
    </AdminModal>
  );
}

function Field({
  label,
  disabled,
  children,
}: {
  label: string;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`flex flex-col gap-1.5 ${disabled ? "opacity-60" : ""}`}>
      <span className="text-xs font-medium text-slate-500 uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}
