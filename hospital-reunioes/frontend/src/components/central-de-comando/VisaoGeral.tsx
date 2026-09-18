"use client";

/**
 * A tela Visão Geral da Central de Comando (issue #814, PRD #809, ADR 0058).
 *
 * Pede ao backend o payload inteiro da tela e desenha o que veio: a conta
 * (variação, datas do período) é do backend, e a tela não compõe chamadas.
 *
 * Um bloco do payload, um componente. Nesta fatia é o número-manchete dos
 * Visitantes; as seguintes acrescentam os seus (o frescor e o Atualizar agora,
 * o Ao vivo, o contexto do número, o Instagram num relance, os Objetivos em
 * foco e "O que vem por aí") no mesmo molde, abaixo do que já existe.
 *
 * Honestidade do dado: sem credencial (503) ou com a fonte fora (502), a tela
 * diz o que houve com a frase do servidor e não desenha número nenhum.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, LayoutDashboard, Loader2, PlugZap } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";
import { BASE_CENTRAL, FALHA_DE_CONEXAO, SEM_SESSAO, lerRecusa, type Recusa } from "@/lib/central-de-comando/api";
import type { Periodo } from "@/lib/central-de-comando/periodo";

import { BlocoVisitantes, type PeriodoDoPayload, type VisitantesDoPayload } from "./BlocoVisitantes";
import { SeletorDePeriodo } from "./SeletorDePeriodo";

export const CAMINHO_VISAO_GERAL = "/admin/central-de-comando/visao-geral";

/** O que `GET /api/admin/central-de-comando/visao-geral` devolve. */
export type VisaoGeralPayload = {
  periodo: PeriodoDoPayload;
  visitantes: VisitantesDoPayload;
};

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; dados: VisaoGeralPayload }
  | Recusa
  | { tipo: "sem-conexao"; mensagem: string };

export function VisaoGeral({ periodo }: { periodo: Periodo }) {
  const { token, loading: carregandoAuth } = useAuth();
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    // O `useAuth` começa sem token e com `loading`: acusar falta de sessão
    // antes de ele terminar seria alarme falso em toda abertura da tela.
    if (carregandoAuth) return;
    if (!token) {
      setEstado({ tipo: "sem-conexao", mensagem: SEM_SESSAO });
      return;
    }

    // Trocar de período no meio de uma resposta lenta não pode deixar a tela
    // com o número do período anterior: a resposta velha é descartada.
    let descartada = false;
    setEstado({ tipo: "carregando" });
    (async () => {
      try {
        const resposta = await fetch(`${BASE_CENTRAL}/visao-geral?periodo=${periodo}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const proximo: Estado = resposta.ok
          ? { tipo: "pronto", dados: (await resposta.json()) as VisaoGeralPayload }
          : await lerRecusa(resposta);
        if (!descartada) setEstado(proximo);
      } catch (e) {
        console.error("[central-de-comando/visao-geral] falha ao carregar", e);
        if (!descartada) setEstado({ tipo: "sem-conexao", mensagem: FALHA_DE_CONEXAO });
      }
    })();
    return () => {
      descartada = true;
    };
  }, [carregandoAuth, token, periodo]);

  return (
    <div className="animate-fade-in-up space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary">
            <LayoutDashboard className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Visão Geral</h1>
            <p className="text-sm text-text-secondary">Central de Comando: o Site do hospital num só relance.</p>
          </div>
        </div>
        <SeletorDePeriodo ativo={periodo} caminho={CAMINHO_VISAO_GERAL} />
      </header>

      {estado.tipo === "carregando" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-2xl border border-border bg-white p-6 text-sm text-text-secondary shadow-premium"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando os números do Site
        </div>
      )}

      {estado.tipo === "pronto" && (
        <BlocoVisitantes periodo={estado.dados.periodo} visitantes={estado.dados.visitantes} />
      )}

      {estado.tipo === "nao-configurado" && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Sem ligação com o Google Analytics</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {(estado.tipo === "falhou" || estado.tipo === "sem-conexao") && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível buscar os números do Site agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}
