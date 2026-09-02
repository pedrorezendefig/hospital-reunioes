/**
 * O tipo da manifestação e o que ele decide sobre o sigilo (issue #372).
 *
 * O tipo é lista fechada: a tela oferece só o que o backend aceita, e o rótulo
 * humano do caso (`categoria`) virou texto que descreve, não que decide. A
 * regra de sigilo aqui é a mesma do backend, e existe para a tela não oferecer
 * um caminho que termina em 409: o gate de verdade é o servidor.
 */

export type TipoManifestacao =
  | "denuncia"
  | "reclamacao"
  | "sugestao"
  | "elogio"
  | "relato_de_conduta"
  | "informacao";

/**
 * `informacao` é o sexto valor (issue #490, ADR 0040 decisão 1). O cartaz do
 * ponto de escuta promete essa natureza a quem lê o QR (RN-88), e sem ela na
 * lista o seletor da Validação e o da Classificação do Dossiê não tinham como
 * oferecê-la. A ordem é a mesma do backend, e o tipo novo entra no fim para a
 * fila do ouvidor não mudar de lugar debaixo da mão dele.
 */
export const TIPOS_MANIFESTACAO: TipoManifestacao[] = [
  "denuncia",
  "reclamacao",
  "sugestao",
  "elogio",
  "relato_de_conduta",
  "informacao",
];

export const LABEL_TIPO: Record<TipoManifestacao, string> = {
  denuncia: "Denúncia",
  reclamacao: "Reclamação",
  sugestao: "Sugestão",
  elogio: "Elogio",
  relato_de_conduta: "Relato de conduta",
  informacao: "Informação",
};

/** Sigilosos por natureza (ADR 0034, decisão 1): o sigilo vem com o tipo. */
const TIPOS_SIGILOSOS: TipoManifestacao[] = ["denuncia", "relato_de_conduta"];

/**
 * O caso é sigiloso pelo que ele é?
 *
 * Sem tipo, o caso ainda não foi classificado, e aí ele é sigiloso: é assim
 * que entram o formulário público, o QR e o canal da Ana.
 */
export function ehSigilosoPorNatureza(tipo: TipoManifestacao | null): boolean {
  return tipo === null || TIPOS_SIGILOSOS.includes(tipo);
}

/**
 * O sigilo que vai valer se o ouvidor salvar assim. A regra automática é piso,
 * nunca teto: o tipo sigiloso sobe sozinho e não desce, e nos demais vale a
 * marca que o ouvidor deixou.
 */
export function sigiloResultante(tipo: TipoManifestacao, marcado: boolean): boolean {
  return ehSigilosoPorNatureza(tipo) || marcado;
}

/** O que a tela mostra no lugar do tipo, inclusive quando ele ainda não existe. */
export function rotuloDoTipo(tipo: TipoManifestacao | null): string {
  return tipo ? LABEL_TIPO[tipo] : "Não classificada";
}
