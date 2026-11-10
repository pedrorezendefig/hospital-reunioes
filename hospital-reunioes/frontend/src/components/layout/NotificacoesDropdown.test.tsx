/**
 * @vitest-environment jsdom
 */

/**
 * O sino e o aviso de Contas médicas (issue #1124, PRD #1113).
 *
 * Quando as contas de um envio ficam prontas, a faturista recebe um aviso
 * CONTAS_MEDICAS com o envio como referência. Clicar nele leva à fila de
 * contas, e não ao kanban de pendências, que é para onde vão os outros tipos.
 * O irmão de presença: a menção continua indo para o kanban.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apareceComoFoiEscrito } from "@/lib/caixa-alta";
import type { Notificacao } from "@/types";

import { NotificacoesDropdown } from "./NotificacoesDropdown";

const navegacao = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navegacao.push }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ENVIO = "9b2f4c1e-0000-4000-8000-000000000001";

let notificacoes: Notificacao[] = [];

beforeEach(() => {
  navegacao.push.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const corpo = url.includes("/count")
        ? { nao_lidas: notificacoes.length }
        : url.startsWith("/api/notificacoes?")
          ? notificacoes
          : { ok: true };
      return new Response(JSON.stringify(corpo), { status: 200 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function aviso(campos: Partial<Notificacao>): Notificacao {
  return {
    id: "n-1",
    destinatario_id: "F1",
    tipo: "CONTAS_MEDICAS",
    titulo: "2 contas prontas",
    mensagem: "Os guias estão na fila de Contas médicas.",
    referencia_id: ENVIO,
    lida: false,
    created_at: new Date().toISOString(),
    ...campos,
  };
}

async function clicarNoAviso(titulo: string) {
  render(<NotificacoesDropdown />);
  fireEvent.click(screen.getByRole("button", { name: "Notificações" }));
  fireEvent.click(await screen.findByText(titulo));
}

describe("aviso de Contas médicas no sino", () => {
  it("leva à fila de contas", async () => {
    notificacoes = [aviso({})];

    await clicarNoAviso("2 contas prontas");

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/contas-medicas"));
    expect(navegacao.push).toHaveBeenCalledTimes(1);
  });

  it("o aviso de reajuste de contrato leva à tela Contratos (#1144)", async () => {
    notificacoes = [
      aviso({
        titulo: "Contrato ASSIM: reajuste",
        mensagem: "ASSIM: o contrato vence em 60 dias (01/05/2027). Iniciar a negociação do reajuste.",
        referencia_id: "contrato:5d0c7a52-0000-4000-8000-000000000002",
      }),
    ];

    await clicarNoAviso("Contrato ASSIM: reajuste");

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/contas-medicas/contratos"));
    expect(navegacao.push).toHaveBeenCalledTimes(1);
  });

  it("a menção segue para o kanban de pendências", async () => {
    notificacoes = [aviso({ tipo: "MENCAO", titulo: "Ana mencionou você", referencia_id: "A-0042" })];

    await clicarNoAviso("Ana mencionou você");

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/pendencias/kanban?highlight=A-0042"));
  });
});

describe("aviso da Conversa da Demanda no sino (#1537)", () => {
  it("abre a Demanda na aba Tecnologia", async () => {
    notificacoes = [
      aviso({
        tipo: "TECNOLOGIA",
        titulo: "Pedro Vitta escreveu na Demanda",
        mensagem: "O relatório some",
        referencia_id: "d-42",
      }),
    ];

    await clicarNoAviso("Pedro Vitta escreveu na Demanda");

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/admin/tecnologia?demanda=d-42"));
    expect(navegacao.push).toHaveBeenCalledTimes(1);
  });
});

describe("painel do sino quando a lista falha (#1430)", () => {
  it("não diz 'Sem notificações' com o sino marcando avisos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/count")
          ? new Response(JSON.stringify({ nao_lidas: 3 }), { status: 200 })
          : new Response("Internal Server Error", { status: 500 }),
      ),
    );

    render(<NotificacoesDropdown />);
    await screen.findByText("3");
    fireEvent.click(screen.getByRole("button", { name: "Notificações" }));

    await screen.findByText("Não foi possível carregar os avisos.");
    expect(screen.queryByText("Sem notificações")).toBeNull();
  });
});

describe("caixa alta no painel do sino (ADR 0080)", () => {
  it("o título do painel é Texto curto e o aviso inteiro fica corrido", async () => {
    notificacoes = [aviso({})];
    render(<NotificacoesDropdown />);
    fireEvent.click(screen.getByRole("button", { name: "Notificações" }));

    const titulo = await screen.findByRole("heading", { name: "Notificações" });
    expect(apareceComoFoiEscrito(titulo)).toBe(false);

    const textoDoAviso = await screen.findByText("2 contas prontas");
    const item = textoDoAviso.closest("button")!;
    expect(apareceComoFoiEscrito(textoDoAviso)).toBe(true);
    expect(apareceComoFoiEscrito(within(item).getByText("Os guias estão na fila de Contas médicas."))).toBe(true);
    expect(apareceComoFoiEscrito(within(item).getByText("agora"))).toBe(true);
  });
});
