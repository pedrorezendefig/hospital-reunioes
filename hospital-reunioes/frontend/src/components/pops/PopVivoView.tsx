"use client";

import { Crosshair, FileText } from "lucide-react";
import {
  CRITICIDADE_POP_LABELS,
  SECOES_POP_CONTEUDO,
  type PopElaboracaoPopInfo,
  type RascunhoPop,
} from "@/types";

interface PopVivoViewProps {
  pop: PopElaboracaoPopInfo;
  numeroVersao: string;
  rascunho: RascunhoPop;
  /** Seção apontada (⌖), ou null. */
  sectionContext: string | null;
  /** Aponta uma seção — dirige a próxima mensagem do chat (padrão Ata Guiada). */
  onSectionContext?: (ctx: string) => void;
  /** true quando já montou no client — habilita a formatação de data pt-BR. */
  mounted?: boolean;
}

/** Botão-alvo (⌖) de "apontar seção" — mesmo padrão de UX da Ata Guiada (ADR 0006). */
function AlvoSecao({ ativo, onClick }: { ativo: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`p-1.5 rounded-lg transition-colors ${
        ativo ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"
      }`}
      title="Apontar para esta seção"
    >
      <Crosshair className="w-4 h-4" />
    </button>
  );
}

/**
 * O POP vivo (issue #83): as 11 seções do template institucional (DRF §4.2)
 * tomando forma ao vivo na conversa com o agente. A seção 1 (Identificação)
 * deriva do cadastro do POP — código travado, responsáveis — e é imune ao
 * agente; as seções 2–11 renderizam o rascunho persistido na Versão.
 * Componente apresentacional: dados entram, eventos de ⌖ saem (espelha o
 * AtaEnxutaView da Ata Guiada).
 */
export default function PopVivoView({
  pop,
  numeroVersao,
  rascunho,
  sectionContext,
  onSectionContext,
  mounted = true,
}: PopVivoViewProps) {
  const dataFmt =
    mounted && pop.created_at ? new Date(pop.created_at).toLocaleDateString("pt-BR") : "—";

  const identificacao: { rotulo: string; valor: string }[] = [
    { rotulo: "Código", valor: pop.codigo },
    { rotulo: "Setor", valor: pop.setor_nome ? `${pop.setor_nome} (${pop.setor_sigla})` : "—" },
    { rotulo: "Versão", valor: `v${numeroVersao}` },
    { rotulo: "Data de criação", valor: dataFmt },
    { rotulo: "Criticidade", valor: CRITICIDADE_POP_LABELS[pop.criticidade] },
    { rotulo: "Base normativa", valor: pop.base_normativa || "—" },
    { rotulo: "Elaborador", valor: pop.elaborador_nome || pop.elaborador_id },
    { rotulo: "Revisor", valor: pop.revisor_nome || pop.revisor_id },
    { rotulo: "Validador", valor: pop.validador_nome || pop.validador_id },
  ];

  return (
    <div className="space-y-4">
      {/* Seção 1 — Identificação (do sistema, imune ao agente) */}
      <section className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <FileText className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900">1. Identificação</h2>
            <p className="text-xs text-slate-400">Preenchida pelo sistema — código travado</p>
          </div>
        </div>
        <div className="px-5 py-4">
          <p className="text-base font-bold text-slate-900 mb-3">{pop.nome}</p>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2.5">
            {identificacao.map(({ rotulo, valor }) => (
              <div key={rotulo}>
                <dt className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{rotulo}</dt>
                <dd className="text-sm text-slate-700">{valor}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Seções 2–11 — conteúdo elaborado com o agente (rascunho persistido) */}
      {SECOES_POP_CONTEUDO.map(({ chave, titulo }, i) => {
        const conteudo = (rascunho[chave] || "").trim();
        const tituloNumerado = `${i + 2}. ${titulo}`;
        return (
          <section
            key={chave}
            className={`bg-white rounded-2xl border shadow-premium overflow-hidden transition-colors ${
              sectionContext === titulo ? "border-primary/40" : "border-border"
            }`}
          >
            <div className="px-5 py-3 border-b border-slate-50 flex items-center justify-between gap-3">
              <h2 className={`text-sm font-bold ${conteudo ? "text-slate-900" : "text-slate-400"}`}>
                {tituloNumerado}
              </h2>
              {onSectionContext && (
                <AlvoSecao ativo={sectionContext === titulo} onClick={() => onSectionContext(titulo)} />
              )}
            </div>
            <div className="px-5 py-4">
              {conteudo ? (
                <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{conteudo}</p>
              ) : (
                <p className="text-sm text-slate-300 italic">
                  Esta seção toma forma conforme a conversa com o agente.
                </p>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
