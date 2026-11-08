/**
 * @vitest-environment jsdom
 */

/**
 * A conversa da Conta com o Auditor, no Guia (issue #1489, PRD #1484, ADR 0081).
 *
 * A tela não decide nada: quem aponta, a origem e quem abre o pedido para a
 * Tecnologia vêm do servidor. O que se trava aqui é o que a pessoa vê (o nome
 * do agente, a resposta, o botão do pedido só para quem pode) e o que cada
 * clique dispara (a URL e o corpo).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import type { FaltouIsto } from "@/lib/contas-medicas/faltouIsto";

import { ConversaDaConta } from "./ConversaDaConta";

const CONTA = "11111111-1111-1111-1111-111111111111";
const ROTA = `/api/contas-medicas/contas/${CONTA}/guia/faltou-isto`;
const DIAS = ["2026-10-03", "2026-10-04", "2026-10-05"];

function apontamento(campos: Partial<FaltouIsto> = {}): FaltouIsto {
  return {
    id: "f-1",
    data: "2026-10-03",
    item: "Equipo macrogotas",
    pagina: 2,
    texto: "Por que você não achou o equipo nesta página?",
    origem: "PESSOA",
    classificacao: "DEFEITO",
    explicacao: "O acesso está na página 2, mas o Guia não pediu o equipo.",
    pedido_aberto: false,
    pode_abrir_pedido: true,
    ...campos,
  };
}

let chamadas: { url: string; metodo: string; corpo: unknown }[] = [];
let lista: FaltouIsto[] = [];

beforeEach(() => {
  chamadas = [];
  lista = [apontamento()];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = init?.body ? JSON.parse(String(init.body)) : undefined;
      chamadas.push({ url, metodo, corpo });
      if (url.endsWith("/pedido")) {
        const aberto = { ...apontamento(), pedido_aberto: true, pode_abrir_pedido: false };
        return new Response(JSON.stringify({ apontamento: aberto }), { status: 200 });
      }
      const novo = apontamento({
        id: "f-2",
        data: corpo.data,
        item: corpo.item,
        pagina: corpo.pagina,
        texto: corpo.texto,
        classificacao: "REGRA",
        explicacao: "Nenhuma regra da memória cobra a fralda neste caso.",
        pode_abrir_pedido: false,
      });
      return new Response(JSON.stringify({ apontamento: novo }), { status: 200 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function abrir(escolha: { dia: string; vez: number } | null = null) {
  return render(
    <ToastProvider>
      <ConversaDaConta contaId={CONTA} token="token-de-teste" dias={DIAS} iniciais={lista} escolha={escolha} />
    </ToastProvider>,
  );
}

describe("a conversa com o Auditor", () => {
  it("chama o agente de Auditor e mostra a fala de quem apontou com a resposta e a origem", async () => {
    abrir();

    const conversa = screen.getByRole("region", { name: "Falar com o auditor" });
    expect(within(conversa).getByRole("heading", { name: "Falar com o auditor" })).toBeTruthy();
    expect(
      await within(conversa).findByText(
        "Faltou isto em 03/10, página 2: Equipo macrogotas. Por que você não achou o equipo nesta página?",
      ),
    ).toBeTruthy();
    const resposta = within(conversa).getByRole("article", { name: "Resposta do Auditor" });
    expect(within(resposta).getByText("Auditor")).toBeTruthy();
    expect(within(resposta).getByText("Defeito do sistema")).toBeTruthy();
    expect(within(resposta).getByText("O acesso está na página 2, mas o Guia não pediu o equipo.")).toBeTruthy();
    expect(chamadas).toEqual([]);
  });

  it("aponta o Faltou isto do dia escolhido, com o item, a página e a pergunta", async () => {
    abrir();
    await screen.findByText(/Equipo macrogotas\./);

    fireEvent.change(screen.getByLabelText("Dia"), { target: { value: "2026-10-04" } });
    fireEvent.change(screen.getByLabelText("Item que faltou"), { target: { value: "Fralda geriátrica" } });
    fireEvent.change(screen.getByLabelText("Página do prontuário"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Mensagem para o auditor"), { target: { value: "E a fralda?" } });
    fireEvent.click(screen.getByRole("button", { name: "Perguntar ao auditor" }));

    expect(await screen.findByText("Nenhuma regra da memória cobra a fralda neste caso.")).toBeTruthy();
    expect(chamadas.at(-1)).toEqual({
      url: ROTA,
      metodo: "POST",
      corpo: { data: "2026-10-04", item: "Fralda geriátrica", pagina: 12, texto: "E a fralda?" },
    });
    expect(screen.getByText("Falta regra")).toBeTruthy();
    expect((screen.getByLabelText("Item que faltou") as HTMLInputElement).value).toBe("");
  });

  it("sem o item, o botão de perguntar fica desligado", async () => {
    abrir();

    const perguntar = screen.getByRole("button", { name: "Perguntar ao auditor" }) as HTMLButtonElement;
    expect(perguntar.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Item que faltou"), { target: { value: "Equipo" } });
    expect(perguntar.disabled).toBe(false);
  });

  it("o dia escolhido no Guia chega ao formulário", async () => {
    abrir({ dia: "2026-10-05", vez: 1 });

    await waitFor(() => expect((screen.getByLabelText("Dia") as HTMLSelectElement).value).toBe("2026-10-05"));
    expect(screen.getAllByRole("option").map((opcao) => opcao.textContent)).toEqual(["03/10", "04/10", "05/10"]);
  });
});

describe("o pedido para a Tecnologia", () => {
  it("quem apontou dá o ok e o pedido fica aberto, sem número na tela", async () => {
    abrir();

    fireEvent.click(await screen.findByRole("button", { name: "Abrir o pedido para a Tecnologia" }));

    expect(await screen.findByText("Pedido aberto para a Tecnologia.")).toBeTruthy();
    expect(chamadas.at(-1)).toEqual({ url: `${ROTA}/f-1/pedido`, metodo: "POST", corpo: undefined });
    expect(screen.queryByRole("button", { name: "Abrir o pedido para a Tecnologia" })).toBeNull();
  });

  it("quem não apontou não vê o botão do pedido", async () => {
    lista = [apontamento({ pode_abrir_pedido: false })];
    abrir();

    expect(await screen.findByText("O acesso está na página 2, mas o Guia não pediu o equipo.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Abrir o pedido para a Tecnologia" })).toBeNull();
  });
});
