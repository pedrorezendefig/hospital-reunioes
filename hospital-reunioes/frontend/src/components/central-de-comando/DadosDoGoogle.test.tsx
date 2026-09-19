/**
 * @vitest-environment jsdom
 */

/**
 * A tela Dados do Google da Central de Comando (issue #817, ADR 0058).
 *
 * No molde do teste de leitura direta do dashboard: os gráficos não são o
 * assunto desta suíte, e o `recharts` não desenha em jsdom, então os dois
 * gráficos viram dublês que escrevem o que receberam. O que se testa é a
 * tela: o que ela pede ao backend (endereço e token), o que entrega a cada
 * gráfico para um dado payload, o período, a barra de frescor com o Atualizar
 * agora, e a honestidade do dado quando não há número. Os gráficos de verdade
 * têm os testes deles (`GraficoVisitantesPorDia.test.tsx`,
 * `GraficoDispositivos.test.tsx`).
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DadosDoGoogle, type DadosDoGooglePayload } from "./DadosDoGoogle";
import type { DispositivoDoPayload } from "./GraficoDispositivos";
import type { PontoDoMovimento } from "./GraficoVisitantesPorDia";

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

// Os dublês dos gráficos escrevem o que receberam: a série dia a dia e as
// fatias da rosca.
vi.mock("./GraficoVisitantesPorDia", () => ({
  GraficoVisitantesPorDia: ({ pontos }: { pontos: PontoDoMovimento[] }) => (
    <ol data-testid="grafico-visitantes">
      {pontos.map((p) => (
        <li key={p.data}>{`${p.data}: ${p.visitantes} (anterior ${p.data_anterior}: ${p.visitantes_anterior})`}</li>
      ))}
    </ol>
  ),
}));

vi.mock("./GraficoDispositivos", () => ({
  GraficoDispositivos: ({ dispositivos }: { dispositivos: DispositivoDoPayload[] }) => (
    <ol data-testid="grafico-dispositivos">
      {dispositivos.map((d) => (
        <li key={d.chave}>{`${d.rotulo}: ${d.percentual}% de ${d.visitas}`}</li>
      ))}
    </ol>
  ),
}));

const CAMINHO = "/admin/central-de-comando/dados-do-google";

// 18/09/2026, 13h50 em Brasília: 5 minutos depois do carimbo dos payloads.
const AGORA = Date.parse("2026-09-18T16:50:00Z");

function dia(data: string, visitantes: number, data_anterior: string, visitantes_anterior: number) {
  return { data, visitantes, data_anterior, visitantes_anterior, variacao: null };
}

function payloadDe7Dias(ultimoDia = 402): DadosDoGooglePayload {
  return {
    periodo: {
      chave: "7d",
      dias: 7,
      atual: { inicio: "2026-09-11", fim: "2026-09-17" },
      anterior: { inicio: "2026-09-04", fim: "2026-09-10" },
    },
    movimento: [
      dia("2026-09-11", 410, "2026-09-04", 350),
      dia("2026-09-12", 385, "2026-09-05", 362),
      dia("2026-09-13", 0, "2026-09-06", 298),
      dia("2026-09-14", 520, "2026-09-07", 301),
      dia("2026-09-15", 498, "2026-09-08", 455),
      dia("2026-09-16", 471, "2026-09-09", 470),
      dia("2026-09-17", ultimoDia, "2026-09-10", 441),
    ],
    dispositivos: [
      { chave: "celular", rotulo: "Celular", visitas: 1850, percentual: 74 },
      { chave: "computador", rotulo: "Computador", visitas: 640, percentual: 26 },
    ],
    frescor: { atualizado_em: "2026-09-18T16:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

function payloadDe90Dias(): DadosDoGooglePayload {
  const movimento = Array.from({ length: 90 }, (_, i) => {
    const data = new Date(Date.UTC(2026, 5, 20 + i)).toISOString().slice(0, 10);
    const anterior = new Date(Date.UTC(2026, 2, 22 + i)).toISOString().slice(0, 10);
    return dia(data, i === 0 ? 120 : 0, anterior, i === 0 ? 95 : 0);
  });
  return {
    periodo: {
      chave: "90d",
      dias: 90,
      atual: { inicio: "2026-06-20", fim: "2026-09-17" },
      anterior: { inicio: "2026-03-22", fim: "2026-06-19" },
    },
    movimento,
    dispositivos: [
      { chave: "computador", rotulo: "Computador", visitas: 12000, percentual: 50 },
      { chave: "celular", rotulo: "Celular", visitas: 11000, percentual: 46 },
      { chave: "tablet", rotulo: "Tablet", visitas: 1000, percentual: 4 },
    ],
    frescor: { atualizado_em: "2026-09-18T16:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

function resposta(status: number, corpo: unknown): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

type Pedido = { metodo: string; url: string; autorizacao: string | null };
let pedidos: Pedido[] = [];

/**
 * O servidor falso: `leitura` responde o GET da tela pelo período pedido, e
 * `atualizar` o POST do Atualizar agora. Qualquer outro pedido é 404, e todos
 * ficam anotados.
 */
function servidor(rotas: {
  leitura: (periodo: string) => Response | Promise<Response>;
  atualizar?: () => Response | Promise<Response>;
}) {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      pedidos.push({ metodo, url, autorizacao: new Headers(init?.headers).get("Authorization") });
      const leitura = url.match(/\/dados-do-google\?periodo=(\w+)$/);
      if (metodo === "GET" && leitura) return rotas.leitura(leitura[1]);
      if (metodo === "POST" && url.includes("/atualizar-agora?") && rotas.atualizar) return rotas.atualizar();
      return resposta(404, { detail: "rota que o teste não conhece" });
    }),
  );
}

const pelosPeriodos = (periodo: string) => resposta(200, periodo === "90d" ? payloadDe90Dias() : payloadDe7Dias());

const itens = (testId: string) =>
  within(screen.getByTestId(testId))
    .getAllByRole("listitem")
    .map((item) => item.textContent);

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

describe("Dados do Google: os dois blocos", () => {
  it("pede ao backend os Dados do Google do período escolhido, com o token da sessão", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    await screen.findByTestId("grafico-visitantes");
    expect(pedidos).toEqual([
      {
        metodo: "GET",
        url: "/api/admin/central-de-comando/dados-do-google?periodo=7d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("entrega ao gráfico de Visitantes por dia todos os dias do período, inclusive o dia sem visita", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    await screen.findByTestId("grafico-visitantes");
    expect(itens("grafico-visitantes")).toEqual([
      "2026-09-11: 410 (anterior 2026-09-04: 350)",
      "2026-09-12: 385 (anterior 2026-09-05: 362)",
      "2026-09-13: 0 (anterior 2026-09-06: 298)",
      "2026-09-14: 520 (anterior 2026-09-07: 301)",
      "2026-09-15: 498 (anterior 2026-09-08: 455)",
      "2026-09-16: 471 (anterior 2026-09-09: 470)",
      "2026-09-17: 402 (anterior 2026-09-10: 441)",
    ]);
  });

  it("entrega à rosca os dispositivos com os rótulos e as fatias que vieram do backend", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    await screen.findByTestId("grafico-dispositivos");
    expect(itens("grafico-dispositivos")).toEqual(["Celular: 74% de 1850", "Computador: 26% de 640"]);
  });

  it("nomeia os dois blocos e diz o período e as datas, para conferir com o Google", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    expect(await screen.findByRole("heading", { level: 2, name: "Movimento do site" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Por dispositivo" })).toBeTruthy();
    expect(screen.getByText(/Visitantes por dia · últimos 7 dias/)).toBeTruthy();
    expect(screen.getByText(/11\/09\/2026 a 17\/09\/2026/)).toBeTruthy();
    expect(screen.getByText(/04\/09\/2026 a 10\/09\/2026/)).toBeTruthy();
  });
});

describe("Dados do Google: o período", () => {
  it("oferece 7, 28 e 90 dias, marca o ativo e aponta para a própria tela", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=28d`);
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("href")).toBe(`${CAMINHO}?periodo=90d`);
    await screen.findByTestId("grafico-visitantes");
  });

  it("trocar o período troca os dois blocos", async () => {
    servidor({ leitura: pelosPeriodos });
    const { rerender } = render(<DadosDoGoogle periodo="7d" />);
    await screen.findByTestId("grafico-visitantes");

    rerender(<DadosDoGoogle periodo="90d" />);

    await waitFor(() => expect(itens("grafico-visitantes")).toHaveLength(90));
    expect(itens("grafico-visitantes")[0]).toBe("2026-06-20: 120 (anterior 2026-03-22: 95)");
    expect(itens("grafico-dispositivos")).toEqual([
      "Computador: 50% de 12000",
      "Celular: 46% de 11000",
      "Tablet: 4% de 1000",
    ]);
    expect(screen.getByText(/Visitantes por dia · últimos 90 dias/)).toBeTruthy();
    expect(pedidos.map((p) => p.url)).toEqual([
      "/api/admin/central-de-comando/dados-do-google?periodo=7d",
      "/api/admin/central-de-comando/dados-do-google?periodo=90d",
    ]);
  });
});

describe("Dados do Google: o frescor", () => {
  it("mostra de quando são os números, com o Atualizar agora", async () => {
    servidor({ leitura: pelosPeriodos });

    render(<DadosDoGoogle periodo="7d" />);

    expect(await screen.findByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("o Atualizar agora pede a renovação desta tela e troca os dois blocos pelos números novos", async () => {
    const novo = payloadDe7Dias(999);
    novo.dispositivos = [{ chave: "computador", rotulo: "Computador", visitas: 3, percentual: 100 }];
    novo.frescor = { atualizado_em: "2026-09-18T16:50:00+00:00", atualizacao_falhou: false, motivo: null };
    servidor({ leitura: pelosPeriodos, atualizar: () => resposta(200, novo) });
    render(<DadosDoGoogle periodo="7d" />);
    await screen.findByTestId("grafico-visitantes");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    });

    await waitFor(() => expect(itens("grafico-dispositivos")).toEqual(["Computador: 100% de 3"]));
    expect(itens("grafico-visitantes").at(-1)).toBe("2026-09-17: 999 (anterior 2026-09-10: 441)");
    expect(screen.getByText("Atualizado agora mesmo")).toBeTruthy();
    expect(pedidos.filter((p) => p.metodo === "POST").map((p) => p.url)).toEqual([
      "/api/admin/central-de-comando/atualizar-agora?tela=dados-do-google&periodo=7d",
    ]);
  });

  it("com a tela aberta, renova sozinha de hora em hora, pela renovação desta tela", async () => {
    servidor({ leitura: pelosPeriodos, atualizar: () => resposta(200, payloadDe7Dias(999)) });
    render(<DadosDoGoogle periodo="7d" />);
    await screen.findByTestId("grafico-visitantes");

    // 60 minutos escritos à mão, como no teste da Visão Geral.
    await act(async () => {
      vi.advanceTimersByTime(60 * 60_000);
    });

    await waitFor(() =>
      expect(itens("grafico-visitantes").at(-1)).toBe("2026-09-17: 999 (anterior 2026-09-10: 441)"),
    );
    expect(pedidos.filter((p) => p.metodo === "POST").map((p) => p.url)).toEqual([
      "/api/admin/central-de-comando/atualizar-agora?tela=dados-do-google&periodo=7d",
    ]);
  });

  it("com a fonte fora, mostra o último número bom e o aviso, sem zerar os blocos", async () => {
    const guardado = payloadDe7Dias();
    guardado.frescor = {
      atualizado_em: "2026-09-18T16:45:00+00:00",
      atualizacao_falhou: true,
      motivo: "O Google Analytics respondeu HTTP 503.",
    };
    servidor({ leitura: () => resposta(200, guardado) });

    render(<DadosDoGoogle periodo="7d" />);

    expect(await screen.findByText(/Não foi possível atualizar agora/)).toBeTruthy();
    expect(screen.getByText("O Google Analytics respondeu HTTP 503.")).toBeTruthy();
    expect(itens("grafico-visitantes")).toHaveLength(7);
    expect(itens("grafico-dispositivos")).toHaveLength(2);
  });
});

describe("Dados do Google: a honestidade do dado", () => {
  const SEM_CREDENCIAL =
    "A Central de Comando ainda não está ligada ao Google Analytics: falta configurar GA4_PROPERTY_ID e GOOGLE_APPLICATION_CREDENTIALS_JSON no backend.";

  it("enquanto o backend não responde, diz que está carregando", async () => {
    servidor({ leitura: () => new Promise<Response>(() => {}) });

    render(<DadosDoGoogle periodo="28d" />);

    expect(await screen.findByText(/Carregando os números do Site/)).toBeTruthy();
    expect(screen.queryByTestId("grafico-visitantes")).toBeNull();
  });

  it("sem credencial do Google (503), diz o que falta e não desenha gráfico nenhum", async () => {
    servidor({ leitura: () => resposta(503, { detail: SEM_CREDENCIAL }) });

    render(<DadosDoGoogle periodo="28d" />);

    expect(await screen.findByText(SEM_CREDENCIAL)).toBeTruthy();
    expect(screen.getByText("Sem ligação com o Google Analytics")).toBeTruthy();
    expect(screen.queryByTestId("grafico-visitantes")).toBeNull();
    expect(screen.queryByTestId("grafico-dispositivos")).toBeNull();
  });

  it("com o Google fora e nada guardado (502), diz que não conseguiu buscar e não desenha gráfico", async () => {
    servidor({ leitura: () => resposta(502, { detail: "O Google Analytics não respondeu no tempo esperado." }) });

    render(<DadosDoGoogle periodo="28d" />);

    expect(await screen.findByText("O Google Analytics não respondeu no tempo esperado.")).toBeTruthy();
    expect(screen.getByText(/Não foi possível buscar os números do Site/)).toBeTruthy();
    expect(screen.queryByTestId("grafico-visitantes")).toBeNull();
  });

  it("com a rede fora, avisa em vez de mostrar a tela vazia", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    render(<DadosDoGoogle periodo="28d" />);

    expect(await screen.findByText(/Não foi possível falar com o servidor/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor({ leitura: pelosPeriodos });
    sessao.token = null;

    render(<DadosDoGoogle periodo="28d" />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(pedidos).toEqual([]);
  });
});
