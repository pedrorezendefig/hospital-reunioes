"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { useToast } from "@/components/ui/Toast";
import {
  CalendarDays,
  CalendarPlus,
  Clock,
  Loader2,
  Pencil,
  Trash2,
  UserCircle2,
  Users,
} from "lucide-react";

interface ReuniaoCalendario {
  id_reuniao: string;
  data: string;
  hora_inicio: string | null;
  hora_fim?: string | null;
  tipo: string | null;
  titulo: string | null;
  objetivo: string | null;
  status_ata: string;
  facilitador_id?: string | null;
  criada_por?: string | null;
  participantes: Array<{ id: string; nome: string; cargo: string }>;
}

function formatarData(iso: string): string {
  const [y, m, d] = iso.split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export default function SecretariaHome() {
  const { participante } = useCurrentParticipante();
  const { toast: showToast } = useToast();
  const [reunioes, setReunioes] = useState<ReuniaoCalendario[]>([]);
  const [nomePorId, setNomePorId] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const meuId = participante?.id;

  const fetchReunioes = useCallback(async () => {
    setLoading(true);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};

      const [resReunioes, resParticipantes] = await Promise.all([
        fetch("/api/reunioes/calendario", { headers, cache: "no-store" }),
        fetch("/api/participantes?ativo=true&limit=200", { headers }),
      ]);

      if (!resReunioes.ok) throw new Error("Erro ao buscar reuniões");
      const data = (await resReunioes.json()) as ReuniaoCalendario[];

      // Backend já filtra pra secretária só PROGRAMADAS futuras.
      // Ainda assim filtramos no frontend só PROGRAMADAS pra ser explícito.
      const programadas = data
        .filter((r) => r.status_ata === "PROGRAMADA")
        .sort((a, b) => (a.data > b.data ? 1 : -1));
      setReunioes(programadas);

      if (resParticipantes.ok) {
        const lista = (await resParticipantes.json()) as Array<{
          id: string;
          nome_completo: string;
        }>;
        const map: Record<string, string> = {};
        for (const p of lista) map[p.id] = p.nome_completo;
        setNomePorId(map);
      }
    } catch (err) {
      console.error(err);
      showToast(
        err instanceof Error ? err.message : "Erro ao carregar reuniões",
        "error"
      );
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (meuId) fetchReunioes();
  }, [meuId, fetchReunioes]);

  async function handleCancelar(id_reuniao: string) {
    const confirmar = window.confirm(
      "Tem certeza que deseja cancelar essa reunião? Essa ação não pode ser desfeita."
    );
    if (!confirmar) return;
    setRemovingId(id_reuniao);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;
      const res = await fetch(`/api/reunioes/${id_reuniao}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Erro ao cancelar reunião");
      }
      showToast("Reunião cancelada", "success");
      setReunioes((prev) => prev.filter((r) => r.id_reuniao !== id_reuniao));
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erro ao cancelar",
        "error"
      );
    } finally {
      setRemovingId(null);
    }
  }

  const total = useMemo(() => reunioes.length, [reunioes]);
  const primeiroNome = participante?.nome_completo?.split(" ")[0] || "Secretária";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Olá, {primeiroNome}!
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Reuniões agendadas que ainda vão acontecer. Você pode editar ou cancelar
            qualquer uma antes da transcrição ser anexada.
          </p>
        </div>
        <Link
          href="/secretaria/nova"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity"
        >
          <CalendarPlus className="w-4 h-4" />
          Marcar nova reunião
        </Link>
      </header>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : total === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
          <CalendarDays className="w-10 h-10 mx-auto text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">
            Nenhuma reunião agendada no momento.
          </p>
          <Link
            href="/secretaria/nova"
            className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-primary text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <CalendarPlus className="w-4 h-4" />
            Marcar a primeira
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {reunioes.map((r) => {
            const facilitadorNome = r.facilitador_id
              ? nomePorId[r.facilitador_id] || "—"
              : "—";
            const criadorNome = r.criada_por
              ? nomePorId[r.criada_por] || "—"
              : null;
            return (
              <article
                key={r.id_reuniao}
                className="rounded-2xl border border-slate-200 bg-white p-5 hover:border-slate-300 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h2 className="font-semibold text-slate-900 truncate">
                      {r.titulo || "Sem título"}
                    </h2>
                    {r.objetivo ? (
                      <p className="text-sm text-slate-500 mt-1 line-clamp-2">
                        {r.objetivo}
                      </p>
                    ) : null}
                    <div className="flex items-center gap-4 flex-wrap text-xs text-slate-500 mt-3">
                      <span className="inline-flex items-center gap-1.5">
                        <CalendarDays className="w-3.5 h-3.5" />
                        {formatarData(r.data)}
                      </span>
                      {r.hora_inicio ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5" />
                          {r.hora_inicio.slice(0, 5)}
                          {r.hora_fim ? ` até ${r.hora_fim.slice(0, 5)}` : ""}
                        </span>
                      ) : null}
                      <span className="inline-flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5" />
                        Facilitador: {facilitadorNome}
                      </span>
                      {criadorNome ? (
                        <span className="inline-flex items-center gap-1.5">
                          <UserCircle2 className="w-3.5 h-3.5" />
                          Marcada por: {r.criada_por === meuId ? "Você" : criadorNome}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/secretaria/nova?edit=${r.id_reuniao}`}
                      className="p-2 rounded-xl hover:bg-slate-100 text-slate-500"
                      title="Editar"
                    >
                      <Pencil className="w-4 h-4" />
                    </Link>
                    <button
                      type="button"
                      disabled={removingId === r.id_reuniao}
                      onClick={() => handleCancelar(r.id_reuniao)}
                      className="p-2 rounded-xl hover:bg-rose-50 text-rose-500 disabled:opacity-50"
                      title="Cancelar reunião"
                    >
                      {removingId === r.id_reuniao ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
