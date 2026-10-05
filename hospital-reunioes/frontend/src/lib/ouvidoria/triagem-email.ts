/**
 * A Triagem de e-mail da Ouvidoria (issue #648, PRD #646, ADR 0051).
 *
 * Todo e-mail que chega em ouvidoria@ entra numa lista que só o Perfil da
 * Ouvidoria vê, antes de virar caso. Nesta fatia o ouvidor só lê: a lista e o
 * item, com o corpo em texto e os anexos. Não é "caixa de entrada": o app não
 * responde e-mail por aqui.
 *
 * Aqui moram os tipos do que a API devolve e as regras puras da tela. O gate
 * de verdade é o backend (`require_perfil_ouvidoria`, 403 para os demais).
 */

/** Os dois perfis da Ouvidoria. Super admin fica de fora, como no Dossiê. */
export const PERFIS_DA_TRIAGEM = ["ouvidor", "diretoria_executiva"];

export type EstadoDaTriagem = "pendente" | "virou_manifestacao" | "juntado" | "descartado";

/** O cabeçalho de um e-mail recebido, como a lista devolve. */
export interface EmailRecebidoResumo {
  id: string;
  remetente_endereco: string;
  remetente_nome: string | null;
  assunto: string;
  recebido_em: string;
  estado: EstadoDaTriagem;
  incompleto: boolean;
  interno: boolean;
  quantidade_de_anexos: number;
}

export interface AnexoDoEmail {
  id: string;
  filename: string;
  content_type: string;
  tamanho_bytes: number | null;
  /** Falso quando o binário não está guardado: a tela mostra o nome, sem link. */
  disponivel: boolean;
  /**
   * Por que o binário foi recusado (tipo fora do catálogo ou acima do teto),
   * com o lugar do original. Null com `disponivel` falso: não veio do Resend.
   */
  motivo_indisponivel?: string | null;
}

/**
 * O item aberto. Não há HTML aqui, e isso é a decisão: ele fica guardado no
 * servidor e nunca chega à tela, que desenha só o corpo em texto.
 */
export interface EmailRecebido extends Omit<EmailRecebidoResumo, "quantidade_de_anexos"> {
  destinatarios: string[];
  corpo_texto: string | null;
  cabecalhos: Record<string, string>;
  anexos: AnexoDoEmail[];
  /**
   * Quantos anexos o e-mail anunciou além do teto de quantidade por e-mail.
   * Eles não viram anexo da lista: só a contagem, e o original fica na caixa.
   */
  anexos_excedentes?: number;
  /** Por que esses anexos ficaram de fora, com o lugar do original. */
  motivo_dos_excedentes?: string | null;
}

/** Quem pode abrir a Triagem de e-mail. */
export function podeVerTriagemDeEmail(perfil: string | null | undefined): boolean {
  return PERFIS_DA_TRIAGEM.includes(String(perfil));
}

/** O remetente pelo nome, e pelo endereço quando o e-mail não traz nome. */
export function nomeDoRemetente(
  email: Pick<EmailRecebidoResumo, "remetente_nome" | "remetente_endereco">
): string {
  return email.remetente_nome?.trim() || email.remetente_endereco;
}

const FORMATO_DA_CHEGADA = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** A data e a hora de chegada, no fuso do hospital. */
export function formatarChegada(iso: string): string {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return FORMATO_DA_CHEGADA.format(data).replace(",", "");
}

/** A contagem de anexos da linha da lista, em palavras. */
export function rotuloDosAnexos(quantidade: number): string {
  if (quantidade === 0) return "Sem anexo";
  return quantidade === 1 ? "1 anexo" : `${quantidade} anexos`;
}

/**
 * O aviso dos anexos que passaram do teto de quantidade por e-mail, ou null
 * quando não há. Eles não viram anexo da lista, mas o ouvidor precisa saber
 * que existem e onde está o original.
 */
export function avisoDosExcedentes(
  email: Pick<EmailRecebido, "anexos_excedentes" | "motivo_dos_excedentes">
): string | null {
  const quantidade = email.anexos_excedentes ?? 0;
  if (quantidade <= 0) return null;
  const rotulo = `Mais ${rotuloDosAnexos(quantidade)}`;
  return email.motivo_dos_excedentes ? `${rotulo}: ${email.motivo_dos_excedentes}` : rotulo;
}

/**
 * As marcas do item. "Interno" é remetente do domínio do hospital (resposta de
 * área, colega); "Incompleto" é corpo ou anexo que não veio do Resend.
 */
export function marcasDoEmail(email: Pick<EmailRecebidoResumo, "interno" | "incompleto">): string[] {
  return [...(email.interno ? ["Interno"] : []), ...(email.incompleto ? ["Incompleto"] : [])];
}
