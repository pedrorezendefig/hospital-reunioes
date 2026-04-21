"use client";

import { useState } from "react";
import { Shield, Eye, EyeOff, Loader2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";

export default function SecuritySection() {
  const { toast } = useToast();

  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [showNova, setShowNova] = useState(false);
  const [showConfirmar, setShowConfirmar] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (novaSenha.length < 8) {
      toast("A senha deve ter no mínimo 8 caracteres.", "warning");
      return;
    }

    if (novaSenha !== confirmarSenha) {
      toast("As senhas não coincidem.", "warning");
      return;
    }

    setSaving(true);
    try {
      const supabase = createClient();
      const { error } = await supabase.auth.updateUser({ password: novaSenha });

      if (error) {
        toast(error.message || "Erro ao alterar senha.", "error");
        return;
      }

      toast("Senha alterada com sucesso!", "success");
      setNovaSenha("");
      setConfirmarSenha("");
    } catch {
      toast("Erro inesperado ao alterar senha.", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Shield className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Segurança</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Gerencie sua senha de acesso ao sistema
      </p>

      {/* Form */}
      <form onSubmit={handleSubmit} className="max-w-md space-y-5">
        {/* Nova senha */}
        <div>
          <label className="block text-sm font-medium text-text mb-1.5">
            Nova senha
          </label>
          <div className="relative">
            <input
              type={showNova ? "text" : "password"}
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              placeholder="Mínimo 8 caracteres"
              className="w-full px-4 py-2.5 pr-11 rounded-xl border border-border text-sm text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            />
            <button
              type="button"
              onClick={() => setShowNova(!showNova)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors"
            >
              {showNova ? (
                <EyeOff className="w-4.5 h-4.5" />
              ) : (
                <Eye className="w-4.5 h-4.5" />
              )}
            </button>
          </div>
          {novaSenha.length > 0 && novaSenha.length < 8 && (
            <p className="text-xs text-amber-600 mt-1">
              A senha deve ter no mínimo 8 caracteres
            </p>
          )}
        </div>

        {/* Confirmar senha */}
        <div>
          <label className="block text-sm font-medium text-text mb-1.5">
            Confirmar nova senha
          </label>
          <div className="relative">
            <input
              type={showConfirmar ? "text" : "password"}
              value={confirmarSenha}
              onChange={(e) => setConfirmarSenha(e.target.value)}
              placeholder="Repita a nova senha"
              className="w-full px-4 py-2.5 pr-11 rounded-xl border border-border text-sm text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
            />
            <button
              type="button"
              onClick={() => setShowConfirmar(!showConfirmar)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors"
            >
              {showConfirmar ? (
                <EyeOff className="w-4.5 h-4.5" />
              ) : (
                <Eye className="w-4.5 h-4.5" />
              )}
            </button>
          </div>
          {confirmarSenha.length > 0 && novaSenha !== confirmarSenha && (
            <p className="text-xs text-red-500 mt-1">As senhas não coincidem</p>
          )}
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={saving || novaSenha.length < 8 || novaSenha !== confirmarSenha}
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          Alterar senha
        </button>
      </form>
    </div>
  );
}
