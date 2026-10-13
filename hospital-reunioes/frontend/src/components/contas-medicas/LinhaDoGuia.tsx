"use client";

/**
 * Uma linha do Guia da faturista (issue #1121, PRD #1113, ADR 0070).
 *
 * Verbo na frente, quantidade, período, valor com sinal e o código que copia
 * com um clique. Aberta, tem Feito, Não procede e Bloqueado; marcada, recolhe
 * com a cor do estado e o Desfazer. A linha Validar não tem botão: o item já
 * foi para a validação. A tela não decide nada; quem recusa é o servidor.
 */

import { useState } from "react";
import { Copy } from "lucide-react";

import {
  type LinhaGuia,
  type MotivoNaoProcede,
  MOTIVOS_NAO_PROCEDE,
  ROTULO_ACAO,
  ROTULO_NIVEL,
  reais,
  textoDaLinha,
  valorComSinal,
} from "@/lib/contas-medicas/guia";

export interface Marcacao {
  estado: "FEITO" | "NAO_PROCEDE" | "BLOQUEADO";
  motivo?: MotivoNaoProcede;
  texto?: string;
}

interface Props {
  linha: LinhaGuia;
  concluida: boolean;
  ocupado: boolean;
  onMarcar: (marcacao: Marcacao) => void;
  onDesfazer: () => void;
  onCopiar: (codigo: string) => void;
}

const ETIQUETA = "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-[0.04em]";

const ESTADO_MARCADO: Record<string, { rotulo: string; cor: string; fundo: string }> = {
  FEITO: { rotulo: "Feito", cor: "bg-[#DCFCE7] text-[#166534]", fundo: "bg-[#F0FDF4] border-[#BBF7D0]" },
  NAO_PROCEDE: { rotulo: "Não procede", cor: "bg-[#F1F5F9] text-[#475569]", fundo: "bg-slate-50 border-border" },
  BLOQUEADO: { rotulo: "Bloqueado", cor: "bg-[#FEF3C7] text-[#92400E]", fundo: "bg-[#FFFBEB] border-[#FDE68A]" },
};

const BOTAO = "px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-[0.04em] disabled:opacity-50";

export function LinhaDoGuia({ linha, concluida, ocupado, onMarcar, onDesfazer, onCopiar }: Props) {
  const [evidenciaAberta, setEvidenciaAberta] = useState(false);
  const [naoProcedeAberto, setNaoProcedeAberto] = useState(false);
  const [motivo, setMotivo] = useState<MotivoNaoProcede | null>(null);
  const [texto, setTexto] = useState("");

  const nome = linha.descricao ?? linha.codigo ?? "Linha do guia";
  const validar = linha.acao === "VALIDAR";
  const marcado = ESTADO_MARCADO[linha.estado];
  // A Validação decidiu (issue #1142): com ação, volta para a faturista lançar;
  // sem ação (Validar descartado), não há nada a fazer no MV.
  const decidida = linha.estado === "DECIDIDA";

  const codigo = linha.codigo ? (
    <button
      type="button"
      aria-label={`Copiar código ${linha.codigo}`}
      onClick={() => onCopiar(linha.codigo as string)}
      className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
    >
      {linha.codigo}
      <Copy className="w-3 h-3" aria-hidden="true" />
    </button>
  ) : null;

  if (marcado && !validar) {
    return (
      <article aria-label={nome} className={`rounded-xl border px-3 py-2 ${marcado.fundo}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`${ETIQUETA} ${marcado.cor}`}>{marcado.rotulo}</span>
          <span className="text-sm text-slate-700 min-w-0 break-words">{nome}</span>
          {codigo}
          {linha.valor_diferenca != null && (
            <span className="ml-auto text-sm text-slate-500">{valorComSinal(linha.valor_diferenca)}</span>
          )}
          {!concluida && (
            <button
              type="button"
              onClick={onDesfazer}
              disabled={ocupado}
              className="text-xs font-semibold text-primary hover:underline disabled:opacity-50"
            >
              Desfazer
            </button>
          )}
        </div>
      </article>
    );
  }

  const textoObrigatorio = motivo === "OUTRO";
  const podeConfirmar = motivo !== null && (!textoObrigatorio || texto.trim() !== "");

  function confirmarNaoProcede() {
    if (!motivo) return;
    const limpo = texto.trim();
    onMarcar({ estado: "NAO_PROCEDE", motivo, ...(limpo ? { texto: limpo } : {}) });
    setNaoProcedeAberto(false);
  }

  return (
    <article
      aria-label={nome}
      className="rounded-xl border border-border bg-white px-3 py-3 space-y-1.5 min-w-0"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`${ETIQUETA} ${validar ? "bg-[#FEF3C7] text-[#92400E]" : "bg-[#EEEEF6] text-primary"}`}
        >
          {ROTULO_ACAO[linha.acao]}
        </span>
        {decidida && !validar && (
          <span className={`${ETIQUETA} bg-[#FEF3C7] text-[#92400E]`}>Decidida na validação</span>
        )}
        {linha.nao_conferido &&<span className={`${ETIQUETA} bg-[#F1F5F9] text-[#475569]`}>Não conferido</span>}
        {linha.confianca === "BAIXA" && (
          <span className={`${ETIQUETA} bg-[#FEF3C7] text-[#92400E]`}>conferir evidência</span>
        )}
        {!validar && linha.valor_diferenca != null && (
          <span className="ml-auto text-sm font-semibold text-slate-900">
            {valorComSinal(linha.valor_diferenca)}
          </span>
        )}
      </div>

      <p className="text-sm font-semibold text-slate-900 break-words">{nome}</p>
      <p className="text-sm text-slate-700 break-words">{textoDaLinha(linha)}</p>
      {linha.motivo && <p className="text-xs text-slate-500 break-words">{linha.motivo}</p>}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        {codigo}
        {linha.regra_codigo && <span>Regra {linha.regra_codigo}</span>}
        {(linha.evidencia_pagina != null || linha.evidencia_trecho) && (
          <button
            type="button"
            aria-expanded={evidenciaAberta}
            onClick={() => setEvidenciaAberta((aberta) => !aberta)}
            className="text-primary hover:underline"
          >
            Ver evidência
          </button>
        )}
      </div>

      {evidenciaAberta && (
        <div className="rounded-lg bg-slate-50 border border-border px-3 py-2 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            {linha.evidencia_pagina != null && (
              <span className="text-xs font-semibold text-slate-700">Prontuário, p. {linha.evidencia_pagina}</span>
            )}
            {linha.nivel_evidencia && (
              <span className={`${ETIQUETA} bg-[#EEEEF6] text-primary`}>{ROTULO_NIVEL[linha.nivel_evidencia]}</span>
            )}
          </div>
          {linha.evidencia_trecho && (
            <blockquote className="text-xs text-slate-600 break-words border-l-2 border-border pl-2">
              {linha.evidencia_trecho}
            </blockquote>
          )}
        </div>
      )}

      {validar && decidida ? (
        <p className="text-xs text-slate-500">Decidida na validação, sem ação no MV</p>
      ) : validar ? (
        <div className="text-xs text-[#92400E] space-y-0.5">
          <p>Você não precisa decidir: o item já foi para a validação</p>
          {linha.valor_diferenca != null && (
            <p className="font-semibold">Em jogo: R$ {reais(Math.abs(linha.valor_diferenca))}</p>
          )}
        </div>
      ) : (
        !concluida && (
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={() => onMarcar({ estado: "FEITO" })}
              disabled={ocupado}
              className={`${BOTAO} bg-primary text-white`}
            >
              Feito
            </button>
            <button
              type="button"
              onClick={() => setNaoProcedeAberto((aberto) => !aberto)}
              disabled={ocupado}
              className={`${BOTAO} border border-border text-slate-700 bg-white`}
            >
              Não procede
            </button>
            <button
              type="button"
              onClick={() => onMarcar({ estado: "BLOQUEADO" })}
              disabled={ocupado}
              className={`${BOTAO} border border-border text-slate-700 bg-white`}
            >
              Bloqueado
            </button>
          </div>
        )
      )}

      {naoProcedeAberto && !validar && !concluida && (
        <fieldset className="rounded-lg border border-border px-3 py-2 space-y-2">
          <legend className="px-1 text-xs font-semibold text-slate-700">Por que não procede?</legend>
          <div className="flex flex-col gap-1">
            {MOTIVOS_NAO_PROCEDE.map((opcao) => (
              <label key={opcao.valor} className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="radio"
                  name={`motivo-${linha.id}`}
                  value={opcao.valor}
                  checked={motivo === opcao.valor}
                  onChange={() => setMotivo(opcao.valor)}
                />
                {opcao.rotulo}
              </label>
            ))}
          </div>
          <textarea
            aria-label="Motivo do Não procede"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder={textoObrigatorio ? "Escreva o motivo" : "Conte mais, se quiser"}
            rows={2}
            className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-label="Confirmar Não procede"
              onClick={confirmarNaoProcede}
              disabled={!podeConfirmar || ocupado}
              className={`${BOTAO} bg-primary text-white`}
            >
              Confirmar
            </button>
            <button
              type="button"
              onClick={() => setNaoProcedeAberto(false)}
              className={`${BOTAO} border border-border text-slate-700 bg-white`}
            >
              Cancelar
            </button>
          </div>
        </fieldset>
      )}
    </article>
  );
}
