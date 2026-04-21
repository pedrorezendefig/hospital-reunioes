"use client";

import { useState } from "react";
import { Check, Copy, KeyRound, X } from "lucide-react";

interface Props {
  email: string;
  password: string;
  onClose: () => void;
}

/**
 * Modal exibido UMA UNICA VEZ apos reset de senha: o backend retorna
 * a senha em claro e o admin precisa copia-la agora (ninguem mais
 * podera visualiza-la depois).
 */
export function NewPasswordModal({ email, password, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback silencioso
    }
  }

  return (
    <div className="modal-backdrop z-[200] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-premium-strong w-full max-w-md overflow-hidden">
        <header className="flex items-start justify-between px-6 py-4 border-b border-border">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-amber-50">
              <KeyRound className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h2 className="text-base font-bold text-text">Senha gerada</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Copie agora — esta senha não será exibida novamente.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
            aria-label="Fechar"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="px-6 py-5 space-y-4">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase mb-1">
              Usuário
            </p>
            <p className="text-sm text-slate-700">{email}</p>
          </div>

          <div>
            <p className="text-xs font-medium text-slate-500 uppercase mb-1">
              Nova senha
            </p>
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
              <code className="flex-1 text-sm font-mono text-slate-800 break-all">
                {password}
              </code>
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-100 transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-500" />
                    Copiado
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    Copiar
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="rounded-lg bg-amber-50 border border-amber-100 px-4 py-3 text-xs text-amber-700">
            Esta senha é sensível. Compartilhe por um canal seguro e oriente o
            usuário a trocá-la no primeiro acesso.
          </div>
        </div>

        <footer className="flex items-center justify-end gap-3 px-6 py-4 bg-slate-50 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-primary to-primary-light text-white shadow-md hover:shadow-lg transition-all"
          >
            Fechar
          </button>
        </footer>
      </div>
    </div>
  );
}
