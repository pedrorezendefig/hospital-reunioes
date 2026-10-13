/**
 * O Guia da faturista: tipos e textos (issue #1121, PRD #1113, ADR 0070).
 *
 * O servidor manda as linhas já agrupadas por dia e setor e os três números
 * prontos; aqui só se escreve o que a tela mostra. Cada linha começa pelo verbo
 * e diz a quantidade e o período (spec do diretor, item 4.3).
 */

export type AcaoGuia = "INCLUIR" | "AJUSTAR_QUANTIDADE" | "RETIRAR" | "CORRIGIR_PRECO" | "VALIDAR";

export type EstadoLinha =
  | "ABERTA"
  | "FEITO"
  | "NAO_PROCEDE"
  | "BLOQUEADO"
  | "EM_VALIDACAO"
  | "DECIDIDA";

export type MotivoNaoProcede = "JA_ESTA_NA_CONTA" | "SEM_EVIDENCIA" | "REGRA_E_OUTRA" | "OUTRO";

export interface LinhaGuia {
  id: string;
  acao: AcaoGuia;
  data: string | null;
  data_fim: string | null;
  setor: string | null;
  codigo: string | null;
  descricao: string | null;
  quantidade_lancada: number | null;
  quantidade_devida: number | null;
  preco_lancado: number | null;
  preco_tabela: number | null;
  valor_diferenca: number | null;
  regra_codigo: string | null;
  motivo: string | null;
  evidencia_pagina: number | null;
  evidencia_trecho: string | null;
  nivel_evidencia: "REGISTRADO" | "PRESCRITO" | "PRESCRITO_SN" | "POR_REGRA" | null;
  confianca: "ALTA" | "MEDIA" | "BAIXA" | null;
  estado: EstadoLinha;
  motivo_nao_procede: MotivoNaoProcede | null;
  texto_nao_procede: string | null;
  nao_conferido: boolean;
  /** A marca do reenvio da conta corrigida (issue #1136), só nas linhas Feito de conta reenviada. */
  reenvio?: MarcaDoReenvio | null;
}

export type MarcaDoReenvio = "CORRIGIDA" | "AINDA_NA_CONTA";

export interface Reenvio {
  nota_saida: number | null;
  reenviada_em: string;
  corrigidas: number;
  ainda_na_conta: number;
}

export interface GrupoGuia {
  data: string | null;
  setor: string | null;
  linhas: LinhaGuia[];
}

export interface Guia {
  cabecalho: {
    numero_atendimento: string | null;
    paciente_rotulo: string | null;
    numero_conta: string | null;
    operadora: string | null;
    coluna_preco: string | null;
    periodo_inicio: string | null;
    periodo_fim: string | null;
    situacao: string;
    parecer_parcial: boolean;
    faltantes: unknown[];
  };
  numeros: {
    nota_entrada: number;
    valor_a_ajustar: number;
    itens_a_ajustar: number;
    valor_em_validacao: number;
    itens_feitos: number;
    itens_total: number;
    itens_sem_marcacao: number;
  };
  grupos: GrupoGuia[];
  /** O botão "Reanalisar" (issue #1130): a permissão de regra contratual e tabelas, na conta ainda aberta. */
  pode_reanalisar?: boolean;
  /** O reenvio da conta corrigida (issue #1136): nulo enquanto a conta não foi reenviada. */
  reenvio?: Reenvio | null;
  /** O botão "Reenviar conta corrigida": a conta concluída. */
  pode_reenviar?: boolean;
  /** O "Responder ao time" da Validação sobre o que esta conta levantou (issue #1142). */
  respostas?: RespostaDaValidacao[];
}

export interface RespostaDaValidacao {
  titulo: string;
  regra_codigo: string | null;
  resposta: string;
  decidido_em: string | null;
}

export const ROTULO_REENVIO: Record<MarcaDoReenvio, string> = {
  CORRIGIDA: "corrigida no MV",
  AINDA_NA_CONTA: "ainda na conta",
};

/** "2 corrigidas no MV, 1 ainda na conta, nota de saída 86" */
export function resumoDoReenvio(r: { corrigidas: number; ainda_na_conta: number; nota_saida: number | null }): string {
  const corrigidas = `${r.corrigidas} ${r.corrigidas === 1 ? "corrigida" : "corrigidas"} no MV`;
  return `${corrigidas}, ${r.ainda_na_conta} ainda na conta, nota de saída ${r.nota_saida}`;
}

export const ROTULO_ACAO: Record<AcaoGuia, string> = {
  INCLUIR: "Incluir",
  AJUSTAR_QUANTIDADE: "Ajustar quantidade",
  CORRIGIR_PRECO: "Corrigir preço",
  RETIRAR: "Retirar",
  VALIDAR: "Validar",
};

export const MOTIVOS_NAO_PROCEDE: { valor: MotivoNaoProcede; rotulo: string }[] = [
  { valor: "JA_ESTA_NA_CONTA", rotulo: "Já está na conta" },
  { valor: "SEM_EVIDENCIA", rotulo: "Sem evidência no prontuário" },
  { valor: "REGRA_E_OUTRA", rotulo: "A regra é outra" },
  { valor: "OUTRO", rotulo: "Outro" },
];

export const ROTULO_NIVEL: Record<NonNullable<LinhaGuia["nivel_evidencia"]>, string> = {
  REGISTRADO: "Registrado",
  PRESCRITO: "Prescrito",
  PRESCRITO_SN: "Prescrito SN",
  POR_REGRA: "Por regra",
};

/**
 * A etiqueta âmbar da linha "se necessário" sem registro de uso no MV (nível
 * PRESCRITO_SN, issue #1134). O texto para a faturista vem no motivo.
 */
export const ETIQUETA_SE_NECESSARIO = "SE NECESSÁRIO · SEM REGISTRO NO MV";

/** O motivo que o Não procede já traz marcado: a linha SN sem uso não tem evidência. */
export function motivoInicialDoNaoProcede(linha: LinhaGuia): MotivoNaoProcede | null {
  return linha.nivel_evidencia === "PRESCRITO_SN" ? "SEM_EVIDENCIA" : null;
}

export const ROTULO_SITUACAO: Record<string, string> = {
  A_FAZER: "A fazer",
  EM_CORRECAO: "Em correção",
  CONCLUIDA: "Concluída",
  CONCLUIDA_COM_PENDENCIA: "Concluída com pendência",
  RETORNO: "Retorno",
};

export const CONCLUIDAS = ["CONCLUIDA", "CONCLUIDA_COM_PENDENCIA"];

const DINHEIRO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const PRECO = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const QUANTIDADE = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });

/** "1.212,00" */
export function reais(valor: number): string {
  return DINHEIRO.format(valor);
}

/** "+R$ 68,40" ou "-R$ 4,17": hífen, e não travessão nem sinal de menos. */
export function valorComSinal(valor: number): string {
  return `${valor < 0 ? "-" : "+"}R$ ${reais(Math.abs(valor))}`;
}

/** "03/10", de uma data ISO. */
export function dataCurta(iso: string): string {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
}

function periodo(linha: LinhaGuia): string {
  if (!linha.data) return "";
  if (linha.data_fim && linha.data_fim !== linha.data) {
    return `de ${dataCurta(linha.data)} a ${dataCurta(linha.data_fim)}`;
  }
  return `em ${dataCurta(linha.data)}`;
}

function quantidade(valor: number): string {
  return QUANTIDADE.format(valor);
}

function verbo(linha: LinhaGuia): string {
  const lancada = linha.quantidade_lancada;
  const devida = linha.quantidade_devida;
  switch (linha.acao) {
    case "INCLUIR":
      return devida == null ? "Incluir" : `Incluir ${quantidade(devida - (lancada ?? 0))}`;
    case "AJUSTAR_QUANTIDADE":
      return lancada == null || devida == null
        ? "Ajustar quantidade"
        : `Ajustar quantidade de ${quantidade(lancada)} para ${quantidade(devida)}`;
    case "RETIRAR":
      return lancada == null ? "Retirar" : `Retirar ${quantidade(lancada - (devida ?? 0))}`;
    case "CORRIGIR_PRECO":
      return linha.preco_lancado == null || linha.preco_tabela == null
        ? "Corrigir preço"
        : `Corrigir preço de R$ ${PRECO.format(linha.preco_lancado)} para R$ ${PRECO.format(linha.preco_tabela)}`;
    default:
      return ROTULO_ACAO[linha.acao] ?? linha.acao;
  }
}

/** "Incluir 180, de 03/10 a 05/10": o verbo na frente, a quantidade e o período. */
export function textoDaLinha(linha: LinhaGuia): string {
  const quando = periodo(linha);
  return quando ? `${verbo(linha)}, ${quando}` : verbo(linha);
}

/** "03/10 · CTI" */
export function rotuloDoGrupo(grupo: GrupoGuia): string {
  const partes = [grupo.data ? dataCurta(grupo.data) : "Sem data", grupo.setor ?? "Sem setor"];
  return partes.join(" · ");
}

/** A confirmação de concluir com item sem marcação; sem nenhum, não pergunta. */
export function perguntaDeConclusao(semMarcacao: number): string | null {
  if (semMarcacao <= 0) return null;
  const itens = semMarcacao === 1 ? "1 item" : `${semMarcacao} itens`;
  return `${itens} sem marcação. Concluir assim mesmo?`;
}
