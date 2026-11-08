"use client";

/**
 * A conversa da Conta com o Auditor, no fim do Guia (issue #1489, PRD #1484, ADR 0081).
 *
 * Quem vê o Guia aponta o Faltou isto de um dia: o item, a página do
 * prontuário e a pergunta. O Auditor responde por que o Guia não achou e de
 * onde a falha veio. Na página não lida e no defeito do sistema, quem apontou
 * dá o ok e o pedido vai para a Tecnologia. O servidor decide quem pode o quê;
 * a tela desenha pelo que ele manda.
 */

import { useEffect, useRef, useState } from "react";

import { Ditar, juntarDitado } from "@/components/contas-medicas/Ditar";
import { useToast } from "@/components/ui/Toast";
import { type FaltouIsto, ROTULO_DA_ORIGEM, falaDeQuemApontou } from "@/lib/contas-medicas/faltouIsto";
import { dataCurta } from "@/lib/contas-medicas/guia";

const TITULO = "text-xs font-semibold uppercase tracking-[0.04em] text-slate-500";
const BOTAO = "px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-50";

async function detalhe(resposta: Response, padrao: string): Promise<string> {
  try {
    const corpo = await resposta.json();
    return typeof corpo?.detail === "string" ? corpo.detail : padrao;
  } catch {
    return padrao;
  }
}

interface Props {
  contaId: string;
  token: string | null;
  /** Os dias do período da conta, em ISO. */
  dias: string[];
  /** Os Faltou isto da conta, como o Guia trouxe. */
  iniciais: FaltouIsto[];
  /** O dia escolhido no "Faltou isto" de um grupo do Guia; `vez` muda a cada clique. */
  escolha: { dia: string; vez: number } | null;
}

export function ConversaDaConta({ contaId, token, dias, iniciais, escolha }: Props) {
  const { toast } = useToast();
  const [apontamentos, setApontamentos] = useState<FaltouIsto[]>(iniciais);
  const [dia, setDia] = useState(dias[0] ?? "");
  const [item, setItem] = useState("");
  const [pagina, setPagina] = useState("");
  const [texto, setTexto] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const campoDoItem = useRef<HTMLInputElement>(null);

  const rota = `/api/contas-medicas/contas/${contaId}/guia/faltou-isto`;

  useEffect(() => {
    if (!escolha) return;
    setDia(escolha.dia);
    campoDoItem.current?.focus();
  }, [escolha]);

  async function enviar(caminho: string, corpo?: unknown): Promise<FaltouIsto | null> {
    if (!token) return null;
    setOcupado(true);
    try {
      const resposta = await fetch(`${rota}${caminho}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          ...(corpo !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(corpo !== undefined ? { body: JSON.stringify(corpo) } : {}),
      });
      if (!resposta.ok) {
        toast(await detalhe(resposta, "Não deu certo. Tente de novo."), "error");
        return null;
      }
      return (await resposta.json()).apontamento as FaltouIsto;
    } finally {
      setOcupado(false);
    }
  }

  async function perguntar() {
    const numero = Number.parseInt(pagina, 10);
    const novo = await enviar("", {
      data: dia,
      item: item.trim(),
      pagina: Number.isFinite(numero) && numero > 0 ? numero : null,
      texto: texto.trim() || null,
    });
    if (!novo) return;
    setApontamentos((atuais) => [...atuais, novo]);
    setItem("");
    setPagina("");
    setTexto("");
  }

  async function abrirPedido(apontamento: FaltouIsto) {
    const aberto = await enviar(`/${apontamento.id}/pedido`);
    if (!aberto) return;
    setApontamentos((atuais) => atuais.map((atual) => (atual.id === aberto.id ? aberto : atual)));
    toast("Pedido aberto para a Tecnologia", "success");
  }

  return (
    <section
      aria-labelledby="falar-com-o-auditor"
      className="bg-white rounded-2xl border border-border shadow-premium p-4 space-y-3"
    >
      <h2 id="falar-com-o-auditor" className={TITULO}>
        Falar com o auditor
      </h2>

      {apontamentos.map((apontamento) => (
        <div key={apontamento.id} className="space-y-2">
          <p className="text-sm text-slate-700 break-words">{falaDeQuemApontou(apontamento)}</p>
          {apontamento.explicacao && (
            <article
              aria-label="Resposta do Auditor"
              className="rounded-lg bg-[#EEEEF6] border border-border px-3 py-2 space-y-1"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-primary">Auditor</span>
                {apontamento.classificacao && (
                  <span className="etiqueta inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold bg-white text-primary">
                    {ROTULO_DA_ORIGEM[apontamento.classificacao]}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-700 whitespace-pre-line break-words">{apontamento.explicacao}</p>
              {apontamento.pedido_aberto && (
                <p className="text-xs font-semibold text-slate-600">Pedido aberto para a Tecnologia.</p>
              )}
              {apontamento.pode_abrir_pedido && (
                <button
                  type="button"
                  onClick={() => abrirPedido(apontamento)}
                  disabled={ocupado}
                  className={`${BOTAO} bg-primary text-white`}
                >
                  Abrir o pedido para a Tecnologia
                </button>
              )}
            </article>
          )}
        </div>
      ))}

      <fieldset className="rounded-lg border border-border px-3 py-2 space-y-2">
        <legend className="px-1 text-xs font-semibold text-slate-700">Faltou isto</legend>
        <p className="text-xs text-slate-500">
          Diga o que o Guia não apontou e a página do prontuário. O Auditor explica por que não achou.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-[8rem_1fr_9rem] gap-2">
          <label className="text-xs text-slate-600 space-y-1">
            <span className="block">Dia</span>
            <select
              aria-label="Dia"
              value={dia}
              onChange={(evento) => setDia(evento.target.value)}
              className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
            >
              {dias.map((opcao) => (
                <option key={opcao} value={opcao}>
                  {dataCurta(opcao)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-600 space-y-1">
            <span className="block">Item que faltou</span>
            <input
              ref={campoDoItem}
              aria-label="Item que faltou"
              value={item}
              maxLength={200}
              onChange={(evento) => setItem(evento.target.value)}
              className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-xs text-slate-600 space-y-1">
            <span className="block">Página do prontuário</span>
            <input
              aria-label="Página do prontuário"
              type="number"
              min={1}
              inputMode="numeric"
              value={pagina}
              onChange={(evento) => setPagina(evento.target.value)}
              className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
            />
          </label>
        </div>
        <textarea
          aria-label="Mensagem para o auditor"
          value={texto}
          maxLength={2000}
          onChange={(evento) => setTexto(evento.target.value)}
          placeholder="Opcional. Por exemplo: por que você não achou isto nesta página?"
          rows={2}
          className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
        />
        <Ditar
          campo="Mensagem para o auditor"
          aoTranscrever={(ditado) => setTexto((atual) => juntarDitado(atual, ditado))}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={perguntar}
            disabled={ocupado || !item.trim() || !dia}
            className={`${BOTAO} bg-primary text-white`}
          >
            Perguntar ao auditor
          </button>
          {ocupado && (
            <p role="status" className="text-xs text-slate-500">
              O Auditor está lendo o dia...
            </p>
          )}
        </div>
      </fieldset>
    </section>
  );
}
