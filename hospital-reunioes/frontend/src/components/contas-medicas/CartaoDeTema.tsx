"use client";

/**
 * Um cartão da fila de Validação (issue #1142, PRD #1129).
 *
 * O tema com a operadora, quantas contas, desde quando e o R$ em jogo, e os
 * botões do tipo dele. "Validar regra" e "Editar a regra" abrem o texto da
 * regra para conferir antes de gravar; "Responder ao time" abre o campo da
 * resposta. A tela não decide nada: quem grava e recusa é o servidor.
 */

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";

import { reais } from "@/lib/contas-medicas/guia";
import { dataBr, plural } from "@/lib/contas-medicas/operadoras";
import { type Decisao, ROTULO_DO_TIPO, type Tema } from "@/lib/contas-medicas/validacao";

const BOTAO =
  "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_SECUNDARIO =
  "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50";
const CAMPO =
  "w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white text-slate-800 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const ETIQUETA = "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-[0.04em]";

const COR_DO_TIPO: Record<Tema["tipo"], string> = {
  REGRA_PENDENTE: "bg-[#FEF3C7] text-[#92400E]",
  BLOQUEADO: "bg-[#FEE2E2] text-[#991B1B]",
  OBSERVACAO: "bg-[#EEEEF6] text-primary",
  DICIONARIO: "bg-[#F1F5F9] text-[#475569]",
};

type Aberto = "regra" | "resposta" | null;

interface Props {
  tema: Tema;
  ocupado: boolean;
  onDecidir: (decisao: Decisao, corpo?: { texto?: string }) => void;
  onEnviarAoCadastro: () => void;
}

export function CartaoDeTema({ tema, ocupado, onDecidir, onEnviarAoCadastro }: Props) {
  const [aberto, setAberto] = useState<Aberto>(null);
  const [texto, setTexto] = useState("");

  function abrir(qual: Aberto) {
    setTexto(qual === "regra" ? (tema.regra?.texto ?? "") : "");
    setAberto(qual);
  }

  const detalhes = [
    tema.operadora,
    tema.tipo !== "DICIONARIO" ? plural(tema.contas, "conta", "contas") : null,
    tema.desde ? `desde ${dataBr(tema.desde)}` : null,
  ].filter(Boolean);

  return (
    <article aria-label={tema.titulo} className="bg-white rounded-2xl border border-border shadow-premium p-5 space-y-3">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <span className={`${ETIQUETA} ${COR_DO_TIPO[tema.tipo]}`}>{ROTULO_DO_TIPO[tema.tipo]}</span>
          <h2 className="text-base font-semibold text-slate-900 break-words">{tema.titulo}</h2>
          <p className="text-xs text-slate-500">{detalhes.join(" · ")}</p>
        </div>
        {tema.tipo !== "DICIONARIO" && (
          <p className="text-right">
            <span className="block text-[11px] font-semibold uppercase tracking-[0.04em] text-slate-500">Em jogo</span>
            <span className="text-lg font-bold text-primary">R$ {reais(tema.valor)}</span>
          </p>
        )}
      </div>

      {tema.regra && (
        <blockquote className="text-sm text-slate-700 border-l-2 border-border pl-3 whitespace-pre-line break-words">
          {tema.regra.texto}
        </blockquote>
      )}

      {tema.dicionario && (
        <p className="text-sm text-slate-700">
          <span className="font-semibold">{tema.dicionario.termo}</span> liga ao código{" "}
          <span className="font-mono">{tema.dicionario.codigo_conta ?? "sem código"}</span>
          {tema.dicionario.descricao_conta && <> ({tema.dicionario.descricao_conta})</>}
        </p>
      )}

      {tema.observacoes.length > 0 && (
        <ul className="space-y-1 text-sm text-slate-700">
          {tema.observacoes.map((fala, i) => (
            <li key={i} className="rounded-lg bg-slate-50 px-3 py-1.5 break-words">
              {fala}
            </li>
          ))}
        </ul>
      )}

      {tema.tipo === "OBSERVACAO" && (
        <p className="flex items-start gap-2 text-sm text-slate-600">
          <Sparkles className="w-4 h-4 mt-0.5 shrink-0 text-primary" aria-hidden="true" />
          <span>
            <span className="font-semibold text-slate-700">Leitura da IA: </span>
            {tema.leitura_ia ?? "lendo as observações..."}
            <span className="block text-xs text-slate-500">É apoio: quem decide é você.</span>
          </span>
        </p>
      )}

      {aberto === "regra" && (
        <form
          aria-label={`Editar a regra ${tema.regra_codigo ?? ""}`}
          onSubmit={(e) => {
            e.preventDefault();
            onDecidir(tema.tipo === "REGRA_PENDENTE" ? "VALIDAR_REGRA" : "EDITAR_REGRA", { texto: texto.trim() });
          }}
          className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2"
        >
          <p className="text-xs font-medium text-slate-500 uppercase">Texto da regra {tema.regra_codigo}</p>
          <textarea
            aria-label="Texto da regra"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={3}
            className={CAMPO}
          />
          <p className="text-xs text-slate-500">Gravar cria uma versão nova da memória da operadora.</p>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={!texto.trim() || ocupado} className={BOTAO}>
              {ocupado && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {tema.tipo === "REGRA_PENDENTE" ? "Confirmar e validar" : "Salvar a regra"}
            </button>
            <button type="button" onClick={() => setAberto(null)} className={BOTAO_SECUNDARIO}>
              Cancelar
            </button>
          </div>
        </form>
      )}

      {aberto === "resposta" && (
        <form
          aria-label="Responder ao time"
          onSubmit={(e) => {
            e.preventDefault();
            onDecidir("RESPONDER", { texto: texto.trim() });
          }}
          className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2"
        >
          <textarea
            aria-label="Resposta ao time"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={3}
            placeholder="A faturista vê esta resposta no Guia da conta"
            className={CAMPO}
          />
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={!texto.trim() || ocupado} className={BOTAO}>
              Enviar resposta
            </button>
            <button type="button" onClick={() => setAberto(null)} className={BOTAO_SECUNDARIO}>
              Cancelar
            </button>
          </div>
        </form>
      )}

      {aberto === null && (
        <div className="flex flex-wrap gap-2 pt-1">
          {tema.tipo === "REGRA_PENDENTE" && (
            <>
              <button type="button" disabled={ocupado} onClick={() => abrir("regra")} className={BOTAO}>
                Validar regra
              </button>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => onDecidir("DEIXAR_PENDENTE")}
                className={BOTAO_SECUNDARIO}
              >
                Deixar pendente
              </button>
            </>
          )}
          {tema.tipo === "BLOQUEADO" && (
            <>
              <button type="button" disabled={ocupado} onClick={onEnviarAoCadastro} className={BOTAO}>
                Enviar ao cadastro
              </button>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => onDecidir("DESCARTAR")}
                className={BOTAO_SECUNDARIO}
              >
                Descartar
              </button>
            </>
          )}
          {tema.tipo === "OBSERVACAO" && (
            <>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => onDecidir("MANTER_REGRA")}
                className={BOTAO_SECUNDARIO}
              >
                Manter a regra
              </button>
              {tema.regra && (
                <button type="button" disabled={ocupado} onClick={() => abrir("regra")} className={BOTAO_SECUNDARIO}>
                  Editar a regra
                </button>
              )}
              <button type="button" disabled={ocupado} onClick={() => abrir("resposta")} className={BOTAO}>
                Responder ao time
              </button>
            </>
          )}
          {tema.tipo === "DICIONARIO" && (
            <>
              <button type="button" disabled={ocupado} onClick={() => onDecidir("CONFIRMAR")} className={BOTAO}>
                Confirmar
              </button>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => onDecidir("REJEITAR")}
                className={BOTAO_SECUNDARIO}
              >
                Rejeitar
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
