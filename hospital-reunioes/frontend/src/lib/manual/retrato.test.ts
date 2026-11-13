/**
 * @vitest-environment jsdom
 */

/**
 * A montagem do Retrato da Ana numa página só (issue #1720, ADR 0094, decisão 3).
 *
 * O quadro do Retrato é isolado da página do app, então não leva o login: tudo
 * o que a página do Retrato carrega precisa entrar nela antes, buscado pela
 * rota do backend com o login do app. O repositório aqui é falso, do formato
 * do Retrato de verdade (caminhos relativos, fonte dentro do CSS, os dados por
 * `fetch`).
 */

import { describe, expect, it } from "vitest";

import { montarRetrato } from "./retrato";

const INDEX = `<!doctype html>
<html lang="pt-BR"><head>
<link rel="stylesheet" href="assets/hospital.css">
</head><body>
<img class="logo" src="assets/logo-hsm.png" alt="Hospital">
<a href="#aba">aba</a>
<script src="assets/retrato.js"></script>
</body></html>`;

const ARQUIVOS: Record<string, { corpo: string; tipo: string }> = {
  "index.html": { corpo: INDEX, tipo: "text/html" },
  "assets/hospital.css": {
    corpo: '@font-face { src: url("fonts/Fonte.ttf") format("truetype"); } body { color: navy; }',
    tipo: "text/css",
  },
  "assets/fonts/Fonte.ttf": { corpo: "FONTE", tipo: "font/ttf" },
  "assets/logo-hsm.png": { corpo: "PNG", tipo: "image/png" },
  "assets/retrato.js": { corpo: 'var x = "</script>"; window.RODOU = 1;', tipo: "text/javascript" },
  "dados/retrato.json": { corpo: '{"esferas":[]}', tipo: "application/json" },
};

function repositorio() {
  const pedidos: string[] = [];
  async function buscar(caminho: string): Promise<Response> {
    pedidos.push(caminho);
    const arquivo = ARQUIVOS[caminho];
    if (!arquivo) return new Response("não achei", { status: 404 });
    return new Response(arquivo.corpo, { headers: { "Content-Type": arquivo.tipo } });
  }
  return { buscar, pedidos };
}

function dataUrl(tipo: string, corpo: string): string {
  return `data:${tipo};base64,${btoa(corpo)}`;
}

function ler(html: string): Document {
  return new DOMParser().parseFromString(html, "text/html");
}

describe("montarRetrato", () => {
  it("põe o CSS, o script, a imagem, a fonte e os dados dentro da página", async () => {
    const { buscar, pedidos } = repositorio();

    const doc = ler(await montarRetrato(buscar));

    expect(doc.querySelector("link[rel=stylesheet]")).toBeNull();
    const estilo = doc.querySelector("style")?.textContent ?? "";
    expect(estilo).toContain("body { color: navy; }");
    expect(estilo).toContain(`url("${dataUrl("font/ttf", "FONTE")}")`);

    const script = [...doc.querySelectorAll("script")].find((s) => s.textContent?.includes("RODOU"));
    expect(script?.getAttribute("src")).toBeNull();
    expect(script?.textContent).toContain("window.RODOU = 1;");

    expect(doc.querySelector("img")?.getAttribute("src")).toBe(dataUrl("image/png", "PNG"));
    expect(doc.querySelector("a")?.getAttribute("href")).toBe("#aba");

    expect(pedidos.sort()).toEqual(Object.keys(ARQUIVOS).sort());
  });

  it("os dados entram como RETRATO_DADOS antes do script do Retrato rodar", async () => {
    const { buscar } = repositorio();

    const doc = ler(await montarRetrato(buscar));

    const scripts = [...doc.querySelectorAll("script")].map((s) => s.textContent ?? "");
    const dados = scripts.findIndex((s) => s.includes("RETRATO_DADOS"));
    const retrato = scripts.findIndex((s) => s.includes("RODOU"));
    expect(dados).toBeGreaterThanOrEqual(0);
    expect(dados).toBeLessThan(retrato);
    expect(scripts[dados]).toContain(JSON.stringify(dataUrl("application/json", '{"esferas":[]}')));
  });

  it("um fim de script dentro do código não fecha o script da página", async () => {
    const { buscar } = repositorio();

    const html = await montarRetrato(buscar);

    expect(html).not.toContain('"</script>"');
    expect(html).toContain('"<\\/script>"');
  });

  it("arquivo que a rota não entrega derruba a montagem", async () => {
    async function semIndex(): Promise<Response> {
      return new Response("O Retrato da Ana ainda não está ligado", { status: 503 });
    }

    await expect(montarRetrato(semIndex)).rejects.toThrow();
  });
});
