/**
 * O que vai à área além do Extrato para o setor, na tela de validação (issue
 * #769).
 *
 * O ouvidor decide o que escrever no extrato olhando para o texto de ajuda do
 * campo, então o texto precisa dizer a verdade sobre o que mais chega ao
 * responsável no caso que está na tela. A regra é do backend
 * (`ouvidoria_blocos.py`: `montar_blocos`, `identificacao_do_caso`,
 * `paciente_do_caso`); a tela espelha as três variantes porque a marca de
 * sigilo muda ao vivo no modal, antes de qualquer ida ao servidor.
 *
 * O espelho é travado nas duas pontas pelo contrato `o-que-viaja-ao-setor.json`:
 * o backend prova que ele diz o que a regra faz, e `o-que-viaja.test.ts` prova
 * que a variante e a frase daqui dizem o que ele diz.
 */

export type VarianteDoQueViaja = "comum" | "anonimo" | "sigilo";

/**
 * O sigilo vence o anonimato, como no backend: é ele que corta os blocos, e o
 * caso anônimo sob sigilo reforçado leva só o extrato.
 */
export function varianteDoQueViaja(caso: { sigilo: boolean; anonimo: boolean }): VarianteDoQueViaja {
  if (caso.sigilo) return "sigilo";
  return caso.anonimo ? "anonimo" : "comum";
}

export const AJUDA_DO_EXTRATO: Record<VarianteDoQueViaja, string> = {
  comum:
    "Vai no email e na tela do responsável junto do resumo, do relato integral, do nome de quem manifestou e do Paciente do caso, quando houver. Escreva com as suas palavras o que a área precisa resolver: é o pedido da Ouvidoria ao setor. Sem este texto o acionamento não sai.",
  anonimo:
    "Manifestação anônima: vai no email e na tela do responsável junto do resumo, do relato integral e do Paciente do caso, quando houver, sem a identificação de quem manifestou. Escreva com as suas palavras o que a área precisa resolver: é o pedido da Ouvidoria ao setor. Sem este texto o acionamento não sai.",
  sigilo:
    "Sigilo reforçado: é este texto que vai no email e na tela do responsável, e só ele. Escreva com as suas palavras o que a área precisa resolver, sem nada que identifique quem manifestou. Sem este texto o acionamento não sai.",
};
