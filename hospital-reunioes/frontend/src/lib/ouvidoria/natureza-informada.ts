/**
 * A natureza que o MANIFESTANTE informou, para o Dossiê (issue #474).
 *
 * O formulário público passou a perguntar o que a pessoa traz (issue #473,
 * RN-88), e a coluna `natureza_informada` guardava a resposta sem nenhuma tela
 * lendo: dado gravado que ninguém lê não serve a ninguém.
 *
 * A lista fechada e os rótulos vêm de `publico.ts`, onde a escolha nasce: são
 * as mesmas quatro palavras do cartaz, e ter duas listas seria ter duas
 * verdades. O que este módulo acrescenta é a única coisa que a tela do ouvidor
 * precisa e a tela pública não: dizer de quem é a palavra.
 */

import { NATUREZAS_INFORMADAS, type NaturezaInformada } from "./publico";

/**
 * O que separa a sugestão da classificação (ADR 0040, decisão 3).
 *
 * Sem esta linha, "Elogio" impresso no Dossiê se lê como caso já classificado,
 * e a soberania da classificação é do ouvidor: o campo dele é o tipo, e é o
 * tipo que decide sigilo e estado.
 */
export const SUGESTAO_NAO_E_CLASSIFICACAO =
  "É a sugestão de quem manifestou, não a classificação do caso: quem classifica é o ouvidor.";

export interface CasoComNatureza {
  natureza_informada: string | null;
}

export interface NaturezaDescrita {
  /** A linha em destaque, já com a origem da palavra. */
  titulo: string;
  /** O rótulo humano da natureza escolhida. */
  rotulo: string;
  aviso: string;
}

const ROTULO_POR_NATUREZA = new Map<string, string>(
  NATUREZAS_INFORMADAS.map(({ valor, rotulo }) => [valor as NaturezaInformada, rotulo])
);

export function descreverNaturezaInformada(caso: CasoComNatureza): NaturezaDescrita | null {
  if (!caso.natureza_informada) return null;
  // Valor fora da lista fechada não vira texto na tela. A lista vale na tela
  // pública, na aplicação e no CHECK da migration 090, então chegar aqui outra
  // coisa é linha corrompida, e imprimi-la crua daria palanque no Dossiê a
  // texto que nenhuma das três portas aceitou.
  const rotulo = ROTULO_POR_NATUREZA.get(caso.natureza_informada);
  if (!rotulo) return null;
  return {
    titulo: `O manifestante informou: ${rotulo}`,
    rotulo,
    aviso: SUGESTAO_NAO_E_CLASSIFICACAO,
  };
}
