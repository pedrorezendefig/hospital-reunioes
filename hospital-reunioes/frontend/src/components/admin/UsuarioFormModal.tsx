"use client";

import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { UserRole } from "@/types";
import { AdminUsuario, AdminUsuarioPayload } from "./types";
import { AdminModal } from "./AdminModal";

interface Props {
  mode: "create" | "edit";
  initial?: AdminUsuario;
  roleOptions: UserRole[];
  /**
   * Setores/cargos canonicos da taxonomia (tabelas `setores`/`cargos`).
   * Usado como sugestao via <datalist>. Valores livres continuam aceitos
   * para preservar legacy data — backend faz lookup silencioso e grava
   * setor_id/cargo_id quando o nome bate (migration 028).
   */
  setoresDisponiveis?: string[];
  cargosDisponiveis?: string[];
  onClose: () => void;
  onSubmit: (data: AdminUsuarioPayload) => Promise<boolean | void>;
}

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors";

/**
 * Modal de formulario para criar/editar participante via admin.
 * Campos: nome, email, cargo, setor, area, role, is_externo, ativo.
 * No modo edit, o botao "Salvar" so envia campos alterados.
 */
export function UsuarioFormModal({
  mode,
  initial,
  roleOptions,
  setoresDisponiveis,
  cargosDisponiveis,
  onClose,
  onSubmit,
}: Props) {
  const [nome, setNome] = useState(initial?.nome_completo ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [cargo, setCargo] = useState(initial?.cargo ?? "");
  const [setor, setSetor] = useState(initial?.setor ?? "");
  const [area, setArea] = useState(initial?.area ?? "");
  const [role, setRole] = useState<UserRole>(
    (initial?.role as UserRole) ?? "coordenador"
  );
  const [isExterno, setIsExterno] = useState(initial?.is_externo ?? false);
  const [ativo, setAtivo] = useState(initial?.ativo ?? true);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const formId = useId();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      let payload: AdminUsuarioPayload;
      if (mode === "create") {
        payload = {
          nome_completo: nome.trim(),
          email: email.trim(),
          cargo: cargo.trim(),
          setor: setor.trim() || null,
          area: area.trim() || null,
          role,
          is_externo: isExterno,
          ativo,
        };
      } else {
        // Edit: inclui apenas o que mudou.
        payload = {};
        if (nome !== initial?.nome_completo) payload.nome_completo = nome.trim();
        if (email !== initial?.email) payload.email = email.trim();
        if (cargo !== (initial?.cargo ?? "")) payload.cargo = cargo.trim();
        if (setor !== (initial?.setor ?? ""))
          payload.setor = setor.trim() || null;
        if (area !== (initial?.area ?? ""))
          payload.area = area.trim() || null;
        if (role !== (initial?.role ?? "coordenador")) payload.role = role;
        if (isExterno !== initial?.is_externo) payload.is_externo = isExterno;
        if (ativo !== initial?.ativo) payload.ativo = ativo;
        if (reason.trim()) payload.reason = reason.trim();
      }
      await onSubmit(payload);
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminModal
      open
      onClose={onClose}
      title={mode === "create" ? "Novo usuário" : "Editar usuário"}
      size="lg"
      scrollable
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form={formId}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-primary to-primary-light text-white shadow-md hover:shadow-lg disabled:opacity-60 transition-all"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {mode === "create" ? "Criar" : "Salvar"}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Nome completo" required>
            <input
              required
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Email" required>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Cargo" required>
            <input
              required
              value={cargo}
              onChange={(e) => setCargo(e.target.value)}
              list="cargos-datalist"
              className={INPUT_CLASS}
              placeholder="Selecione ou digite"
            />
            {cargosDisponiveis && cargosDisponiveis.length > 0 && (
              <datalist id="cargos-datalist">
                {cargosDisponiveis.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            )}
          </Field>
          <Field label="Setor">
            <input
              value={setor ?? ""}
              onChange={(e) => setSetor(e.target.value)}
              list="setores-datalist"
              className={INPUT_CLASS}
              placeholder="Selecione ou digite"
            />
            {setoresDisponiveis && setoresDisponiveis.length > 0 && (
              <datalist id="setores-datalist">
                {setoresDisponiveis.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            )}
          </Field>
          <Field label="Área">
            <input
              value={area ?? ""}
              onChange={(e) => setArea(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Role">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className={`${INPUT_CLASS} capitalize`}
            >
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="flex items-center gap-6 pt-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isExterno}
              onChange={(e) => setIsExterno(e.target.checked)}
              className="accent-primary"
            />
            É externo
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={ativo}
              onChange={(e) => setAtivo(e.target.checked)}
              className="accent-primary"
            />
            Ativo
          </label>
        </div>

        {mode === "edit" && (
          <Field label="Motivo da alteração (opcional)">
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className={`${INPUT_CLASS} resize-none`}
              placeholder="Ex: correção de dados cadastrais"
            />
          </Field>
        )}
      </form>
    </AdminModal>
  );
}

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
