"use client";

/**
 * A tela Dados do Google da Central de Comando (issue #817, PRD #809, ADR 0058).
 *
 * Pede ao backend o payload inteiro da tela e desenha o que veio: a série dia
 * a dia, as fatias e as datas são conta do backend, e a tela não compõe
 * chamadas. Um bloco do payload, um bloco da tela:
 *
 * - Movimento do site: os Visitantes por dia do período, ao lado do período
 *   anterior (`GraficoVisitantesPorDia`);
 * - Por dispositivo: as Visitas no celular, no computador e no tablet
 *   (`GraficoDispositivos`).
 *
 * A #818 acrescenta aqui os blocos dela (Áreas do site, Origem do público e
 * Contatos gerados), no mesmo payload e no mesmo molde.
 *
 * O frescor é o da #815, sem componente novo: a leitura, o Atualizar agora e
 * a renovação de hora em hora moram no `useTelaDaCentral`, e a
 * `BarraDeFrescor` fica em cima dos blocos. Os dados só saem do backend, que
 * exige Super admin em toda rota: esta tela não confia no guard do
 * `layout.tsx` para nada.
 *
 * Honestidade do dado, como na Visão Geral: sem credencial (503 com a frase
 * do backend) ou com a fonte fora e nada guardado (502), a tela diz o que
 * houve e não desenha gráfico nenhum; com a fonte fora e números guardados, o
 * backend manda o último valor bom, e a barra avisa que não atualizou. Vale
 * para a tela inteira, como na Visão Geral até a #821.
 */

import { AlertTriangle, ChartLine, Loader2, PlugZap } from "lucide-react";

import type { Frescor } from "@/lib/central-de-comando/api";
import { formatarData } from "@/lib/central-de-comando/formato";
import { temAnterior } from "@/lib/central-de-comando/graficos";
import type { Periodo } from "@/lib/central-de-comando/periodo";

import { BarraDeFrescor } from "./BarraDeFrescor";
import type { PeriodoDoPayload } from "./BlocoVisitantes";
import { GraficoDispositivos, type DispositivoDoPayload } from "./GraficoDispositivos";
import { GraficoVisitantesPorDia, type PontoDoMovimento } from "./GraficoVisitantesPorDia";
import { SeletorDePeriodo } from "./SeletorDePeriodo";
import { useTelaDaCentral } from "./useTelaDaCentral";

export const CAMINHO_DADOS_DO_GOOGLE = "/admin/central-de-comando/dados-do-google";

/** O que `GET /api/admin/central-de-comando/dados-do-google` devolve. */
export type DadosDoGooglePayload = {
  periodo: PeriodoDoPayload;
  movimento: PontoDoMovimento[];
  dispositivos: DispositivoDoPayload[];
  frescor: Frescor;
};

export function DadosDoGoogle({ periodo }: { periodo: Periodo }) {
  const { estado, atualizando, aviso, atualizarAgora } = useTelaDaCentral<DadosDoGooglePayload>(
    "dados-do-google",
    periodo,
  );

  return (
    <div className="animate-fade-in-up space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary">
            <ChartLine className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Dados do Google</h1>
            <p className="text-sm text-text-secondary">
              Central de Comando: o movimento do Site, direto do Google Analytics.
            </p>
          </div>
        </div>
        <SeletorDePeriodo ativo={periodo} caminho={CAMINHO_DADOS_DO_GOOGLE} />
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
            <Bloco id="central-movimento" titulo="Movimento do site" dica={`Visitantes por dia · últimos ${estado.dados.periodo.dias} dias`}>
              <GraficoVisitantesPorDia pontos={estado.dados.movimento} />
              <DatasDoMovimento periodo={estado.dados.periodo} comAnterior={temAnterior(estado.dados.movimento)} />
            </Bloco>
            <Bloco
              id="central-dispositivos"
              titulo="Por dispositivo"
              dica="Onde o público navega: as Visitas do período em cada tipo de aparelho"
            >
              <GraficoDispositivos dispositivos={estado.dados.dispositivos} />
            </Bloco>
            <p className="text-xs text-text-secondary">
              Números do Google Analytics. Os Visitantes por dia contam as pessoas de cada dia, e quem volta em outro
              dia conta de novo; Por dispositivo conta as Visitas, as idas ao Site.
            </p>
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

/**
 * As datas do Movimento do site, para conferir com o Google. Quando o período
 * anterior não teve visita, o gráfico não desenha a linha dele, e a frase diz
 * isso em vez de prometer uma comparação que não está na tela.
 */
function DatasDoMovimento({ periodo, comAnterior }: { periodo: PeriodoDoPayload; comAnterior: boolean }) {
  const atual = `${formatarData(periodo.atual.inicio)} a ${formatarData(periodo.atual.fim)}`;
  const anterior = `${formatarData(periodo.anterior.inicio)} a ${formatarData(periodo.anterior.fim)}`;
  return (
    <p className="text-xs text-text-secondary">
      {comAnterior
        ? `De ${atual}, ao lado do período anterior, de ${anterior}.`
        : `De ${atual}. O período anterior, de ${anterior}, não teve visita.`}
    </p>
  );
}

/** Um bloco da tela: o cartão com o título, a dica do que o número conta e o gráfico. */
function Bloco({
  id,
  titulo,
  dica,
  children,
}: {
  id: string;
  titulo: string;
  dica: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="space-y-4 rounded-2xl border border-border bg-white p-6 shadow-premium">
      <div className="space-y-1">
        <h2 id={id} className="text-lg font-bold text-text">
          {titulo}
        </h2>
        <p className="text-xs text-text-secondary">{dica}</p>
      </div>
      {children}
    </section>
  );
}
