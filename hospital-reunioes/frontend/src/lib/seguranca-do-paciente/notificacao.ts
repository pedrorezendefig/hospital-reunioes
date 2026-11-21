/**
 * A Notificação de incidente (issue #1987, PRD #1979): os tipos, os textos das
 * opções e a montagem do envio, sem React, para a tela e o teste lerem igual.
 */

/** Por onde a pessoa chegou ao formulário. Quem notifica não escolhe. */
export type Porta = "qr" | "endereco" | "modulo";

export type Turno = "manha" | "tarde" | "noite";
export type ChegouAoPaciente = "nao" | "sem_dano" | "com_dano" | "nao_sei";
export type SimNaoNaoSei = "sim" | "nao" | "nao_sei";

export const TURNOS: { valor: Turno; rotulo: string }[] = [
  { valor: "manha", rotulo: "Manhã" },
  { valor: "tarde", rotulo: "Tarde" },
  { valor: "noite", rotulo: "Noite" },
];

export const CHEGOU_AO_PACIENTE: { valor: ChegouAoPaciente; rotulo: string }[] = [
  { valor: "nao", rotulo: "Não chegou" },
  { valor: "sem_dano", rotulo: "Chegou, sem dano" },
  { valor: "com_dano", rotulo: "Chegou, com dano" },
  { valor: "nao_sei", rotulo: "Não sei" },
];

export const PERCEBIDO: { valor: SimNaoNaoSei; rotulo: string }[] = [
  { valor: "sim", rotulo: "Sim" },
  { valor: "nao", rotulo: "Não" },
  { valor: "nao_sei", rotulo: "Não sei" },
];

export const TITULOS_DAS_TELAS = ["O que aconteceu", "Onde e quando", "O paciente foi atingido", "Identificação"];

/** A linha de orientação no topo de cada tela (seção 17 da especificação). */
export const ORIENTACOES = [
  "Conte com as suas palavras. Você não precisa classificar nada.",
  "Ajude o Núcleo a localizar o incidente.",
  "Diga até onde o incidente chegou.",
  "Escolha se o Núcleo pode saber quem notificou.",
];

export const SEM_PUNICAO = "Notificar não gera punição.";
export const AVISO_DO_PACIENTE =
  "Não escreva o nome do paciente. Se precisar, informe o leito ou o número do atendimento.";
export const QUEM_VE_O_NOME = "Seu nome aparece só para a Presidência do Núcleo e o Diretor Executivo.";

export interface FormularioDeNotificacao {
  relato: string;
  leito: string;
  setorId: string;
  data: string;
  turno: Turno | null;
  hora: string;
  chegou: ChegouAoPaciente | null;
  grave: boolean | null;
  percebido: SimNaoNaoSei | null;
  anonimo: boolean;
  nome: string;
  contato: string;
}

/** A gravidade só se pergunta quando houve dano ou a pessoa não sabe. */
export function perguntaAGravidade(chegou: ChegouAoPaciente | null): boolean {
  return chegou === "com_dano" || chegou === "nao_sei";
}

/** A tela (de 1 a 4) tem o que precisa para seguir? */
export function telaCompleta(tela: number, form: FormularioDeNotificacao, porta: Porta): boolean {
  if (tela === 1) return form.relato.trim() !== "";
  if (tela === 2) return form.setorId !== "" && form.data !== "" && form.turno !== null;
  if (tela === 3) return form.chegou !== null && (!perguntaAGravidade(form.chegou) || form.grave !== null);
  if (form.anonimo || porta === "modulo") return true;
  return form.nome.trim() !== "" && form.contato.trim() !== "";
}

/** O corpo do envio. A porta do módulo não manda nome nem contato: quem
 * identifica é a sessão. */
export function montarEnvio(form: FormularioDeNotificacao, porta: Porta): Record<string, unknown> {
  const envio: Record<string, unknown> = {
    relato: form.relato.trim(),
    leito_ou_atendimento: form.leito.trim() || null,
    setor_id: form.setorId,
    data_ocorrencia: form.data,
    turno: form.turno,
    hora_aproximada: form.hora || null,
    chegou_ao_paciente: form.chegou,
    grave_ou_morte: perguntaAGravidade(form.chegou) ? form.grave : null,
    percebido_ou_reclamacao: form.percebido,
    anonimo: form.anonimo,
  };
  if (porta !== "modulo") {
    envio.origem = porta;
    if (!form.anonimo) {
      envio.nome = form.nome.trim();
      envio.contato = form.contato.trim();
    }
  }
  return envio;
}

/** De onde o Núcleo achou o incidente, no registro rápido (issue #1998). */
export type OrigemDoRegistroRapido = "busca_ativa" | "ronda" | "reuniao_rapida" | "auditoria" | "outra";

export const ORIGENS_DO_REGISTRO_RAPIDO: { valor: OrigemDoRegistroRapido; rotulo: string }[] = [
  { valor: "busca_ativa", rotulo: "Busca ativa" },
  { valor: "ronda", rotulo: "Ronda" },
  { valor: "reuniao_rapida", rotulo: "Reunião rápida" },
  { valor: "auditoria", rotulo: "Auditoria" },
  { valor: "outra", rotulo: "Outra" },
];
