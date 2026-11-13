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

import { cleanup, render } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import { afterEach, describe, expect, it } from "vitest";

import { PreDoManual } from "./PreDoManual";

afterEach(cleanup);

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
