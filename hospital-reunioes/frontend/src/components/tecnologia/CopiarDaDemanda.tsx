"use client";

/**
 * Os dois botões de copiar do modal da Demanda (issue #640, PRD #634, ADR 0050).
 *
 * "Copiar para IA" leva a Demanda inteira, com a Conversa, para o diretor colar
 * na IA dele. O texto vem PRONTO da API: quem monta é o serviço puro do
 * backend, fonte única. Montar aqui seria uma segunda versão do mesmo texto, e
 * as duas divergiriam na primeira mudança de formato.
 *
 * "Copiar link" leva o endereço da Demanda, para mandar no WhatsApp. O endereço
 * sai do `linkDaDemanda`, o mesmo formato que o Quadro lê ao abrir pela URL.
 *
 * A cópia pode simplesmente não acontecer: o `navigator.clipboard` só existe em
 * contexto seguro, e mesmo existindo o navegador pode negar. Quando isso
 * acontece o texto vai para uma caixa na tela, já selecionada, de onde dá para
 * copiar à mão. Um botão que falha calado faz a pessoa mandar um link vazio sem
 * saber.
 */

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Bot, Check, Link2 } from "lucide-react";

import { BASE_TECNOLOGIA, Demanda, FALHA_DE_CONEXAO, linkDaDemanda } from "./demandas";

type Props = {
  demanda: Demanda;
  token: string | null;
};

/**
 * A frase de quando a cópia não acontece.
 *
 * Ela NÃO culpa uma causa que o código não distingue: o `writeText` falha do
 * mesmo jeito quando a API não existe no contexto e quando o navegador nega a
 * permissão, e o `catch` não sabe qual das duas foi. O que ela diz é o desfecho
 * e a saída, que está logo abaixo dela, na tela.
 */
const NAO_COPIOU =
  "O navegador não liberou a cópia automática. O texto está na caixa abaixo, já selecionado: copie com Ctrl+C (ou Cmd+C).";

const NAO_MONTOU =
  "Não foi possível montar o texto desta Demanda. Recarregue o Quadro e tente de novo.";

type Aviso = { tom: "ok" | "atencao"; frase: string };

export function CopiarDaDemanda({ demanda, token }: Props) {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [paraPegarAMao, setParaPegarAMao] = useState<string | null>(null);
  const caixa = useRef<HTMLTextAreaElement | null>(null);

  // Selecionar a caixa é o que transforma "está aí" em "copie com Ctrl+C": sem
  // isso a pessoa ainda teria que arrastar o mouse por um texto longo.
  useEffect(() => {
    if (paraPegarAMao) caixa.current?.select();
  }, [paraPegarAMao]);

  /**
   * Toda ação começa do zero.
   *
   * Sem isto, a caixa da ação ANTERIOR fica na tela embaixo do aviso da ação
   * nova: o pior caso é "não foi possível montar o texto desta Demanda" com o
   * link da vez passada logo abaixo, numa caixa que a própria tela chamou de
   * "para copiar à mão". A pessoa lê que não deu certo e vê um texto para
   * copiar; ou copia a coisa errada, ou não sabe em qual das duas acreditar.
   */
  function zerar() {
    setAviso(null);
    setParaPegarAMao(null);
  }

  async function copiar(texto: string, oQue: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setParaPegarAMao(null);
      setAviso({ tom: "ok", frase: `${oQue} copiado.` });
    } catch (e) {
      console.error("[admin/tecnologia] o navegador não copiou", e);
      setParaPegarAMao(texto);
      setAviso({ tom: "atencao", frase: NAO_COPIOU });
    }
  }

  async function copiarParaIa() {
    zerar();
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/texto-para-ia`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setAviso({ tom: "atencao", frase: NAO_MONTOU });
        return;
      }
      const corpo = await resposta.json();
      if (typeof corpo?.texto !== "string" || !corpo.texto) {
        setAviso({ tom: "atencao", frase: NAO_MONTOU });
        return;
      }
      await copiar(corpo.texto, "Texto da Demanda");
    } catch (e) {
      console.error("[admin/tecnologia] falha ao buscar o texto para a IA", e);
      setAviso({ tom: "atencao", frase: FALHA_DE_CONEXAO });
    }
  }

  function copiarLink() {
    zerar();
    return copiar(linkDaDemanda(demanda.id, window.location.origin), "Link da Demanda");
  }

  return (
    <div className="space-y-2 pt-4 border-t border-border">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={copiarParaIa}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors"
        >
          <Bot className="w-4 h-4" />
          Copiar para IA
        </button>
        <button
          type="button"
          onClick={copiarLink}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors"
        >
          <Link2 className="w-4 h-4" />
          Copiar link
        </button>
        {/* Diz PARA ONDE o texto vai, e não só o que vai dentro dele. Quem
            copia precisa saber que o pedido e a Conversa inteira saem daqui
            antes de colar, e não depois. */}
        <span className="text-xs text-text-secondary">
          O texto sai do app e vai para uma IA de fora: ele leva o pedido e a Conversa inteira.
        </span>
      </div>

      {aviso &&
        (aviso.tom === "ok" ? (
          <p role="status" className="flex items-center gap-2 text-sm text-emerald-700">
            <Check className="w-4 h-4 shrink-0" />
            <span>{aviso.frase}</span>
          </p>
        ) : (
          <p
            role="alert"
            className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{aviso.frase}</span>
          </p>
        ))}

      {paraPegarAMao && (
        <textarea
          ref={caixa}
          aria-label="Texto para copiar à mão"
          readOnly
          rows={4}
          value={paraPegarAMao}
          className="w-full px-3 py-2 text-sm font-mono border border-slate-200 rounded-lg bg-white"
        />
      )}
    </div>
  );
}
