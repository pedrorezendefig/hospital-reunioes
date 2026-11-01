/**
 * O Planejamento da Demanda, do lado da tela (issue #1345, PRD #1344, ADR 0075).
 *
 * A conversa vive no servidor, guardada na Demanda: a tela só pede, mostra e
 * manda a resposta. Quem decide quem pode planejar é o backend (409 com a
 * frase); o `podePlanejar` daqui só esconde o botão que já se sabe que vai
 * voltar recusado.
 */

import { BASE_TECNOLOGIA, Demanda, EstadoDemanda, ROTA_TECNOLOGIA, TipoDemanda } from "./demandas";

export type LetraDaOpcao = "A" | "B";

export type OpcaoDoPlanejamento = { letra: LetraDaOpcao; texto: string };

/**
 * Uma fala da conversa. `pergunta` e `encerrou` são da IA; `resposta` é de
 * quem planeja, com a letra clicada (nula quando escreveu no campo livre).
 * `nao_bateu` também é de quem planeja: o que não bateu no resumo (#1347).
 */
export type MensagemDoPlanejamento = {
  tipo: "pergunta" | "encerrou" | "resposta" | "nao_bateu";
  contexto?: string | null;
  opcoes?: OpcaoDoPlanejamento[];
  recomendada?: LetraDaOpcao | null;
  opcao?: LetraDaOpcao | null;
  texto?: string | null;
};

/**
 * O resumo do Fechar e resumir (issue #1347). A pergunta e a escolha vêm da
 * conversa, e o servidor descarta a decisão de pergunta que ficou sem resposta.
 */
export type DecisaoDoResumo = { pergunta: string; escolha: string; porque: string };

export type ResumoDoPlanejamento = { decisoes: DecisaoDoResumo[]; em_aberto: string[] };

/** `estado` nulo é "ainda não começou": não há conversa guardada. */
export type Planejamento = {
  demanda_id: string;
  titulo: string;
  estado: string | null;
  mensagens: MensagemDoPlanejamento[];
  decisoes: string[];
  resumo?: ResumoDoPlanejamento | null;
};

/** O que vai no POST: vazio começa, a letra ou o texto respondem. */
export type RespostaDoPlanejamento = { opcao: LetraDaOpcao } | { texto: string } | Record<string, never>;

/** Os Tipos que viram código (ADR 0075, decisão 2). */
export const TIPOS_QUE_SE_PLANEJAM: TipoDemanda[] = ["novo", "ajuste"];

const ESTADOS_ENCERRADOS: EstadoDemanda[] = ["concluida", "cancelada"];

export const PLANEJAR_COM_A_IA = "Planejar com a IA";

/**
 * O botão aparece no card de uma Demanda Novo ou Ajuste, aberta e sem Vínculo.
 *
 * O Vínculo vem do booleano `tem_vinculo`, que chega a todo mundo: o objeto
 * `vinculo` vem nulo para quem não tem login no GitHub (ADR 0054, decisão 9),
 * e por ele o diretor veria o botão numa Demanda que já foi para o
 * desenvolvimento.
 */
export function podePlanejar(demanda: Pick<Demanda, "tipo" | "estado" | "tem_vinculo">): boolean {
  return (
    TIPOS_QUE_SE_PLANEJAM.includes(demanda.tipo) &&
    !demanda.tem_vinculo &&
    !ESTADOS_ENCERRADOS.includes(demanda.estado)
  );
}

export function urlDoPlanejamento(demandaId: string): string {
  return `${BASE_TECNOLOGIA}/demandas/${encodeURIComponent(demandaId)}/planejamento`;
}

export function urlDoResumo(demandaId: string): string {
  return `${urlDoPlanejamento(demandaId)}/resumo`;
}

export function urlDoNao(demandaId: string): string {
  return `${urlDoPlanejamento(demandaId)}/nao`;
}

/** O "sim" do resumo (issue #1349): cria o PRD do diretor e vincula a Demanda. */
export function urlDoEnvio(demandaId: string): string {
  return `${urlDoPlanejamento(demandaId)}/enviar`;
}

/** A tela do planejamento, que o botão do card abre. */
export function rotaDoPlanejamento(demandaId: string): string {
  return `${ROTA_TECNOLOGIA}/planejamento/${encodeURIComponent(demandaId)}`;
}

/** A pergunta que espera resposta: a última fala, se for uma pergunta. */
export function perguntaEmAberto(planejamento: Planejamento | null): MensagemDoPlanejamento | null {
  const ultima = planejamento?.mensagens[planejamento.mensagens.length - 1];
  return ultima?.tipo === "pergunta" ? ultima : null;
}

/**
 * A conversa espera a IA falar: ainda não começou, ou a última fala é de
 * quem planeja sem pergunta depois (o "não" do resumo, cuja pergunta seguinte
 * ainda não veio ou falhou). A tela pede o turno nesses casos.
 */
export function esperaAIA(planejamento: Planejamento): boolean {
  if (planejamento.estado === null) return true;
  if (planejamento.estado !== "em_andamento") return false;
  return perguntaEmAberto(planejamento) === null;
}

function textoOuNulo(valor: unknown): boolean {
  return valor === undefined || valor === null || typeof valor === "string";
}

function letraOuNula(valor: unknown): boolean {
  return valor === undefined || valor === null || valor === "A" || valor === "B";
}

function mensagemValida(item: unknown): boolean {
  if (typeof item !== "object" || item === null) return false;
  const m = item as Record<string, unknown>;
  const opcoesValidas =
    m.opcoes === undefined ||
    (Array.isArray(m.opcoes) &&
      m.opcoes.every(
        (o) =>
          typeof o === "object" &&
          o !== null &&
          letraOuNula((o as Record<string, unknown>).letra) &&
          typeof (o as Record<string, unknown>).texto === "string",
      ));
  return (
    (m.tipo === "pergunta" || m.tipo === "encerrou" || m.tipo === "resposta" || m.tipo === "nao_bateu") &&
    textoOuNulo(m.contexto) &&
    textoOuNulo(m.texto) &&
    letraOuNula(m.recomendada) &&
    letraOuNula(m.opcao) &&
    opcoesValidas
  );
}

function listaDeTextos(valor: unknown): boolean {
  return Array.isArray(valor) && valor.every((t) => typeof t === "string");
}

function resumoValido(valor: unknown): boolean {
  if (valor === undefined || valor === null) return true;
  if (typeof valor !== "object") return false;
  const r = valor as Record<string, unknown>;
  return (
    Array.isArray(r.decisoes) &&
    r.decisoes.every((d) => {
      if (typeof d !== "object" || d === null) return false;
      const campos = d as Record<string, unknown>;
      return typeof campos.pergunta === "string" && typeof campos.escolha === "string" && typeof campos.porque === "string";
    }) &&
    listaDeTextos(r.em_aberto)
  );
}

/** O corpo serve para a tela usar? Mesma fronteira dos outros corpos da aba. */
export function planejamentoValido(corpo: unknown): corpo is Planejamento {
  if (typeof corpo !== "object" || corpo === null) return false;
  const p = corpo as Record<string, unknown>;
  return (
    typeof p.demanda_id === "string" &&
    typeof p.titulo === "string" &&
    textoOuNulo(p.estado) &&
    Array.isArray(p.mensagens) &&
    p.mensagens.every(mensagemValida) &&
    listaDeTextos(p.decisoes) &&
    resumoValido(p.resumo)
  );
}
