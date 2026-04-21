"use client";

import { useState, useEffect } from "react";
import { Link as LinkIcon, Loader2, CheckCircle, XCircle, RefreshCw } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Integration {
  nome: string;
  descricao: string;
  conectado: boolean;
  ambiente?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function IntegrationsSection({ token }: { token: string | null }) {
  const { toast } = useToast();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingMap, setTestingMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!token) return;

    async function fetchIntegrations() {
      try {
        const res = await fetch("/api/admin/integracoes", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          setError("Erro ao carregar integrações.");
          setLoading(false);
          return;
        }

        const data = await res.json();
        setIntegrations(Array.isArray(data) ? data : data.integracoes || []);
      } catch {
        setError("Erro ao carregar integrações.");
      } finally {
        setLoading(false);
      }
    }

    fetchIntegrations();
  }, [token]);

  async function handleTest(nome: string) {
    if (!token) return;

    setTestingMap((prev) => ({ ...prev, [nome]: true }));

    try {
      const slug = nome.toLowerCase().replace(/\s+/g, "-");
      const res = await fetch(`/api/admin/integracoes/${slug}/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok && data.sucesso) {
        toast(data.mensagem || `${nome}: conexão bem-sucedida!`, "success");
      } else {
        toast(data.mensagem || data.detail || `${nome}: falha na conexão.`, "error");
      }
    } catch {
      toast(`Erro ao testar ${nome}.`, "error");
    } finally {
      setTestingMap((prev) => ({ ...prev, [nome]: false }));
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <LinkIcon className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Integrações</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Status das integrações externas do sistema
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
      ) : integrations.length === 0 ? (
        <p className="text-sm text-text-secondary">
          Nenhuma integração configurada.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {integrations.map((integration) => (
            <IntegrationCard
              key={integration.nome}
              integration={integration}
              testing={testingMap[integration.nome] ?? false}
              onTest={() => handleTest(integration.nome)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Integration Card ─────────────────────────────────────────────────────────

function IntegrationCard({
  integration,
  testing,
  onTest,
}: {
  integration: Integration;
  testing: boolean;
  onTest: () => void;
}) {
  return (
    <div className="bg-slate-50 rounded-xl border border-border/50 p-4 flex flex-col gap-3">
      {/* Top row: name + badge */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-text">{integration.nome}</h3>
        {integration.conectado ? (
          <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
            <CheckCircle className="w-3 h-3" />
            Conectado
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs font-medium text-red-500 bg-red-50 px-2 py-0.5 rounded-full">
            <XCircle className="w-3 h-3" />
            Desconectado
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-xs text-text-secondary leading-relaxed">
        {integration.descricao}
      </p>

      {/* Environment badge */}
      {integration.ambiente && (
        <span className="inline-flex self-start text-[10px] font-semibold uppercase tracking-wider text-text-secondary bg-slate-200 px-2 py-0.5 rounded">
          {integration.ambiente}
        </span>
      )}

      {/* Test button */}
      <button
        onClick={onTest}
        disabled={testing}
        className="flex items-center justify-center gap-2 mt-auto px-3 py-2 rounded-lg text-xs font-medium text-primary border border-primary/20 hover:bg-primary/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
      >
        {testing ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <RefreshCw className="w-3.5 h-3.5" />
        )}
        Testar conexão
      </button>
    </div>
  );
}
