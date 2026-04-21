"use client";

import { FormEvent, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { AdminModal } from "./AdminModal";

export interface PendenciaEditable {
  id_acao: string;
  id_reuniao: string | null;
  descricao_acao: string | null;
  responsavel_id: string | null;
  responsavel_nome: string | null;
  co_responsavel_id: string | null;
  co_responsavel_nome: string | null;
  cargo: string | null;
  prazo: string | null;
  status: string | null;
  meta_entregavel: string | null;
  deleted_at: string | null;
}

const STATUS_OPTIONS = [
  "PENDENTE",
  "EM_PROGRESSO",
  "CONCLUIDO",
  "ATRASADO",
  "CANCELADO",
  "REPACTUADA",
];

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors";

interface Props {
  target: PendenciaEditable;
  token: string;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Modal de edicao administrativa de pendencia.
 * Todos os campos sao editaveis (sem bloqueio por status).
 */
export function PendenciaEditModal({ target, token, onClose, onSaved }: Props) {
  const { toast } = useToast();
  const formId = useId();

  const [descricao, setDescricao] = useState(target.descricao_acao ?? "");
  const [statusP, setStatusP] = useState(target.status ?? "PENDENTE");
  const [respId, setRespId] = useState(target.responsavel_id ?? "");
  const [respNome, setRespNome] = useState(target.responsavel_nome ?? "");
  const [coRespId, setCoRespId] = useState(target.co_responsavel_id ?? "");
  const [coRespNome, setCoRespNome] = useState(
    target.co_responsavel_nome ?? "",
  );
  const [prazo, setPrazo] = useState(target.prazo ?? "");
  const [cargo, setCargo] = useState(target.cargo ?? "");
  const [metaEntregavel, setMetaEntregavel] = useState(
    target.meta_entregavel ?? "",
  );
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      const set = (k: string, v: string, orig: string | null) => {
        if (v !== (orig ?? "")) payload[k] = v || null;
      };
      set("descricao_acao", descricao, target.descricao_acao);
      set("status", statusP, target.status);
      set("responsavel_id", respId, target.responsavel_id);
      set("responsavel_nome", respNome, target.responsavel_nome);
      set("co_responsavel_id", coRespId, target.co_responsavel_id);
      set("co_responsavel_nome", coRespNome, target.co_responsavel_nome);
      set("prazo", prazo, target.prazo);
      set("cargo", cargo, target.cargo);
      set("meta_entregavel", metaEntregavel, target.meta_entregavel);
      if (reason.trim()) payload.reason = reason.trim();
      if (Object.keys(payload).length === 0) {
        toast("Nenhuma alteração", "info");
        onClose();
        return;
      }
      const res = await fetch(`/api/admin/pendencias/${target.id_acao}`, {
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
      toast("Pendência atualizada", "success");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminModal
      open
      onClose={onClose}
      title="Editar pendência"
      description={`${target.id_acao} · Reunião ${target.id_reuniao ?? "—"}`}
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
        <Field label="Descrição">
          <textarea
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            rows={3}
            className={`${INPUT_CLASS} resize-none`}
            required
          />
        </Field>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Status">
            <select
              value={statusP}
              onChange={(e) => setStatusP(e.target.value)}
              className={INPUT_CLASS}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Prazo">
            <input
              type="date"
              value={prazo}
              onChange={(e) => setPrazo(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Responsável (ID)">
            <input
              value={respId}
              onChange={(e) => setRespId(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Responsável (nome cache)">
            <input
              value={respNome}
              onChange={(e) => setRespNome(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Co-responsável (ID)">
            <input
              value={coRespId}
              onChange={(e) => setCoRespId(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Co-responsável (nome cache)">
            <input
              value={coRespNome}
              onChange={(e) => setCoRespNome(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Cargo">
            <input
              value={cargo}
              onChange={(e) => setCargo(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
        </div>
        <Field label="Meta / entregável">
          <textarea
            value={metaEntregavel}
            onChange={(e) => setMetaEntregavel(e.target.value)}
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
            placeholder="Ex: correção de responsável trocado"
          />
        </Field>
      </form>
    </AdminModal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate-500 uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}
