/**
 * @vitest-environment jsdom
 */

/**
 * A tela do Instagram da Central de Comando (issue #819, ADR 0058).
 *
 * Porte dos testes de `StatCard`, `EngagementBlock`, `TopPostsGrid` e
 * `page.test.tsx` do repositório antigo, no molde do teste da tela Dados do
 * Google: o que se testa é o que a tela pede ao backend e o que ela mostra para
 * um dado payload, com o `fetch` dublado. Na interface diz-se sempre
 * "Instagram", nunca a empresa dona da rede.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Instagram, type InstagramPayload } from "./Instagram";

const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null }));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: async () => sessao.token ?? undefined,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const CAMINHO = "/admin/central-de-comando/instagram";

// 18/09/2026, 13h50 em Brasília: 5 minutos depois do carimbo do payload.
const AGORA = Date.parse("2026-09-18T16:50:00Z");

function payload28d(): InstagramPayload {
  return {
    periodo: {
      chave: "28d",
      dias: 28,
      atual: { inicio: "2026-08-21", fim: "2026-09-17" },
      anterior: { inicio: "2026-07-24", fim: "2026-08-20" },
    },
    seguidores: { total: 18420, crescimento: 312, crescimento_anterior: 248, ganhos: 340, perdidos: 28 },
    alcance: { atual: 41280, anterior: 37650, variacao: 3630 / 37650 },
    visualizacoes: { atual: 96540, anterior: 88210, variacao: 8330 / 88210 },
    engajamento: {
      interacoes: 7820,
      interacoes_anterior: 6910,
      variacao: 910 / 6910,
      partes: [
        { chave: "curtidas", rotulo: "Curtidas", valor: 5980 },
        { chave: "comentarios", rotulo: "Comentários", valor: 540 },
        { chave: "salvamentos", rotulo: "Salvamentos", valor: 820 },
        { chave: "compartilhamentos", rotulo: "Compartilhamentos", valor: 480 },
      ],
      contas_engajadas: 5140,
      contas_engajadas_anterior: 4720,
    },
    principais_publicacoes: [
      {
        id: "m1",
        legenda: "Mutirão de vacinação",
        tipo: "imagem",
        rotulo_tipo: "Imagem",
        miniatura: "https://cdn/m1.jpg",
        link: "https://www.instagram.com/p/m1",
        interacoes: 1840,
      },
      {
        id: "m2",
        legenda: "Bastidores da Maternidade",
        tipo: "reel",
        rotulo_tipo: "Reel",
        miniatura: "https://cdn/m2.jpg",
        link: "https://www.instagram.com/reel/m2",
        interacoes: 1520,
      },
      {
        id: "m3",
        legenda: "Dicas do cardiologista",
        tipo: "carrossel",
        rotulo_tipo: "Carrossel",
        miniatura: "https://cdn/m3.jpg",
        link: "https://www.instagram.com/p/m3",
        interacoes: 1190,
      },
    ],
    frescor: { atualizado_em: "2026-09-18T16:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

function resposta(status: number, corpo: unknown): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

let pedidos: { metodo: string; url: string; autorizacao: string | null }[] = [];

function servidor(rotas: { leitura: (periodo: string) => Response | Promise<Response> }) {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      pedidos.push({ metodo, url, autorizacao: new Headers(init?.headers).get("Authorization") });
      const leitura = url.match(/\/instagram\?periodo=(\w+)$/);
      if (metodo === "GET" && leitura) return rotas.leitura(leitura[1]);
      return resposta(404, { detail: "rota que o teste não conhece" });
    }),
  );
}

const pelos28 = () => resposta(200, payload28d());

beforeEach(() => {
  sessao.token = "token-de-teste";
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(AGORA);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Instagram: os números principais", () => {
  it("pede a tela do Instagram do período, com o token da sessão", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    await screen.findByText("18.420");
    expect(pedidos).toEqual([
      {
        metodo: "GET",
        url: "/api/admin/central-de-comando/instagram?periodo=28d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("mostra Seguidores como estoque, com o crescimento do período e sem variação percentual", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    expect(await screen.findByText("18.420")).toBeTruthy();
    expect(screen.getByText(/\+312 no período/)).toBeTruthy();
    expect(screen.getByText(/340 seguiram/)).toBeTruthy();
    expect(screen.getByText(/28 saíram/)).toBeTruthy();
    // Estoque não tem porcentagem: o crescimento não aparece como "%".
    const seguidores = screen.getByRole("group", { name: /Seguidores/ });
    expect(within(seguidores).queryByText(/%/)).toBeNull();
  });

  it("mostra Alcance e Visualizações lado a lado, com a diferença entre pessoas e vezes", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    expect(await screen.findByText("41.280")).toBeTruthy();
    expect(screen.getByText("96.540")).toBeTruthy();
    expect(screen.getByText(/quantas pessoas/i)).toBeTruthy();
    expect(screen.getByText(/quantas vezes/i)).toBeTruthy();
  });
});

describe("Instagram: engajamento", () => {
  it("mostra as Interações, as quatro partes e as Contas que engajaram", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    expect(await screen.findByText("7.820")).toBeTruthy();
    expect(screen.getByText("Curtidas")).toBeTruthy();
    expect(screen.getByText("5.980")).toBeTruthy();
    expect(screen.getByText("Comentários")).toBeTruthy();
    expect(screen.getByText("Salvamentos")).toBeTruthy();
    expect(screen.getByText("Compartilhamentos")).toBeTruthy();
    expect(screen.getByText(/Contas que engajaram/)).toBeTruthy();
    expect(screen.getByText("5.140")).toBeTruthy();
  });
});

describe("Instagram: principais publicações", () => {
  it("mostra as publicações ordenadas com link externo para o Instagram", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    await screen.findByText("18.420");
    const reel = screen.getByRole("link", { name: /Bastidores da Maternidade/ });
    expect(reel.getAttribute("href")).toBe("https://www.instagram.com/reel/m2");
    expect(reel.getAttribute("target")).toBe("_blank");
    expect(reel.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText("Reel")).toBeTruthy();
    expect(screen.getByText(/1\.840 interações/)).toBeTruthy();
  });

  // A miniatura vazia é o pedido da issue; a `http://` segue a mesma regra do
  // link (só `https://` vira `src`), e não uma imagem de conteúdo misto.
  it.each([
    ["vazia", ""],
    ["http://", "http://cdn/m2.jpg"],
  ])(
    "publicação com miniatura %s mostra o marcador no lugar da imagem, e não uma imagem quebrada",
    async (_caso, miniatura) => {
      const semMiniatura = payload28d();
      semMiniatura.principais_publicacoes[1].miniatura = miniatura;
      servidor({ leitura: () => resposta(200, semMiniatura) });

      render(<Instagram periodo="28d" />);

      await screen.findByText("18.420");
      const cartao = screen.getByRole("link", { name: /Bastidores da Maternidade/ });
      expect(cartao.querySelector("img")).toBeNull();
      expect(within(cartao).getByRole("img", { name: "Bastidores da Maternidade" })).toBeTruthy();
      expect(within(cartao).getByText("Sem miniatura")).toBeTruthy();
      // As outras seguem com a miniatura delas.
      const comMiniatura = screen.getByRole("link", { name: /Mutirão de vacinação/ });
      expect(comMiniatura.querySelector("img")?.getAttribute("src")).toBe("https://cdn/m1.jpg");
    },
  );

  it.each([["javascript:alert(1)"], ["http://www.instagram.com/p/m3"], [""]])(
    "link que não é https (%j) não vira href: a publicação aparece, sem link",
    async (link) => {
      const comLinkRuim = payload28d();
      comLinkRuim.principais_publicacoes[2].link = link;
      servidor({ leitura: () => resposta(200, comLinkRuim) });

      render(<Instagram periodo="28d" />);

      await screen.findByText("18.420");
      expect(screen.getByText("Dicas do cardiologista")).toBeTruthy();
      expect(screen.queryByRole("link", { name: /Dicas do cardiologista/ })).toBeNull();
      expect(screen.getByText(/1\.190 interações/)).toBeTruthy();
      // As outras seguem com o link delas.
      const mutirao = screen.getByRole("link", { name: /Mutirão de vacinação/ });
      expect(mutirao.getAttribute("href")).toBe("https://www.instagram.com/p/m1");
    },
  );

  it("sem publicações no período, mostra o estado vazio calmo", async () => {
    const semPosts = payload28d();
    semPosts.principais_publicacoes = [];
    servidor({ leitura: () => resposta(200, semPosts) });

    render(<Instagram periodo="28d" />);

    expect(await screen.findByText(/Sem publicações no período/)).toBeTruthy();
  });
});

describe("Instagram: o período", () => {
  it("oferece só 7 e 28 dias e diz a razão de não haver 90", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=7d`);
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("aria-current")).toBe("page");
    expect(screen.queryByRole("link", { name: "90 dias" })).toBeNull();
    expect(screen.getByText(/30 dias por consulta/)).toBeTruthy();
  });
});

describe("Instagram: estados de erro", () => {
  it("token vencido com número guardado: mostra os números e o aviso de renovação", async () => {
    const comFalha = payload28d();
    comFalha.frescor = {
      atualizado_em: "2026-09-18T16:45:00+00:00",
      atualizacao_falhou: true,
      motivo: "O acesso ao Instagram expirou. Renove o token para voltar a atualizar os números.",
    };
    servidor({ leitura: () => resposta(200, comFalha) });

    render(<Instagram periodo="28d" />);

    // Os números continuam de pé (o último valor bom).
    expect(await screen.findByText("18.420")).toBeTruthy();
    expect(screen.getByText(/Renove o token/)).toBeTruthy();
    expect(screen.getByText(/Não foi possível atualizar agora/)).toBeTruthy();
  });

  it("token vencido sem número guardado: mostra o aviso calmo de renovação, e não o erro técnico", async () => {
    const frase = "O acesso ao Instagram expirou. Renove o token para voltar a atualizar os números.";
    servidor({ leitura: () => resposta(502, { detail: frase, causa: "token-vencido" }) });

    render(<Instagram periodo="28d" />);

    const aviso = (await screen.findByText(frase)).closest("[role]");
    expect(aviso?.getAttribute("role")).toBe("status");
    expect(within(aviso as HTMLElement).getByText(/renovar o acesso/i)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/Não foi possível buscar/)).toBeNull();
    expect(screen.queryByText("18.420")).toBeNull();
  });

  it("outra falha sem número guardado: segue o erro honesto, com a frase do servidor", async () => {
    servidor({ leitura: () => resposta(502, { detail: "O Instagram não respondeu." }) });

    render(<Instagram periodo="28d" />);

    const alerta = await screen.findByRole("alert");
    expect(within(alerta).getByText(/Não foi possível buscar/)).toBeTruthy();
    expect(within(alerta).getByText("O Instagram não respondeu.")).toBeTruthy();
  });

  it("conta não configurada: mostra a tela calma com a frase do backend", async () => {
    const frase =
      "A Central de Comando ainda não está ligada ao Instagram no servidor. Enquanto isso, nenhum número do Instagram é mostrado.";
    servidor({ leitura: () => resposta(503, { detail: frase }) });

    render(<Instagram periodo="28d" />);

    expect(await screen.findByText(frase)).toBeTruthy();
    expect(screen.queryByText("18.420")).toBeNull();
  });
});

describe("Instagram: a interface diz Instagram, nunca a empresa dona da rede", () => {
  it("não escreve o nome da empresa em lugar nenhum da tela", async () => {
    servidor({ leitura: pelos28 });

    render(<Instagram periodo="28d" />);

    await screen.findByText("18.420");
    expect(document.body.textContent ?? "").not.toMatch(/\b(meta|facebook)\b/i);
    expect(screen.getAllByText(/Instagram/).length).toBeGreaterThan(0);
  });
});
