"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Loader2,
  Megaphone,
  RotateCcw,
} from "lucide-react";
import {
  classificarPrazo,
  type ClassePrazo,
  type StatusProtocolo,
} from "@/lib/ouvidoria/prazo";

// Índice, não dossiê (ADR 0031): o painel só conhece estes campos. Nome, CPF e
// relato do manifestante vivem na conversa da Ana e nunca chegam a esta tela.
interface ProtocoloOuvidoria {
  id: string;
  numero: number;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusProtocolo;
  categoria: string;
  setor: string;
  resumo: string;
  conversa_id: string;
}

function formatarData(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR");
}

function PrazoCell({ prazo, classe }: { prazo: string; classe: ClassePrazo }) {
  const label = formatarData(prazo);
  if (classe === "estourado") {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 text-sm font-semibold">
        <AlertCircle className="w-3.5 h-3.5" />
        {label}
        <span className="text-[10px] font-bold uppercase tracking-wide bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">
          Estourado
        </span>
      </span>
    );
  }
  if (classe === "perto") {
    return (
      <span className="inline-flex items-center gap-1 text-amber-600 text-sm font-medium">
        <CalendarDays className="w-3.5 h-3.5" />
        {label}
      </span>
    );
  }
  return <span className="text-slate-600 text-sm">{label}</span>;
}

function StatusBadge({ status }: { status: StatusProtocolo }) {
  if (status === "aberto") {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-100 text-sky-700">
        Aberto
      </span>
    );
  }
  if (status === "respondido") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
        <CheckCircle2 className="w-3 h-3" />
        Respondido
      </span>
    );
  }
  // Estado terminal vindo do import do NocoDB: o painel não altera.
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500">
      Encerrado
    </span>
  );
}

export default function OuvidoriaPage() {
  const [protocolos, setProtocolos] = useState<ProtocoloOuvidoria[]>([]);
  const [loading, setLoading] = useState(true);
  const [semAcesso, setSemAcesso] = useState(false);
  const [erroCarga, setErroCarga] = useState(false);
  const [erroMudanca, setErroMudanca] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [mudandoId, setMudandoId] = useState<string | null>(null);
  const [hoje, setHoje] = useState<string | null>(null);

  useEffect(() => {
    // Data local do navegador (data civil, sem UTC), só após montar: evita
    // divergência de hidratação no destaque de prazo.
    const agora = new Date();
    setHoje(
      `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}-${String(
        agora.getDate()
      ).padStart(2, "0")}`
    );

    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      if (!sessionToken) {
        setLoading(false);
        return;
      }
      try {
        const res = await fetch("/api/ouvidoria/protocolos", {
          headers: { Authorization: `Bearer ${sessionToken}` },
        });
        if (res.status === 403) {
          setSemAcesso(true);
        } else if (res.ok) {
          setProtocolos((await res.json()).protocolos);
        } else {
          // Erro não pode virar "nenhum protocolo": falso negativo num
          // painel de prazo.
          setErroCarga(true);
        }
      } catch (e) {
        console.error("Erro ao carregar protocolos:", e);
        setErroCarga(true);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  async function mudarStatus(p: ProtocoloOuvidoria, novo: "aberto" | "respondido") {
    if (!token) return;
    setMudandoId(p.id);
    setErroMudanca(null);
    try {
      const res = await fetch(`/api/ouvidoria/protocolos/${p.id}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: novo }),
      });
      if (res.ok) {
        const atualizado: ProtocoloOuvidoria = await res.json();
        setProtocolos((prev) => prev.map((x) => (x.id === p.id ? { ...x, ...atualizado } : x)));
      } else {
        setErroMudanca(`Não foi possível atualizar o protocolo ${p.protocolo}. Tente novamente.`);
      }
    } catch (e) {
      console.error("Erro ao mudar status:", e);
      setErroMudanca(`Não foi possível atualizar o protocolo ${p.protocolo}. Tente novamente.`);
    } finally {
      setMudandoId(null);
    }
  }

  const abertos = protocolos.filter((p) => p.status === "aberto").length;
  const estourados = hoje
    ? protocolos.filter((p) => classificarPrazo(p.prazo_resposta, p.status, hoje) === "estourado")
        .length
    : 0;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Protocolos registrados pela Ana no atendimento do WhatsApp
          </p>
        </div>
        {!loading && !semAcesso && !erroCarga && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-sky-100 text-sky-700">
              {abertos} em aberto
            </span>
            {estourados > 0 && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-red-100 text-red-700">
                <AlertCircle className="w-4 h-4" />
                {estourados} com prazo estourado
              </span>
            )}
          </div>
        )}
      </div>

      {erroMudanca && (
        <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {erroMudanca}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando protocolos...
          </div>
        ) : semAcesso ? (
          <div className="text-center py-16">
            <p className="text-slate-500 font-medium">Acesso restrito à equipe de Reuniões</p>
          </div>
        ) : erroCarga ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-7 h-7 text-red-400" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Não foi possível carregar os protocolos</p>
            <p className="text-slate-400 text-sm mt-1">Recarregue a página para tentar novamente.</p>
          </div>
        ) : protocolos.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <Megaphone className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhum protocolo registrado</p>
            <p className="text-slate-400 text-sm mt-1">
              Os protocolos nascem pelo registro da Ana no WhatsApp.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  {["Protocolo", "Abertura", "Prazo", "Categoria", "Setor", "Resumo", "Status"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-5 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide"
                      >
                        {h}
                      </th>
                    )
                  )}
                  <th className="px-5 py-3 text-right">
                    <span className="sr-only">Ações</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {protocolos.map((p) => {
                  const classe = hoje
                    ? classificarPrazo(p.prazo_resposta, p.status, hoje)
                    : "normal";
                  return (
                    <tr
                      key={p.id}
                      className={classe === "estourado" ? "bg-red-50/50" : undefined}
                    >
                      <td className="px-5 py-3 font-mono font-semibold text-slate-800 whitespace-nowrap">
                        {p.protocolo}
                      </td>
                      <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                        {formatarData(p.data_abertura)}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        <PrazoCell prazo={p.prazo_resposta} classe={classe} />
                      </td>
                      <td className="px-5 py-3 text-slate-600 whitespace-nowrap">{p.categoria}</td>
                      <td className="px-5 py-3 text-slate-600 whitespace-nowrap">{p.setor}</td>
                      <td className="px-5 py-3 text-slate-600 max-w-md">{p.resumo}</td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        <StatusBadge status={p.status} />
                      </td>
                      <td className="px-5 py-3 text-right whitespace-nowrap">
                        {mudandoId === p.id ? (
                          <Loader2 className="w-4 h-4 animate-spin text-slate-400 inline" />
                        ) : p.status === "aberto" ? (
                          <button
                            onClick={() => mudarStatus(p, "respondido")}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Marcar respondido
                          </button>
                        ) : p.status === "respondido" ? (
                          <button
                            onClick={() => mudarStatus(p, "aberto")}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 transition-colors"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            Reabrir
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
