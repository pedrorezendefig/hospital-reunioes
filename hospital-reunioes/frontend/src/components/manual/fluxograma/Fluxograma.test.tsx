/**
 * @vitest-environment jsdom
 */

/**
 * O Fluxograma do manual (issue #1719, emenda da ADR 0094).
 *
 * Um bloco `fluxograma` do Markdown da página vira o desenho do app, em SVG,
 * com os passos e as ligações declarados. Os testes passam pelo mesmo caminho
 * da página: o `react-markdown` com o `PreDoManual` no lugar do `<pre>`.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PreDoManual } from "./PreDoManual";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** O `matchMedia` que o jsdom não tem, dublado: casa só as consultas pedidas. */
function simularTela(...consultasQueCasam: string[]) {
  vi.stubGlobal("matchMedia", (consulta: string) => ({
    matches: consultasQueCasam.includes(consulta),
    media: consulta,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/** O atraso e a duração, em ms, de uma `animation` escrita no style. */
function tempoDa(animacao: string): number {
  const [duracao, atraso] = [...animacao.matchAll(/(\d+)ms/g)].map((m) => Number(m[1]));
  return duracao + (atraso ?? 0);
}

const REUNIAO = [
  "inicio abrir 1,1: Abrir a reunião",
  "passo pauta 2,1: Montar a pauta | O Secretário escolhe os itens da semana.",
  "decisao quorum 3,1: Tem quórum?",
  "fim ata 4,1: Ata assinada",
  "passo remarcar 3,2: Remarcar a reunião",
  "abrir -> pauta",
  "pauta -> quorum",
  "quorum -> ata: sim",
  "quorum -> remarcar: não",
].join("\n");

function pagina(fonte: string): string {
  return ["# Reuniões", "", "Como a reunião anda:", "", "```fluxograma", fonte, "```", ""].join("\n");
}

function desenhar(fonte: string) {
  return render(<ReactMarkdown components={{ pre: PreDoManual }}>{pagina(fonte)}</ReactMarkdown>);
}

/** Os pontos de um `d` de SVG feito só de M e L. */
function pontosDo(d: string): [number, number][] {
  return [...d.matchAll(/(-?[\d.]+)[ ,](-?[\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);
}

describe("o bloco fluxograma da página", () => {
  it("vira o desenho com os passos e as ligações declarados", () => {
    const { container } = desenhar(REUNIAO);

    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    const passos = [...svg!.querySelectorAll("[data-passo]")];
    expect(passos.map((p) => p.getAttribute("data-passo"))).toEqual(["abrir", "pauta", "quorum", "ata", "remarcar"]);
    expect(svg!.querySelector('[data-passo="quorum"]')!.getAttribute("data-forma")).toBe("decisao");
    expect(svg!.querySelector('[data-passo="abrir"]')!.getAttribute("data-forma")).toBe("inicio");
    expect(svg!.querySelector('[data-passo="ata"]')!.getAttribute("data-forma")).toBe("fim");
    expect(svg!.querySelector('[data-passo="pauta"]')!.getAttribute("data-forma")).toBe("passo");
    expect(svg!.querySelector('[data-passo="pauta"]')!.textContent).toContain("Montar a pauta");

    const ligacoes = [...svg!.querySelectorAll("[data-ligacao]")].map((l) => l.getAttribute("data-ligacao"));
    expect(ligacoes).toEqual(["abrir->pauta", "pauta->quorum", "quorum->ata", "quorum->remarcar"]);
    expect(svg!.querySelector('[data-ligacao="quorum->remarcar"]')!.textContent).toContain("não");
    expect(svg!.querySelector('[data-ligacao="quorum->ata"]')!.textContent).toContain("sim");
    expect(svg!.querySelector('[data-ligacao="abrir->pauta"] [data-seta]')).not.toBeNull();

    // As ligações saem em ângulo reto: o caminho só anda na horizontal ou na vertical.
    for (const caminho of svg!.querySelectorAll("[data-ligacao] path:not([data-seta])")) {
      const pontos = pontosDo(caminho.getAttribute("d")!);
      expect(pontos.length).toBeGreaterThanOrEqual(2);
      for (let i = 1; i < pontos.length; i++) {
        const [x0, y0] = pontos[i - 1];
        const [x1, y1] = pontos[i];
        expect(x0 === x1 || y0 === y1).toBe(true);
      }
    }
    // O passo da coluna 2 fica à direita do da coluna 1, na mesma linha.
    const xDe = (id: string) => Number(svg!.querySelector(`[data-passo="${id}"]`)!.getAttribute("data-x"));
    const yDe = (id: string) => Number(svg!.querySelector(`[data-passo="${id}"]`)!.getAttribute("data-y"));
    expect(xDe("remarcar")).toBeGreaterThan(xDe("quorum"));
    expect(yDe("remarcar")).toBe(yDe("quorum"));
    expect(yDe("ata")).toBeGreaterThan(yDe("quorum"));

    // O bloco cru não fica na página.
    expect(container.textContent).not.toContain("abrir -> pauta");
  });

  it("um bloco de código que não é fluxograma continua código", () => {
    const { container } = render(
      <ReactMarkdown components={{ pre: PreDoManual }}>{"```bash\nls -la\n```"}</ReactMarkdown>,
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelector("pre code")!.textContent).toContain("ls -la");
  });
});

describe("a entrada do fluxograma", () => {
  it("os passos aparecem em sequência pela ordem do fluxo, e tudo acaba em menos de 1,5 s", () => {
    simularTela();
    const { container } = desenhar(REUNIAO);
    expect(container.querySelector("[data-fluxograma]")!.getAttribute("data-movimento")).toBe("normal");

    const atrasoDe = (id: string) => {
      const animacao = (container.querySelector(`[data-passo="${id}"]`) as SVGElement).style.animation;
      expect(animacao).toContain("fluxograma-passo");
      return Number(/ (\d+)ms both/.exec(animacao)![1]);
    };
    const ordem = ["abrir", "pauta", "quorum", "ata", "remarcar"];
    const atrasos = ordem.map(atrasoDe);
    for (let i = 1; i < atrasos.length; i++) expect(atrasos[i]).toBeGreaterThan(atrasos[i - 1]);

    // A ligação se desenha depois que a origem dela apareceu.
    const traco = container.querySelector('[data-ligacao="quorum->remarcar"] path:not([data-seta])') as SVGElement;
    expect(traco.style.animation).toContain("fluxograma-ligacao");
    expect(Number(/ (\d+)ms both/.exec(traco.style.animation)![1])).toBeGreaterThan(atrasoDe("quorum"));

    const animados = [...container.querySelectorAll<SVGElement>("svg *")].filter((el) => el.style.animation);
    expect(Math.max(...animados.map((el) => tempoDa(el.style.animation)))).toBeLessThan(1500);
  });

  it("com movimento reduzido, o fluxograma aparece pronto", () => {
    simularTela("(prefers-reduced-motion: reduce)");
    const { container } = desenhar(REUNIAO);

    expect(container.querySelector("[data-fluxograma]")!.getAttribute("data-movimento")).toBe("reduzido");
    const elementos = [...container.querySelectorAll<SVGElement>("svg *")];
    expect(elementos.filter((el) => el.style.animation)).toEqual([]);
    expect(elementos.filter((el) => el.getAttribute("stroke-dasharray"))).toEqual([]);
    for (const passo of container.querySelectorAll<SVGElement>("[data-passo]")) expect(passo.style.opacity).toBe("1");
  });

  it("no celular, a grade desce para uma coluna na ordem do fluxo", () => {
    simularTela("(max-width: 767px)");
    const { container } = desenhar(REUNIAO);
    const xs = new Set([...container.querySelectorAll("[data-passo]")].map((p) => p.getAttribute("data-x")));
    expect(xs.size).toBe(1);
    const y = (id: string) => Number(container.querySelector(`[data-passo="${id}"]`)!.getAttribute("data-y"));
    expect(y("ata")).toBeGreaterThan(y("quorum"));
    expect(y("remarcar")).toBeGreaterThan(y("ata"));
  });
});

describe("o hover e o Percorrer", () => {
  const estado = (container: HTMLElement, atributo: string) =>
    Object.fromEntries(
      [...container.querySelectorAll(`[${atributo}]`)].map((el) => [
        el.getAttribute(atributo === "data-passo" ? "data-passo" : "data-ligacao"),
        el.getAttribute(atributo === "data-passo" ? "data-realcado" : "data-realcada"),
      ]),
    );

  it("passar o mouse num passo destaca o caminho que passa por ele e mostra o detalhe", () => {
    const { container } = desenhar(REUNIAO);
    expect(container.querySelector("[data-detalhe]")).toBeNull();

    fireEvent.mouseEnter(container.querySelector('[data-passo="ata"]')!);
    expect(estado(container, "data-passo")).toEqual({
      abrir: "sim",
      pauta: "sim",
      quorum: "sim",
      ata: "sim",
      remarcar: "nao",
    });
    expect(estado(container, "data-ligacao")).toEqual({
      "abrir->pauta": "sim",
      "pauta->quorum": "sim",
      "quorum->ata": "sim",
      "quorum->remarcar": "nao",
    });
    expect(container.querySelector("[data-detalhe]")!.textContent).toContain("Ata assinada");

    fireEvent.mouseLeave(container.querySelector('[data-passo="ata"]')!);
    expect(container.querySelector("[data-detalhe]")).toBeNull();

    // No celular, tocar faz o mesmo: o detalhe do passo aparece.
    fireEvent.click(container.querySelector('[data-passo="pauta"]')!);
    expect(container.querySelector("[data-detalhe]")!.textContent).toContain(
      "O Secretário escolhe os itens da semana.",
    );
    expect(estado(container, "data-passo").remarcar).toBe("sim");
  });

  it("Percorrer acende um passo de cada vez, com Anterior e Próximo", () => {
    const { container } = desenhar(REUNIAO);
    const atual = () =>
      [...container.querySelectorAll('[data-atual="sim"]')].map((el) => el.getAttribute("data-passo"));
    expect(atual()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Percorrer" }));
    expect(atual()).toEqual(["abrir"]);
    expect(screen.getByRole("button", { name: "Anterior" })).toHaveProperty("disabled", true);

    fireEvent.click(screen.getByRole("button", { name: "Próximo" }));
    expect(atual()).toEqual(["pauta"]);
    expect(within(container).getByText("Passo 2 de 5")).toBeTruthy();
    expect(container.querySelector("[data-detalhe]")!.textContent).toContain("Montar a pauta");

    fireEvent.click(screen.getByRole("button", { name: "Próximo" }));
    fireEvent.click(screen.getByRole("button", { name: "Próximo" }));
    expect(atual()).toEqual(["ata"]);

    fireEvent.click(screen.getByRole("button", { name: "Anterior" }));
    expect(atual()).toEqual(["quorum"]);

    fireEvent.click(screen.getByRole("button", { name: "Próximo" }));
    fireEvent.click(screen.getByRole("button", { name: "Próximo" }));
    expect(atual()).toEqual(["remarcar"]);
    expect(screen.getByRole("button", { name: "Próximo" })).toHaveProperty("disabled", true);

    fireEvent.click(screen.getByRole("button", { name: "Encerrar" }));
    expect(atual()).toEqual([]);
  });
});

describe("o leitor de tela", () => {
  it("recebe o mesmo fluxo como lista numerada, com as decisões e os caminhos escritos", () => {
    const { container } = desenhar(REUNIAO);
    expect(container.querySelector("svg")!.getAttribute("aria-hidden")).toBe("true");

    const lista = container.querySelector("figure ol")!;
    const itens = within(lista as HTMLElement)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(itens).toEqual([
      "Início: Abrir a reunião. Depois: Montar a pauta.",
      "Montar a pauta. O Secretário escolhe os itens da semana. Depois: Tem quórum?",
      "Decisão: Tem quórum? Se sim: Ata assinada. Se não: Remarcar a reunião.",
      "Fim: Ata assinada.",
      "Remarcar a reunião.",
    ]);
  });
});
