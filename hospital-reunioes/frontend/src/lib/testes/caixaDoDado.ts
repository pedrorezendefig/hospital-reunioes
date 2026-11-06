/**
 * A caixa em que um texto aparece, para os testes da Caixa alta (ADR 0080).
 *
 * A caixa alta é do CSS: o título, o botão, a aba e o nome de campo herdam
 * `text-transform: uppercase` da regra base, e o dado digitado desliga a regra
 * com `normal-case` no trecho dele. O jsdom não calcula o Tailwind, então o
 * teste lê a classe: sobe do elemento até achar a primeira classe de caixa,
 * que é a que vale para o texto (a mais próxima ganha na herança).
 */
export type Caixa = "normal-case" | "uppercase" | null;

export function caixaDoDado(elemento: Element): Caixa {
  for (let atual: Element | null = elemento; atual; atual = atual.parentElement) {
    const classes = (atual.getAttribute("class") ?? "").split(/\s+/);
    if (classes.includes("normal-case")) return "normal-case";
    if (classes.includes("uppercase")) return "uppercase";
  }
  return null;
}
