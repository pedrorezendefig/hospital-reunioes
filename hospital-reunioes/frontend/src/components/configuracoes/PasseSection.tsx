"use client";

import { useState, useEffect } from "react";
import { Key, Eye, EyeOff, Loader2 } from "lucide-react";

export default function PasseSection({ token }: { token: string | null }) {
  const [passe, setPasse] = useState<string | null>(null);
  const [passeMascarado, setPasseMascarado] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    async function fetchPasse() {
      try {
        const res = await fetch("/api/admin/passe", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          setError("Erro ao carregar código passe.");
          setLoading(false);
          return;
        }

        const data = await res.json();
        setPasse(data.passe || null);
        setPasseMascarado(data.passe_mascarado || null);
      } catch {
        setError("Erro ao carregar código passe.");
      } finally {
        setLoading(false);
      }
    }

    fetchPasse();
  }, [token]);

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Key className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Código Passe</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Código necessário para novos cadastros no sistema
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
      ) : passeMascarado ? (
        <div className="bg-slate-50 rounded-xl px-5 py-4 flex items-center justify-between max-w-md">
          <div>
            <p className="text-xs text-text-secondary mb-1">Código atual</p>
            <p className="text-xl font-mono font-bold text-text tracking-wider">
              {revealed ? passe : passeMascarado}
            </p>
          </div>
          <button
            onClick={() => setRevealed(!revealed)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-primary hover:bg-primary/5 transition-colors cursor-pointer"
          >
            {revealed ? (
              <>
                <EyeOff className="w-4 h-4" />
                Ocultar
              </>
            ) : (
              <>
                <Eye className="w-4 h-4" />
                Mostrar
              </>
            )}
          </button>
        </div>
      ) : (
        <p className="text-sm text-text-secondary">
          Nenhum código passe configurado.
        </p>
      )}
    </div>
  );
}
