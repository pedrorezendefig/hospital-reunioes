/**
 * @vitest-environment jsdom
 */

/**
 * A página da lente lê o identificador e o período do endereço (issue #820).
 * Quais períodos cada lente tem é o backend quem diz, no payload (issue #847):
 * a página só descarta o que não é período nenhum. O período que a lente não
 * tem (90 dias no Instagram) cai no padrão dentro da `LenteDoObjetivo`.
 */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: async () => "token-de-teste",
}));

vi.mock("next/navigation", () => ({
  notFound: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import LenteDoObjetivoPage from "./page";

const SRC = join(process.cwd(), "src");

/** Os nomes que não são componente importados de um módulo `@/` que começa com "use client". */
function valoresDeModuloDoNavegador(fonte: string): string[] {
  const achados: string[] = [];
  for (const [, nomes, modulo] of fonte.matchAll(/import\s*\{([^}]*)\}\s*from\s*"@\/([^"]+)"/g)) {
    const arquivo = [".tsx", ".ts"].map((ext) => join(SRC, modulo + ext)).find(existsSync);
    if (!arquivo || !/^\s*["']use client["']/.test(readFileSync(arquivo, "utf8"))) continue;
    for (const cru of nomes.split(",")) {
      const nome = cru.trim().split(/\s+as\s+/)[0];
      if (!nome || nome.startsWith("type ")) continue;
      if (!/^[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*$/.test(nome)) achados.push(nome);
    }
  }
  return achados;
}

const pedidos: string[] = [];

function servidor() {
  pedidos.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      return new Response(JSON.stringify({ detail: "fora do teste" }), { status: 503 });
    }),
  );
}

const params = (identificador: string) => Promise.resolve({ identificador });
const sp = (periodo?: string) => Promise.resolve(periodo === undefined ? {} : { periodo });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a página da lente de um Objetivo", () => {
  it("pede a lente do identificador e do período que estão no endereço", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("site-visitantes"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/site-visitantes?periodo=90d"]),
    );
  });

  it("não decide os períodos pelo nome do Objetivo: quem diz é o backend (issue #847)", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("instagram-seguidores"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/instagram-seguidores?periodo=90d"]),
    );
  });

  it("a nota no Google tem lente própria, e o período vale para o teste do convite (issues #1619 e #1625)", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("google-reputacao"), searchParams: sp("90d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/google-reputacao?periodo=90d"]),
    );
  });

  it("só importa componente dos módulos do navegador, porque constante de lá chega ao servidor como referência e não como valor", () => {
    // A página roda no servidor. Um valor exportado por um módulo "use client"
    // chega aqui como referência de cliente, não como o texto: a comparação
    // com o identificador da nota no Google dava falso, e a lente da nota
    // quebrava na tela (achado na página do manual, issue #1725). O teste
    // acima não pega, porque no vitest o import é o valor de verdade.
    const fonte = readFileSync(join(__dirname, "page.tsx"), "utf8");
    expect(valoresDeModuloDoNavegador(fonte)).toEqual([]);
  });

  it("o detector pega a constante importada de um módulo do navegador", () => {
    const fonte = 'import { NotaNoGoogle, OBJETIVO_NOTA_NO_GOOGLE } from "@/components/central-de-comando/NotaNoGoogle";';
    expect(valoresDeModuloDoNavegador(fonte)).toEqual(["OBJETIVO_NOTA_NO_GOOGLE"]);
  });

  it("período que não existe no endereço vira o padrão de 28", async () => {
    servidor();

    render(await LenteDoObjetivoPage({ params: params("site-visitantes"), searchParams: sp("365d") }));

    await waitFor(() =>
      expect(pedidos).toEqual(["/api/admin/central-de-comando/objetivos/site-visitantes?periodo=28d"]),
    );
  });
});
