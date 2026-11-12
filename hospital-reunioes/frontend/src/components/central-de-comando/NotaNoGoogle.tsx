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
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, PlugZap } from "lucide-react";

import { getAuthToken } from "@/hooks/useAuth";
import { BASE_CENTRAL, FALHA_DE_CONEXAO, lerRecusa, SEM_SESSAO } from "@/lib/central-de-comando/api";
import { formatarInteiro } from "@/lib/central-de-comando/formato";
import { formatarNota } from "@/lib/ouvidoria/nota-externa";

import { CAMINHO_OBJETIVOS } from "./Objetivos";

export const OBJETIVO_NOTA_NO_GOOGLE = "google-reputacao";

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

export function NotaNoGoogle() {
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
        const resposta = await fetch(`${BASE_CENTRAL}/objetivos/${OBJETIVO_NOTA_NO_GOOGLE}`, {
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
  }, []);

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
            <p className="text-sm">A busca semanal da nota ainda não foi ligada. Quando for, a nota aparece aqui.</p>
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
        </>
      )}
    </div>
  );
}
