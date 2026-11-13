"use client";

/**
 * A lente de "Melhorar a nota no Google" (issue #1619, PRD #1527, ADR 0089).
 *
 * Os números não vêm do Google Analytics: vêm do diário de Nota externa da
 * Ouvidoria, que um job lê na Places API uma vez por semana. Por isso esta
 * lente não usa o cache, o seletor de período nem o Atualizar agora das
 * outras: mostra a nota, as avaliações novas do mês e a tendência, e a data
 * da última leitura. A conta é do backend; a tela só escreve.
 *
 * Sem a chave da Places API, o backend diz `medida: false`, e a tela avisa
 * que a nota não está sendo medida, sem número.
 *
 * Abaixo dos números, o gráfico do mês (issue #1699): as leituras semanais
 * da nota e das avaliações acumuladas contra as do mês anterior.
 *
 * Abaixo da nota, o teste do convite ao Google no QR (issue #1625, ADR 0089
 * decisão 7): por ponto e período, os convites exibidos, os cliques e a taxa
 * de clique, e o aviso de reavaliar depois de 60 dias. O seletor de período
 * vale só para o convite; a nota continua mensal.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, PlugZap } from "lucide-react";

import { getAuthToken } from "@/hooks/useAuth";
import {
  BASE_CENTRAL,
  FALHA_DE_CONEXAO,
  lerRecusa,
  OBJETIVO_NOTA_NO_GOOGLE,
  SEM_SESSAO,
} from "@/lib/central-de-comando/api";
import { formatarInteiro } from "@/lib/central-de-comando/formato";
import { PERIODO_PADRAO, type Periodo } from "@/lib/central-de-comando/periodo";
import { formatarNota } from "@/lib/ouvidoria/nota-externa";

import { GraficoDoMesDaNota, type LeituraDaNota } from "./GraficoDoMesDaNota";
import { CAMINHO_OBJETIVOS } from "./Objetivos";
import { SeletorDePeriodo } from "./SeletorDePeriodo";

/** O que `GET /api/admin/central-de-comando/objetivos/google-reputacao` devolve. */
export type NotaNoGooglePayload = {
  objetivo: { id: string; nome: string; descricao: string };
  reputacao: {
    medida: boolean;
    nota: number | null;
    escala: number;
    total: number | null;
    lida_em: string | null;
    avaliacoes_do_mes: number | null;
    nota_mes_anterior: number | null;
    tendencia: "melhorou" | "piorou" | "igual" | null;
    /** As leituras do mês e do anterior, para o gráfico (issue #1699). */
    leituras_do_mes: LeituraDaNota[];
    leituras_mes_anterior: LeituraDaNota[];
  };
  /** O teste do convite ao Google no período (issue #1625). */
  convite?: {
    periodo: Periodo;
    ligado: boolean;
    ligado_em: string | null;
    dias_ligado: number | null;
    dias_do_teste: number;
    reavaliar: boolean;
    intervalo: { inicio: string; fim: string };
    pontos: { ponto_id: string; nome: string; ligado: boolean; convites: number; cliques: number; taxa: number | null }[];
    total: { convites: number; cliques: number; taxa: number | null };
  };
};

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; dados: NotaNoGooglePayload }
  | { tipo: "falhou"; mensagem: string };

const TENDENCIA: Record<"melhorou" | "piorou" | "igual", { rotulo: string; cor: string }> = {
  melhorou: { rotulo: "Melhorou", cor: "text-emerald-600" },
  piorou: { rotulo: "Piorou", cor: "text-amber-600" },
  igual: { rotulo: "Igual", cor: "text-text" },
};

function formatarDia(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

function formatarTaxa(taxa: number | null): string {
  if (taxa === null) return "Sem convite";
  return `${(taxa * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

export function NotaNoGoogle({ periodo = PERIODO_PADRAO }: { periodo?: Periodo }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    let vivo = true;

    async function carregar() {
      let token: string | undefined;
      try {
        token = await getAuthToken();
      } catch {
        token = undefined;
      }
      if (!token) {
        if (vivo) setEstado({ tipo: "falhou", mensagem: SEM_SESSAO });
        return;
      }
      try {
        const resposta = await fetch(`${BASE_CENTRAL}/objetivos/${OBJETIVO_NOTA_NO_GOOGLE}?periodo=${periodo}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resposta.ok) {
          const recusa = await lerRecusa(resposta);
          if (vivo) setEstado({ tipo: "falhou", mensagem: recusa.mensagem });
          return;
        }
        const dados = (await resposta.json()) as NotaNoGooglePayload;
        if (vivo) setEstado({ tipo: "pronto", dados });
      } catch {
        if (vivo) setEstado({ tipo: "falhou", mensagem: FALHA_DE_CONEXAO });
      }
    }

    carregar();
    return () => {
      vivo = false;
    };
  }, [periodo]);

  return (
    <div className="animate-fade-in-up space-y-6">
      <Link
        href={CAMINHO_OBJETIVOS}
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text"
      >
        <ArrowLeft className="h-4 w-4" />
        Objetivos
      </Link>

      {estado.tipo === "carregando" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-2xl border border-border bg-white p-6 text-sm text-text-secondary shadow-premium"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando os números
        </div>
      )}

      {estado.tipo === "pronto" && <Lente dados={estado.dados} />}
      {estado.tipo === "pronto" && estado.dados.convite && <TesteDoConvite convite={estado.dados.convite} />}

      {estado.tipo === "falhou" && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível buscar os números agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function Lente({ dados }: { dados: NotaNoGooglePayload }) {
  const { objetivo, reputacao } = dados;
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold text-text">{objetivo.nome}</h1>
        <p className="text-sm text-text-secondary">{objetivo.descricao}</p>
      </header>

      {!reputacao.medida ? (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">A nota do Google não está sendo medida</p>
            <p className="text-sm">A busca semanal da nota ainda não foi ligada. Quando for, a nota e o gráfico do mês aparecem aqui.</p>
          </div>
        </div>
      ) : reputacao.nota === null ? (
        <p role="status" className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-secondary">
          A busca semanal está ligada e ainda não fez a primeira leitura. A nota aparece aqui depois dela.
        </p>
      ) : (
        <>
          <p className="text-xs text-text-secondary">
            {reputacao.lida_em
              ? `Última leitura no Google em ${formatarDia(reputacao.lida_em)}. A nota é lida uma vez por semana.`
              : "A nota é lida uma vez por semana."}
          </p>
          <ul aria-label="Números do Objetivo" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <li className="rounded-2xl border border-border bg-white p-5 shadow-premium">
              <p className="text-xs text-text-secondary">Nota no Google</p>
              <p className="text-3xl font-bold tabular-nums text-text">{formatarNota(reputacao.nota, reputacao.escala)}</p>
              {reputacao.total !== null && (
                <p className="text-sm text-text-secondary">{formatarInteiro(reputacao.total)} avaliações no total</p>
              )}
            </li>
            <li className="rounded-2xl border border-border bg-white p-5 shadow-premium">
              <p className="text-xs text-text-secondary">Avaliações novas no mês</p>
              {reputacao.avaliacoes_do_mes !== null ? (
                <p className="text-3xl font-bold tabular-nums text-text">{formatarInteiro(reputacao.avaliacoes_do_mes)}</p>
              ) : (
                <p className="text-sm text-text-secondary">O número precisa de duas leituras no mês.</p>
              )}
              <p className="mt-1 text-xs text-text-secondary">
                O Google não diz quantas avaliações chegaram em cada mês. O número é a diferença do total de
                avaliações entre a primeira e a última leitura do mês.
              </p>
            </li>
            <li className="rounded-2xl border border-border bg-white p-5 shadow-premium">
              <p className="text-xs text-text-secondary">Tendência</p>
              {reputacao.tendencia !== null ? (
                <>
                  <p className={`text-3xl font-bold ${TENDENCIA[reputacao.tendencia].cor}`}>
                    {TENDENCIA[reputacao.tendencia].rotulo}
                  </p>
                  {reputacao.nota_mes_anterior !== null && (
                    <p className="text-sm text-text-secondary">
                      {formatarNota(reputacao.nota_mes_anterior, reputacao.escala)} no fim do mês anterior
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-text-secondary">Sem leitura do mês anterior para comparar.</p>
              )}
            </li>
          </ul>
          <GraficoDoMesDaNota
            doMes={reputacao.leituras_do_mes}
            anterior={reputacao.leituras_mes_anterior}
            escala={reputacao.escala}
            nota={reputacao.nota}
            notaAnterior={reputacao.nota_mes_anterior}
            tendencia={reputacao.tendencia}
          />
        </>
      )}
    </div>
  );
}

function TesteDoConvite({ convite }: { convite: NonNullable<NotaNoGooglePayload["convite"]> }) {
  return (
    <section aria-labelledby="titulo-do-convite" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 id="titulo-do-convite" className="text-lg font-semibold text-text">
            Teste do convite ao Google no QR
          </h2>
          <p className="text-sm text-text-secondary">
            {convite.ligado
              ? `O convite está ligado${
                  convite.ligado_em ? ` desde ${formatarDia(convite.ligado_em)}` : ""
                }${convite.dias_ligado !== null ? `, há ${convite.dias_ligado} dias` : ""}. Aparece para as notas 4 e 5, nos pontos com a chave ligada.`
              : "O convite ao Google está desligado. Só a diretoria executiva liga, na tela Pontos de escuta da Ouvidoria."}
          </p>
        </div>
        <SeletorDePeriodo ativo={convite.periodo} caminho={`${CAMINHO_OBJETIVOS}/${OBJETIVO_NOTA_NO_GOOGLE}`} />
      </div>

      {convite.reavaliar && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <p className="text-sm">
            O teste passou de {convite.dias_do_teste} dias. Hora de reavaliar: compare a taxa de clique com a nota do
            Google. O convite não se desliga sozinho e continua aparecendo até a diretoria executiva desligar.
          </p>
        </div>
      )}

      <div className="overflow-x-auto rounded-2xl border border-border bg-white shadow-premium">
        <table aria-label="Convites ao Google por ponto" className="w-full text-sm">
          <caption className="px-5 pt-4 text-left text-xs text-text-secondary">
            De {formatarData(convite.intervalo.inicio)} a {formatarData(convite.intervalo.fim)}. A taxa de clique é
            quantos dos convites exibidos viraram clique no Avaliar no Google.
          </caption>
          <thead>
            <tr className="text-left text-xs text-text-secondary">
              <th scope="col" className="px-5 py-3 font-medium">Ponto</th>
              <th scope="col" className="px-5 py-3 text-right font-medium">Convites</th>
              <th scope="col" className="px-5 py-3 text-right font-medium">Cliques</th>
              <th scope="col" className="px-5 py-3 text-right font-medium">Taxa de clique</th>
            </tr>
          </thead>
          <tbody>
            {convite.pontos.map((ponto) => (
              <tr key={ponto.ponto_id} className="border-t border-border">
                <td className="px-5 py-3 text-text">{ponto.nome}</td>
                <td className="px-5 py-3 text-right tabular-nums">{formatarInteiro(ponto.convites)}</td>
                <td className="px-5 py-3 text-right tabular-nums">{formatarInteiro(ponto.cliques)}</td>
                <td className="px-5 py-3 text-right tabular-nums">{formatarTaxa(ponto.taxa)}</td>
              </tr>
            ))}
            <tr className="border-t border-border font-semibold">
              <td className="px-5 py-3 text-text">Total</td>
              <td className="px-5 py-3 text-right tabular-nums">{formatarInteiro(convite.total.convites)}</td>
              <td className="px-5 py-3 text-right tabular-nums">{formatarInteiro(convite.total.cliques)}</td>
              <td className="px-5 py-3 text-right tabular-nums">{formatarTaxa(convite.total.taxa)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
