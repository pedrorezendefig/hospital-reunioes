/**
 * Ponto de escuta: os cartazes de QR da Ouvidoria (issue #378, ADR 0036).
 *
 * Cada Ponto de escuta é um cartaz impresso. O que vai no papel é o código
 * curto, e o servidor resolve o setor e o rótulo: a página pública deixa de
 * receber texto de origem pela query string.
 */

export interface PontoDeEscuta {
  id: string;
  codigo: string;
  setor: string;
  ponto: string;
  ativo: boolean;
  criado_em: string;
  /** O PNG do QR embutido: o front autentica por header, e `<img src>` não
   * manda header, então a imagem viaja dentro do JSON. */
  qr_data_uri: string;
}

export interface GrupoDeCartazes {
  setor: string;
  pontos: PontoDeEscuta[];
}

/**
 * Quem cria e aposenta cartaz: os dois perfis da Ouvidoria (ADR 0036,
 * decisão 7). É mais largo que a tela de Responsáveis, que é só da Diretoria,
 * porque cartaz é operação do canal e não governança: não carrega dado de
 * paciente e não muda prazo nem responsabilidade. O backend recusa de novo,
 * para quem chamar a API direto.
 */
export function podeGerirPontos(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "ouvidor" || perfilOuvidoria === "diretoria_executiva";
}

/**
 * A lista como o ouvidor procura: por setor, e dentro dele pelo lugar. A tela é
 * uma lista de lugares físicos, e procurar "Poltrona 12" numa ordem aleatória é
 * o que faz alguém desistir de usar a tela.
 */
export function agruparPorSetor(pontos: PontoDeEscuta[]): GrupoDeCartazes[] {
  const porSetor = new Map<string, PontoDeEscuta[]>();
  for (const ponto of pontos) {
    porSetor.set(ponto.setor, [...(porSetor.get(ponto.setor) ?? []), ponto]);
  }
  return [...porSetor.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "pt-BR"))
    .map(([setor, doSetor]) => ({
      setor,
      pontos: [...doSetor].sort((a, b) => a.ponto.localeCompare(b.ponto, "pt-BR")),
    }));
}

/** O botão só liga com os dois campos preenchidos: o rótulo é o que faz alguém
 * achar o cartaz na parede depois. */
export function pontoEstaCompleto(form: { setor: string; ponto: string }): boolean {
  return Boolean(form.setor.trim() && form.ponto.trim());
}

/** O nome do arquivo baixado leva o código, senão a pasta de downloads vira uma
 * pilha de arquivos com o mesmo nome. */
export function nomeDoArquivo(ponto: PontoDeEscuta, tipo: "png" | "pdf"): string {
  const prefixo = tipo === "pdf" ? "cartaz-ouvidoria" : "qr-ouvidoria";
  return `${prefixo}-${ponto.codigo}.${tipo}`;
}
