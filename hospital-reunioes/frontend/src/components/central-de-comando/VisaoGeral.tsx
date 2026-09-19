"use client";

/**
 * A tela Visão Geral da Central de Comando (issue #814, PRD #809, ADR 0058).
 *
 * Pede ao backend o payload inteiro da tela e desenha o que veio: a conta
 * (variação, datas do período) é do backend, e a tela não compõe chamadas.
 *
 * Um bloco do payload, um componente. Hoje é o número-manchete dos Visitantes;
 * as fatias seguintes acrescentam os seus (o Ao vivo, o contexto do número, o
 * Instagram num relance, os Objetivos em foco e "O que vem por aí") no mesmo
 * molde, abaixo do que já existe.
 *
 * O frescor (issue #815) é da tela inteira: a leitura, o Atualizar agora e a
 * renovação de hora em hora moram no `useTelaDaCentral`, e a `BarraDeFrescor`
 * fica em cima dos blocos. Enquanto um Atualizar agora está no ar, os blocos
 * esmaecem, mas continuam na tela.
 *
 * Honestidade do dado: sem credencial (503 com a frase do backend) ou com a
 * fonte fora e nada guardado (502), a tela diz o que houve com a frase do
 * servidor e não desenha número nenhum. Com a fonte fora e números guardados,
 * o backend manda o último valor bom, e a barra avisa que não atualizou. Hoje
 * isso vale para a tela INTEIRA: o backend responde um status só para o
 * payload todo, e um aviso substitui todos os blocos. Vale até a #821, que
 * passa a usar status por bloco.
 */

import { AlertTriangle, LayoutDashboard, Loader2, PlugZap } from "lucide-react";

import type { Frescor } from "@/lib/central-de-comando/api";
import type { Periodo } from "@/lib/central-de-comando/periodo";

import { BarraDeFrescor } from "./BarraDeFrescor";
import { BlocoVisitantes, type PeriodoDoPayload, type VisitantesDoPayload } from "./BlocoVisitantes";
import { SeletorDePeriodo } from "./SeletorDePeriodo";
import { useTelaDaCentral } from "./useTelaDaCentral";

export const CAMINHO_VISAO_GERAL = "/admin/central-de-comando/visao-geral";

/** O que `GET /api/admin/central-de-comando/visao-geral` devolve. */
export type VisaoGeralPayload = {
  periodo: PeriodoDoPayload;
  visitantes: VisitantesDoPayload;
  frescor: Frescor;
};

export function VisaoGeral({ periodo }: { periodo: Periodo }) {
  const { estado, atualizando, aviso, atualizarAgora } = useTelaDaCentral<VisaoGeralPayload>("visao-geral", periodo);

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
        <>
          <BarraDeFrescor
            frescor={estado.dados.frescor}
            atualizando={atualizando}
            aviso={aviso}
            onAtualizar={atualizarAgora}
          />
          <div className={`space-y-6 transition-opacity ${atualizando ? "pointer-events-none opacity-50" : ""}`}>
            <BlocoVisitantes periodo={estado.dados.periodo} visitantes={estado.dados.visitantes} />
          </div>
        </>
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
