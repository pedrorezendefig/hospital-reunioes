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
 *
 * Os prints (issue #1061, ADR 0069) sobem DEPOIS da criação, um por vez, para
 * a Demanda que acabou de nascer: a imagem precisa de um card para morar. A
 * que o servidor recusar vira aviso junto da Demanda, como o e-mail que não
 * saiu, e a página não navega para quem criou não perder a frase.
 */

import { useState } from "react";
import { ImagePlus, X } from "lucide-react";

import { Select } from "@/components/ui/Select";

import { anexarImagem, avisoDasImagens, escolherImagens } from "./anexos";
import { corpoValidado, demandaCriadaValida, IMAGENS_ACEITAS } from "./assistente";

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
  const [imagens, setImagens] = useState<File[]>([]);
  const [avisoDaEscolha, setAvisoDaEscolha] = useState<string | null>(null);

  function aoEscolher(e: React.ChangeEvent<HTMLInputElement>) {
    const escolha = escolherImagens(imagens, Array.from(e.target.files ?? []));
    setImagens(escolha.imagens);
    setAvisoDaEscolha(escolha.aviso);
    // Sem isto, escolher de novo o MESMO arquivo (depois de tirá-lo) não
    // dispara `change`.
    e.target.value = "";
  }

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
    if (criada === null) {
      setSalvando(false);
      console.error("[admin/tecnologia] a resposta da criação não deu para usar");
      onCriadaSemConfirmacao();
      return;
    }
    // Uma por vez, na ordem escolhida: é a ordem em que o card as mostra.
    const recusadas: { nome: string; motivo: string }[] = [];
    for (const arquivo of imagens) {
      const motivo = await anexarImagem(criada.id, arquivo, token);
      if (motivo) recusadas.push({ nome: arquivo.name, motivo });
    }
    setSalvando(false);
    const avisos = [
      typeof criada.aviso_por_email === "string" ? criada.aviso_por_email : null,
      avisoDasImagens(recusadas),
    ].filter((a): a is string => a !== null);
    onCriada(criada, avisos.length > 0 ? avisos.join(" ") : null);
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
        <div className="md:col-span-2 space-y-2">
          <label className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-sm text-text-secondary hover:border-primary hover:text-primary transition-colors cursor-pointer">
            <ImagePlus className="w-4 h-4" />
            Anexar prints (até 10)
            <input
              type="file"
              multiple
              aria-label="Anexar imagens"
              accept={IMAGENS_ACEITAS.join(",")}
              onChange={aoEscolher}
              className="sr-only"
            />
          </label>
          {avisoDaEscolha && (
            <p role="status" className="text-xs text-amber-700">
              {avisoDaEscolha}
            </p>
          )}
          {imagens.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {imagens.map((arquivo, i) => (
                <li
                  key={`${arquivo.name}-${i}`}
                  className="flex items-center gap-1 pl-2 pr-1 py-1 rounded-lg bg-slate-100 text-xs text-text"
                >
                  <span>{arquivo.name}</span>
                  <button
                    type="button"
                    aria-label={`Tirar ${arquivo.name}`}
                    onClick={() => setImagens(imagens.filter((_, j) => j !== i))}
                    className="p-0.5 rounded hover:bg-slate-200"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
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
