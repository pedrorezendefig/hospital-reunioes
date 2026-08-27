"use client";

/**
 * Nota externa do hospital: Google e Reclame Aqui (issue #347, PRD #319).
 *
 * A tela onde o ouvidor digita o que leu nas duas páginas de fora. O sistema
 * não calcula esses números, e a integração automática é fase seguinte da spec:
 * até lá, esta é a única porta por onde eles entram no relatório da Diretoria.
 *
 * Cada gravação é um registro NOVO, e não uma edição: a tabela é um diário, e
 * o relatório de cada quinzena congela a nota que valia naquele dia. Por isso a
 * tela mostra a data do último registro ao lado de cada nota, e não só o número.
 *
 * A régua de cada fonte mora em `lib/ouvidoria/nota-externa.ts`, com testes
 * próprios. O gate de verdade é o backend, que recusa a quem não é da
 * Ouvidoria; aqui a tela só não oferece o formulário.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, ArrowLeft, Check, Loader2, Star } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  ESCALA,
  FONTES,
  type FonteExterna,
  ROTULO_FONTE,
  formatarNota,
  podeRegistrarNotaExterna,
  validarNota,
} from "@/lib/ouvidoria/nota-externa";

interface NotaRegistrada {
  fonte: FonteExterna;
  nota: number | null;
  escala: number;
  registrada_em: string | null;
  registrada_por_nome: string;
}

function formatarDia(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

export default function NotaExternaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeRegistrar = podeRegistrarNotaExterna(participante?.perfil_ouvidoria);

  const [token, setToken] = useState<string | null>(null);
  const [notas, setNotas] = useState<NotaRegistrada[]>([]);
  const [digitado, setDigitado] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);

  const carregar = useCallback(async (sessionToken: string) => {
    try {
      const res = await fetch("/api/ouvidoria/nota-externa", {
        headers: { Authorization: `Bearer ${sessionToken}` },
      });
      if (!res.ok) {
        setErro("Não foi possível carregar as notas registradas.");
        return;
      }
      setNotas((await res.json()).notas);
      setErro(null);
    } catch (e) {
      console.error("Erro ao carregar a nota externa:", e);
      setErro("Não foi possível carregar as notas registradas.");
    }
  }, []);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      if (sessionToken) await carregar(sessionToken);
      setLoading(false);
    }
    init();
  }, [carregar]);

  async function registrar(fonte: FonteExterna) {
    if (!token) return;
    const validada = validarNota(fonte, digitado[fonte] ?? "");
    if (!validada.ok) {
      setErro(validada.erro);
      return;
    }
    setSalvando(fonte);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/nota-externa", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ fonte, nota: validada.valor }),
      });
      if (!res.ok) {
        setErro(`Não foi possível registrar a nota do ${ROTULO_FONTE[fonte]}.`);
        return;
      }
      await carregar(token);
      setDigitado((atual) => ({ ...atual, [fonte]: "" }));
      setSalvo(fonte);
      setTimeout(() => setSalvo(null), 2000);
    } catch (e) {
      console.error("Erro ao registrar a nota externa:", e);
      setErro(`Não foi possível registrar a nota do ${ROTULO_FONTE[fonte]}.`);
    } finally {
      setSalvando(null);
    }
  }

  if (loading || carregandoPerfil) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  const porFonte = new Map(notas.map((n) => [n.fonte, n]));

  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Painel da Ouvidoria
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Nota externa do hospital</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        A nota que o hospital tem no Google e no Reclame Aqui, lida nas duas páginas e digitada
        aqui. O relatório da Diretoria mostra a última nota registrada de cada fonte. As escalas
        são diferentes: o Google vai de 0 a 5 e o Reclame Aqui de 0 a 10.
      </p>

      {erro && (
        <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {erro}
        </div>
      )}

      {!podeRegistrar && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          Só a Ouvidoria registra a nota externa.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {FONTES.map((fonte) => {
          const atual = porFonte.get(fonte);
          return (
            <div
              key={fonte}
              className="bg-white rounded-2xl border border-border shadow-premium p-5"
            >
              <div className="flex items-center gap-2 mb-1">
                <Star className="w-4 h-4 text-amber-500" />
                <h2 className="font-semibold text-slate-800">{ROTULO_FONTE[fonte]}</h2>
              </div>

              <div className="text-2xl font-bold text-slate-900 mt-2">
                {formatarNota(atual?.nota, ESCALA[fonte])}
              </div>
              <div className="text-xs text-slate-400 mt-0.5 min-h-[1rem]">
                {atual?.registrada_em
                  ? `Registrada em ${formatarDia(atual.registrada_em)}${
                      atual.registrada_por_nome ? ` por ${atual.registrada_por_nome}` : ""
                    }`
                  : "Nenhum registro até agora."}
              </div>

              {podeRegistrar && (
                <div className="flex items-center gap-2 mt-4">
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={`Nova nota do ${ROTULO_FONTE[fonte]}`}
                    placeholder={`0 a ${ESCALA[fonte]}`}
                    value={digitado[fonte] ?? ""}
                    onChange={(e) =>
                      setDigitado((atualDigitado) => ({
                        ...atualDigitado,
                        [fonte]: e.target.value,
                      }))
                    }
                    className="w-28 px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <button
                    onClick={() => registrar(fonte)}
                    disabled={salvando === fonte}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >
                    {salvando === fonte ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : salvo === fonte ? (
                      <Check className="w-4 h-4" />
                    ) : null}
                    Registrar
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
