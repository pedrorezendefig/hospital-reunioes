"use client";

/**
 * O formulário de Nova Demanda (extraído do Quadro na issue #727).
 *
 * Ele era um painel dentro do `QuadroDemandas`. Saiu de lá porque "Nova
 * Demanda" passou a abrir o Assistente de Tecnologia numa página própria
 * (ADR 0056, decisão 5), e o formulário continua a um clique dali, atrás do
 * "prefiro preencher à mão".
 *
 * O comportamento é o de sempre, campo por campo: os cinco campos, o Produto
 * só entre os ativos, o título com teto de 200, o botão que só libera com
 * título e Produto, e a recusa do servidor chegando como `role="alert"`. Quem
 * decide estado e responsável continua sendo o backend, pelo Produto.
 */

import { useState } from "react";

import { Select } from "@/components/ui/Select";

import { corpoValidado, demandaCriadaValida } from "./assistente";

import {
  BASE_TECNOLOGIA,
  Demanda,
  FALHA_DE_CONEXAO,
  motivoDaRecusa,
  PRIORIDADE_ROTULO,
  PRIORIDADES,
  PrioridadeDemanda,
  ProdutoDaEscolha,
  TIPO_ROTULO,
  TIPOS,
  TipoDemanda,
} from "./demandas";

type Props = {
  token: string | null;
  produtos: ProdutoDaEscolha[];
  /**
   * Chamada com a Demanda que o backend devolveu, para a página decidir para
   * onde ir. O segundo argumento é o aviso de que o e-mail de atribuição não
   * saiu (quando saiu, é `null`): ele viaja porque quem criou a Demanda
   * precisa saber que o responsável não foi avisado.
   */
  onCriada: (demanda: Demanda, avisoDeEmail: string | null) => void;
  /**
   * Chamada quando o servidor aceitou (201) e a resposta não deu para usar: a
   * Demanda existe, a confirmação é que se perdeu.
   */
  onCriadaSemConfirmacao: () => void;
};

const FORM_VAZIO = {
  titulo: "",
  tipo: "decisao" as TipoDemanda,
  produto_id: "",
  prioridade: "normal" as PrioridadeDemanda,
  descricao: "",
};

export function FormularioNovaDemanda({ token, produtos, onCriada, onCriadaSemConfirmacao }: Props) {
  const [form, setForm] = useState(FORM_VAZIO);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const produtosAtivos = produtos.filter((p) => p.ativo);

  async function criar() {
    setSalvando(true);
    let resposta: Response;
    try {
      resposta = await fetch(`${BASE_TECNOLOGIA}/demandas`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          titulo: form.titulo,
          tipo: form.tipo,
          produto_id: form.produto_id,
          prioridade: form.prioridade,
          descricao: form.descricao,
        }),
      });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao criar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
      setSalvando(false);
      return;
    }
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      setSalvando(false);
      return;
    }
    /**
     * Mesma fronteira do assistente, e pelo mesmo motivo: o corpo da resposta é
     * a Demanda criada E o aviso de e-mail, e ler por `as` era promessa não
     * verificada. Com 201 e corpo que não dá para usar, a Demanda NASCEU e o
     * que se perdeu foi a confirmação: quem avisa é a página, que troca o
     * formulário pelo aviso e tira o botão da tela, em vez de reabilitá-lo para
     * um segundo clique que nasceria a Demanda repetida.
     *
     * (O `avisoPorEmail` de `demandas.ts` não serve aqui: ele consome o mesmo
     * corpo, e o corpo de uma `Response` só se lê uma vez.)
     */
    const criada = await corpoValidado(resposta, demandaCriadaValida);
    setSalvando(false);
    if (criada === null) {
      console.error("[admin/tecnologia] a resposta da criação não deu para usar");
      onCriadaSemConfirmacao();
      return;
    }
    onCriada(criada, typeof criada.aviso_por_email === "string" ? criada.aviso_por_email : null);
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
      {erro && (
        <p
          role="alert"
          className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm whitespace-pre-line"
        >
          {erro}
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <input
          type="text"
          aria-label="Título"
          placeholder="O que precisa acontecer"
          maxLength={200}
          value={form.titulo}
          onChange={(e) => setForm({ ...form, titulo: e.target.value })}
          className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white md:col-span-2"
        />
        <Select
          label="Tipo"
          value={form.tipo}
          onChange={(tipo) => setForm({ ...form, tipo: tipo as TipoDemanda })}
          options={TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] }))}
        />
        <Select
          label="Produto"
          value={form.produto_id}
          onChange={(produto_id) => setForm({ ...form, produto_id })}
          options={produtosAtivos.map((p) => ({ value: p.id, label: p.nome }))}
          placeholder="Escolha o Produto"
        />
        <Select
          label="Prioridade"
          value={form.prioridade}
          onChange={(prioridade) => setForm({ ...form, prioridade: prioridade as PrioridadeDemanda })}
          options={PRIORIDADES.map((p) => ({ value: p, label: PRIORIDADE_ROTULO[p] }))}
        />
        <textarea
          aria-label="Descrição"
          rows={2}
          placeholder="Contexto, se ajudar"
          value={form.descricao}
          onChange={(e) => setForm({ ...form, descricao: e.target.value })}
          className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white md:col-span-2"
        />
      </div>
      <button
        type="button"
        onClick={criar}
        disabled={salvando || !form.titulo.trim() || !form.produto_id}
        className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
      >
        Abrir Demanda
      </button>
    </div>
  );
}
