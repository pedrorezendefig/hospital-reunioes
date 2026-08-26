/**
 * Spec das três tabelas de valores do módulo Dados do Atendimento
 * (ADR 0031; convênios por especialidade saiu no ADR 0038). Espelho da spec do backend
 * (app/routers/admin/dados_atendimento.py): campos editáveis, obrigatórios
 * e colunas da listagem.
 */

export type CampoTipo = "text" | "textarea" | "number" | "boolean";

export type Campo = {
  key: string;
  label: string;
  tipo: CampoTipo;
  obrigatorio?: boolean;
};

export type Coluna = {
  key: string;
  header: string;
  formato?: "moeda" | "simnao";
  width?: string;
};

export type TabelaSpec = {
  slug: string;
  titulo: string;
  itemNoun: string;
  artigo: "o" | "a";
  campos: Campo[];
  colunas: Coluna[];
};

export type Registro = {
  id: string;
  ativo: boolean;
  ultima_atualizacao: string;
  [key: string]: unknown;
};

export const TABELAS: TabelaSpec[] = [
  {
    slug: "consultas-particulares",
    titulo: "Consultas particulares",
    itemNoun: "consulta particular",
    artigo: "a",
    campos: [
      { key: "especialidade", label: "Especialidade", tipo: "text", obrigatorio: true },
      { key: "valor_rs", label: "Valor (R$)", tipo: "number", obrigatorio: true },
      { key: "descricao_servico", label: "Descrição do serviço", tipo: "textarea", obrigatorio: true },
      { key: "diferencial_1", label: "Diferencial 1", tipo: "textarea" },
      { key: "diferencial_2", label: "Diferencial 2", tipo: "textarea" },
      { key: "diferencial_3", label: "Diferencial 3", tipo: "textarea" },
      { key: "alta_demanda", label: "Alta demanda", tipo: "boolean" },
      { key: "observacoes_ana", label: "Observações para a Ana", tipo: "textarea" },
    ],
    colunas: [
      { key: "especialidade", header: "Especialidade" },
      { key: "valor_rs", header: "Valor", formato: "moeda", width: "120px" },
      { key: "alta_demanda", header: "Alta demanda", formato: "simnao", width: "130px" },
    ],
  },
  {
    slug: "exames",
    titulo: "Exames",
    itemNoun: "exame",
    artigo: "o",
    campos: [
      { key: "nome_exame", label: "Nome do exame", tipo: "text", obrigatorio: true },
      { key: "tipo_exame", label: "Tipo", tipo: "text", obrigatorio: true },
      { key: "valor_particular_rs", label: "Valor particular (R$)", tipo: "number", obrigatorio: true },
      { key: "convenio_aceito", label: "Aceita convênio", tipo: "boolean" },
      { key: "requer_pedido_medico", label: "Requer pedido médico", tipo: "boolean" },
      { key: "preparo_necessario", label: "Preparo necessário", tipo: "boolean" },
      { key: "instrucoes_preparo_completas", label: "Instruções de preparo", tipo: "textarea" },
      { key: "tempo_resultado", label: "Tempo de resultado", tipo: "text" },
      { key: "local_realizacao", label: "Local de realização", tipo: "text" },
      { key: "diferencial_1", label: "Diferencial 1", tipo: "textarea" },
      { key: "diferencial_2", label: "Diferencial 2", tipo: "textarea" },
      { key: "observacoes_ana", label: "Observações para a Ana", tipo: "textarea" },
    ],
    colunas: [
      { key: "nome_exame", header: "Exame" },
      { key: "tipo_exame", header: "Tipo", width: "140px" },
      { key: "valor_particular_rs", header: "Valor", formato: "moeda", width: "120px" },
      { key: "convenio_aceito", header: "Convênio", formato: "simnao", width: "110px" },
    ],
  },
  {
    slug: "cirurgias-estimativas",
    titulo: "Estimativas de cirurgias",
    itemNoun: "estimativa de cirurgia",
    artigo: "a",
    campos: [
      { key: "procedimento", label: "Procedimento", tipo: "text", obrigatorio: true },
      { key: "descricao_procedimento", label: "Descrição do procedimento", tipo: "textarea", obrigatorio: true },
      { key: "honorarios_equipe_rs", label: "Honorários da equipe (R$)", tipo: "number", obrigatorio: true },
      { key: "valor_internacao_rs", label: "Valor da internação (R$)", tipo: "number", obrigatorio: true },
      { key: "estimativa_total_rs", label: "Estimativa total (R$)", tipo: "number", obrigatorio: true },
      { key: "o_que_inclui_honorarios", label: "O que os honorários incluem", tipo: "textarea" },
      { key: "o_que_inclui_internacao", label: "O que a internação inclui", tipo: "textarea" },
      { key: "diferencial_1", label: "Diferencial 1", tipo: "textarea" },
      { key: "diferencial_2", label: "Diferencial 2", tipo: "textarea" },
      { key: "caveat_obrigatorio_ana", label: "Aviso obrigatório da Ana", tipo: "textarea", obrigatorio: true },
      { key: "observacoes_ana", label: "Observações para a Ana", tipo: "textarea" },
    ],
    colunas: [
      { key: "procedimento", header: "Procedimento" },
      { key: "honorarios_equipe_rs", header: "Honorários", formato: "moeda", width: "120px" },
      { key: "valor_internacao_rs", header: "Internação", formato: "moeda", width: "120px" },
      { key: "estimativa_total_rs", header: "Total", formato: "moeda", width: "120px" },
    ],
  },
];
