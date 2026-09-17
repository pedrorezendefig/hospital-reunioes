/**
 * Formulário público de ouvidoria (issue #323, ADR 0034 decisão 9).
 *
 * O que o formulário decide antes de falar com o servidor: se há relato e o
 * que de fato vai no envio. A regra vale de novo no backend, que é quem grava.
 */

/**
 * As quatro naturezas que o cartaz do ponto de escuta promete ao manifestante
 * (RN-88, issue #473, ADR 0040 decisão 3).
 *
 * NÃO é o tipo da manifestação (esse é do ouvidor, em `taxonomia.ts`): é a
 * sugestão de quem manifestou, e ela não decide tipo, estado nem sigilo. A
 * ordem é a da tela, com o elogio primeiro, porque o canal também serve para
 * elogiar. A lista fechada vale de novo no backend e no CHECK do banco.
 */
export type NaturezaInformada = "elogio" | "reclamacao" | "sugestao" | "informacao";

export const NATUREZAS_INFORMADAS: { valor: NaturezaInformada; rotulo: string }[] = [
  { valor: "elogio", rotulo: "Elogio" },
  { valor: "reclamacao", rotulo: "Reclamação" },
  { valor: "sugestao", rotulo: "Sugestão" },
  { valor: "informacao", rotulo: "Informação" },
];

/**
 * De quem é o relato (issue #666, ADR 0052, decisão 2).
 *
 * São duas palavras da TELA, e não os vínculos que o caso grava: quem responde
 * "Sobre mim" entra como `paciente` e quem responde "Sobre outra pessoa" entra
 * como `acompanhante`, e essa tradução é do servidor. Manter as duas grafias
 * separadas é o que impede o canal público de escrever vínculo direto.
 */
export type SobreQuem = "mim" | "outra_pessoa";

export const SOBRE_QUEM: { valor: SobreQuem; rotulo: string }[] = [
  { valor: "mim", rotulo: "Sobre mim" },
  { valor: "outra_pessoa", rotulo: "Sobre outra pessoa" },
];

/**
 * O que a tela diz quando falta a única resposta obrigatória do formulário.
 * Mora aqui porque é a régua do botão desabilitado, e não decoração da página.
 */
export const FALTA_DIZER_SOBRE_QUEM = 'Responda "Este relato é sobre quem?" para enviar.';

/**
 * O aviso abaixo do nome do paciente. A segunda frase só aparece para quem
 * pediu anonimato: "Acompanhante da Maria, leito 12" às vezes entrega quem
 * falou, e a pessoa decide isso sabendo (ADR 0052, consequências).
 */
export const AVISO_SEM_NOME_DO_PACIENTE =
  "Sem o nome do paciente, o hospital não consegue achar o atendimento.";
export const AVISO_PACIENTE_PODE_IDENTIFICAR =
  "O nome do paciente pode indicar quem manifestou.";

export function avisoDoPaciente(anonimo: boolean): string {
  return anonimo
    ? `${AVISO_SEM_NOME_DO_PACIENTE} ${AVISO_PACIENTE_PODE_IDENTIFICAR}`
    : AVISO_SEM_NOME_DO_PACIENTE;
}

export interface FormularioPublico {
  relato: string;
  nome: string;
  contato: string;
  anonimo: boolean;
  /**
   * A resposta a "Este relato é sobre quem?", ou nada enquanto a pessoa não
   * respondeu. É a única resposta obrigatória do formulário: sem ela o envio
   * nem sai, e o servidor devolveria 422.
   */
  sobre: SobreQuem | null;
  /** O Paciente do caso. Opcional, e só existe em "Sobre outra pessoa". */
  pacienteNome?: string;
  pacienteReferencia?: string;
  /**
   * O código do cartaz que a pessoa leu, vindo do QR pela URL. Nulo no
   * formulário do site.
   *
   * É a ÚNICA origem que a página manda desde o ADR 0036 (decisão 10): o setor
   * e o ponto saem do cadastro, no servidor, e não de texto que o cliente
   * escolheu.
   */
  p: string | null;
  /** A natureza que a pessoa marcou, ou nada: marcar é opcional. */
  natureza: NaturezaInformada | null;
}

export interface EnvioPublico {
  relato: string;
  anonimo: boolean;
  nome?: string;
  contato?: string;
  p?: string;
  natureza_informada?: NaturezaInformada;
  sobre?: SobreQuem;
  paciente_nome?: string;
  paciente_referencia?: string;
}

/**
 * Padrão anti-vazio da casa. A régua é a mesma do backend (que exige um
 * caractere de palavra): relato só de emoji ou de pontuação seria recusado lá
 * com 422, e é melhor a pessoa saber disso antes de perder o que escreveu.
 */
export function relatoEstaVazio(relato: string): boolean {
  return !/[\p{L}\p{N}]/u.test(relato);
}

/**
 * Monta o corpo do envio. Campo em branco é omitido em vez de virar string
 * vazia, e quem escolheu ser anônimo não leva identificação nenhuma, mesmo que
 * tenha digitado antes de marcar a caixa.
 */
export function montarEnvio(form: FormularioPublico): EnvioPublico {
  const envio: EnvioPublico = {
    relato: form.relato.trim(),
    anonimo: form.anonimo,
  };
  if (!form.anonimo) {
    const nome = form.nome.trim();
    const contato = form.contato.trim();
    if (nome) envio.nome = nome;
    if (contato) envio.contato = contato;
  }
  const codigo = form.p?.trim();
  if (codigo) envio.p = codigo;
  // Quem não escolheu natureza não manda campo nenhum: o caso entra sem
  // sugestão, que é o normal.
  if (form.natureza) envio.natureza_informada = form.natureza;
  if (form.sobre) envio.sobre = form.sobre;
  // O paciente só acompanha quem disse que o relato é sobre outra pessoa. Quem
  // respondeu "Sobre mim" e tinha digitado antes de trocar a resposta não leva
  // paciente nenhum, pelo mesmo motivo que o anônimo não leva identificação.
  //
  // O anonimato NÃO entra nesta conta: quem ele protege é quem fala, e o
  // paciente é outra pessoa (ADR 0052, decisão 3).
  if (form.sobre === "outra_pessoa") {
    const pacienteNome = form.pacienteNome?.trim();
    const pacienteReferencia = form.pacienteReferencia?.trim();
    if (pacienteNome) envio.paciente_nome = pacienteNome;
    if (pacienteReferencia) envio.paciente_referencia = pacienteReferencia;
  }
  return envio;
}

