"use client";

/**
 * O painel lateral do Processamento de uma conta (issue #1418, PRD #1415).
 *
 * Abre pelo clique no cartão do envio: as cinco Etapas do processamento, cada
 * uma feita, em curso ou por fazer, com o tempo; a tentativa e a posição na
 * fila. A seção do custo da IA só é desenhada quando a resposta traz os campos,
 * e o servidor só os manda para quem tem "painel completo".
 */

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import {
  type DetalheDoProcessamento,
  type EtapaNoPainel,
  type ItemDaFila,
  MAXIMO_DE_TENTATIVAS,
  dolares,
  duracao,
  nomeDaEtapa,
  rotaDoProcessamento,
} from "@/lib/contas-medicas/envio";

const NUMERO = new Intl.NumberFormat("pt-BR");

const COR_DO_ESTADO: Record<EtapaNoPainel["estado"], string> = {
  feita: "bg-emerald-500",
  atual: "bg-[#1E40AF] animate-pulse",
  falta: "bg-slate-300",
};

function tempoDaEtapa(etapa: EtapaNoPainel): string {
  if (etapa.estado === "falta") return "por fazer";
  const tempo = etapa.tempo_s != null ? duracao(etapa.tempo_s) : null;
  if (etapa.estado === "atual") return tempo ? `em curso, ${tempo}` : "em curso";
  return tempo ?? "feita";
}

function LinhaDoCusto({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <dt className="text-slate-500">{rotulo}</dt>
      <dd className="text-right font-medium text-slate-900">{valor}</dd>
    </div>
  );
}

export function PainelDoProcessamento({
  conta,
  token,
  onFechar,
}: {
  conta: ItemDaFila;
  token: string;
  onFechar: () => void;
}) {
  const [detalhe, setDetalhe] = useState<DetalheDoProcessamento | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // Relê quando o cartão muda de situação, de etapa ou de parte.
  useEffect(() => {
    let vivo = true;
    fetch(rotaDoProcessamento(conta.id), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status));
        const corpo: DetalheDoProcessamento = await resposta.json();
        if (vivo) {
          setDetalhe(corpo);
          setErro(null);
        }
      })
      .catch(() => {
        if (vivo) setErro("Não consegui carregar o processamento desta conta.");
      });
    return () => {
      vivo = false;
    };
  }, [conta.id, conta.situacao, conta.etapa, conta.parte, token]);

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") onFechar();
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onFechar]);

  const comCusto = detalhe !== null && "custo_usd" in detalhe;
  const titulo = `Processamento do atendimento ${conta.numero_atendimento}`;
  return (
    <div className="fixed inset-0 z-[200]">
      <button type="button" aria-label="Fechar o painel" onClick={onFechar} className="absolute inset-0 bg-black/30" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="absolute right-0 top-0 h-full w-96 max-w-[90vw] overflow-y-auto border-l border-border bg-white p-5 shadow-premium-strong space-y-5"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-900">{titulo}</h2>
          <button
            type="button"
            onClick={onFechar}
            aria-label="Fechar"
            className="rounded-lg p-1 text-slate-500 hover:bg-slate-100"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {erro ? (
          <p role="alert" className="text-sm text-red-700">
            {erro}
          </p>
        ) : !detalhe ? (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Carregando
          </p>
        ) : (
          <>
            <ol aria-label="Etapas do processamento" className="space-y-2">
              {detalhe.etapas.map((etapa) => {
                const parte =
                  etapa.estado === "atual" && detalhe.parte && detalhe.partes
                    ? `, parte ${detalhe.parte} de ${detalhe.partes}`
                    : "";
                return (
                  <li key={etapa.etapa} data-estado={etapa.estado} className="flex items-center gap-3 text-sm">
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${COR_DO_ESTADO[etapa.estado]}`} aria-hidden="true" />
                    <span className={`flex-1 ${etapa.estado === "falta" ? "text-slate-500" : "text-slate-900"}`}>
                      {nomeDaEtapa(etapa.etapa) + parte}
                    </span>
                    <span className="text-xs text-slate-500">{tempoDaEtapa(etapa)}</span>
                  </li>
                );
              })}
            </ol>

            {(detalhe.tentativa || detalhe.posicao_na_fila) && (
              <p className="text-sm text-slate-600">
                {[
                  detalhe.posicao_na_fila ? `${detalhe.posicao_na_fila}ª na fila` : null,
                  detalhe.tentativa ? `tentativa ${detalhe.tentativa} de ${MAXIMO_DE_TENTATIVAS}` : null,
                ]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            )}

            {comCusto && (
              <section aria-label="Custo da IA" className="rounded-xl border border-border p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Custo da IA</h3>
                <dl className="space-y-1.5">
                  <LinhaDoCusto rotulo="Modelo" valor={detalhe.modelo || "sem chamada"} />
                  <LinhaDoCusto rotulo="Chamadas" valor={NUMERO.format(detalhe.chamadas ?? 0)} />
                  <LinhaDoCusto rotulo="Tokens de entrada" valor={NUMERO.format(detalhe.tokens_entrada ?? 0)} />
                  <LinhaDoCusto rotulo="Tokens de saída" valor={NUMERO.format(detalhe.tokens_saida ?? 0)} />
                  <LinhaDoCusto rotulo="Tokens do cache" valor={NUMERO.format(detalhe.tokens_cache ?? 0)} />
                  <LinhaDoCusto rotulo="Custo" valor={dolares(detalhe.custo_usd ?? 0)} />
                </dl>
              </section>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
