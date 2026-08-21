"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  CalendarDays,
  FileText,
  Loader2,
  Lock,
  Megaphone,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { DossieModal } from "@/components/ouvidoria/DossieModal";
import { agruparPorStatus, LABEL_STATUS } from "@/lib/ouvidoria/fila";
import {
  classificarPrazo,
  EM_ANDAMENTO,
  type ClassePrazo,
  type StatusManifestacao,
} from "@/lib/ouvidoria/prazo";

// Índice da manifestação: o que o painel lista para qualquer perfil com acesso.
// Relato, nome e contato só existem no Dossiê, atrás do perfil da Ouvidoria.
interface ManifestacaoIndice {
  id: string;
  numero: number;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusManifestacao;
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

const CLASSE_DO_GRUPO: Record<StatusManifestacao, string> = {
  novo: "bg-violet-100 text-violet-700",
  em_classificacao: "bg-sky-100 text-sky-700",
  aguardando_area: "bg-amber-100 text-amber-700",
  respondido: "bg-emerald-100 text-emerald-700",
  encerrado: "bg-slate-100 text-slate-500",
};

export default function OuvidoriaPage() {
  const [manifestacoes, setManifestacoes] = useState<ManifestacaoIndice[]>([]);
  const [loading, setLoading] = useState(true);
  const [semAcesso, setSemAcesso] = useState(false);
  const [erroCarga, setErroCarga] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [hoje, setHoje] = useState<string | null>(null);
  const [abertaId, setAbertaId] = useState<string | null>(null);

  const { participante } = useCurrentParticipante();
  const podeAbrirDossie = Boolean(participante?.perfil_ouvidoria);

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
          setManifestacoes((await res.json()).protocolos);
        } else {
          // Erro não pode virar "nenhuma manifestação": falso negativo num
          // painel de prazo.
          setErroCarga(true);
        }
      } catch (e) {
        console.error("Erro ao carregar manifestações:", e);
        setErroCarga(true);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const grupos = agruparPorStatus(manifestacoes).filter((g) => g.itens.length > 0);
  const emAndamento = manifestacoes.filter((m) => EM_ANDAMENTO.has(m.status)).length;
  const estourados = hoje
    ? manifestacoes.filter(
        (m) => classificarPrazo(m.prazo_resposta, m.status, hoje) === "estourado"
      ).length
    : 0;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Manifestações do hospital, na ordem do trabalho da ouvidoria
          </p>
        </div>
        {!loading && !semAcesso && !erroCarga && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-sky-100 text-sky-700">
              {emAndamento} em andamento
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

      {!loading && !semAcesso && !erroCarga && !podeAbrirDossie && manifestacoes.length > 0 && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 text-sm">
          <Lock className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Você vê o índice das manifestações. O conteúdo completo é restrito ao Ouvidor e à
            Diretoria Executiva.
          </span>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando manifestações...
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
            <p className="text-slate-500 font-medium">Não foi possível carregar as manifestações</p>
            <p className="text-slate-400 text-sm mt-1">Recarregue a página para tentar novamente.</p>
          </div>
        ) : manifestacoes.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <Megaphone className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhuma manifestação registrada</p>
            <p className="text-slate-400 text-sm mt-1">
              As manifestações chegam pelo atendimento da Ana e pelo registro da ouvidoria.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {grupos.map((grupo) => (
              <section key={grupo.status}>
                <header className="flex items-center gap-2 px-5 py-3 bg-slate-50 border-b border-slate-100">
                  <span
                    className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${CLASSE_DO_GRUPO[grupo.status]}`}
                  >
                    {LABEL_STATUS[grupo.status]}
                  </span>
                  <span className="text-xs text-slate-400">
                    {grupo.itens.length}{" "}
                    {grupo.itens.length === 1 ? "manifestação" : "manifestações"}
                  </span>
                </header>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="sr-only">
                      <tr>
                        {["Protocolo", "Abertura", "Prazo", "Categoria", "Setor", "Resumo"].map(
                          (h) => (
                            <th key={h}>{h}</th>
                          )
                        )}
                        <th>Ações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {grupo.itens.map((m) => {
                        const classe = hoje
                          ? classificarPrazo(m.prazo_resposta, m.status, hoje)
                          : "normal";
                        return (
                          <tr
                            key={m.id}
                            className={classe === "estourado" ? "bg-red-50/50" : undefined}
                          >
                            <td className="px-5 py-3 font-mono font-semibold text-slate-800 whitespace-nowrap">
                              {m.protocolo}
                            </td>
                            <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                              {formatarData(m.data_abertura)}
                            </td>
                            <td className="px-5 py-3 whitespace-nowrap">
                              <PrazoCell prazo={m.prazo_resposta} classe={classe} />
                            </td>
                            <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                              {m.categoria}
                            </td>
                            <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                              {m.setor}
                            </td>
                            <td className="px-5 py-3 text-slate-600 max-w-md">{m.resumo}</td>
                            <td className="px-5 py-3 text-right whitespace-nowrap">
                              {podeAbrirDossie && (
                                <button
                                  onClick={() => setAbertaId(m.id)}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
                                >
                                  <FileText className="w-3.5 h-3.5" />
                                  Abrir manifestação
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      <DossieModal manifestacaoId={abertaId} token={token} onClose={() => setAbertaId(null)} />
    </div>
  );
}
