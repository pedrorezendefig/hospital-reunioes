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
import { caixaDoDado } from "@/lib/testes/caixaDoDado";
import {
  type FilaDeValidacao,
  PERGUNTA_A_CADA_MS,
  type PedidoAoAuditor,
  type Tema,
} from "@/lib/contas-medicas/validacao";

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
    recomendacao: null,
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

const SEM_PEDIDO: PedidoAoAuditor = { temas: 0, provas: 0, custo_estimado_usd: 0, em_andamento: false };

function servidor(
  fila: FilaDeValidacao = FILA,
  status = 200,
  leitura: Leitura = "ok",
  pedido: PedidoAoAuditor = { ...SEM_PEDIDO },
) {
  const pedidos: Pedido[] = [];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    pedidos.push({ url, metodo, corpo: typeof init?.body === "string" ? JSON.parse(init.body) : null });
    if (url === "/api/contas-medicas/validacao") {
      return { ok: status === 200, status, json: async () => (status === 200 ? fila : { detail: "Sem permissão" }) };
    }
    if (url === "/api/contas-medicas/validacao/recomendacao") {
      if (metodo === "POST") pedido.em_andamento = true;
      return { ok: true, status: metodo === "POST" ? 202 : 200, json: async () => ({ ...pedido }) };
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

  it("o título do cartão mostra o termo e o código como estão gravados, fora da caixa alta (issue #1455)", async () => {
    servidor();

    abrir();

    const termo = await screen.findByRole("heading", { level: 2, name: "Termo SERINGA PRONTA no dicionário" });
    expect(caixaDoDado(termo)).toBe("normal-case");
    expect(caixaDoDado(screen.getByRole("heading", { level: 2, name: "Regra ALFA-PRI-03" }))).toBe("normal-case");
  });
});

// A fila decidida pelo Auditor (issue #1491): a regra com a prova, a
// observação com a resposta pronta; o bloqueado e o termo, sem recomendação.
const DECIDIDA: FilaDeValidacao = {
  ...FILA,
  temas: FILA.temas.map((t) => {
    if (t.id === "regra") {
      return {
        ...t,
        recomendacao: {
          decisao: "VALIDAR_REGRA",
          motivo: "A seringa pronta é cobrada à parte no contrato da ALFA.",
          texto: null,
          prova: {
            contas: 10,
            mudaria: true,
            feitas_que_sumiriam: 1,
            por_conta: [{ numero_conta: "48803", entrariam: 2, sairiam: 1, mudariam: 0 }],
          },
          recomendado_em: "2026-11-08T10:00:00+00:00",
        },
      };
    }
    if (t.id === "observacao") {
      return {
        ...t,
        recomendacao: {
          decisao: "RESPONDER",
          motivo: "A regra já cobre o caso.",
          texto: "Na ALFA o Clexane vem no pacote: a regra segue como está.",
          prova: null,
          recomendado_em: "2026-11-08T10:30:00+00:00",
        },
      };
    }
    return t;
  }),
};

type RespostaDoLote = {
  decididos: { id: string; decisao: string }[];
  falhas: { id: string; titulo: string; motivo: string }[];
  cadastro: string[];
};

function servidorDoLote(resposta: RespostaDoLote, fila: FilaDeValidacao = DECIDIDA) {
  const pedidos = servidor(fila);
  const base = globalThis.fetch as unknown as (url: string, init?: RequestInit) => Promise<unknown>;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const resultado = await base(url, init);
      if (url === "/api/contas-medicas/validacao/lote") {
        return { ok: true, status: 200, json: async () => resposta };
      }
      return resultado;
    }),
  );
  return pedidos;
}

const LOTE_OK: RespostaDoLote = {
  decididos: [
    { id: "regra", decisao: "VALIDAR_REGRA" },
    { id: "observacao", decisao: "RESPONDER" },
  ],
  falhas: [],
  cadastro: [],
};

describe("a fila decidida pelo Auditor (issue #1491)", () => {
  it("cada cartão mostra a recomendação e o motivo, e a regra pendente mostra a prova", async () => {
    servidor(DECIDIDA);
    abrir();

    const regra = await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });
    expect(regra.textContent).toContain("O Auditor recomenda: Validar regra");
    expect(regra.textContent).toContain("A seringa pronta é cobrada à parte no contrato da ALFA.");
    expect(regra.textContent).toContain("Prova da regra em 10 contas concluídas");
    expect(regra.textContent).toContain("Conta 48803: 2 entrariam, 1 sairia, 0 mudariam");
    expect(regra.textContent).toContain("1 linha já feita sumiria");

    const observacao = cartao("Observações sobre a regra ALFA-PRI-07");
    expect(observacao.textContent).toContain("O Auditor recomenda: Responder ao time");
    expect(observacao.textContent).toContain("Na ALFA o Clexane vem no pacote: a regra segue como está.");

    expect(cartao("Código 70000020 bloqueado").textContent).toContain("O Auditor ainda não recomendou");
  });

  it("a prova que não mudaria nada diz isso", async () => {
    servidor({
      ...DECIDIDA,
      temas: DECIDIDA.temas.map((t) =>
        t.id === "regra" && t.recomendacao
          ? { ...t, recomendacao: { ...t.recomendacao, prova: { contas: 4, mudaria: false, feitas_que_sumiriam: 0, por_conta: [] } } }
          : t,
      ),
    });
    abrir();

    const regra = await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });
    expect(regra.textContent).toContain("A regra não mudaria nada nas 4 contas concluídas da prova.");
  });

  it("Aprovar o lote manda a recomendação que cada cartão mostrava e relê a fila", async () => {
    const pedidos = servidorDoLote(LOTE_OK);
    abrir();
    await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });

    fireEvent.click(screen.getByRole("button", { name: "Aprovar o lote (2)" }));

    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/lote",
        metodo: "POST",
        corpo: {
          temas: [
            { id: "regra", decisao: "VALIDAR_REGRA", recomendado_em: "2026-11-08T10:00:00+00:00" },
            { id: "observacao", decisao: "RESPONDER", recomendado_em: "2026-11-08T10:30:00+00:00" },
          ],
        },
      }),
    );
    await waitFor(() => expect(pedidos.filter((p) => p.url === "/api/contas-medicas/validacao")).toHaveLength(2));
  });

  it("o lote que mandou código ao cadastro baixa a lista, e o tema que recusou aparece com o motivo", async () => {
    const pedidos = servidorDoLote({
      decididos: [{ id: "bloqueado", decisao: "ENVIAR_AO_CADASTRO" }],
      falhas: [{ id: "regra", titulo: "Regra ALFA-PRI-03", motivo: "Sem a permissão de regra contratual." }],
      cadastro: ["bloqueado"],
    });
    abrir();
    await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });

    fireEvent.click(screen.getByRole("button", { name: "Aprovar o lote (2)" }));

    await waitFor(() =>
      expect(pedidos).toContainEqual({
        url: "/api/contas-medicas/validacao/temas/bloqueado/cadastro",
        metodo: "GET",
        corpo: null,
      }),
    );
    expect(URL.createObjectURL).toHaveBeenCalled();
    const aviso = await screen.findByRole("alert");
    expect(aviso.textContent).toContain("Regra ALFA-PRI-03: Sem a permissão de regra contratual.");
  });

  it("sem recomendação na fila, não há lote para aprovar", async () => {
    servidor();
    abrir();
    await screen.findByRole("article", { name: "Regra ALFA-PRI-03" });

    expect(screen.queryByRole("button", { name: /Aprovar o lote/ })).toBeNull();
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

describe("o pedido de recomendação ao Auditor (ADR 0082, issue #1523)", () => {
  const ROTA = "/api/contas-medicas/validacao/recomendacao";
  const TRES = (): PedidoAoAuditor => ({ temas: 3, provas: 1, custo_estimado_usd: 0.42, em_andamento: false });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("mostra quantos cartões estão sem recomendação, as provas e o custo antes do clique", async () => {
    const pedidos = servidor(FILA, 200, "ok", TRES());
    abrir();

    const pedido = await screen.findByRole("region", { name: "Pedido ao Auditor" });
    expect(pedido.textContent).toContain("3 cartões estão sem recomendação do Auditor, 1 com Prova da regra");
    expect(pedido.textContent).toContain("cerca de US$ 0,42");
    expect(pedidos.filter((p) => p.url === ROTA && p.metodo === "POST")).toHaveLength(0);
  });

  it("o clique pergunta com o custo, manda o pedido e mostra que o Auditor está recomendando", async () => {
    const pedidos = servidor(FILA, 200, "ok", TRES());
    const confirmar = vi.spyOn(window, "confirm").mockReturnValue(true);
    abrir();

    fireEvent.click(await screen.findByRole("button", { name: "Pedir recomendação ao Auditor" }));

    expect(confirmar).toHaveBeenCalledWith(
      "Pedir ao Auditor a recomendação de 3 cartões? Custo estimado: cerca de US$ 0,42.",
    );
    await screen.findByText("O Auditor está recomendando a fila. A tela atualiza sozinha quando ele terminar.", {
      exact: false,
    });
    expect(pedidos).toContainEqual({ url: ROTA, metodo: "POST", corpo: null });
    expect(screen.queryByRole("button", { name: "Pedir recomendação ao Auditor" })).toBeNull();
  });

  it("sem confirmar, não pede nada ao servidor", async () => {
    const pedidos = servidor(FILA, 200, "ok", TRES());
    vi.spyOn(window, "confirm").mockReturnValue(false);
    abrir();

    fireEvent.click(await screen.findByRole("button", { name: "Pedir recomendação ao Auditor" }));

    expect(pedidos.filter((p) => p.url === ROTA && p.metodo === "POST")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Pedir recomendação ao Auditor" })).toBeTruthy();
  });

  it("sem cartão sem recomendação, o botão não aparece", async () => {
    servidor(FILA, 200, "ok", { ...SEM_PEDIDO });
    abrir();

    await screen.findByRole("region", { name: "Números da Validação" });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Pedido ao Auditor" })).toBeNull());
  });

  it("quando o Auditor termina, a tela relê a fila e o aviso some", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const pedido = { ...TRES(), em_andamento: true };
    const pedidos = servidor(FILA, 200, "ok", pedido);
    abrir();
    await screen.findByText("O Auditor está recomendando a fila.", { exact: false });

    Object.assign(pedido, { temas: 0, provas: 0, em_andamento: false });
    await vi.advanceTimersByTimeAsync(PERGUNTA_A_CADA_MS);

    await waitFor(() => expect(pedidos.filter((p) => p.url === "/api/contas-medicas/validacao")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Pedido ao Auditor" })).toBeNull());
  });
});

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
