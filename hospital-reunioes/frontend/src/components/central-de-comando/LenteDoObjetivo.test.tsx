/**
 * @vitest-environment jsdom
 */

/**
 * A lente de um Objetivo da Central de Comando (issue #820, ADR 0058).
 *
 * O servidor é falso e a conta fica com ele. As asserções olham o que o Super
 * admin lê para um dado payload, a chamada que a tela faz (endereço, período e
 * token), e o identificador inexistente, que cai na página de não encontrado.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LenteDoObjetivo, type LentePayload } from "./LenteDoObjetivo";

const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null, carregando: false }));
const nav = vi.hoisted(() => ({ notFound: vi.fn() }));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: () =>
    sessao.carregando ? new Promise<string | undefined>(() => {}) : Promise.resolve(sessao.token ?? undefined),
}));

vi.mock("next/navigation", () => ({ notFound: nav.notFound }));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function lente(parcial: Partial<LentePayload> = {}): LentePayload {
  return {
    objetivo: parcial.objetivo ?? {
      id: "instagram-seguidores",
      nome: "Crescer no Instagram",
      descricao: "Aumentar o número de seguidores da conta.",
    },
    periodo: parcial.periodo ?? { chave: "28d", dias: 28 },
    numeros: parcial.numeros ?? [
      { chave: "followers", rotulo: "Seguidores", valor: 18420, crescimento: 312, crescimento_anterior: 248 },
      { chave: "reach", rotulo: "Alcance", valor: 41280, anterior: 37650, variacao: 0.0964 },
    ],
    sugestoes: parcial.sugestoes ?? [],
    frescor: parcial.frescor ?? { atualizado_em: "2026-09-18T13:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

type Chamada = { url: string; autorizacao: string | null };
let chamadas: Chamada[] = [];

function servidor(status: number, corpo: unknown) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      chamadas.push({ url, autorizacao: cabecalhos.get("Authorization") });
      return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

beforeEach(() => {
  sessao.token = "token-de-teste";
  sessao.carregando = false;
  nav.notFound.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a lente de um Objetivo", () => {
  it("mostra os números do Objetivo", async () => {
    servidor(200, lente());

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("18.420")).toBeTruthy();
    expect(screen.getByText("Seguidores")).toBeTruthy();
    expect(screen.getByText("+312 no período")).toBeTruthy();
    expect(screen.getByText("41.280")).toBeTruthy();
  });

  it("mostra cada sugestão com o porquê", async () => {
    servidor(
      200,
      lente({
        sugestoes: [
          {
            id: "queda-de-alcance",
            titulo: "Seu alcance caiu",
            detalhe: "Vale revisar os horários de publicação.",
            porque: "Alcance -20% no período (de 37.650 para 30.120).",
            tom: "atencao",
          },
        ],
      }),
    );

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("Seu alcance caiu")).toBeTruthy();
    expect(screen.getByText("Alcance -20% no período (de 37.650 para 30.120).")).toBeTruthy();
    expect(screen.queryByText(/tudo no rumo/)).toBeNull();
  });

  it("sem sugestão, diz que está tudo no rumo, como a Central antiga", async () => {
    servidor(200, lente({ sugestoes: [] }));

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    await screen.findByText("18.420");
    const sugestoes = screen.getByRole("region", { name: "Sugestões" });
    expect(sugestoes.textContent).toContain("Tá tudo no rumo, nenhuma ação urgente para esse objetivo agora.");
  });

  it("sem número e sem sugestão, não diz que está tudo no rumo", async () => {
    servidor(200, lente({ numeros: [], sugestoes: [] }));

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText(/Ainda sem número para este período/)).toBeTruthy();
    expect(screen.queryByText(/tudo no rumo/)).toBeNull();
  });

  it("pede a lente do Objetivo no período, com o token da sessão", async () => {
    servidor(200, lente());

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);
    await screen.findByText("18.420");

    expect(chamadas).toEqual([
      {
        url: "/api/admin/central-de-comando/objetivos/instagram-seguidores?periodo=28d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("identificador inexistente (404) cai na página de não encontrado", async () => {
    servidor(404, { detail: "A Central não tem esse Objetivo." });

    render(<LenteDoObjetivo identificador="nao-existe" periodo="28d" />);

    await waitFor(() => expect(nav.notFound).toHaveBeenCalled());
  });

  it("sem credencial (503) diz o que falta e não mostra número", async () => {
    servidor(503, { detail: "A Central ainda não está ligada à fonte." });

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("A Central ainda não está ligada à fonte.")).toBeTruthy();
    expect(screen.queryByText("18.420")).toBeNull();
    expect(nav.notFound).not.toHaveBeenCalled();
  });

  it("com a fonte fora (502) avisa e não mostra número", async () => {
    servidor(502, { detail: "A fonte não respondeu no tempo esperado." });

    render(<LenteDoObjetivo identificador="contatos" periodo="28d" />);

    expect(await screen.findByText("A fonte não respondeu no tempo esperado.")).toBeTruthy();
    expect(screen.getByText(/Não foi possível buscar os números/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor(200, lente());
    sessao.token = null;

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });
});

describe("a lente de um Objetivo: o Atualizar agora (issue #861)", () => {
  // Cinco minutos depois do carimbo da `lente()` (13h45 UTC).
  const AGORA = new Date("2026-09-18T13:50:00+00:00");

  type Pedido = { metodo: string; url: string; autorizacao: string | null };
  let pedidos: Pedido[] = [];

  function resposta(status: number, corpo: unknown): Response {
    return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
  }

  /** `leitura` responde o GET da lente, `atualizar` o POST do Atualizar agora. */
  function servidorComRotas(rotas: { leitura: () => Response; atualizar?: () => Response }) {
    pedidos = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const metodo = init?.method ?? "GET";
        pedidos.push({ metodo, url, autorizacao: new Headers(init?.headers).get("Authorization") });
        if (metodo === "GET" && url.includes("/objetivos/")) return rotas.leitura();
        if (metodo === "POST" && url.includes("/atualizar-agora?") && rotas.atualizar) return rotas.atualizar();
        return resposta(404, { detail: "rota que o teste não conhece" });
      }),
    );
  }

  const seguidoresNovos = lente({
    numeros: [{ chave: "followers", rotulo: "Seguidores", valor: 18500, crescimento: 392, crescimento_anterior: 248 }],
    frescor: { atualizado_em: "2026-09-18T13:50:00+00:00", atualizacao_falhou: false, motivo: null },
  });

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("tem o carimbo e o botão das outras telas", async () => {
    servidorComRotas({ leitura: () => resposta(200, lente()) });

    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);

    expect(await screen.findByText("18.420")).toBeTruthy();
    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("o clique pede a renovação da lente no período, e o número e o carimbo mudam", async () => {
    servidorComRotas({
      leitura: () => resposta(200, lente()),
      atualizar: () => resposta(200, seguidoresNovos),
    });
    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);
    await screen.findByText("18.420");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText("18.500")).toBeTruthy();
    expect(screen.getByText("Atualizado agora mesmo")).toBeTruthy();
    expect(pedidos.filter((p) => p.metodo === "POST")).toEqual([
      {
        metodo: "POST",
        url: "/api/admin/central-de-comando/atualizar-agora?tela=objetivos/instagram-seguidores&periodo=28d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("no limite de taxa, os números de antes ficam e a tela avisa", async () => {
    servidorComRotas({
      leitura: () => resposta(200, lente()),
      atualizar: () => resposta(429, { error: "Rate limit exceeded: 5 per 1 minute" }),
    });
    render(<LenteDoObjetivo identificador="instagram-seguidores" periodo="28d" />);
    await screen.findByText("18.420");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText(/Muitas atualizações em pouco tempo/)).toBeTruthy();
    expect(screen.getByText("18.420")).toBeTruthy();
    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
  });
});
