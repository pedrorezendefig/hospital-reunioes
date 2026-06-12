"use client";

import { MessageSquareWarning } from "lucide-react";
import { ETAPA_DEVOLUCAO_LABELS, type PopDevolucao } from "@/types";

/**
 * Histórico de Devoluções de uma Versão (issue #85) — comentários com nome,
 * etapa e timestamp. A mais recente vem aberta em destaque (é a pauta da
 * correção); as anteriores ficam recolhidas. Usado na tela de elaboração
 * (o Elaborador ajusta o que foi pedido) e na leitura da Revisão/Validação
 * (auditoria do histórico — user story 26).
 */
export default function DevolucoesPanel({
  devolucoes,
  mounted = true,
}: {
  /** Da mais recente para a mais antiga (ordem do backend). */
  devolucoes: PopDevolucao[];
  /** true quando já montou no client — habilita a formatação de data pt-BR. */
  mounted?: boolean;
}) {
  if (devolucoes.length === 0) return null;
  const [atual, ...anteriores] = devolucoes;

  const dataFmt = (iso: string | null) =>
    mounted && iso
      ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
      : "—";

  return (
    <section className="bg-amber-50 rounded-2xl border border-amber-200 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-amber-100 flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center">
          <MessageSquareWarning className="w-4 h-4 text-amber-700" />
        </div>
        <div>
          <h2 className="text-sm font-bold text-amber-900">
            Devolvido na {ETAPA_DEVOLUCAO_LABELS[atual.etapa_retorno]}
          </h2>
          <p className="text-xs text-amber-700/80">
            {atual.autor_nome || atual.autor_id} · {dataFmt(atual.created_at)} — no reenvio, a Versão volta direto
            para essa etapa
          </p>
        </div>
      </div>
      <div className="px-5 py-4">
        <p className="text-sm text-amber-900 leading-relaxed whitespace-pre-wrap">{atual.comentarios}</p>

        {anteriores.length > 0 && (
          <details className="mt-3">
            <summary className="text-xs font-semibold text-amber-700 cursor-pointer hover:text-amber-900 transition-colors">
              Devoluções anteriores ({anteriores.length})
            </summary>
            <ul className="mt-2 space-y-2">
              {anteriores.map((d) => (
                <li key={d.id} className="bg-white/60 rounded-lg border border-amber-100 px-3.5 py-2.5">
                  <p className="text-[11px] font-semibold text-amber-700">
                    {ETAPA_DEVOLUCAO_LABELS[d.etapa_retorno]} · {d.autor_nome || d.autor_id} · {dataFmt(d.created_at)}
                  </p>
                  <p className="text-sm text-amber-900/90 mt-1 whitespace-pre-wrap">{d.comentarios}</p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}
