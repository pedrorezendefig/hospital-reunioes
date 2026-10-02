"use client";

/**
 * A tela Visão Geral da Central de Comando (issue #821, PRD #809, ADR 0058).
 *
 * O panorama da Central num relance: o número-manchete e o contexto dele, o
 * Instagram num relance, os Objetivos em foco, os atalhos para as outras telas e
 * o "O que vem por aí". Pede ao backend o payload inteiro e desenha o que veio;
 * a conta é do backend, a tela só escreve.
 *
 * **Cada bloco degrada sozinho (issue #821).** O backend responde 200 com um
 * `estado` por bloco de fonte: se a fonte de um bloco falha, o bloco mostra o
 * estado calmo (`nao-configurado`) ou o erro honesto (`sem-dado`), e os outros
 * quatro seguem. Nenhum bloco derruba a tela. Os atalhos e o "O que vem por aí"
 * são conteúdo fixo, sempre presentes.
 *
 * O frescor (issue #815) é combinado dos blocos: a `BarraDeFrescor` fica em cima,
 * e o aviso do último valor bom vale para a tela. Só uma falha de transporte (a
 * rede fora, o servidor sem responder) troca a tela inteira por um aviso, porque
 * aí não há payload nenhum para desenhar.
 */

import { AlertTriangle, LayoutDashboard, Loader2, PlugZap } from "lucide-react";

import type { Frescor } from "@/lib/central-de-comando/api";
import type { Periodo } from "@/lib/central-de-comando/periodo";

import { Atalhos } from "./Atalhos";
import { BarraDeFrescor } from "./BarraDeFrescor";
import { BlocoVisitantes, type PeriodoDoPayload, type VisitantesDoPayload } from "./BlocoVisitantes";
import { IndicadorAoVivo } from "./IndicadorAoVivo";
import { InstagramNumRelance, type InstagramDeRelance } from "./InstagramNumRelance";
import { ObjetivosEmFoco, type ObjetivoEmFoco } from "./ObjetivosEmFoco";
import { OQueVemPorAi } from "./OQueVemPorAi";
import { SeletorDePeriodo } from "./SeletorDePeriodo";
import { useTelaDaCentral } from "./useTelaDaCentral";

export const CAMINHO_VISAO_GERAL = "/admin/central-de-comando/visao-geral";

/** O que `GET /api/admin/central-de-comando/visao-geral` devolve (issue #821). */
export type VisaoGeralPayload = {
  periodo: PeriodoDoPayload;
  visitantes: VisitantesDoPayload;
  instagram: InstagramDeRelance;
  objetivos: { em_foco: ObjetivoEmFoco[] };
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
          {/* O Ao vivo é tempo real e não passa pelo cache: fica fora do bloco
              que esmaece durante o Atualizar agora. Some sozinho sem número. */}
          <IndicadorAoVivo />
          <div className={`space-y-6 transition-opacity ${atualizando ? "pointer-events-none opacity-50" : ""}`}>
            <BlocoVisitantes periodo={estado.dados.periodo} visitantes={estado.dados.visitantes} />
            <InstagramNumRelance instagram={estado.dados.instagram} />
            <ObjetivosEmFoco objetivos={estado.dados.objetivos.em_foco} />
            <Atalhos />
            <OQueVemPorAi />
          </div>
        </>
      )}

      {estado.tipo === "nao-configurado" && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Central de Comando indisponível</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {(estado.tipo === "falhou" || estado.tipo === "sem-conexao") && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível abrir a Visão Geral agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}
