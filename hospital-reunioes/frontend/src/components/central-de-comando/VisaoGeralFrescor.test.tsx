/**
 * @vitest-environment jsdom
 */

/**
 * O frescor da Visão Geral da Central de Comando (issue #815, ADR 0058).
 *
 * Porte de `components/analytics/RefreshScope.test.tsx` do repositório antigo:
 * a barra e o conteúdo juntos, o Atualizar agora e a renovação automática de
 * hora em hora. E o que a issue pede a mais: a tela nunca zera por causa de uma
 * falha, seja a fonte fora (o backend manda o último valor bom, marcado) ou o
 * próprio Atualizar agora recusado (o limite de taxa, a rede).
 *
 * O servidor é falso e responde por caminho e método: a leitura da tela (GET)
 * e o Atualizar agora (POST). As asserções olham o que o Super admin lê e os
 * pedidos que a tela faz, que é o que ela controla.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VisaoGeral, type VisaoGeralPayload } from "./VisaoGeral";

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

// 18/09/2026, 13h50 em Brasília.
const AGORA = Date.parse("2026-09-18T16:50:00Z");

function payload(atual: number, frescor: Partial<VisaoGeralPayload["frescor"]> = {}): VisaoGeralPayload {
  return {
    periodo: {
      chave: "28d",
      dias: 28,
      atual: { inicio: "2026-08-21", fim: "2026-09-17" },
      anterior: { inicio: "2026-07-24", fim: "2026-08-20" },
    },
    visitantes: { atual, anterior: 10000, variacao: 0.2345 },
    frescor: {
      atualizado_em: "2026-09-18T16:45:00+00:00",
      atualizacao_falhou: false,
      motivo: null,
      ...frescor,
    },
  };
}

function resposta(status: number, corpo: unknown): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

type Pedido = { metodo: string; url: string; autorizacao: string | null };
let pedidos: Pedido[] = [];

/**
 * O servidor falso: `leitura` responde o GET da tela, `atualizar` o POST do
 * Atualizar agora. Qualquer outro pedido é 404, e todos ficam anotados.
 */
function servidor(rotas: {
  leitura: () => Response | Promise<Response>;
  atualizar?: () => Response | Promise<Response>;
}) {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      pedidos.push({ metodo, url, autorizacao: new Headers(init?.headers).get("Authorization") });
      if (metodo === "GET" && url.includes("/visao-geral?")) return rotas.leitura();
      if (metodo === "POST" && url.includes("/atualizar-agora?") && rotas.atualizar) return rotas.atualizar();
      return resposta(404, { detail: "rota que o teste não conhece" });
    }),
  );
}

const atualizacoes = () => pedidos.filter((p) => p.metodo === "POST");

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

describe("Visão Geral: a barra de frescor", () => {
  it("mostra de quando são os números, junto deles", async () => {
    servidor({ leitura: () => resposta(200, payload(12345)) });

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("12.345")).toBeTruthy();
    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });
});

describe("Visão Geral: o Atualizar agora", () => {
  it("pede ao backend a renovação da tela e do período, e mostra o número novo com o carimbo novo", async () => {
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload(12400, { atualizado_em: "2026-09-18T16:50:00+00:00" })),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(screen.getByText("Atualizado agora mesmo")).toBeTruthy();
    expect(atualizacoes()).toEqual([
      {
        metodo: "POST",
        url: "/api/admin/central-de-comando/atualizar-agora?tela=visao-geral&periodo=28d",
        autorizacao: "Bearer token-de-teste",
      },
    ]);
  });

  it("enquanto atualiza, diz 'Atualizando…' e os números de antes continuam na tela", async () => {
    let responder: (r: Response) => void = () => {};
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => new Promise<Response>((r) => (responder = r)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByRole("button", { name: /Atualizando/ })).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();

    await act(async () => responder(resposta(200, payload(12400))));

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });
});

describe("Visão Geral: a renovação automática", () => {
  async function passar(ms: number) {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  }

  it("com a tela aberta, renova sozinha de hora em hora, sem ninguém clicar", async () => {
    let numero = 12345;
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload((numero += 55), { atualizado_em: new Date().toISOString() })),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    // 60 minutos escritos à mão: medir contra a própria constante ficaria
    // verde com ela trocada para um dia, que é o mesmo que não renovar.
    await passar(60 * 60_000);

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(atualizacoes().map((p) => p.url)).toEqual([
      "/api/admin/central-de-comando/atualizar-agora?tela=visao-geral&periodo=28d",
    ]);

    await passar(60 * 60_000);

    expect(await screen.findByText("12.455")).toBeTruthy();
    expect(atualizacoes()).toHaveLength(2);
  });

  it("não renova antes da hora", async () => {
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload(12400)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    await passar(59 * 60_000);

    expect(atualizacoes()).toEqual([]);
    expect(screen.getByText("12.345")).toBeTruthy();
  });

  it("renova em silêncio: não pisca 'Atualizando…' nem apaga os números", async () => {
    let responder: (r: Response) => void = () => {};
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => new Promise<Response>((r) => (responder = r)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    await passar(60 * 60_000);

    await waitFor(() => expect(atualizacoes()).toHaveLength(1));
    expect(screen.queryByText(/Atualizando/)).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();

    await act(async () => responder(resposta(200, payload(12400))));
    expect(await screen.findByText("12.400")).toBeTruthy();
  });

  it("renova mesmo quando o relógio bate logo depois de os números aparecerem", async () => {
    // O timer não pode depender de o React já ter rodado os efeitos do render
    // que desenhou os números: o CI em Linux pegou o timer batendo antes, com a
    // tela ainda marcada como "carregando", e a renovação da hora se perdia.
    // A corrida só aparece quando o render passa do quadro de 5 ms do React (a
    // máquina lenta do CI), então este teste pode passar numa máquina rápida
    // mesmo com o defeito; quem a fecha de vez é a marca de "pedido no ar",
    // posta na hora do pedido, e os dois testes seguintes provam a regra dela.
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload(12400)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    act(() => {
      vi.advanceTimersByTime(60 * 60_000);
    });

    await waitFor(() => expect(atualizacoes()).toHaveLength(1));
    expect(await screen.findByText("12.400")).toBeTruthy();
  });

  it("não renova por cima da leitura que ainda está no ar", async () => {
    let responderLeitura: (r: Response) => void = () => {};
    servidor({
      leitura: () => new Promise<Response>((r) => (responderLeitura = r)),
      atualizar: () => resposta(503, "<html>fora</html>"),
    });
    render(<VisaoGeral periodo="28d" />);
    await waitFor(() => expect(pedidos).toHaveLength(1));

    await passar(60 * 60_000);
    await act(async () => responderLeitura(resposta(200, payload(12345))));

    expect(await screen.findByText("12.345")).toBeTruthy();
    expect(atualizacoes()).toEqual([]);
  });

  it("não renova por cima de um Atualizar agora clicado, e o botão não fica preso", async () => {
    let responderClique: (r: Response) => void = () => {};
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => new Promise<Response>((r) => (responderClique = r)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    await screen.findByRole("button", { name: /Atualizando/ });

    await passar(60 * 60_000);
    await act(async () => responderClique(resposta(200, payload(12400))));

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
    expect(atualizacoes()).toHaveLength(1);
  });

  it("pede a sessão de novo a cada renovação: o token da abertura vence em 1 hora", async () => {
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload(12400)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    sessao.token = "token-renovado";

    await passar(60 * 60_000);

    await waitFor(() => expect(atualizacoes()).toHaveLength(1));
    expect(atualizacoes()[0].autorizacao).toBe("Bearer token-renovado");
  });
});

describe("Visão Geral: o último valor bom", () => {
  it("com a fonte fora, mostra os números de antes e avisa que não conseguiu atualizar", async () => {
    servidor({
      leitura: () =>
        resposta(
          200,
          payload(12345, {
            atualizado_em: "2026-09-18T14:45:00+00:00",
            atualizacao_falhou: true,
            motivo: "O Google Analytics não respondeu no tempo esperado.",
          }),
        ),
    });

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText("12.345")).toBeTruthy();
    const aviso = screen.getByRole("status");
    expect(aviso.textContent).toContain("Não foi possível atualizar agora");
    expect(aviso.textContent).toContain("Mostrando os números de 11h45");
    expect(aviso.textContent).toContain("O Google Analytics não respondeu no tempo esperado.");
  });

  it("o Atualizar agora que volta com a fonte fora mantém os números e passa a avisar", async () => {
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () =>
        resposta(200, payload(12345, { atualizacao_falhou: true, motivo: "O Google Analytics respondeu HTTP 500." })),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText(/Não foi possível atualizar agora/)).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();
    expect(screen.getByText("O Google Analytics respondeu HTTP 500.")).toBeTruthy();
  });
});

describe("Visão Geral: o Atualizar agora que não trouxe números", () => {
  const casos: [string, () => Response | Promise<Response>, string][] = [
    [
      "o limite de taxa (429)",
      () => resposta(429, { error: "Rate limit exceeded: 5 per 1 minute" }),
      "Muitas atualizações em pouco tempo. Espere um minuto e tente de novo.",
    ],
    [
      "o Google fora sem número guardado (502)",
      () => resposta(502, { detail: "O Google Analytics respondeu HTTP 503." }),
      "O Google Analytics respondeu HTTP 503.",
    ],
    [
      "a rede fora",
      () => Promise.reject(new TypeError("Failed to fetch")),
      "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.",
    ],
  ];

  it.each(casos)("%s: os números continuam na tela, com o aviso do porquê", async (_caso, atualizar, frase) => {
    servidor({ leitura: () => resposta(200, payload(12345)), atualizar });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText(frase)).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();
    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("o aviso sai quando o Atualizar agora seguinte dá certo", async () => {
    let vez = 0;
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () =>
        ++vez === 1 ? resposta(429, { error: "Rate limit exceeded" }) : resposta(200, payload(12400)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    await screen.findByText(/Muitas atualizações/);

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(screen.queryByText(/Muitas atualizações/)).toBeNull();
  });
});

describe("Visão Geral: trocar de período no meio de uma atualização", () => {
  it("o número do período antigo, chegando atrasado, não entra na tela do novo", async () => {
    let responderAtualizacao: (r: Response) => void = () => {};
    servidor({
      leitura: () => resposta(200, payload(pedidos.at(-1)?.url.includes("periodo=7d") ? 3100 : 12345)),
      atualizar: () => new Promise<Response>((r) => (responderAtualizacao = r)),
    });
    const { rerender } = render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    await screen.findByRole("button", { name: /Atualizando/ });

    rerender(<VisaoGeral periodo="7d" />);
    expect(await screen.findByText("3.100")).toBeTruthy();
    await act(async () => responderAtualizacao(resposta(200, payload(99999))));

    expect(screen.getByText("3.100")).toBeTruthy();
    expect(screen.queryByText("99.999")).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });
});
