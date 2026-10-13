"use client";

/**
 * Um lembrete da Conferência da coordenação (issue #1143): o cenário, a data e
 * o setor, a orientação, "Ver evidência", os insumos que faltam com o código
 * que copia com um clique, a quantidade sugerida e o valor, e os dois botões
 * de um clique (Incluído e Não se aplica) com a observação opcional.
 */

import { useState } from "react";
import { Copy } from "lucide-react";

import { Ditar, juntarDitado } from "@/components/contas-medicas/Ditar";
import { type EstadoDaMarcacao, type Lembrete, dataESetor } from "@/lib/contas-medicas/coordenacao";
import { reais } from "@/lib/contas-medicas/guia";

const ETIQUETA = "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-[0.04em]";
const BOTAO = "px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-[0.04em] disabled:opacity-50";
const QUANTIDADE = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });

interface Props {
  lembrete: Lembrete;
  ocupado: boolean;
  onMarcar: (estado: EstadoDaMarcacao, observacao: string | null) => void;
  onCopiar: (codigo: string) => void;
}

export function CartaoDoLembrete({ lembrete, ocupado, onMarcar, onCopiar }: Props) {
  const [evidenciaAberta, setEvidenciaAberta] = useState(false);
  const [observacao, setObservacao] = useState("");
  const nome = lembrete.cenario.nome ?? lembrete.cenario.codigo ?? "Lembrete";
  const temEvidencia = lembrete.evidencia_pagina != null || Boolean(lembrete.evidencia_trecho);

  function marcar(estado: EstadoDaMarcacao) {
    onMarcar(estado, observacao.trim() || null);
  }

  return (
    <article aria-label={nome} className="rounded-xl border border-border bg-white px-3 py-3 space-y-2 min-w-0">
      <div className="flex flex-wrap items-center gap-1.5">
        {lembrete.cenario.codigo && (
          <span className={`${ETIQUETA} bg-[#EEEEF6] text-primary`}>{lembrete.cenario.codigo}</span>
        )}
        {lembrete.etiquetas.map((etiqueta) => (
          <span key={etiqueta} className={`${ETIQUETA} bg-[#FEF3C7] text-[#92400E]`}>
            {etiqueta}
          </span>
        ))}
      </div>
      <p className="text-sm font-semibold text-slate-900 break-words">{nome}</p>
      {dataESetor(lembrete) && <p className="text-sm text-slate-700">{dataESetor(lembrete)}</p>}
      {lembrete.cenario.orientacao && (
        <p className="text-xs text-slate-500 break-words">{lembrete.cenario.orientacao}</p>
      )}

      {temEvidencia && (
        <button
          type="button"
          aria-expanded={evidenciaAberta}
          onClick={() => setEvidenciaAberta((aberta) => !aberta)}
          className="text-xs text-primary hover:underline"
        >
          Ver evidência
        </button>
      )}
      {evidenciaAberta && (
        <div className="rounded-lg bg-slate-50 border border-border px-3 py-2 space-y-1">
          {lembrete.evidencia_pagina != null && (
            <span className="text-xs font-semibold text-slate-700">Prontuário, p. {lembrete.evidencia_pagina}</span>
          )}
          {lembrete.evidencia_trecho && (
            <blockquote className="text-xs text-slate-600 break-words border-l-2 border-border pl-2">
              {lembrete.evidencia_trecho}
            </blockquote>
          )}
        </div>
      )}

      <ul aria-label="Insumos que faltam" className="divide-y divide-border rounded-lg border border-border">
        {lembrete.insumos.map((insumo) => (
          <li key={insumo.codigo} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
            <button
              type="button"
              aria-label={`Copiar código ${insumo.codigo}`}
              onClick={() => onCopiar(insumo.codigo)}
              className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
            >
              {insumo.codigo}
              <Copy className="w-3 h-3" aria-hidden="true" />
            </button>
            <span className="min-w-0 flex-1 break-words text-slate-700">{insumo.descricao}</span>
            {insumo.quantidade != null && (
              <span className="text-xs text-slate-500">Qtd. {QUANTIDADE.format(insumo.quantidade)}</span>
            )}
            <span className="text-sm font-semibold text-slate-900">
              {insumo.valor != null ? `R$ ${reais(insumo.valor)}` : "sem preço na tabela"}
            </span>
          </li>
        ))}
      </ul>

      <label className="block text-xs text-slate-600">
        Observação (opcional)
        <textarea
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          rows={2}
          maxLength={1000}
          className="mt-1 w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        />
      </label>
      <Ditar
        campo="Observação do lembrete"
        aoTranscrever={(ditado) => setObservacao((atual) => juntarDitado(atual, ditado).slice(0, 1000))}
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => marcar("INCLUIDO")}
          disabled={ocupado}
          className={`${BOTAO} bg-[#DCFCE7] text-[#166534]`}
        >
          Incluído
        </button>
        <button
          type="button"
          onClick={() => marcar("NAO_SE_APLICA")}
          disabled={ocupado}
          className={`${BOTAO} bg-[#F1F5F9] text-[#475569]`}
        >
          Não se aplica
        </button>
      </div>
    </article>
  );
}
