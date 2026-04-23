"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Users, Loader2, ArrowRight } from "lucide-react";

interface Participant {
  id: string;
  ativo?: boolean;
}

export default function UsersSection({ token }: { token: string | null }) {
  const router = useRouter();
  const [total, setTotal] = useState(0);
  const [ativos, setAtivos] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    async function fetchParticipantes() {
      try {
        const res = await fetch("/api/participantes", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          setError("Erro ao carregar participantes.");
          setLoading(false);
          return;
        }

        const data: Participant[] = await res.json();
        setTotal(data.length);
        setAtivos(data.filter((p) => p.ativo !== false).length);
      } catch {
        setError("Erro ao carregar participantes.");
      } finally {
        setLoading(false);
      }
    }

    fetchParticipantes();
  }, [token]);

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Users className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Usuários</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Visão geral dos usuários cadastrados no sistema
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
      ) : (
        <div className="space-y-5">
          {/* Stats */}
          <div className="bg-slate-50 rounded-xl px-5 py-4 max-w-md">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-primary">{ativos}</span>
              <span className="text-text-secondary text-sm">
                usuários ativos de{" "}
                <span className="font-semibold text-text">{total}</span> total
              </span>
            </div>
          </div>

          {/* Action */}
          <button
            onClick={() => router.push("/admin/usuarios")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all duration-200 cursor-pointer"
          >
            Gerenciar Participantes
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
