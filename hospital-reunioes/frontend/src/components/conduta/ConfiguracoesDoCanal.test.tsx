/**
 * @vitest-environment jsdom
 */

/**
 * A tela Configurações do Canal de Conduta (issue #1826, PRD #1786).
 *
 * A coordenação vê cada item com a versão vigente, edita e salva uma versão
 * nova, e consulta as anteriores. Quem não é da coordenação vê a recusa. O
 * backend é um dublê que responde por rota; o que se confere é o que a tela
 * mostra do que veio e o que ela manda. Pessoas de teste.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfiguracoesDoCanal } from "./ConfiguracoesDoCanal";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ROTA = "/api/comite-de-conduta/configuracoes";

function versao(n: number, texto: string) {
  return { id: `v-${n}`, versao: n, texto, autor: "Coordenadora de Teste", criado_em: `2026-11-1${n}T15:00:00+00:00` };
}

function itens() {
  return {
    itens: [
      { chave: "contato_dp", rotulo: "Contato do DP exibido", grupo: "Contatos", publico: true, versoes: [] },
      {
        chave: "aviso_p1_boa_fe",
        rotulo: "Aviso 3: boa-fé e acusação falsa",
        grupo: "Avisos do passo 1",
        publico: true,
        versoes: [versao(2, "Texto validado pelo jurídico."), versao(1, "Texto da especificação.")],
      },
      {
        chave: "local_guarda_envelopes",
        rotulo: "Local padrão de guarda dos envelopes",
        grupo: "Comitê",
        publico: false,
        versoes: [],
      },
    ],
  };
}

let chamadas: { url: string; init?: RequestInit }[] = [];
let statusDaLista = 200;

beforeEach(() => {
  chamadas = [];
  statusDaLista = 200;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      if (url === ROTA && statusDaLista !== 200) {
        return new Response(JSON.stringify({ detail: "Sem acesso a este conteúdo do Canal de Conduta" }), {
          status: statusDaLista,
        });
      }
      if (url === ROTA) return new Response(JSON.stringify(itens()), { status: 200 });
      if (url.startsWith(`${ROTA}/`) && init?.method === "POST") {
        return new Response(JSON.stringify(versao(1, "Ramal 2040")), { status: 201 });
      }
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** O cartão de um item, achado pelo título dele. */
async function cartao(rotulo: string): Promise<HTMLElement> {
  return (await screen.findByRole("heading", { name: rotulo })).closest("article") as HTMLElement;
}

describe("ConfiguracoesDoCanal", () => {
  it("mostra a versão vigente de cada item, com autor e data, e o que ainda não foi preenchido", async () => {
    render(<ConfiguracoesDoCanal />);

    const aviso = await cartao("Aviso 3: boa-fé e acusação falsa");
    expect(within(aviso).getByText("Texto validado pelo jurídico.")).toBeTruthy();
    expect(within(aviso).getByText(/Versão 2, por Coordenadora de Teste em 12\/11\/2026/)).toBeTruthy();
    expect(within(await cartao("Contato do DP exibido")).getByText("Ainda não preenchido.")).toBeTruthy();
  });

  it("guarda as versões anteriores para consulta", async () => {
    render(<ConfiguracoesDoCanal />);

    const aviso = await cartao("Aviso 3: boa-fé e acusação falsa");
    fireEvent.click(within(aviso).getByText("Versões anteriores (1)"));

    expect(within(aviso).getByText("Texto da especificação.")).toBeTruthy();
    expect(within(aviso).getByText(/Versão 1, por Coordenadora de Teste em 11\/11\/2026/)).toBeTruthy();
  });

  it("salvar manda o texto novo do item e recarrega a lista", async () => {
    render(<ConfiguracoesDoCanal />);

    const contato = await cartao("Contato do DP exibido");
    fireEvent.click(within(contato).getByRole("button", { name: "Editar" }));
    fireEvent.change(within(contato).getByLabelText("Contato do DP exibido"), { target: { value: "Ramal 2040" } });
    fireEvent.click(within(contato).getByRole("button", { name: "Salvar nova versão" }));

    await waitFor(() => expect(chamadas.filter((c) => c.url === ROTA)).toHaveLength(2));
    const envio = chamadas.find((c) => c.init?.method === "POST");
    expect(envio?.url).toBe(`${ROTA}/contato_dp`);
    expect(JSON.parse(String(envio?.init?.body))).toEqual({ texto: "Ramal 2040" });
  });

  it("não tem campo de e-mail do DP", async () => {
    render(<ConfiguracoesDoCanal />);
    await screen.findByText("Contato do DP exibido");

    expect(document.body.textContent).not.toMatch(/e-?mail/i);
  });

  it("quem não é da coordenação vê a recusa, sem os itens", async () => {
    statusDaLista = 403;
    render(<ConfiguracoesDoCanal />);

    expect(await screen.findByText("Esta tela é só da coordenação do Comitê.")).toBeTruthy();
    expect(screen.queryByText("Contato do DP exibido")).toBeNull();
  });
});
