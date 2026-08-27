"use client";

/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319, histórias 11 a 14).
 *
 * O retrato de AGORA para o ouvidor e para a Diretoria: a fila por situação, o
 * que vence hoje e amanhã, o que cada área já deve e os críticos abertos.
 *
 * Duas fontes, sem mistura. As contagens de área vêm do módulo de métricas, a
 * MESMA função que o relatório em PDF consome, e por isso os dois nunca
 * divergem. Os casos com nome vêm da listagem, porque o módulo de métricas não
 * identifica caso nenhum (contrato da issue #341). Somar as duas seria somar
 * universos diferentes: a fila viva é de hoje e o volume é do período.
 *
 * A régua de quem entra em cada bloco mora em `lib/ouvidoria/painel.ts`, com
 * testes próprios. Aqui só há tela.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  CalendarDays,
  Loader2,
  RefreshCw,
  ShieldAlert,
  UserX,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { usePolling } from "@/hooks/usePolling";
import { LABEL_STATUS } from "@/lib/ouvidoria/fila";
import { CLASSE_GRAVIDADE, LABEL_GRAVIDADE, type Gravidade } from "@/lib/ouvidoria/validacao";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import {
  areasComVencidas,
  atrasoFoiMedidoComCalendarioCerto,
  avisosDeDegradacao,
  contarPorStatus,
  criticosAbertos,
  hojeNoHospital,
  podeVerPainel,
  rotuloDoResponsavel,
  vencendoEm,
  type PendenciaDeArea,
} from "@/lib/ouvidoria/painel";

/** A cada minuto: é o retrato da operação, não um relógio de segundos. */
const INTERVALO_DE_ATUALIZACAO_MS = 60_000;

interface CasoDaListagem {
  id: string;
  protocolo: string;
  status: StatusManifestacao;
  setor: string;
  resumo: string;
  gravidade: string | null;
  prazo_area_em: string | null;
  rotulo_prazo: string;
  prazo_estourado: boolean;
}

interface Metricas {
  degradado: string[];
  pendencias_por_area: PendenciaDeArea[];
}

const CLASSE_DO_STATUS: Record<StatusManifestacao, string> = {
  novo: "bg-violet-100 text-violet-700",
  em_classificacao: "bg-sky-100 text-sky-700",
  aguardando_area: "bg-amber-100 text-amber-700",
  aguardando_manifestante: "bg-slate-200 text-slate-600",
  respondido: "bg-emerald-100 text-emerald-700",
  encerrado: "bg-slate-100 text-slate-500",
};

function formatarHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function EtiquetaDeGravidade({ gravidade }: { gravidade: string | null }) {
  if (!gravidade) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border bg-slate-100 text-slate-500 border-slate-200">
        A classificar
      </span>
    );
  }
  const classe = CLASSE_GRAVIDADE[gravidade as Gravidade] ?? "bg-slate-100 text-slate-600 border-slate-200";
  const label = LABEL_GRAVIDADE[gravidade as Gravidade] ?? gravidade;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${classe}`}>
      {label}
    </span>
  );
}

function LinhaDeCaso({ caso }: { caso: CasoDaListagem }) {
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono font-semibold text-slate-800 text-sm">{caso.protocolo}</span>
        <EtiquetaDeGravidade gravidade={caso.gravidade} />
        <span className="text-sm text-slate-600">{caso.setor}</span>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${CLASSE_DO_STATUS[caso.status]}`}
        >
          {LABEL_STATUS[caso.status]}
        </span>
        {caso.prazo_area_em && (
          <span
            className={`text-xs ml-auto whitespace-nowrap ${caso.prazo_estourado ? "text-red-600 font-semibold" : "text-slate-500"}`}
          >
            {formatarHora(caso.prazo_area_em)}
            {caso.rotulo_prazo ? ` (${caso.rotulo_prazo})` : ""}
          </span>
        )}
      </div>
      {/* O resumo é o mesmo do índice, que a listagem já mostra. Sem ele o
          painel diria que existe um caso grave sem dizer do que se trata, e
          quem lê teria que abrir a manifestação para saber se corre. */}
      {caso.resumo && <p className="text-xs text-slate-500 mt-1 line-clamp-2">{caso.resumo}</p>}
    </li>
  );
}

function Bloco({
  titulo,
  ajuda,
  icone,
  destaque,
  children,
}: {
  titulo: string;
  ajuda: string;
  icone: React.ReactNode;
  destaque?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`bg-white rounded-2xl border shadow-premium overflow-hidden ${destaque ? "border-red-200" : "border-border"}`}
    >
      <header
        className={`px-5 py-3 border-b ${destaque ? "bg-red-50 border-red-100" : "bg-slate-50 border-slate-100"}`}
      >
        <h2
          className={`flex items-center gap-2 font-bold text-sm ${destaque ? "text-red-700" : "text-slate-800"}`}
        >
          {icone}
          {titulo}
        </h2>
        <p className={`text-xs mt-0.5 ${destaque ? "text-red-500" : "text-slate-400"}`}>{ajuda}</p>
      </header>
      {children}
    </section>
  );
}

function Vazio({ texto }: { texto: string }) {
  return <p className="px-5 py-6 text-sm text-slate-400">{texto}</p>;
}

export default function PainelEmTempoRealPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeVer = podeVerPainel(participante?.perfil_ouvidoria);

  const [casos, setCasos] = useState<CasoDaListagem[]>([]);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  // O dia civil no fuso do hospital, calculado só depois de montar, para o
  // servidor e o navegador não renderizarem janelas diferentes.
  const [hoje, setHoje] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [resMetricas, resCasos] = await Promise.all([
        // Sem intervalo: o painel pede o retrato de agora. A fila viva das
        // pendências não depende de período nenhum.
        fetch("/api/ouvidoria/metricas", { headers }),
        fetch("/api/ouvidoria/protocolos", { headers }),
      ]);
      if (!resMetricas.ok || !resCasos.ok) {
        // Falha nunca vira painel zerado: num painel de prazo, o zero falso é
        // pior que a tela não abrir.
        setErro(true);
        return;
      }
      // O dia é relido a cada atualização: painel aberto na virada da
      // meia-noite continuaria chamando de "vence hoje" o que venceu ontem.
      setHoje(hojeNoHospital());
      const corpo = await resMetricas.json();
      setMetricas({
        degradado: corpo.degradado ?? [],
        pendencias_por_area: corpo.pendencias_por_area ?? [],
      });
      setCasos((await resCasos.json()).protocolos);
      setErro(false);
      setAtualizadoEm(new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }));
    } catch (e) {
      console.error("Erro ao carregar o painel da Ouvidoria:", e);
      setErro(true);
    }
  }, []);

  useEffect(() => {
    setHoje(hojeNoHospital());
    if (carregandoPerfil) return;
    if (!podeVer) {
      setLoading(false);
      return;
    }
    carregar().finally(() => setLoading(false));
  }, [carregandoPerfil, podeVer, carregar]);

  usePolling(carregar, INTERVALO_DE_ATUALIZACAO_MS, podeVer && !loading);

  if (carregandoPerfil || loading) {
    return (
      <div className="flex items-center justify-center h-64 gap-2 text-slate-400 text-sm">
        <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
        Carregando o painel...
      </div>
    );
  }

  if (!podeVer) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto text-center py-16">
        <p className="text-slate-500 font-medium">
          O painel em tempo real é restrito ao Ouvidor e à Diretoria Executiva.
        </p>
        <Link href="/ouvidoria" className="inline-block mt-4 text-sm text-primary hover:underline">
          Voltar à Ouvidoria
        </Link>
      </div>
    );
  }

  const degradado = metricas?.degradado ?? [];
  const avisos = avisosDeDegradacao(degradado);
  const atrasoConfiavel = atrasoFoiMedidoComCalendarioCerto(degradado);
  const criticos = criticosAbertos(casos);
  const vencemHoje = hoje ? vencendoEm(casos, "hoje", hoje) : [];
  const vencemAmanha = hoje ? vencendoEm(casos, "amanha", hoje) : [];
  const areas = areasComVencidas(metricas?.pendencias_por_area ?? []);
  const fila = contarPorStatus(casos);

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Painel em tempo real</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            A operação da Ouvidoria agora: o que está na fila, o que vence, o que já venceu e o que é
            grave.
          </p>
        </div>
        {atualizadoEm && (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
            <RefreshCw className="w-3.5 h-3.5" />
            Atualizado às {atualizadoEm}
          </span>
        )}
      </div>

      {erro && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Não foi possível atualizar o painel. Os números abaixo podem estar desatualizados.
          </span>
        </div>
      )}

      {/* O que o painel deixou de poder afirmar. Sem este aviso, o número sai
          com cara de bom e ninguém tem como desconfiar. */}
      {avisos.length > 0 && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <p className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Parte dos números não pôde ser medida
          </p>
          <ul className="mt-1.5 space-y-1 list-disc list-inside">
            {avisos.map((aviso) => (
              <li key={aviso.leitura}>{aviso.texto}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Fila por status: a mesma ordem e os mesmos rótulos da listagem. */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {fila.map((linha) => (
          <div
            key={linha.status}
            className="bg-white rounded-2xl border border-border shadow-premium px-4 py-3"
          >
            <p className="text-2xl font-bold text-slate-900">{linha.total}</p>
            <p className="text-xs text-slate-500 mt-0.5">{linha.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-5">
        <Bloco
          titulo={`Críticos abertos (${criticos.length})`}
          ajuda="Risco à vida, à segurança ou à imagem. Sai daqui quando a Ouvidoria encerra, não quando a área responde."
          icone={<ShieldAlert className="w-4 h-4" />}
          destaque
        >
          {criticos.length === 0 ? (
            <Vazio texto="Nenhum caso crítico aberto." />
          ) : (
            <ul className="divide-y divide-slate-50">
              {criticos.map((caso) => (
                <LinhaDeCaso key={caso.id} caso={caso} />
              ))}
            </ul>
          )}
        </Bloco>

        <div className="grid gap-5 lg:grid-cols-2">
          <Bloco
            titulo={`Vence hoje (${vencemHoje.length})`}
            ajuda="Prazo da área que termina hoje, do mais próximo para o mais distante."
            icone={<CalendarClock className="w-4 h-4" />}
          >
            {vencemHoje.length === 0 ? (
              <Vazio texto="Nada vence hoje." />
            ) : (
              <ul className="divide-y divide-slate-50">
                {vencemHoje.map((caso) => (
                  <LinhaDeCaso key={caso.id} caso={caso} />
                ))}
              </ul>
            )}
          </Bloco>

          <Bloco
            titulo={`Vence amanhã (${vencemAmanha.length})`}
            ajuda="Prazo da área que termina amanhã. Fim de semana e feriado não têm vencimento: neste dia a lista fica vazia."
            icone={<CalendarDays className="w-4 h-4" />}
          >
            {vencemAmanha.length === 0 ? (
              <Vazio texto="Nada vence amanhã." />
            ) : (
              <ul className="divide-y divide-slate-50">
                {vencemAmanha.map((caso) => (
                  <LinhaDeCaso key={caso.id} caso={caso} />
                ))}
              </ul>
            )}
          </Bloco>
        </div>

        <Bloco
          titulo={`Vencidos por área (${areas.length})`}
          ajuda="A fila viva de hoje, com nome de quem responde pelo setor. Vem do módulo de métricas, a mesma fonte do relatório da Diretoria."
          icone={<UserX className="w-4 h-4" />}
        >
          {areas.length === 0 ? (
            <Vazio texto="Nenhuma área com caso vencido." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100 text-left">
                    <th className="px-5 py-2.5 font-semibold text-slate-600">Setor</th>
                    <th className="px-5 py-2.5 font-semibold text-slate-600">Responsável</th>
                    <th className="px-5 py-2.5 font-semibold text-slate-600">Pendentes</th>
                    <th className="px-5 py-2.5 font-semibold text-slate-600">Vencidas</th>
                    <th className="px-5 py-2.5 font-semibold text-slate-600">Atraso do pior caso</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {areas.map((area) => {
                    const responsavel = rotuloDoResponsavel(area.responsavel, degradado);
                    return (
                      <tr key={area.setor}>
                        <td className="px-5 py-3 text-slate-800 font-medium">{area.setor}</td>
                        <td
                          className={`px-5 py-3 ${area.responsavel ? "text-slate-600" : "text-slate-400 italic"}`}
                        >
                          {responsavel}
                        </td>
                        <td className="px-5 py-3 text-slate-600">{area.pendentes}</td>
                        <td className="px-5 py-3 text-red-600 font-semibold">{area.vencidas}</td>
                        <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                          {area.dias_uteis_de_atraso.toLocaleString("pt-BR", {
                            minimumFractionDigits: 1,
                            maximumFractionDigits: 1,
                          })}{" "}
                          {area.dias_uteis_de_atraso === 1 ? "dia útil" : "dias úteis"}
                          {!atrasoConfiavel && (
                            <span className="ml-1.5 text-[11px] text-amber-600">(sem o calendário)</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="px-5 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-400">
                A fila é a de agora, sem recorte de data: um caso aberto no mês passado e ainda sem
                resposta aparece aqui. Por isso estes números não somam com o volume do período.
              </p>
            </div>
          )}
        </Bloco>
      </div>
    </div>
  );
}
