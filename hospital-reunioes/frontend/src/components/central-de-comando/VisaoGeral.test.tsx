/**
 * @vitest-environment jsdom
 */

/**
 * A tela Visão Geral da Central de Comando (issue #814, ADR 0058).
 *
 * O servidor é falso e a conta fica com ele: a tela não calcula variação nem
 * datas, ela escreve o que o payload trouxe. Por isso as asserções olham o que
 * o Super admin lê para um dado payload, e a chamada que a tela faz (endereço
 * e token), que é o que ela controla.
 *
 * Porte das partes de `app/(painel)/page.test.tsx` do repositório antigo que
 * cabem nesta fatia: o número-manchete do período, o rótulo "últimos N dias",
 * o seletor com o período ativo e a variação contra o período anterior.
 *
 * O resto do princípio da Central, a honestidade do dado: sem credencial (503)
 * ou com a fonte fora (502), a tela diz o que houve e NÃO mostra número.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VisaoGeral, type VisaoGeralPayload } from "./VisaoGeral";

const sessao = vi.hoisted(() => ({
  token: "token-de-teste" as string | null,
  carregando: false,
}));

// A tela pede a sessão a cada pedido (issue #815: ela fica aberta por horas, e
// o token da abertura vence em 1 hora). Enquanto a sessão carrega, a promessa
// não volta.
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

function payload(parcial: {
  chave?: "7d" | "28d" | "90d";
  dias?: number;
  atual?: number;
  anterior?: number;
  variacao?: number | null;
}): VisaoGeralPayload {
  return {
    periodo: {
      chave: parcial.chave ?? "28d",
      dias: parcial.dias ?? 28,
      atual: { inicio: "2026-08-21", fim: "2026-09-17" },
      anterior: { inicio: "2026-07-24", fim: "2026-08-20" },
    },
    visitantes: {
      atual: parcial.atual ?? 12345,
      anterior: parcial.anterior ?? 10000,
      variacao: parcial.variacao === undefined ? 0.2345 : parcial.variacao,
    },
    frescor: { atualizado_em: "2026-09-18T16:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

type Chamada = { url: string; autorizacao: string | null };
let chamadas: Chamada[] = [];

/** O servidor falso: responde o status e o corpo dados, e anota a chamada. */
function servidor(status: number, corpo: unknown) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      chamadas.push({ url, autorizacao: cabecalhos.get("Authorization") });
      return new Response(JSON.stringify(corpo), {
        status,
        headers: { "Content-Type": "application/json" },
      });
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

describe("Visão Geral: o número-manchete", () => {
  it("mostra os Visitantes do período padrão, de 28 dias", async () => {
    servidor(200, payload({}));

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("12.345")).toBeTruthy();
    expect(screen.getByText(/últimos 28 dias/)).toBeTruthy();
  });

  it("pede ao backend o período escolhido, com o token da sessão", async () => {
    servidor(200, payload({ chave: "7d", dias: 7, atual: 1000, anterior: 800, variacao: 0.25 }));

    render(<VisaoGeral periodo="7d" />);

    expect(await screen.findByText("1.000")).toBeTruthy();
    expect(screen.getByText(/últimos 7 dias/)).toBeTruthy();
    // `toContainEqual`, e não a lista exata: a tela agora traz também o
    // indicador Ao vivo (issue #816), que consulta `/ao-vivo` em paralelo. O
    // que este teste mede é a chamada da Visão Geral, com o período e o token.
    expect(chamadas).toContainEqual({
      url: "/api/admin/central-de-comando/visao-geral?periodo=7d",
      autorizacao: "Bearer token-de-teste",
    });
  });

  it("mostra a variação para cima contra o período anterior", async () => {
    servidor(200, payload({ variacao: 0.2345 }));

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/↑\s*23,5%/)).toBeTruthy();
    expect(screen.getByText(/em relação ao período anterior/)).toBeTruthy();
  });

  it("mostra a variação para baixo sem sinal de menos, só com a seta", async () => {
    servidor(200, payload({ atual: 3100, anterior: 3350, variacao: -0.0746 }));

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/↓\s*7,5%/)).toBeTruthy();
    expect(screen.queryByText(/-7,5%/)).toBeNull();
  });

  it("sem base de comparação não desenha seta nem porcentagem", async () => {
    servidor(200, payload({ atual: 500, anterior: 0, variacao: null }));

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("500")).toBeTruthy();
    expect(screen.queryByText(/[↑↓]/)).toBeNull();
    expect(screen.getByText(/sem base de comparação com o período anterior/)).toBeTruthy();
  });

  it("diz as datas do período e do anterior, para conferir com o Google", async () => {
    servidor(200, payload({}));

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/21\/08\/2026 a 17\/09\/2026/)).toBeTruthy();
    expect(screen.getByText(/24\/07\/2026 a 20\/08\/2026/)).toBeTruthy();
  });
});

describe("Visão Geral: o seletor de período", () => {
  it("oferece 7, 28 e 90 dias e marca o período ativo", async () => {
    servidor(200, payload({ chave: "7d", dias: 7 }));

    render(<VisaoGeral periodo="7d" />);

    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=28d`);
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=90d`);
  });
});

describe("Visão Geral: a honestidade do dado", () => {
  const SEM_CREDENCIAL =
    "A Central de Comando ainda não está ligada ao Google Analytics: falta configurar GA4_PROPERTY_ID e GOOGLE_APPLICATION_CREDENTIALS_JSON no backend.";

  it("sem credencial do Google (503), diz o que falta e não mostra número nenhum", async () => {
    servidor(503, { detail: SEM_CREDENCIAL });

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(SEM_CREDENCIAL)).toBeTruthy();
    expect(screen.getByText("Sem ligação com o Google Analytics")).toBeTruthy();
    expect(screen.queryByText(/^0$/)).toBeNull();
    expect(screen.queryByText(/últimos 28 dias/)).toBeNull();
  });

  it("um 503 sem a frase do backend (proxy fora do ar) não vira falta de configuração", async () => {
    // Só o backend sabe dizer que falta configurar, e ele diz com a frase no
    // `detail`. Um 503 cru do proxy, no meio de um deploy, é falha comum.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>Service Unavailable</html>", { status: 503 })),
    );

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/Não foi possível buscar os números do Site/)).toBeTruthy();
    expect(screen.getByText("O servidor respondeu 503.")).toBeTruthy();
    expect(screen.queryByText("Sem ligação com o Google Analytics")).toBeNull();
  });

  it("com o Google fora (502), diz que não conseguiu buscar e não mostra número", async () => {
    servidor(502, { detail: "O Google Analytics não respondeu no tempo esperado." });

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("O Google Analytics não respondeu no tempo esperado.")).toBeTruthy();
    expect(screen.getByText(/Não foi possível buscar os números do Site/)).toBeTruthy();
    expect(screen.queryByText(/últimos 28 dias/)).toBeNull();
  });

  it("com a rede fora, avisa em vez de mostrar a tela vazia", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/Não foi possível falar com o servidor/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor(200, payload({}));
    sessao.token = null;

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });

  it("enquanto a sessão carrega, espera em vez de acusar falta de sessão", async () => {
    servidor(200, payload({}));
    sessao.token = null;
    sessao.carregando = true;

    render(<VisaoGeral periodo="28d" />);

    await waitFor(() => expect(screen.getByText(/Carregando os números do Site/)).toBeTruthy());
    expect(screen.queryByText(/sessão não está ativa/)).toBeNull();
  });
});
