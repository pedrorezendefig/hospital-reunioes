"use client";

/**
 * A barra de filtros das abas "Minha vez" e Histórico (issue #641).
 *
 * Os filtros são COMPARTILHADOS entre as três abas (issue #639): o estado mora
 * no `TecnologiaModulo` e desce por prop, e aqui a barra só o mostra e o troca.
 * Uma aba que não desenhasse a barra herdaria o filtro do Quadro sem oferecer
 * onde vê-lo nem onde desfazê-lo, e uma lista vazia por filtro pareceria uma
 * lista vazia de verdade.
 *
 * O Quadro continua com a barra dele, escrita dentro do próprio componente. As
 * duas são a mesma barra, e juntá-las numa só é a limpeza natural desta parte
 * da tela; ela não entra nesta fatia porque o `QuadroDemandas` está sendo
 * mexido em paralelo pela issue #642, e mover código de lá para cá agora seria
 * conflito de merge no arquivo que a outra fatia reescreve.
 */

import { Select } from "@/components/ui/Select";

import { FiltrosDoQuadro, PessoaDaAba, ProdutoDaEscolha, SEM_FILTRO, TIPO_ROTULO, TIPOS, temFiltroAtivo } from "./demandas";

/** As opções que LIMPAM cada filtro: o rótulo é o mesmo do campo em branco. */
const TODOS_OS_TIPOS = "Todos os tipos";
const TODOS_OS_PRODUTOS = "Todos os Produtos";
const TODOS_OS_RESPONSAVEIS = "Todos os responsáveis";

type Props = {
  filtros: FiltrosDoQuadro;
  onFiltrosChange: (filtros: FiltrosDoQuadro) => void;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
  /** O que a frase de aviso diz que está sendo estreitado ("a lista", "o Histórico"). */
  oQueEstaFiltrado: string;
};

export function FiltrosDeDemandas({ filtros, onFiltrosChange, produtos, pessoas, oQueEstaFiltrado }: Props) {
  const filtrando = temFiltroAtivo(filtros);

  return (
    <div className="rounded-xl border border-border bg-surface p-3 space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Select
          label="Filtrar por tipo"
          value={filtros.tipo}
          onChange={(tipo) => onFiltrosChange({ ...filtros, tipo })}
          options={[
            { value: "", label: TODOS_OS_TIPOS },
            ...TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] })),
          ]}
          placeholder={TODOS_OS_TIPOS}
        />
        <Select
          label="Filtrar por Produto"
          value={filtros.produto_id}
          onChange={(produto_id) => onFiltrosChange({ ...filtros, produto_id })}
          // Todos os Produtos, e não só os ativos: desativar tira o Produto da
          // escolha de quem abre Demanda nova, não do histórico (ADR 0050,
          // decisão 11). Sem esta opção, as Demandas de um Produto desativado
          // ficariam fora do alcance de qualquer filtro.
          options={[
            { value: "", label: TODOS_OS_PRODUTOS },
            ...produtos.map((p) => ({ value: p.id, label: p.ativo ? p.nome : `${p.nome} (inativo)` })),
          ]}
          placeholder={TODOS_OS_PRODUTOS}
        />
        <Select
          label="Filtrar por responsável"
          value={filtros.responsavel_id}
          onChange={(responsavel_id) => onFiltrosChange({ ...filtros, responsavel_id })}
          options={[
            { value: "", label: TODOS_OS_RESPONSAVEIS },
            ...pessoas.map((p) => ({ value: p.id, label: p.nome_completo })),
          ]}
          placeholder={TODOS_OS_RESPONSAVEIS}
        />
      </div>

      {/* Lista filtrada e calada é indistinguível de lista vazia: quem chega à
          aba com o filtro que deixou ligado no Quadro concluiria que as
          Demandas sumiram. O aviso diz o que está acontecendo e onde desfazer. */}
      {filtrando && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-amber-700">
            {oQueEstaFiltrado} está filtrado: o que ficou fora do filtro não aparece aqui.
          </p>
          <button
            type="button"
            onClick={() => onFiltrosChange(SEM_FILTRO)}
            className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-text-secondary hover:border-primary hover:text-primary transition-colors"
          >
            Limpar filtros
          </button>
        </div>
      )}
    </div>
  );
}
