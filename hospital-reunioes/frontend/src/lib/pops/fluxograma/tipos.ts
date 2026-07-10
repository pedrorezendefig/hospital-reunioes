/**
 * Gramática restrita do Fluxograma de POP (ADR 0024, issues #221 e #222),
 * espelho dos tipos do backend (`app/models/pops_fluxograma.py`).
 *
 * A seção de tipo `fluxograma` carrega um objeto JSON validado nos dois lados:
 * a lista `nos` é a coluna principal do fluxo (Início implícito antes do
 * primeiro nó, Fim implícito depois do último). Nó `passo` segue para o próximo
 * da lista; nó `decisao` tem 2 ou mais ramos rotulados (default Sim e Não; em
 * triagens e classificações, um ramo por categoria). Ramo com `desvio` cria um
 * card lateral que retorna a um nó por `retorna_para` ou segue o fluxo; ramo
 * com `vai_para` salta para um nó qualquer ou para `"fim"`. Um ramo não leva
 * `desvio` e `vai_para` ao mesmo tempo.
 */

export interface FluxogramaDesvio {
  texto: string;
  retorna_para?: string | null;
}

export interface FluxogramaRamo {
  rotulo: string;
  desvio?: FluxogramaDesvio | null;
  vai_para?: string | null;
}

export interface FluxogramaNo {
  id: string;
  tipo: "passo" | "decisao";
  texto: string;
  ramos?: FluxogramaRamo[] | null;
}

export interface FluxogramaEstrutura {
  nos: FluxogramaNo[];
}
