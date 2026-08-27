/**
 * Formulário público de ouvidoria (issue #323, ADR 0034 decisão 9).
 *
 * O que o formulário decide antes de falar com o servidor: se há relato e o
 * que de fato vai no envio. A regra vale de novo no backend, que é quem grava.
 */

export interface FormularioPublico {
  relato: string;
  nome: string;
  contato: string;
  anonimo: boolean;
  /**
   * O código do cartaz que a pessoa leu, vindo do QR pela URL. Nulo no
   * formulário do site.
   *
   * É a ÚNICA origem que a página manda desde o ADR 0036 (decisão 10): o setor
   * e o ponto saem do cadastro, no servidor, e não de texto que o cliente
   * escolheu.
   */
  p: string | null;
}

export interface EnvioPublico {
  relato: string;
  anonimo: boolean;
  nome?: string;
  contato?: string;
  p?: string;
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
  return envio;
}

