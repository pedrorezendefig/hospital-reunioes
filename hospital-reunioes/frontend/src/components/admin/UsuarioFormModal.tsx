"use client";

import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { AccessProfile, ACCESS_PROFILE_LABELS, UserRole } from "@/types";
import { AdminUsuario, AdminUsuarioPayload } from "./types";
import { AdminModal } from "./AdminModal";
import { AutocompleteInput } from "@/components/ui/AutocompleteInput";
import { Select } from "@/components/ui/Select";

interface Props {
  mode: "create" | "edit";
  initial?: AdminUsuario;
  roleOptions: UserRole[];
  /**
   * Setores/cargos canonicos da taxonomia (tabelas `setores`/`cargos`).
   * Sugeridos via combobox custom; valores livres continuam aceitos para
   * preservar legacy data.
   */
  setoresDisponiveis?: string[];
  cargosDisponiveis?: string[];
  onClose: () => void;
  onSubmit: (data: AdminUsuarioPayload) => Promise<boolean | void>;
}

const INPUT_CLASS =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors";

const ACCESS_PROFILE_HELP: Record<AccessProfile, string> = {
  regular: "Usuário comum. Vê só reuniões em que participa.",
  secretaria:
    "Apenas marca reuniões e aloca facilitador. Não vê pendências nem conteúdo de reuniões.",
  super_admin: "Acesso irrestrito. Vê e edita tudo no sistema.",
};

function inferInitialAccessProfile(initial?: AdminUsuario): AccessProfile {
  if (!initial) return "regular";
  if (initial.access_profile) return initial.access_profile;
  return initial.is_super_admin ? "super_admin" : "regular";
}

export function UsuarioFormModal({
  mode,
  initial,
  roleOptions,
  setoresDisponiveis,
  cargosDisponiveis,
  onClose,
  onSubmit,
}: Props) {
  const initialAccessProfile = inferInitialAccessProfile(initial);
  const [accessProfile, setAccessProfile] = useState<AccessProfile>(
    initialAccessProfile
  );
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

  const isSecretaria = accessProfile === "secretaria";
  // Pra secretária, cargo/role/setor/área viram opcionais (função sistêmica).

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      let payload: AdminUsuarioPayload;
      if (mode === "create") {
        payload = {
          nome_completo: nome.trim(),
          email: email.trim(),
          cargo: isSecretaria ? null : cargo.trim() || null,
          setor: setor.trim() || null,
          area: area.trim() || null,
          role: isSecretaria ? null : role,
          access_profile: accessProfile,
          is_externo: isExterno,
          ativo,
        };
      } else {
        payload = {};
        if (nome !== initial?.nome_completo) payload.nome_completo = nome.trim();
        if (email !== initial?.email) payload.email = email.trim();
        if (cargo !== (initial?.cargo ?? "")) payload.cargo = cargo.trim() || null;
        if (setor !== (initial?.setor ?? ""))
          payload.setor = setor.trim() || null;
        if (area !== (initial?.area ?? ""))
          payload.area = area.trim() || null;
        if (role !== (initial?.role ?? "coordenador")) payload.role = role;
        if (accessProfile !== initialAccessProfile) {
          payload.access_profile = accessProfile;
          if (accessProfile === "secretaria") {
            payload.role = null;
            payload.cargo = null;
          }
        }
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
        <fieldset className="space-y-2">
          <legend className="text-xs font-medium text-slate-500 uppercase">
            Perfil de acesso
          </legend>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {(["regular", "secretaria", "super_admin"] as AccessProfile[]).map(
              (ap) => {
                const active = accessProfile === ap;
                return (
                  <label
                    key={ap}
                    className={`flex flex-col gap-1 p-3 rounded-lg border cursor-pointer text-xs transition-colors ${
                      active
                        ? "border-primary bg-primary/5"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="access_profile"
                        value={ap}
                        checked={active}
                        onChange={() => setAccessProfile(ap)}
                        className="accent-primary"
                      />
                      <span className="font-semibold text-sm text-slate-800">
                        {ACCESS_PROFILE_LABELS[ap]}
                      </span>
                    </span>
                    <span className="text-slate-500 leading-snug">
                      {ACCESS_PROFILE_HELP[ap]}
                    </span>
                  </label>
                );
              }
            )}
          </div>
        </fieldset>

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
          <Field
            label={isSecretaria ? "Cargo (opcional)" : "Cargo"}
            required={!isSecretaria}
          >
            <AutocompleteInput
              value={cargo ?? ""}
              onChange={setCargo}
              options={cargosDisponiveis ?? []}
              placeholder={
                isSecretaria
                  ? "Não se aplica pra secretária"
                  : "Selecione ou digite"
              }
              required={!isSecretaria}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Setor">
            <AutocompleteInput
              value={setor ?? ""}
              onChange={setSetor}
              options={setoresDisponiveis ?? []}
              placeholder="Selecione ou digite"
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Área">
            <input
              value={area ?? ""}
              onChange={(e) => setArea(e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          {!isSecretaria && (
            <Field label="Role (cargo hospitalar)">
              <Select
                value={role}
                onChange={(v) => setRole(v as UserRole)}
                options={roleOptions.map((r) => ({ value: r, label: r }))}
                className="capitalize"
              />
            </Field>
          )}
        </div>

        <div className="flex items-center gap-6 pt-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isExterno}
              onChange={(e) => setIsExterno(e.target.checked)}
              className="accent-primary"
              disabled={isSecretaria}
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
