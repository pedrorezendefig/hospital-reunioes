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

// `quebrada` faz a leitura da sessão rejeitar em vez de devolver token: é o
// que o supabase-js faz com erro que não é de autenticação, ou sem as variáveis
// públicas do cliente.
const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null, quebrada: false }));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: async () => {
    if (sessao.quebrada) throw new Error("o cliente do Supabase não respondeu");
    return sessao.token ?? undefined;
  },
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

// Os números do Instagram e dos Objetivos em foco são fixos e distintos do
// número-manchete (`atual`), para o "12.345" que os testes olham ser só o dele.
function payload(atual: number, frescor: Partial<VisaoGeralPayload["frescor"]> = {}): VisaoGeralPayload {
  return {
    periodo: {
      chave: "28d",
      dias: 28,
      atual: { inicio: "2026-08-21", fim: "2026-09-17" },
      anterior: { inicio: "2026-07-24", fim: "2026-08-20" },
    },
    visitantes: {
      estado: "ok",
      atual,
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
      seguidores: { total: 60001, crescimento: 312 },
      alcance: { atual: 60002, variacao: 0.05 },
      visualizacoes: { atual: 60003, variacao: 0.06 },
      interacoes: { atual: 60004, variacao: 0.07 },
    },
    objetivos: {
      em_foco: [
        { id: "site-visitantes", nome: "Atrair mais visitantes pro site", descricao: "x", numero: { rotulo: "Visitantes", valor: 55501 } },
        { id: "instagram-seguidores", nome: "Crescer no Instagram", descricao: "x", numero: { rotulo: "Seguidores", valor: 55502 } },
        { id: "instagram-engajamento", nome: "Aumentar o engajamento no Instagram", descricao: "x", numero: { rotulo: "Interações", valor: 55503 } },
      ],
    },
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
  sessao.quebrada = false;
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
  // O número que a abertura recebe foi buscado às 16h45 (o `payload` padrão), e
  // a tela abre às 16h50: ele faz 1 hora às 17h45, 55 minutos depois. A tela
  // relê pela leitura comum (GET), e não pelo Atualizar agora: quem chega
  // primeiro depois da hora faz a única ida à fonte, e as outras abas pegam o
  // número novo do cache do servidor (issue #858). Minutos escritos à mão:
  // medir contra a própria constante ficaria verde com ela trocada.
  // Assíncrono: as promessas andam entre um timer e outro, como no navegador,
  // e a releitura sai na hora em que o relógio bate, e não no fim do avanço.
  async function passar(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  // Só a leitura da tela: o Ao vivo, na mesma tela, consulta a cada 30 segundos.
  const leituras = () => pedidos.filter((p) => p.metodo === "GET" && p.url.includes("/visao-geral?"));

  /** O número novo, buscado pelo servidor na hora da releitura. */
  const novo = (numero: number) => resposta(200, payload(numero, { atualizado_em: new Date().toISOString() }));

  it("com a tela aberta, relê quando o número faz 1 hora, sem ninguém clicar", async () => {
    let numero = 12345;
    servidor({
      leitura: () => (leituras().length === 1 ? resposta(200, payload(12345)) : novo((numero += 55))),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    await passar(54 * 60_000);
    expect(leituras()).toHaveLength(1);

    await passar(2 * 60_000);
    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(leituras().map((p) => p.url)).toEqual([
      "/api/admin/central-de-comando/visao-geral?periodo=28d",
      "/api/admin/central-de-comando/visao-geral?periodo=28d",
    ]);

    // O número relido é de agora: a próxima releitura é 1 hora depois dele.
    await passar(58 * 60_000);
    expect(leituras()).toHaveLength(2);
    await passar(2 * 60_000);
    expect(await screen.findByText("12.455")).toBeTruthy();
  });

  it("não usa o Atualizar agora: a renovação não gasta o limite de quem clica", async () => {
    servidor({
      leitura: () => (leituras().length === 1 ? resposta(200, payload(12345)) : novo(12400)),
      atualizar: () => resposta(200, payload(99999)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    await passar(56 * 60_000);

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(atualizacoes()).toEqual([]);
  });

  it("se o servidor ainda devolve o número velho, relê de novo em 5 minutos, e não antes", async () => {
    // O Google fora (o servidor segura as idas por 5 minutos e devolve o último
    // valor bom), ou o relógio da máquina adiantado: a hora do número já
    // passou, e a tela não pode ficar relendo sem parar.
    servidor({ leitura: () => resposta(200, payload(12345)) });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    await passar(56 * 60_000);
    await waitFor(() => expect(leituras()).toHaveLength(2));

    await passar(4 * 60_000);
    expect(leituras()).toHaveLength(2);

    await passar(1 * 60_000);
    await waitFor(() => expect(leituras()).toHaveLength(3));
  });

  it("relê em silêncio: não pisca 'Atualizando…' nem apaga os números", async () => {
    let responder: (r: Response) => void = () => {};
    servidor({
      leitura: () =>
        leituras().length === 1 ? resposta(200, payload(12345)) : new Promise<Response>((r) => (responder = r)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    await passar(56 * 60_000);

    await waitFor(() => expect(leituras()).toHaveLength(2));
    expect(screen.queryByText(/Atualizando/)).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();

    await act(async () => responder(novo(12400)));
    expect(await screen.findByText("12.400")).toBeTruthy();
  });

  it("relê mesmo quando o relógio bate logo depois de os números aparecerem", async () => {
    servidor({ leitura: () => (leituras().length === 1 ? resposta(200, payload(12345)) : novo(12400)) });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");

    act(() => {
      vi.advanceTimersByTime(56 * 60_000);
    });

    await waitFor(() => expect(leituras()).toHaveLength(2));
    expect(await screen.findByText("12.400")).toBeTruthy();
  });

  it("não relê por cima da leitura que ainda está no ar", async () => {
    let responderLeitura: (r: Response) => void = () => {};
    servidor({ leitura: () => new Promise<Response>((r) => (responderLeitura = r)) });
    render(<VisaoGeral periodo="28d" />);
    await waitFor(() => expect(pedidos).toHaveLength(1));

    await passar(60 * 60_000);
    await act(async () => responderLeitura(resposta(200, payload(12345))));

    expect(await screen.findByText("12.345")).toBeTruthy();
    expect(leituras()).toHaveLength(1);
  });

  it("não relê por cima de um Atualizar agora clicado, e o botão não fica preso", async () => {
    let responderClique: (r: Response) => void = () => {};
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => new Promise<Response>((r) => (responderClique = r)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    await screen.findByRole("button", { name: /Atualizando/ });

    await passar(56 * 60_000);
    await act(async () => responderClique(novo(12400)));

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
    expect(leituras()).toHaveLength(1);
    expect(atualizacoes()).toHaveLength(1);
  });

  const falhasDaReleitura: [string, () => Response | Promise<Response>][] = [
    ["o limite de taxa (429)", () => resposta(429, { error: "Rate limit exceeded: 30 per 1 minute" })],
    ["o Google fora sem nada guardado (502)", () => resposta(502, { detail: "O Google Analytics respondeu HTTP 503." })],
    ["a rede fora", () => Promise.reject(new TypeError("Failed to fetch"))],
  ];

  it.each(falhasDaReleitura)(
    "%s: a releitura que falha fica em silêncio, com os números e o carimbo de antes, e tenta de novo",
    async (_caso, falhar) => {
      // Ninguém clicou: não há a quem avisar. O carimbo que envelhece já diz
      // de quando são os números.
      servidor({ leitura: () => (leituras().length === 1 ? resposta(200, payload(12345)) : falhar()) });
      render(<VisaoGeral periodo="28d" />);
      await screen.findByText("12.345");

      await passar(56 * 60_000);
      await waitFor(() => expect(leituras()).toHaveLength(2));
      // A resposta ruim termina de chegar (corpo lido, estado decidido).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });

      expect(screen.getByText("12.345")).toBeTruthy();
      expect(screen.getByText("Atualizado há 1 hora")).toBeTruthy();
      expect(screen.queryByRole("status")).toBeNull();
      expect(screen.queryByText(/Muitas atualizações|Não foi possível/)).toBeNull();
      expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();

      await passar(5 * 60_000);
      await waitFor(() => expect(leituras()).toHaveLength(3));
    },
  );

  it("pede a sessão de novo a cada releitura: o token da abertura vence em 1 hora", async () => {
    servidor({ leitura: () => (leituras().length === 1 ? resposta(200, payload(12345)) : novo(12400)) });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    sessao.token = "token-renovado";

    await passar(56 * 60_000);

    await waitFor(() => expect(leituras()).toHaveLength(2));
    expect(leituras()[1].autorizacao).toBe("Bearer token-renovado");
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

describe("Visão Geral: a sessão que não dá para ler", () => {
  const SEM_SESSAO = /sessão não está ativa ou o servidor não respondeu/;

  async function passar(ms: number) {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  }

  it("na abertura, diz por que não há números em vez de ficar em 'Carregando'", async () => {
    servidor({ leitura: () => resposta(200, payload(12345)) });
    sessao.quebrada = true;

    render(<VisaoGeral periodo="28d" />);

    expect(await screen.findByText(SEM_SESSAO)).toBeTruthy();
    expect(screen.queryByText(/Carregando os números/)).toBeNull();
    expect(pedidos).toEqual([]);
  });

  it("no Atualizar agora, os números ficam, o botão volta e o aviso diz por quê", async () => {
    servidor({
      leitura: () => resposta(200, payload(12345)),
      atualizar: () => resposta(200, payload(12400)),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    sessao.quebrada = true;

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(await screen.findByText(SEM_SESSAO)).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
    expect(atualizacoes()).toEqual([]);
  });

  it("a renovação automática continua depois de a sessão falhar e voltar", async () => {
    const leituras = () => pedidos.filter((p) => p.metodo === "GET" && p.url.includes("/visao-geral?"));
    servidor({
      leitura: () =>
        leituras().length === 1
          ? resposta(200, payload(12345))
          : resposta(200, payload(12400, { atualizado_em: new Date().toISOString() })),
    });
    render(<VisaoGeral periodo="28d" />);
    await screen.findByText("12.345");
    sessao.quebrada = true;
    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));
    await screen.findByText(SEM_SESSAO);
    sessao.quebrada = false;

    await passar(60 * 60_000);

    expect(await screen.findByText("12.400")).toBeTruthy();
    expect(leituras()).toHaveLength(2);
  });
});
