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

/**
 * Padrão anti-vazio da casa. A régua é a mesma do backend (que exige um
 * caractere de palavra): relato só de emoji ou de pontuação seria recusado lá
 * com 422, e é melhor a pessoa saber disso antes de perder o que escreveu.
 */
export function relatoEstaVazio(relato: string): boolean {
  return !/[\p{L}\p{N}]/u.test(relato);
}

/**
 * O rótulo de origem que a página exibe a partir da URL do QR.
 *
 * A página é pública, tem a marca do hospital e a URL é feita para circular:
 * sem isto, um link montado à mão exibiria o texto que o autor quisesse dentro
 * de "Sobre o setor ...". O React já escapa o valor (não há XSS), mas frase
 * arbitrária em página de hospital é superfície de golpe. Só o servidor sabe
 * quais setores existem, então aqui a defesa é de forma: letras, números e
 * pontuação de nome, num rótulo curto. Nulo quando não sobra rótulo.
 */
export function rotuloDeOrigem(valor: string | null): string | null {
  if (!valor) return null;
  const limpo = valor
    .replace(/[^\p{L}\p{N}\s.,'()/-]/gu, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
  return /[\p{L}\p{N}]/u.test(limpo) ? limpo : null;
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
