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
 * Ouvidoria; aqui a tela só não oferece o formulário, e diz por quê.
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

/** O mesmo desenho da tela do painel: o motivo, e o caminho de volta. */
function TelaRestrita({ motivo }: { motivo: string }) {
  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto text-center py-16">
      <p className="text-slate-500 font-medium">{motivo}</p>
      <Link href="/ouvidoria" className="inline-block mt-4 text-sm text-primary hover:underline">
        Voltar à Ouvidoria
      </Link>
    </div>
  );
}

/**
 * O token do momento. Lido a cada chamada, e não guardado em estado: o
 * supabase-js rotaciona o JWT sozinho, e uma aba aberta por mais de uma hora
 * mandaria um token vencido para sempre, com o botão devolvendo erro genérico
 * até alguém recarregar a página.
 */
async function tokenAtual(): Promise<string | null> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ?? null;
}

export default function NotaExternaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeRegistrar = podeRegistrarNotaExterna(participante?.perfil_ouvidoria);

  const [notas, setNotas] = useState<NotaRegistrada[] | null>(null);
  const [digitado, setDigitado] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [semSessao, setSemSessao] = useState(false);
  const [semAcesso, setSemAcesso] = useState(false);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const token = await tokenAtual();
    if (!token) {
      setSemSessao(true);
      setNotas(null);
      return;
    }
    setSemSessao(false);
    try {
      const res = await fetch("/api/ouvidoria/nota-externa", {
        headers: { Authorization: `Bearer ${token}` },
      });
      // 401/403 é restrição, não defeito: dizer "não foi possível carregar"
      // aqui faria uma porta fechada parecer sistema quebrado.
      if (res.status === 401 || res.status === 403) {
        setSemAcesso(true);
        setNotas(null);
        return;
      }
      if (!res.ok) {
        setErro("Não foi possível carregar as notas registradas.");
        return;
      }
      setSemAcesso(false);
      setNotas((await res.json()).notas);
      setErro(null);
    } catch (e) {
      console.error("Erro ao carregar a nota externa:", e);
      setErro("Não foi possível carregar as notas registradas.");
    }
  }, []);

  useEffect(() => {
    async function init() {
      await carregar();
      setLoading(false);
    }
    init();
  }, [carregar]);

  async function registrar(fonte: FonteExterna) {
    const validada = validarNota(fonte, digitado[fonte] ?? "");
    if (!validada.ok) {
      setErro(validada.erro);
      return;
    }
    const token = await tokenAtual();
    if (!token) {
      setSemSessao(true);
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
      if (res.status === 401 || res.status === 403) {
        setSemAcesso(true);
        return;
      }
      if (!res.ok) {
        setErro(`Não foi possível registrar a nota do ${ROTULO_FONTE[fonte]}.`);
        return;
      }
      await carregar();
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

  if (semSessao) {
    return <TelaRestrita motivo="Sua sessão expirou. Entre de novo para registrar a nota externa." />;
  }

  if (semAcesso || !podeRegistrar) {
    return <TelaRestrita motivo="A nota externa do hospital é restrita ao Ouvidor e à Diretoria Executiva." />;
  }

  const porFonte = new Map((notas ?? []).map((n) => [n.fonte, n]));

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
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {salvando === fonte ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : salvo === fonte ? (
                    <Check className="w-4 h-4" />
                  ) : null}
                  Registrar
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
