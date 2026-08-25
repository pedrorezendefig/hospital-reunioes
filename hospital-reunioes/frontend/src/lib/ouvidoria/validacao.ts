/**
 * Validação e acionamento da área (issue #325, ADR 0034).
 *
 * O que a tela precisa saber para o ouvidor validar tipo, área e gravidade, e
 * para a Diretoria manter o cadastro de responsáveis por setor. As regras de
 * quem pode o quê moram aqui, e não no JSX: o gate de verdade é o backend, mas
 * a tela não pode oferecer um caminho que termina em 403.
 */

import type { StatusManifestacao } from "./prazo";

export type Gravidade = "critico" | "alto" | "medio" | "baixo";

export const GRAVIDADES: Gravidade[] = ["critico", "alto", "medio", "baixo"];

export const LABEL_GRAVIDADE: Record<Gravidade, string> = {
  critico: "Crítico",
  alto: "Alto",
  medio: "Médio",
  baixo: "Baixo",
};

/** O que cada nível significa na prática, na linguagem da spec da Diretoria. */
export const AJUDA_GRAVIDADE: Record<Gravidade, string> = {
  critico: "Risco à vida, à segurança ou à imagem. A área é acionada na hora, fora do expediente inclusive.",
  alto: "Dano relevante ao paciente ou ao serviço. A área responde em 2 dias úteis.",
  medio: "Falha que precisa de correção, sem dano imediato.",
  baixo: "Sugestão, elogio ou queixa que a ouvidoria resolve direto.",
};

export const CLASSE_GRAVIDADE: Record<Gravidade, string> = {
  critico: "bg-red-100 text-red-700 border-red-200",
  alto: "bg-orange-100 text-orange-700 border-orange-200",
  medio: "bg-amber-100 text-amber-700 border-amber-200",
  baixo: "bg-slate-100 text-slate-600 border-slate-200",
};

/**
 * Só o caso em classificação vira acionamento. Antes disso não há o que
 * despachar; depois, o setor já foi acordado e validar de novo o acordaria
 * duas vezes pelo mesmo motivo.
 */
export function podeValidar(status: StatusManifestacao): boolean {
  return status === "em_classificacao";
}

/**
 * Encerrar segue o grafo da máquina de estados (RPC `ouvidoria_transicionar`):
 * qualquer caso já classificado encerra, inclusive sem resposta da área (o
 * desfecho "sem condições de apuração" existe para isso). "Novo" ainda não
 * passou pela classificação e "encerrado" já acabou.
 */
export function podeEncerrar(status: StatusManifestacao): boolean {
  return status === "em_classificacao" || status === "aguardando_area" || status === "respondido";
}

export type Desfecho = "procedente" | "improcedente" | "parcialmente_procedente" | "sem_condicoes_de_apuracao";

export const DESFECHOS: Desfecho[] = [
  "procedente",
  "improcedente",
  "parcialmente_procedente",
  "sem_condicoes_de_apuracao",
];

export const LABEL_DESFECHO: Record<Desfecho, string> = {
  procedente: "Procedente",
  improcedente: "Improcedente",
  parcialmente_procedente: "Parcialmente procedente",
  sem_condicoes_de_apuracao: "Sem condições de apuração",
};

/**
 * Encerramento sem desfecho descrito é bloqueado (regra da fundação, RPC da
 * migration 064). A tela repete a régua para não oferecer um envio que
 * termina em 422.
 */
export function descricaoDeDesfechoValida(descricao: string): boolean {
  return descricao.trim().length > 0;
}

/**
 * Quem mantém o cadastro de responsáveis. Mesma régua da tabela de prazos: o
 * ouvidor trabalha com o cadastro, quem o define é a Diretoria Executiva.
 */
export function podeGerirResponsaveis(perfilOuvidoria: string | null | undefined): boolean {
  return perfilOuvidoria === "diretoria_executiva";
}

export type PapelResponsavel = "titular" | "substituto" | "gestor";

export const PAPEIS: PapelResponsavel[] = ["titular", "substituto", "gestor"];

export const LABEL_PAPEL: Record<PapelResponsavel, string> = {
  titular: "Titular",
  substituto: "Substituto",
  gestor: "Gestor da área",
};

export const AJUDA_PAPEL: Record<PapelResponsavel, string> = {
  titular: "Recebe o acionamento da Ouvidoria.",
  substituto: "Entra na cobrança quando o prazo estoura.",
  gestor: "Recebe a demanda quando o setor está sem titular vigente.",
};

export interface Responsavel {
  id: string;
  setor: string;
  papel: PapelResponsavel;
  nome: string;
  email: string;
  vigencia_inicio: string;
  vigencia_fim: string | null;
}

/**
 * A pessoa responde pelo setor neste dia. Mesma regra do servidor
 * (`app/services/ouvidoria_responsaveis.py`), com o fim inclusivo: quem sai no
 * dia 31 ainda responde no dia 31. Datas em ISO, comparadas como data civil.
 */
export function estaVigente(responsavel: Responsavel, hoje: string): boolean {
  if (responsavel.vigencia_inicio > hoje) return false;
  if (responsavel.vigencia_fim && responsavel.vigencia_fim < hoje) return false;
  return true;
}

/**
 * O setor está acionável quando tem titular vigente. Sem ele a demanda sobe ao
 * gestor, e a tela avisa a Diretoria antes de o caso chegar lá.
 */
export function setorTemTitularVigente(responsaveis: Responsavel[], hoje: string): boolean {
  return responsaveis.some((r) => r.papel === "titular" && estaVigente(r, hoje));
}

/**
 * `enviando` é a linha em voo: o servidor a reivindica antes de chamar o
 * provedor de email, para o job periódico não mandar a mesma cobrança de novo.
 * Linha que fica nesse estado é envio cuja confirmação se perdeu, e quem decide
 * insistir é o ouvidor, pelo botão de reenvio.
 */
export type StatusNotificacao = "agendada" | "enviando" | "enviada" | "falha";

export const LABEL_STATUS_NOTIFICACAO: Record<StatusNotificacao, string> = {
  agendada: "Na fila",
  enviando: "Em envio",
  enviada: "Enviada",
  falha: "Falhou",
};

export const LABEL_GATILHO: Record<string, string> = {
  nova_demanda: "Acionamento do setor",
  alerta_sem_titular: "Alerta de setor sem titular",
  prazo_rompido: "Cobrança de prazo rompido",
};

export interface Notificacao {
  id: string;
  gatilho: string;
  destinatario_nome: string;
  destinatario_email: string;
  papel_destinatario: string | null;
  status: StatusNotificacao;
  tentativas: number;
  enviar_a_partir_de: string;
  enviada_em: string | null;
  criada_em: string;
}
