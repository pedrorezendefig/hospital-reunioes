/**
 * A Triagem de e-mail da Ouvidoria (issue #648, PRD #646, ADR 0051).
 *
 * Todo e-mail que chega em ouvidoria@ entra numa lista que só o Perfil da
 * Ouvidoria vê, antes de virar caso. O ouvidor lê a lista e o item, com o
 * corpo em texto e os anexos, e pode virar o e-mail em manifestação (issue
 * #650). Não é "caixa de entrada": o app não responde e-mail por aqui.
 *
 * Aqui moram os tipos do que a API devolve e as regras puras da tela. O gate
 * de verdade é o backend (`require_perfil_ouvidoria`, 403 para os demais).
 */

import type { StatusManifestacao } from "./prazo";
import type { FormularioRegistro } from "./registro";

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
  /** Quem decidiu e quando: null enquanto o item está pendente. */
  decidido_em?: string | null;
  decidido_por_nome?: string | null;
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

/**
 * O caso a que o e-mail pode ser juntado (issue #651), em resumo: o que o
 * ouvidor confere antes de confirmar.
 */
export interface ResumoDoCaso {
  id: string;
  protocolo: string;
  status: StatusManifestacao;
  setor: string | null;
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

const ROTULO_DO_ESTADO: Record<EstadoDaTriagem, string | null> = {
  pendente: null,
  virou_manifestacao: "Virou manifestação",
  juntado: "Juntado a um caso",
  descartado: "Descartado",
};

/** O que a lista diz do item já decidido. Pendente não tem marca. */
export function rotuloDoEstado(estado: EstadoDaTriagem): string | null {
  return ROTULO_DO_ESTADO[estado] ?? null;
}

/**
 * As marcas do item. "Interno" é remetente do domínio do hospital (resposta de
 * área, colega); "Incompleto" é corpo ou anexo que não veio do Resend.
 */
export function marcasDoEmail(email: Pick<EmailRecebidoResumo, "interno" | "incompleto">): string[] {
  return [...(email.interno ? ["Interno"] : []), ...(email.incompleto ? ["Incompleto"] : [])];
}

// ─── Virar manifestação (issue #650, ADR 0051 decisão 2) ────────────────────

/**
 * Os valores com que o registro manual abre quando o e-mail vira manifestação,
 * como a pré-carga da API devolve. Quem cria o caso continua sendo o registro
 * manual, com o `email_recebido_id` daqui.
 */
export interface PreCargaDoEmail {
  email_recebido_id: string;
  canal: "email";
  /** A chegada do e-mail, em ISO: é o T0 do caso, e não a hora do clique. */
  contato_em: string;
  manifestante_nome: string;
  manifestante_contato: string;
  resumo: string;
  relato_integral: string;
  /** Os anexos do e-mail: os que estão guardados passam a ser do caso. */
  anexos: AnexoDoEmail[];
}

const PARTES_DO_CAMPO = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Sao_Paulo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/**
 * A chegada do e-mail no formato do campo datetime-local, em hora de
 * Brasília, que é como o backend lê o valor sem fuso. Os segundos ficam: o T0
 * é a chegada exata, e não o minuto arredondado.
 */
export function chegadaParaCampoLocal(iso: string): string {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "";
  const partes = Object.fromEntries(PARTES_DO_CAMPO.formatToParts(data).map((p) => [p.type, p.value]));
  return `${partes.year}-${partes.month}-${partes.day}T${partes.hour}:${partes.minute}:${partes.second}`;
}

/**
 * O formulário do modal "Nova manifestação" preenchido com o e-mail. Tipo,
 * setor e resumo ficam para o ouvidor; nenhum campo é trava, e o que vale é o
 * que ele salvar.
 */
export function formularioDaPreCarga(pre: PreCargaDoEmail): FormularioRegistro {
  return {
    canal: pre.canal,
    contatoEm: chegadaParaCampoLocal(pre.contato_em),
    tipoManifestacao: "",
    categoria: "",
    setor: "",
    resumo: pre.resumo,
    relatoIntegral: pre.relato_integral,
    manifestanteNome: pre.manifestante_nome,
    manifestanteContato: pre.manifestante_contato,
    manifestanteVinculo: "",
    pacienteNome: "",
    pacienteReferencia: "",
    anonimo: false,
  };
}
