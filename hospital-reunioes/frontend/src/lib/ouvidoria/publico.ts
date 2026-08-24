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
  /** Vem do QR setorial, pela URL. Nulo no formulário do site. */
  setor: string | null;
  ponto: string | null;
}

export interface EnvioPublico {
  relato: string;
  anonimo: boolean;
  nome?: string;
  contato?: string;
  setor?: string;
  ponto?: string;
}

/** Padrão anti-vazio da casa: espaço em branco não é manifestação. */
export function relatoEstaVazio(relato: string): boolean {
  return relato.trim().length === 0;
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
  const setor = form.setor?.trim();
  const ponto = form.ponto?.trim();
  if (setor) envio.setor = setor;
  if (setor && ponto) envio.ponto = ponto;
  return envio;
}
