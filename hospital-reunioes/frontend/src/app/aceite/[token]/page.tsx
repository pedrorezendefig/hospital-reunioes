"use client";

/**
 * Página pública do Aceite interno (ADR 0030, issue #277).
 *
 * O signatário pendente chega pelo link tokenizado do email (ou pela
 * notificação in-app, no caso do Facilitador), lê a ata completa e clica
 * "Li e aceito": nascem todas as Pendências dele de uma vez. Sem login;
 * o token opaco de uso único é a credencial.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  ListChecks,
  Loader2,
  MessageSquare,
  Target,
  Users,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import type { JsonAta } from "@/types";

interface AceiteData {
  reuniao: {
    titulo: string | null;
    tipo: string | null;
    data: string | null;
    hora_inicio: string | null;
  };
  signatario: { nome: string };
  ata: JsonAta;
}

function formatarData(iso: string | null): string {
  if (!iso) return "Data a definir";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}

function formatarPrazo(prazo: string | null | undefined): string {
  if (!prazo) return "A definir";
  const d = new Date(`${prazo}T12:00:00`);
  if (Number.isNaN(d.getTime())) return prazo;
  return d.toLocaleDateString("pt-BR");
}

function Secao({
  titulo,
  icon: Icon,
  children,
}: {
  titulo: string;
  icon: typeof FileText;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white rounded-2xl border border-border shadow-premium">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
        <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4.5 h-4.5 text-primary" />
        </div>
        <h2 className="font-semibold text-slate-900">{titulo}</h2>
      </div>
      <div className="px-6 py-4">{children}</div>
    </section>
  );
}

export default function AceiteInternoPage() {
  const params = useParams();
  const token = params.token as string;

  const [data, setData] = useState<AceiteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aceitando, setAceitando] = useState(false);
  const [aceito, setAceito] = useState(false);
  const [confirmado, setConfirmado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const res = await fetch(`/api/aceite/${encodeURIComponent(token)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErro(body.detail || "Não foi possível carregar este link de aceite.");
        return;
      }
      setData((await res.json()) as AceiteData);
    } catch {
      setErro("Não foi possível carregar este link de aceite. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function handleAceitar() {
    setAceitando(true);
    try {
      const res = await fetch(`/api/aceite/${encodeURIComponent(token)}/aceitar`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErro(body.detail || "Não foi possível registrar o aceite. Tente novamente.");
        return;
      }
      setAceito(true);
    } catch {
      setErro("Não foi possível registrar o aceite. Tente novamente.");
    } finally {
      setAceitando(false);
    }
  }

  const ata = data?.ata;
  const quadro = ata?.quadro_atribuicoes ?? [];
  const participantes = ata?.participantes ?? [];
  const discussao = ata?.discussao ?? [];

  return (
    <main className="min-h-screen bg-bg">
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
        <div className="flex items-center justify-center mb-2">
          <Logo variant="default" size="sm" />
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">Carregando a ata...</span>
          </div>
        ) : erro && !data ? (
          <div className="bg-white rounded-2xl border border-border shadow-premium px-6 py-10 text-center space-y-3">
            <AlertCircle className="w-10 h-10 text-amber-500 mx-auto" />
            <p className="text-slate-700 font-medium">{erro}</p>
            <p className="text-sm text-slate-500">
              Se você acredita que isso é um engano, fale com quem conduziu a reunião.
            </p>
          </div>
        ) : aceito ? (
          <div className="bg-white rounded-2xl border border-emerald-200 shadow-premium px-6 py-10 text-center space-y-3">
            <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
            <h1 className="text-xl font-bold text-slate-900">Aceite registrado</h1>
            <p className="text-sm text-slate-600 max-w-md mx-auto leading-relaxed">
              Obrigado, {data?.signatario.nome || "participante"}. Seu compromisso com as ações desta ata
              foi firmado e suas pendências já entraram no acompanhamento.
            </p>
          </div>
        ) : data ? (
          <>
            {/* Cabeçalho da ata */}
            <div className="bg-white rounded-2xl border border-border shadow-premium px-6 py-5">
              <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-1">
                Ata de reunião para aceite
              </p>
              <h1 className="text-xl font-bold text-slate-900">
                {data.reuniao.titulo || "Reunião sem título"}
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                {data.reuniao.tipo ? `${data.reuniao.tipo} · ` : ""}
                {formatarData(data.reuniao.data)}
                {data.reuniao.hora_inicio ? ` · ${data.reuniao.hora_inicio.slice(0, 5)}` : ""}
              </p>
              <div className="mt-3 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  Olá, <strong>{data.signatario.nome || "participante"}</strong>. A coleta de assinaturas
                  digitais desta ata foi encerrada. Leia o conteúdo abaixo e registre o seu aceite no final
                  da página.
                </span>
              </div>
            </div>

            {participantes.length > 0 && (
              <Secao titulo={`Participantes (${participantes.length})`} icon={Users}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {participantes.map((p, i) => (
                    <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-50">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 to-primary-light/20 flex items-center justify-center text-primary font-semibold text-xs flex-shrink-0">
                        {p.nome.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{p.nome}</p>
                        <p className="text-xs text-slate-400 truncate">{p.cargo}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Secao>
            )}

            {ata?.objetivo && (
              <Secao titulo="Pauta da Reunião" icon={Target}>
                <p className="text-slate-700 text-sm leading-relaxed whitespace-pre-line">{ata.objetivo}</p>
              </Secao>
            )}

            {discussao.length > 0 && (
              <Secao titulo={`Discussão dos Pontos (${discussao.length})`} icon={MessageSquare}>
                <div className="space-y-4">
                  {discussao.map((topico, i) => (
                    <div key={i} className="border-l-4 border-primary/40 bg-slate-50 rounded-r-xl px-4 py-3">
                      <p className="text-sm font-semibold text-primary">
                        4.{i + 1} {topico.titulo}
                      </p>
                      {topico.descricao && (
                        <p className="mt-2 text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                          {topico.descricao}
                        </p>
                      )}
                      {topico.decisao && (
                        <div className="mt-3 px-3 py-2 rounded-lg bg-cyan-50 border-l-2 border-cyan-500 text-sm">
                          <strong className="text-cyan-900">Decisão:</strong>{" "}
                          <span className="text-slate-800">{topico.decisao}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Secao>
            )}

            {ata?.registro_narrativo && discussao.length === 0 && (
              <Secao titulo="Registro da Reunião" icon={FileText}>
                <p className="text-slate-700 text-sm leading-relaxed whitespace-pre-line">
                  {ata.registro_narrativo}
                </p>
              </Secao>
            )}

            {quadro.length > 0 && (
              <Secao titulo={`Quadro de Pendências e Responsáveis (${quadro.length})`} icon={ListChecks}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                        <th className="py-2 pr-4 font-semibold">Ação</th>
                        <th className="py-2 pr-4 font-semibold">Responsável</th>
                        <th className="py-2 font-semibold">Prazo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quadro.map((acao, i) => (
                        <tr key={i} className="border-b border-slate-50 last:border-0 align-top">
                          <td className="py-2.5 pr-4 text-slate-700">{acao.acao}</td>
                          <td className="py-2.5 pr-4 text-slate-800 font-medium whitespace-nowrap">
                            {acao.responsavel || "A definir"}
                          </td>
                          <td className="py-2.5 text-slate-500 whitespace-nowrap">{formatarPrazo(acao.prazo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Secao>
            )}

            {/* Caixa do aceite */}
            <div className="bg-white rounded-2xl border border-border shadow-premium px-6 py-5 space-y-4">
              {erro && (
                <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <span>{erro}</span>
                </div>
              )}
              <label className="flex items-start gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={confirmado}
                  onChange={(e) => setConfirmado(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary"
                />
                <span className="text-sm text-slate-700 leading-relaxed">
                  Li a ata completa acima e aceito os compromissos registrados sob minha responsabilidade.
                </span>
              </label>
              <button
                type="button"
                onClick={() => void handleAceitar()}
                disabled={!confirmado || aceitando}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white font-semibold text-sm shadow-sm hover:opacity-95 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {aceitando ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                Li e aceito
              </button>
              <p className="text-[11px] text-slate-400 text-center">
                O aceite é registrado uma única vez e cria as suas pendências imediatamente.
              </p>
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
