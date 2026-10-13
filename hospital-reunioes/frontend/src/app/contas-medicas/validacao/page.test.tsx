/**
 * @vitest-environment jsdom
 */

/**
 * A fila de Validação de Contas médicas (issue #1142, PRD #1129).
 *
 * A tela não decide nada: o servidor manda os temas em ordem e os três
 * números prontos, e cada botão vira um pedido à rota de decisão. O que se
 * trava aqui é o que aparece (números, cartões na ordem do servidor, os
 * botões de cada tipo) e o que cada botão pede ao servidor.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import type { FilaDeValidacao, Tema } from "@/lib/contas-medicas/validacao";

import ValidacaoPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

function tema(campos: Partial<Tema>): Tema {
  return {
    id: "t-1",
    tipo: "REGRA_PENDENTE",
    titulo: "Regra ALFA-PRI-03",
    operadora: "ALFA",
    regra_codigo: "ALFA-PRI-03",
    regra: { texto: "Seringa de limpeza pronta é cobrada à parte.", tipo: "CONTRATUAL", origem: "PRÁTICA", status: "PENDENTE" },
    codigo_item: null,
    contas: 3,
    desde: "2026-10-05T12:00:00+00:00",
    valor: 250.5,
    leitura_ia: null,
    observacoes: [],
    dicionario: null,
    ...campos,
  };
}

const FILA: FilaDeValidacao = {
  numeros: { aguardando_decisao: 4, contas_afetadas: 3, valor_em_jogo: 361.5 },
  temas: [
    tema({ id: "regra" }),
    tema({
      id: "bloqueado",
      tipo: "BLOQUEADO",
      titulo: "Código 70000020 bloqueado",
      regra_codigo: null,
      regra: null,
      codigo_item: "70000020",
      contas: 2,
      valor: 66,
    }),
    tema({
      id: "observacao",
      tipo: "OBSERVACAO",
      titulo: "Observações sobre a regra ALFA-PRI-07",
      regra_codigo: "ALFA-PRI-07",
      regra: { texto: "Medicamento prescrito e não lançado é incluído.", tipo: "OPERACIONAL", origem: null, status: "VIGENTE" },
      contas: 1,
      valor: 45,
      observacoes: ["A regra é outra: Na ALFA o Clexane vem dentro do pacote"],
    }),
    tema({
      id: "dicionario",
      tipo: "DICIONARIO",
      titulo: "Termo SERINGA PRONTA no dicionário",
      regra_codigo: null,
      regra: null,
      contas: 0,
      valor: 0,
      dicionario: { termo: "SERINGA PRONTA", codigo_conta: "70000010", descricao_conta: "POSIFLUSH SF 0,9% 10ML" },
    }),
  ],
};

const LEITURA = "A regra atual não cobre o caso. Sugestão: editar a regra.";

type Pedido = { url: string; metodo: string; corpo: unknown };

type Leitura = "ok" | "ia-fora" | "sem-rede";

function servidor(fila: FilaDeValidacao = FILA, status = 200, leitura: Leitura = "ok") {
  const pedidos: Pedido[] = [];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    pedidos.push({ url, metodo, corpo: typeof init?.body === "string" ? JSON.parse(init.body) : null });
    if (url === "/api/contas-medicas/validacao") {
      return { ok: status === 200, status, json: async () => (status === 200 ? fila : { detail: "Sem permissão" }) };
    }
    if (url.endsWith("/leitura")) {
      if (leitura === "sem-rede") throw new TypeError("Failed to fetch");
      if (leitura === "ia-fora") {
        return { ok: false, status: 503, json: async () => ({ detail: "Tente de novo em alguns minutos." }) };
      }
      return { ok: true, status: 200, json: async () => ({ leitura_ia: LEITURA }) };
    }
    if (url === "/api/transcricao/voz") {
      return { ok: true, status: 200, json: async () => ({ texto: "vem no pacote da ALFA" }) };
    }
    if (url.endsWith("/cadastro")) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-disposition": 'attachment; filename="cadastro-70000020.csv"' }),
        blob: async () => new Blob(["csv"]),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetch);
  return pedidos;
}

// O Toast é o de verdade: o Ditar avisa por ele (issue #1145).
function abrir() {
  render(
    <ToastProvider>
      <ValidacaoPage />
    </ToastProvider>,
  );
}

function cartao(nome: string): HTMLElement {
  return screen.getByRole("article", { name: nome });
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:csv");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a fila de Validação", () => {
  it("mostra os três números e os cartões na ordem do servidor, com os botões de cada tipo", async () => {
    servidor();

    abrir();

    const numeros = await screen.findByRole("region", { name: "Números da Validação" });
    expect(within(numeros).getByText("Aguardando decisão").closest("div")?.textContent).toContain("4");
    expect(within(numeros).getByText("Contas afetadas").closest("div")?.textContent).toContain("3");
    expect(within(numeros).getByText("R$ em jogo").closest("div")?.textContent).toContain("R$ 361,50");

    const titulos = screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"));
    expect(titulos).toEqual([
      "Regra ALFA-PRI-03",
      "Código 70000020 bloqueado",
      "Observações sobre a regra ALFA-PRI-07",
      "Termo SERINGA PRONTA no dicionário",
    ]);
    const regra = cartao("Regra ALFA-PRI-03");
    expect(regra.textContent).toContain("Regra pendente");
    expect(regra.textContent).toContain("ALFA");
    expect(regra.textContent).toContain("3 contas");
    expect(regra.textContent).toContain("desde 05/10/2026");
    expect(regra.textContent).toContain("R$ 250,50");
    for (const [nome, botoes] of [
      ["Regra ALFA-PRI-03", ["Validar regra", "Deixar pendente"]],
      ["Código 70000020 bloqueado", ["Enviar ao cadastro", "Descartar"]],
      ["Observações sobre a regra ALFA-PRI-07", ["Manter a regra", "Editar a regra", "Responder ao time"]],
      ["Termo SERINGA PRONTA no dicionário", ["Confirmar", "Rejeitar"]],
    ] as const) {
      for (const botao of botoes) {
        expect(within(cartao(nome)).getByRole("button", { name: botao }), `${nome}: ${botao}`).toBeTruthy();
      }
    }
  });

  it("Validar regra abre o texto da regra e grava a decisão com o texto editado", async () => {
    const pedidos = servidor();
    abrir();
    await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });

    fireEvent.click(within(cartao("Regra ALFA-PRI-03")).getByRole("button", { name: "Validar regra" }));
    const texto = within(cartao("Regra ALFA-PRI-03")).getByLabelText("Texto da regra") as HTMLTextAreaElement;
    expect(texto.value).toBe("Seringa de limpeza pronta é cobrada à parte.");
    fireEvent.change(texto, { target: { value: "Seringa pronta é cobrada à parte, uma por dose." } });
    fireEvent.click(within(cartao("Regra ALFA-PRI-03")).getByRole("button", { name: "Confirmar e validar" }));

    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/temas/regra/decisao",
        metodo: "POST",
        corpo: { decisao: "VALIDAR_REGRA", texto: "Seringa pronta é cobrada à parte, uma por dose." },
      }),
    );
    await waitFor(() => expect(pedidos.filter((p) => p.url === "/api/contas-medicas/validacao")).toHaveLength(2));
  });

  it("Enviar ao cadastro pede a lista e Descartar grava a decisão", async () => {
    const pedidos = servidor();
    abrir();
    await screen.findByRole("article", { name: "Código 70000020 bloqueado" });

    fireEvent.click(within(cartao("Código 70000020 bloqueado")).getByRole("button", { name: "Enviar ao cadastro" }));
    await waitFor(() =>
      expect(pedidos.map((p) => p.url)).toContain("/api/contas-medicas/validacao/temas/bloqueado/cadastro"),
    );
    expect(URL.createObjectURL).toHaveBeenCalled();

    fireEvent.click(within(cartao("Código 70000020 bloqueado")).getByRole("button", { name: "Descartar" }));
    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/temas/bloqueado/decisao",
        metodo: "POST",
        corpo: { decisao: "DESCARTAR" },
      }),
    );
  });

  it("a observação mostra a leitura da IA e Responder ao time manda o texto", async () => {
    const pedidos = servidor();
    abrir();
    const observacao = await screen.findByRole("article", { name: "Observações sobre a regra ALFA-PRI-07" });

    expect(observacao.textContent).toContain("Na ALFA o Clexane vem dentro do pacote");
    await waitFor(() => expect(observacao.textContent).toContain(LEITURA));
    expect(pedidos.filter((p) => p.url.endsWith("/leitura")).map((p) => p.url)).toEqual([
      "/api/contas-medicas/validacao/temas/observacao/leitura",
    ]);

    fireEvent.click(within(observacao).getByRole("button", { name: "Responder ao time" }));
    fireEvent.change(within(observacao).getByLabelText("Resposta ao time"), {
      target: { value: "Confirmado com a ALFA: vem no pacote." },
    });
    fireEvent.click(within(observacao).getByRole("button", { name: "Enviar resposta" }));

    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/temas/observacao/decisao",
        metodo: "POST",
        corpo: { decisao: "RESPONDER", texto: "Confirmado com a ALFA: vem no pacote." },
      }),
    );
  });

  it("com a IA fora, o cartão da observação diz que a leitura está indisponível, com a mensagem do servidor", async () => {
    servidor(FILA, 200, "ia-fora");
    abrir();
    const observacao = await screen.findByRole("article", { name: "Observações sobre a regra ALFA-PRI-07" });

    await waitFor(() => expect(observacao.textContent).toContain("Leitura indisponível agora"));
    expect(observacao.textContent).toContain("Tente de novo em alguns minutos.");
    expect(observacao.textContent).not.toContain("lendo as observações");
  });

  it("sem rede, o cartão da observação diz que a leitura está indisponível em vez de ficar lendo", async () => {
    servidor(FILA, 200, "sem-rede");
    abrir();
    const observacao = await screen.findByRole("article", { name: "Observações sobre a regra ALFA-PRI-07" });

    await waitFor(() => expect(observacao.textContent).toContain("Leitura indisponível agora"));
    expect(observacao.textContent).not.toContain("lendo as observações");
  });

  it("o termo do dicionário mostra o código proposto e Confirmar grava a decisão", async () => {
    const pedidos = servidor();
    abrir();
    const termo = await screen.findByRole("article", { name: "Termo SERINGA PRONTA no dicionário" });

    expect(termo.textContent).toContain("70000010");
    expect(termo.textContent).toContain("POSIFLUSH SF 0,9% 10ML");
    fireEvent.click(within(termo).getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/temas/dicionario/decisao",
        metodo: "POST",
        corpo: { decisao: "CONFIRMAR" },
      }),
    );
  });

  it("sem a permissão, diz que não pode e não mostra cartão", async () => {
    servidor(FILA, 403);

    abrir();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("decidir na validação");
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });
});

class GravadorFalso {
  static ultimo: GravadorFalso | null = null;
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor() {
    GravadorFalso.ultimo = this;
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["bytes-de-audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

describe("o Ditar na resposta ao time (issue #1145)", () => {
  it("tem o aviso de paciente ao lado, e o texto ditado entra no campo sem enviar a resposta", async () => {
    GravadorFalso.ultimo = null;
    vi.stubGlobal("MediaRecorder", GravadorFalso);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => ({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    const pedidos = servidor();
    abrir();
    const observacao = await screen.findByRole("article", { name: "Observações sobre a regra ALFA-PRI-07" });
    fireEvent.click(within(observacao).getByRole("button", { name: "Responder ao time" }));

    const botao = within(observacao).getByRole("button", { name: "Ditar: Resposta ao time" });
    expect(botao.parentElement?.textContent).toContain("Não dite nome nem dado de paciente.");

    fireEvent.click(botao);
    await waitFor(() => expect(GravadorFalso.ultimo?.state).toBe("recording"));
    fireEvent.click(within(observacao).getByRole("button", { name: "Parar o ditado: Resposta ao time" }));

    const campo = within(observacao).getByLabelText("Resposta ao time") as HTMLTextAreaElement;
    await waitFor(() => expect(campo.value).toBe("vem no pacote da ALFA"));
    expect(pedidos.filter((p) => p.url === "/api/transcricao/voz")).toHaveLength(1);
    expect(pedidos.filter((p) => p.url.endsWith("/decisao"))).toEqual([]);
  });
});
