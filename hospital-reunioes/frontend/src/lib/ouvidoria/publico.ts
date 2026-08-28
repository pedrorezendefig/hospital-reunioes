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
 * Defesa de FORMA sobre um texto que veio da URL: letras, números e pontuação
 * de nome, num rótulo curto. Nulo quando não sobra rótulo.
 *
 * Sozinha ela não decide o que a página exibe (issue #375, item 9): frase
 * inteira passa por esta régua, e frase em página de hospital é superfície de
 * golpe. Quem decide é `origemConfirmada`, contra a lista do servidor. Esta
 * fica como o corte de forma que roda antes da comparação.
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

/**
 * O rótulo de origem que a página pode exibir: o nome do setor como o SERVIDOR
 * escreve, ou nulo.
 *
 * A página é pública, tem a marca do hospital, e a URL do QR é feita para
 * circular. Exibindo o que estivesse em `?setor=`, um link montado à mão
 * escolhia a frase que aparece dentro de "Você leu o QR de ..." (issue #375,
 * item 9, decisão 3). O React escapa o valor, então não é XSS; é golpe.
 *
 * A comparação ignora caixa e espaço de sobra porque a URL circula e volta
 * de tudo quanto é jeito, mas o que vai para a tela é sempre a string da
 * taxonomia. Lista vazia ou ausente (taxonomia fora do ar) não exibe nada: a
 * página perde o enfeite da origem, e não ganha uma frase de estranho.
 */
export function origemConfirmada(
  valorDaUrl: string | null,
  setoresDoServidor: string[] | null
): string | null {
  const candidato = rotuloDeOrigem(valorDaUrl);
  if (!candidato || !setoresDoServidor?.length) return null;
  const procurado = candidato.trim().toLocaleLowerCase("pt-BR");
  return (
    setoresDoServidor.find(
      (nome) => nome.trim().toLocaleLowerCase("pt-BR") === procurado
    ) ?? null
  );
}
