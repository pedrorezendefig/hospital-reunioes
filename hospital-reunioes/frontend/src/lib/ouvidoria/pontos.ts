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
  /** Os campos do cartaz A4 (issue #1617, ADR 0086 decisão 10). Opcionais no
   * tipo porque a lista de antes da migration 135 não os traz. */
  nome_publico?: string | null;
  descricao_local?: string | null;
  titulo_cartaz?: TituloDoCartaz | null;
  codigo_controle?: string | null;
  ala_internacao?: boolean | null;
  /** A chave do ponto no teste do convite ao Google (issue #1625). */
  google_teste_ativo?: boolean | null;
  /** O PNG do QR embutido: o front autentica por header, e `<img src>` não
   * manda header, então a imagem viaja dentro do JSON. */
  qr_data_uri: string;
}

/** Os dois modelos do cartaz A4 (seção 4.13 da especificação da Diretoria). O
 * valor é o que o banco grava; o rótulo é o título que sai impresso. */
export type TituloDoCartaz = "atendimento_hoje" | "um_minuto";

export const TITULOS_DO_CARTAZ: { valor: TituloDoCartaz; rotulo: string }[] = [
  { valor: "atendimento_hoje", rotulo: "Como foi seu atendimento hoje?" },
  { valor: "um_minuto", rotulo: "Um minuto para nos contar" },
];

/** O que o ouvidor edita num cartaz, como a tela guarda: texto cru dos campos. */
export interface FormDoCartaz {
  ponto: string;
  nome_publico: string;
  descricao_local: string;
  titulo_cartaz: TituloDoCartaz;
  codigo_controle: string;
  ala_internacao: boolean;
}

export const CARTAZ_VAZIO: FormDoCartaz = {
  ponto: "",
  nome_publico: "",
  descricao_local: "",
  titulo_cartaz: "atendimento_hoje",
  codigo_controle: "",
  ala_internacao: false,
};

/** O formulário de edição começa com o que o cartaz já tem. */
export function formDoPonto(ponto: PontoDeEscuta): FormDoCartaz {
  return {
    ponto: ponto.ponto,
    nome_publico: ponto.nome_publico ?? "",
    descricao_local: ponto.descricao_local ?? "",
    titulo_cartaz: ponto.titulo_cartaz ?? "atendimento_hoje",
    codigo_controle: ponto.codigo_controle ?? "",
    ala_internacao: Boolean(ponto.ala_internacao),
  };
}

/** O corpo que vai ao servidor: texto aparado, e o opcional em branco vira
 * nulo (sem nome público, o paciente vê o rótulo do ponto). */
export function camposDoCartaz(form: FormDoCartaz) {
  return {
    ponto: form.ponto.trim(),
    nome_publico: form.nome_publico.trim() || null,
    descricao_local: form.descricao_local.trim(),
    titulo_cartaz: form.titulo_cartaz,
    codigo_controle: form.codigo_controle.trim() || null,
    ala_internacao: form.ala_internacao,
  };
}

export interface GrupoDeCartazes {
  setor: string;
  pontos: PontoDeEscuta[];
}

/**
 * Quem cria e aposenta cartaz: os dois perfis da Ouvidoria (ADR 0036,
 * decisão 7). Era mais largo que a tela de Responsáveis, que foi só da
 * Diretoria até a issue #711; hoje as duas têm a mesma régua, e quem continua
 * só da Diretoria é a Tabela de prazos. O motivo de cartaz nunca ter sido
 * governança segue de pé: não carrega dado de paciente e não muda prazo nem
 * responsabilidade. O backend recusa de novo, para quem chamar a API direto.
 */
export function podeGerirPontos(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "ouvidor" || perfilOuvidoria === "diretoria_executiva";
}

/** A chave geral do teste do convite ao Google, como `GET /pontos` devolve. */
export interface ConviteGoogle {
  global: boolean;
  ligado_em: string | null;
}

/** Só a diretoria executiva liga e desliga o convite ao Google (ADR 0089,
 * decisão 6). O ouvidor vê o estado; o backend recusa de novo com 403. */
export function podeLigarConviteGoogle(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "diretoria_executiva";
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

/** O botão só liga com o rótulo e a descrição do local preenchidos: é o que
 * faz alguém achar o cartaz na parede depois. */
export function cartazEstaCompleto(form: { ponto: string; descricao_local: string }): boolean {
  return Boolean(form.ponto.trim() && form.descricao_local.trim());
}

/** O cartaz novo pede também o setor, que depois não muda. */
export function pontoEstaCompleto(form: { setor: string; ponto: string; descricao_local: string }): boolean {
  return Boolean(form.setor.trim()) && cartazEstaCompleto(form);
}

/** O nome do arquivo baixado leva o código, senão a pasta de downloads vira uma
 * pilha de arquivos com o mesmo nome. */
export function nomeDoArquivo(ponto: PontoDeEscuta, tipo: "png" | "pdf"): string {
  const prefixo = tipo === "pdf" ? "cartaz-ouvidoria" : "qr-ouvidoria";
  return `${prefixo}-${ponto.codigo}.${tipo}`;
}
