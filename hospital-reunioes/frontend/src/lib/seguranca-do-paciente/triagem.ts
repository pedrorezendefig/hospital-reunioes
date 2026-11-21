/**
 * A tela de triagem do Núcleo (issue #1992, PRD #1979): os tipos que a API
 * devolve, os rótulos da tela e as regras que a tela aplica antes de enviar.
 * Quem decide de verdade é o servidor; aqui a tela só não oferece o que ele
 * vai recusar.
 */

export const ORIENTACAO_DA_TRIAGEM =
  "Leia o relato, confira a sugestão e confirme. Se discordar, ajuste: o sistema aprende com a diferença.";
export const ORIENTACAO_DO_CASO_GRAVE = "Caso grave: confirme cada campo. O prazo legal já está correndo.";

export interface ItemDaFila {
  id: string;
  protocolo: string;
  criado_em: string;
  data_ocorrencia: string | null;
  setor: string | null;
  grave_ou_morte: boolean | null;
  faixa: string | null;
  assunto: string | null;
  classificar_manualmente: boolean;
}

export interface Evento {
  situacao: "sim" | "possivel" | "nao" | null;
  item: number | null;
  motivo: string | null;
}

export interface LinhaDeTriagem {
  assunto: string;
  natureza: string;
  grau_de_dano: string;
  categoria: string;
  incidente: string | null;
  evento: Evento;
  iras: boolean;
  risco_de_imagem: boolean;
  protocolo_basico: string;
  canais: string[];
  motivo_do_encaminhamento: string | null;
  faixa: string;
  revisao: string;
  justificativa: string | null;
  confianca: "alta" | "media" | "baixa" | null;
  motivo_da_confianca: string | null;
  alertas: string[];
  perguntas_ao_notificante: string[];
  divergencias: string[] | null;
  frequencia: string | null;
  prioridade: string | null;
}

export interface CasoParecido {
  id: string;
  protocolo: string;
  data_ocorrencia: string;
  estado: string;
  assunto: string | null;
}

export interface Cortes {
  janela_meses: number;
  incomum_a_partir: number;
  ocasional_a_partir: number;
  frequente_a_partir: number;
}

export interface Contexto {
  recorrencia: number | null;
  janela_da_recorrencia_dias: number;
  parecidos: CasoParecido[];
  anteriores: number | null;
  frequencia: string | null;
  prioridade: string | null;
  cortes: Cortes;
}

/** A classificação que a pessoa envia ao ajustar ou ao classificar à mão. */
export interface Classificacao {
  assunto: string;
  natureza: string;
  grau_de_dano: string;
  categoria: string;
  incidente: string;
  evento_situacao: string;
  evento_item: number | null;
  iras: boolean;
  risco_de_imagem: boolean;
  protocolo_basico: string;
  canais: string[];
}

export const CLASSIFICACAO_EM_BRANCO: Classificacao = {
  assunto: "",
  natureza: "",
  grau_de_dano: "",
  categoria: "",
  incidente: "",
  evento_situacao: "",
  evento_item: null,
  iras: false,
  risco_de_imagem: false,
  protocolo_basico: "",
  canais: ["NSP"],
};

export function classificacaoDaSugestao(s: LinhaDeTriagem): Classificacao {
  return {
    assunto: s.assunto,
    natureza: s.natureza,
    grau_de_dano: s.grau_de_dano,
    categoria: s.categoria,
    incidente: s.incidente ?? "",
    evento_situacao: s.evento.situacao ?? "nao",
    evento_item: s.evento.item,
    iras: s.iras,
    risco_de_imagem: s.risco_de_imagem,
    protocolo_basico: s.protocolo_basico,
    canais: [...s.canais],
  };
}

type Opcoes = { valor: string; rotulo: string }[];

export const NATUREZAS: Opcoes = [
  { valor: "circunstancia_de_risco", rotulo: "Circunstância de risco" },
  { valor: "quase_erro", rotulo: "Quase erro" },
  { valor: "incidente_sem_dano", rotulo: "Incidente sem dano" },
  { valor: "evento_adverso", rotulo: "Evento adverso" },
  { valor: "nao_e_do_nsp", rotulo: "Não é do Núcleo" },
  { valor: "indeterminada", rotulo: "Indeterminada" },
];

export const GRAUS_DE_DANO: Opcoes = [
  { valor: "nenhum", rotulo: "Nenhum" },
  { valor: "leve", rotulo: "Leve" },
  { valor: "moderado", rotulo: "Moderado" },
  { valor: "grave", rotulo: "Grave" },
  { valor: "obito", rotulo: "Óbito" },
  { valor: "nao_se_aplica", rotulo: "Não se aplica" },
];

export const SITUACOES_DA_LISTA: Opcoes = [
  { valor: "nao", rotulo: "Não" },
  { valor: "possivel", rotulo: "Possível" },
  { valor: "sim", rotulo: "Sim" },
];

export const PROTOCOLOS_BASICOS: Opcoes = [
  { valor: "nenhum", rotulo: "Nenhum" },
  { valor: "identificacao", rotulo: "Identificação do paciente" },
  { valor: "higiene_das_maos", rotulo: "Higiene das mãos" },
  { valor: "cirurgia_segura", rotulo: "Cirurgia segura" },
  { valor: "medicamentos", rotulo: "Medicamentos" },
  { valor: "quedas", rotulo: "Quedas" },
  { valor: "lesao_por_pressao", rotulo: "Lesão por pressão" },
];

export const CANAIS: Opcoes = [
  { valor: "NSP", rotulo: "Núcleo" },
  { valor: "OUV", rotulo: "Ouvidoria" },
  { valor: "COND", rotulo: "Canal de Conduta" },
  { valor: "SST", rotulo: "Segurança do Trabalho" },
  { valor: "QT", rotulo: "Queixa técnica" },
  { valor: "FORA", rotulo: "Fora de escopo" },
];

export const CONFIANCAS: Record<string, string> = { alta: "alta", media: "média", baixa: "baixa" };
export const FREQUENCIAS: Record<string, string> = {
  remoto: "Remota",
  incomum: "Incomum",
  ocasional: "Ocasional",
  frequente: "Frequente",
};
export const PRIORIDADES: Record<string, string> = { alta: "Alta", moderada: "Moderada", baixa: "Baixa" };

/** Os campos que a Presidência confere um a um, na ordem da tela. */
export const CAMPOS: { campo: string; rotulo: string }[] = [
  { campo: "assunto", rotulo: "Assunto" },
  { campo: "natureza", rotulo: "Natureza" },
  { campo: "grau_de_dano", rotulo: "Grau de dano" },
  { campo: "categoria", rotulo: "Categoria" },
  { campo: "incidente", rotulo: "Incidente" },
  { campo: "evento", rotulo: "Evento que nunca deveria ocorrer" },
  { campo: "iras", rotulo: "IRAS" },
  { campo: "risco_de_imagem", rotulo: "Risco de imagem" },
  { campo: "protocolo_basico", rotulo: "Protocolo básico" },
  { campo: "canais", rotulo: "Canal" },
  { campo: "faixa", rotulo: "Faixa" },
];

export const MOTIVOS_DA_CONFERENCIA: Record<string, string> = {
  faixa: "Faixa A ou B.",
  morte: "O relato fala em morte.",
  evento_possivel: "Evento que nunca deveria ocorrer marcado como possível.",
  grave_marcado: "Quem notificou marcou grave, e a sugestão ficou abaixo da faixa B.",
  agente: "O agente pediu a conferência campo a campo.",
};

export function rotulo(opcoes: Opcoes, valor: string | null | undefined): string {
  return opcoes.find((o) => o.valor === valor)?.rotulo ?? valor ?? "";
}

export function rotuloDaFaixa(faixa: string | null | undefined): string {
  if (!faixa) return "Sem faixa";
  return faixa === "nao_se_aplica" ? "Faixa não se aplica" : `Faixa ${faixa}`;
}

/** A recorrência como a tela mostra: "3ª ocorrência desta categoria neste setor em 60 dias". */
export function textoDaRecorrencia(contexto: Contexto): string | null {
  if (contexto.recorrencia === null) return null;
  return `${contexto.recorrencia}ª ocorrência desta categoria neste setor em ${contexto.janela_da_recorrencia_dias} dias`;
}

/** A faixa pela regra de coerência do Anexo B, a mesma do servidor. */
export function faixaEsperada(natureza: string, grauDeDano: string, situacaoDaLista: string): string {
  if (grauDeDano === "obito" || situacaoDaLista === "sim") return "A";
  if (grauDeDano === "grave") return "B";
  if (grauDeDano === "moderado") return "C";
  if (grauDeDano === "leve" || natureza === "incidente_sem_dano") return "D";
  if (natureza === "quase_erro" || natureza === "circunstancia_de_risco") return "E";
  return "nao_se_aplica";
}

/** Confirmar só libera, na revisão campo a campo, com todos os campos marcados. */
export function podeConfirmar(campoACampo: boolean, marcados: ReadonlySet<string>): boolean {
  return !campoACampo || CAMPOS.every(({ campo }) => marcados.has(campo));
}

/** A classificação completa o bastante para ir ao servidor. */
export function classificacaoPreenchida(c: Classificacao): boolean {
  return Boolean(
    c.assunto.trim() &&
      c.natureza &&
      c.grau_de_dano &&
      c.categoria &&
      c.evento_situacao &&
      (c.evento_situacao === "nao" || c.evento_item !== null) &&
      c.protocolo_basico &&
      c.canais.length > 0
  );
}
