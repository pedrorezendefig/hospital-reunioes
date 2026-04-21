"use client";

import { useState } from "react";
import { X, Loader2 } from "lucide-react";
import { UserRole } from "@/types";
import { AdminUsuario, AdminUsuarioPayload } from "./types";

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
    <div className="modal-backdrop z-[200] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-premium-strong w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <header className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-bold text-text">
            {mode === "create" ? "Novo usuário" : "Editar usuário"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <form
          onSubmit={handleSubmit}
          className="overflow-auto px-6 py-5 space-y-4"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Nome completo" required>
              <input
                required
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Email" required>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Cargo" required>
              <input
                required
                value={cargo}
                onChange={(e) => setCargo(e.target.value)}
                list="cargos-datalist"
                className="input"
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
                className="input"
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
                className="input"
              />
            </Field>
            <Field label="Role">
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                className="input capitalize"
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
                className="input"
                placeholder="Ex: correção de dados cadastrais"
              />
            </Field>
          )}

          <footer className="flex items-center justify-end gap-3 pt-4 border-t border-border -mx-6 px-6 -mb-5 pb-5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-primary to-primary-light text-white shadow-md hover:shadow-lg disabled:opacity-60 transition-all"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {mode === "create" ? "Criar" : "Salvar"}
            </button>
          </footer>
        </form>
      </div>

      {/* Tailwind utility for inputs — scoped via className="input" via arbitrary selector inside JSX is not ideal,
          but we declare a local class via style tag to keep this component self-contained. */}
      <style jsx>{`
        .input {
          width: 100%;
          padding: 0.5rem 0.75rem;
          border: 1px solid rgb(226 232 240);
          border-radius: 0.5rem;
          font-size: 0.875rem;
          outline: none;
          transition: border-color 0.15s, box-shadow 0.15s;
        }
        .input:focus {
          border-color: var(--color-primary, #4f46e5);
          box-shadow: 0 0 0 1px var(--color-primary, #4f46e5);
        }
      `}</style>
    </div>
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
