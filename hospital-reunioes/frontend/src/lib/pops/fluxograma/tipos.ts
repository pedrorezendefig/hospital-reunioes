/**
 * Gramática restrita do Fluxograma de POP (ADR 0024, issue #221), espelho dos
 * tipos do backend (`app/models/pops_fluxograma.py`).
 *
 * A seção de tipo `fluxograma` carrega um objeto JSON validado nos dois lados:
 * a lista `nos` é a coluna principal do fluxo (Início implícito antes do
 * primeiro nó, Fim implícito depois do último). Nó `passo` segue para o próximo
 * da lista; nó `decisao` tem exatamente 2 ramos rotulados (default Sim e Não),
 * com no máximo um ramo em `desvio` (card lateral que retorna a um nó por
 * `retorna_para`, ou segue o fluxo). Decisões com 3 ou mais ramos e saltos
 * (`vai_para`) ficam para a fatia #222.
 */

export interface FluxogramaDesvio {
  texto: string;
  retorna_para?: string | null;
}

export interface FluxogramaRamo {
  rotulo: string;
  desvio?: FluxogramaDesvio | null;
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
