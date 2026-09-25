/**
 * @vitest-environment jsdom
 */

/**
 * A tela Visão Geral da Central de Comando, completa e por bloco (issue #821).
 *
 * O servidor é falso e a conta fica com ele: a tela escreve o que o payload
 * trouxe. As asserções olham o que o Super admin lê para um dado payload. A
 * mudança da #821: cada bloco de fonte degrada sozinho, e a tela responde 200
 * com um `estado` por bloco. Só uma falha de transporte troca a tela inteira.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VisaoGeral, type VisaoGeralPayload } from "./VisaoGeral";

const sessao = vi.hoisted(() => ({
  token: "token-de-teste" as string | null,
  carregando: false,
}));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: () =>
    sessao.carregando ? new Promise<string | undefined>(() => {}) : Promise.resolve(sessao.token ?? undefined),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const CAMINHO = "/admin/central-de-comando/visao-geral";

function payloadCompleto(over: Partial<VisaoGeralPayload> = {}): VisaoGeralPayload {
  return {
    periodo: {
      chave: "28d",
      dias: 28,
      atual: { inicio: "2026-08-21", fim: "2026-09-17" },
      anterior: { inicio: "2026-07-24", fim: "2026-08-20" },
    },
    visitantes: {
      estado: "ok",
      atual: 12345,
      anterior: 10000,
      variacao: 0.2345,
      contexto: {
        area: { chave: "maternidade", nome: "Maternidade", visitas: 3842 },
        origem: { chave: "busca", rotulo: "Busca no Google", percentual: 61 },
        dispositivo: { chave: "celular", rotulo: "Celular", percentual: 71 },
      },
    },
    instagram: {
      estado: "ok",
      seguidores: { total: 18420, crescimento: 312 },
      alcance: { atual: 41280, variacao: 0.05 },
      visualizacoes: { atual: 96540, variacao: 0.06 },
      interacoes: { atual: 7820, variacao: 0.13 },
    },
    objetivos: {
      em_foco: [
        {
          id: "site-visitantes",
          nome: "Atrair mais visitantes pro site",
          descricao: "Mais gente conhecendo o hospital pelo site.",
          numero: { rotulo: "Visitantes", valor: 12345 },
        },
        {
          id: "instagram-seguidores",
          nome: "Crescer no Instagram",
          descricao: "Aumentar o número de seguidores da conta.",
          numero: { rotulo: "Seguidores", valor: 18420 },
        },
        {
          id: "instagram-engajamento",
          nome: "Aumentar o engajamento no Instagram",
          descricao: "Mais gente curtindo, comentando e salvando.",
          numero: { rotulo: "Interações", valor: 7820 },
        },
      ],
    },
    frescor: { atualizado_em: "2026-09-18T16:45:00+00:00", atualizacao_falhou: false, motivo: null },
    ...over,
  };
}

let chamadas: string[] = [];

function servidor(status: number, corpo: unknown) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      chamadas.push(url);
      return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

beforeEach(() => {
  sessao.token = "token-de-teste";
  sessao.carregando = false;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Visão Geral: o número-manchete e o contexto", () => {
  it("mostra os Visitantes do período e a variação", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    expect((await screen.findAllByText("12.345")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/últimos 28 dias/)).toBeTruthy();
    expect(screen.getByText(/↑\s*23,5%/)).toBeTruthy();
  });

  it("mostra o contexto do número: Área do site, Origem do público e dispositivo", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("Área do site que mais atrai")).toBeTruthy();
    expect(screen.getByText("Maternidade")).toBeTruthy();
    expect(screen.getByText(/Busca no Google/)).toBeTruthy();
    expect(screen.getByText("Dispositivo mais usado")).toBeTruthy();
    expect(screen.getByText("Celular")).toBeTruthy();
  });

  it("pede ao backend o período escolhido", async () => {
    servidor(200, payloadCompleto({ periodo: { chave: "7d", dias: 7, atual: { inicio: "2026-09-11", fim: "2026-09-17" }, anterior: { inicio: "2026-09-04", fim: "2026-09-10" } } }));

    render(<VisaoGeral periodo="7d" />);

    await screen.findByText(/últimos 7 dias/);
    // O Ao vivo também consulta o servidor: filtra só a tela e afirma que ela
    // foi pedida uma vez só, para um pedido duplicado não passar despercebido.
    const daTela = chamadas.filter((url) => url.includes("/visao-geral"));
    expect(daTela).toHaveLength(1);
    expect(daTela[0]).toBe("/api/admin/central-de-comando/visao-geral?periodo=7d");
  });
});

describe("Visão Geral: o Instagram num relance", () => {
  it("mostra os quatro números do relance", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("O Instagram num relance")).toBeTruthy();
    const relance = screen.getByRole("region", { name: "O Instagram num relance" });
    expect(within(relance).getByText("18.420")).toBeTruthy();
    expect(within(relance).getByText("41.280")).toBeTruthy();
    expect(within(relance).getByText("96.540")).toBeTruthy();
    expect(within(relance).getByText("7.820")).toBeTruthy();
  });
});

describe("Visão Geral: os Objetivos em foco", () => {
  it("mostra os três Objetivos com link para a lente", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("Objetivos em foco")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Atrair mais visitantes pro site/ }).getAttribute("href")).toBe(
      "/admin/central-de-comando/objetivos/site-visitantes",
    );
    expect(screen.getByRole("link", { name: /Crescer no Instagram/ }).getAttribute("href")).toBe(
      "/admin/central-de-comando/objetivos/instagram-seguidores",
    );
  });
});

describe("Visão Geral: os atalhos para as outras telas", () => {
  it("leva às três outras telas da Central", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    await screen.findByText("Ir para");
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("/admin/central-de-comando/objetivos");
    expect(hrefs).toContain("/admin/central-de-comando/dados-do-google");
    expect(hrefs).toContain("/admin/central-de-comando/instagram");
  });
});

describe("Visão Geral: o que vem por aí", () => {
  it("lista Blog, Editor do Site, Mapa de Calor e Google Ads, sem data", async () => {
    servidor(200, payloadCompleto());

    render(<VisaoGeral periodo="28d" />);

    const secao = await screen.findByRole("region", { name: "O que vem por aí" });
    expect(within(secao).getByText("Blog")).toBeTruthy();
    expect(within(secao).getByText("Editor do Site")).toBeTruthy();
    expect(within(secao).getByText("Mapa de Calor")).toBeTruthy();
    expect(within(secao).getByText("Google Ads")).toBeTruthy();
    // Sem data prometida e sem selo "em breve".
    expect(within(secao).queryByText(/em breve/i)).toBeNull();
    expect(within(secao).queryByText(/\d{1,2}\/\d{4}|\d{4}/)).toBeNull();
  });
});

describe("Visão Geral: cada bloco degrada sozinho", () => {
  it("Instagram não configurado: o relance mostra o estado calmo e o resto segue", async () => {
    servidor(
      200,
      payloadCompleto({
        instagram: { estado: "nao-configurado", motivo: "A conta do Instagram ainda não está configurada." },
      }),
    );

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("Conta do Instagram ainda não configurada")).toBeTruthy();
    // O resto da tela segue: o número-manchete do Google e os blocos fixos.
    expect(screen.getAllByText("12.345").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("O que vem por aí")).toBeTruthy();
    expect(screen.getByText("Ir para")).toBeTruthy();
  });

  it("Visitantes sem dado: o bloco mostra o erro honesto e o Instagram segue", async () => {
    servidor(
      200,
      payloadCompleto({
        visitantes: { estado: "sem-dado", motivo: "O Google Analytics não respondeu no tempo esperado." },
      }),
    );

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("Não foi possível buscar os Visitantes agora.")).toBeTruthy();
    const relance = screen.getByRole("region", { name: "O Instagram num relance" });
    expect(within(relance).getByText("18.420")).toBeTruthy();
  });

  it("o objetivo do Instagram fica sem número, mas o card aparece", async () => {
    servidor(
      200,
      payloadCompleto({
        instagram: { estado: "sem-dado", motivo: "boom" },
        objetivos: {
          em_foco: [
            {
              id: "instagram-seguidores",
              nome: "Crescer no Instagram",
              descricao: "Aumentar o número de seguidores da conta.",
              numero: null,
            },
          ],
        },
      }),
    );

    render(<VisaoGeral periodo="28d" />);

    const card = await screen.findByRole("link", { name: /Crescer no Instagram/ });
    expect(within(card).getByText("Ver os números")).toBeTruthy();
  });
});

describe("Visão Geral: o seletor de período", () => {
  it("oferece 7, 28 e 90 dias e marca o período ativo", async () => {
    servidor(200, payloadCompleto({ periodo: { chave: "7d", dias: 7, atual: { inicio: "2026-09-11", fim: "2026-09-17" }, anterior: { inicio: "2026-09-04", fim: "2026-09-10" } } }));

    render(<VisaoGeral periodo="7d" />);

    await screen.findByText("O que vem por aí");
    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=28d`);
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=90d`);
  });
});

describe("Visão Geral: falha de transporte", () => {
  it("com a rede fora, avisa em vez de mostrar a tela vazia", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/Não foi possível abrir a Visão Geral agora/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor(200, payloadCompleto());
    sessao.token = null;

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });

  it("enquanto a sessão carrega, espera em vez de acusar falta de sessão", async () => {
    servidor(200, payloadCompleto());
    sessao.token = null;
    sessao.carregando = true;

    render(<VisaoGeral periodo="28d" />);

    await waitFor(() => expect(screen.getByText(/Carregando os números do Site/)).toBeTruthy());
    expect(screen.queryByText(/sessão não está ativa/)).toBeNull();
  });
});
