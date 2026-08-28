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
  return (
    status === "em_classificacao" ||
    status === "aguardando_area" ||
    status === "aguardando_manifestante" ||
    status === "respondido"
  );
}

/**
 * A pausa por falta de dado do manifestante (issue #335). Só o caso que está
 * com a área tem relógio correndo para parar: pausar antes do acionamento não
 * pararia nada, e pausar o que já foi respondido não devolveria tempo a
 * ninguém.
 */
export function podePausar(status: StatusManifestacao): boolean {
  return status === "aguardando_area";
}

/** A volta da pausa. Só existe para o caso que está parado. */
export function podeRetomar(status: StatusManifestacao): boolean {
  return status === "aguardando_manifestante";
}

/**
 * A janela da reincidência, em dias CORRIDOS. Mesma régua do servidor
 * (`app/services/ouvidoria_estados.py`): quem volta a reclamar conta o tempo no
 * calendário da vida, não no expediente do hospital.
 */
export const JANELA_REINCIDENCIA_DIAS = 30;

/**
 * Reabrir o caso original por reincidência (issue #335). Fora da janela o
 * retorno é problema novo, e a tela não pode oferecer um caminho que termina
 * em 409: o certo ali é registrar manifestação nova.
 */
export function podeReabrir(
  status: StatusManifestacao,
  encerradaEm: string | null | undefined,
  agora: string,
): boolean {
  if (status !== "encerrado" || !encerradaEm) return false;
  const decorridos = (Date.parse(agora) - Date.parse(encerradaEm)) / (1000 * 60 * 60 * 24);
  return decorridos >= 0 && decorridos <= JANELA_REINCIDENCIA_DIAS;
}

export type Desfecho =
  | "procedente"
  | "improcedente"
  | "parcialmente_procedente"
  | "sem_condicoes_de_apuracao"
  | "sem_retorno_do_manifestante";

export const DESFECHOS: Desfecho[] = [
  "procedente",
  "improcedente",
  "parcialmente_procedente",
  "sem_condicoes_de_apuracao",
  "sem_retorno_do_manifestante",
];

export const LABEL_DESFECHO: Record<Desfecho, string> = {
  procedente: "Procedente",
  improcedente: "Improcedente",
  parcialmente_procedente: "Parcialmente procedente",
  sem_condicoes_de_apuracao: "Sem condições de apuração",
  sem_retorno_do_manifestante: "Sem retorno do manifestante",
};

/**
 * Os desfechos que ficam FORA da conta de resolvido versus não resolvido
 * (PRD #318, história 12). Mesma régua do servidor
 * (`app/services/ouvidoria_estados.py`).
 */
export const DESFECHOS_NEUTROS: Desfecho[] = ["sem_retorno_do_manifestante"];

export function contaNoIndicadorDeResolucao(desfecho: string | null | undefined): boolean {
  return !!desfecho && !DESFECHOS_NEUTROS.includes(desfecho as Desfecho);
}

/**
 * O esforço mínimo antes de encerrar por abandono (PRD #318, história 11): duas
 * tentativas de contato registradas. A espera de cinco dias úteis depende do
 * calendário e dos feriados, que só o servidor conhece, então a tela avisa e o
 * backend decide.
 */
export const TENTATIVAS_MINIMAS_DE_CONTATO = 2;

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
 * A área que já vem marcada no seletor da validação.
 *
 * Só vale o que está na taxonomia da casa. O caso do canal aberto chega com o
 * marcador "A definir", e o backend recusa acionar uma área que não existe
 * (issue #419): deixar o marcador escolhido levaria o ouvidor a clicar em
 * acionar para tomar um 422.
 *
 * Lista vazia é lista que ainda não chegou (ou que falhou ao carregar), e não
 * "nenhuma área existe": apagar a escolha por causa de um fetch lento seria
 * pior que manter o que está gravado.
 */
export function setorPreSelecionado(gravado: string | null | undefined, taxonomia: string[]): string {
  if (!gravado) return "";
  if (taxonomia.length === 0) return gravado;
  return taxonomia.includes(gravado) ? gravado : "";
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
  vespera_vencimento: "Lembrete da véspera do vencimento",
  escalonamento_gestor: "Escalonamento ao gestor da área",
  escalonamento_diretoria: "Escalonamento à Diretoria Executiva",
  alerta_cadastro_setor: "Alerta de setor sem gestor cadastrado",
  critico_imediato: "Aviso imediato de caso crítico",
  prorrogacao_solicitada: "Pedido de prorrogação",
  prorrogacao_decidida: "Decisão sobre a prorrogação",
  resposta_devolvida: "Devolução por insuficiência",
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
