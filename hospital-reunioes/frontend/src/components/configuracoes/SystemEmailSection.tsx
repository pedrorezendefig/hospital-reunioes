"use client";

import { useState, useEffect } from "react";
import { Send, Loader2, CheckCircle, XCircle } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

interface EmailStatus {
  provedor_primario: string;
  email_envio: string;
  resend_configurado: boolean;
  smtp_configurado: boolean;
}

export default function SystemEmailSection({ token }: { token: string | null }) {
  const { toast } = useToast();
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    async function fetchStatus() {
      try {
        const res = await fetch("/api/admin/email/status", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          setError("Erro ao carregar status do email.");
          setLoading(false);
          return;
        }

        const data = await res.json();
        setStatus(data);
      } catch {
        setError("Erro ao carregar status do email.");
      } finally {
        setLoading(false);
      }
    }

    fetchStatus();
  }, [token]);

  async function handleTest() {
    if (!token) return;
    setTesting(true);

    try {
      const res = await fetch("/api/admin/email/test", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok && data.sucesso) {
        toast(data.mensagem || "Email de teste enviado com sucesso!", "success");
      } else {
        toast(data.mensagem || data.detail || "Falha ao enviar email de teste.", "error");
      }
    } catch {
      toast("Erro ao enviar email de teste.", "error");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Send className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Email do Sistema</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Status e configuração do serviço de email
      </p>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      ) : error ? (
        <div className="bg-red-50 text-red-600 text-sm rounded-xl px-4 py-3">
          {error}
        </div>
      ) : status ? (
        <div className="space-y-5">
          {/* Status rows */}
          <div className="bg-slate-50 rounded-xl px-5 py-4 space-y-3 max-w-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Provedor ativo</span>
              <span className="text-sm font-semibold text-text capitalize">
                {status.provedor_primario}
              </span>
            </div>
            <div className="border-t border-border/50" />
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Endereço de envio</span>
              <span className="text-sm font-medium text-text">
                {status.email_envio}
              </span>
            </div>
            <div className="border-t border-border/50" />
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Resend</span>
              {status.resend_configurado ? (
                <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-600">
                  <CheckCircle className="w-4 h-4" />
                  Configurado
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-sm font-medium text-red-500">
                  <XCircle className="w-4 h-4" />
                  Não configurado
                </span>
              )}
            </div>
            <div className="border-t border-border/50" />
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">SMTP</span>
              {status.smtp_configurado ? (
                <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-600">
                  <CheckCircle className="w-4 h-4" />
                  Configurado
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-sm font-medium text-red-500">
                  <XCircle className="w-4 h-4" />
                  Não configurado
                </span>
              )}
            </div>
          </div>

          {/* Test button */}
          <button
            onClick={handleTest}
            disabled={testing}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {testing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            Enviar email de teste
          </button>
        </div>
      ) : (
        <p className="text-sm text-text-secondary">
          Nenhuma configuração de email encontrada.
        </p>
      )}
    </div>
  );
}
