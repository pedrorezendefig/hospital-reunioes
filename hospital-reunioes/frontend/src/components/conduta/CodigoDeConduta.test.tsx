/**
 * @vitest-environment jsdom
 */

/**
 * O Código de Conduta na tela Configurações (issue #1841, PRD #1786).
 *
 * A coordenação vê a versão vigente e as anteriores, abre o PDF de qualquer
 * uma e publica uma versão nova com a data de vigência. Quem não é da
 * coordenação não vê o bloco (a recusa da tela já aparece acima). O backend é
 * um dublê que responde por rota. Pessoas de teste.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CodigoDeConduta } from "./CodigoDeConduta";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ROTA = "/api/comite-de-conduta/codigo-de-conduta";

function versao(n: number, vigente_desde: string) {
  return {
    id: `v-${n}`,
    versao: n,
    vigente_desde,
    nome_arquivo: `codigo-${n}.pdf`,
    tamanho_bytes: 2048,
    autor: "Coordenadora de Teste",
    criado_em: "2026-11-20T15:00:00+00:00",
  };
}

let chamadas: { url: string; init?: RequestInit }[] = [];
let statusDaLista = 200;
let versoes = [versao(2, "2026-12-01"), versao(1, "2026-11-20")];
let cliques: { href: string; download: string }[] = [];

beforeEach(() => {
  chamadas = [];
  statusDaLista = 200;
  versoes = [versao(2, "2026-12-01"), versao(1, "2026-11-20")];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      if (url === ROTA && init?.method === "POST") {
        return new Response(JSON.stringify(versao(3, "2027-01-01")), { status: 201 });
      }
      if (url === ROTA && statusDaLista !== 200) {
        return new Response(JSON.stringify({ detail: "Sem acesso a este conteúdo do Canal de Conduta" }), {
          status: statusDaLista,
        });
      }
      if (url === ROTA) return new Response(JSON.stringify({ versoes }), { status: 200 });
      if (url.startsWith(`${ROTA}/arquivo`)) return new Response(new Blob(["%PDF-1.7"]), { status: 200 });
      return new Response("{}", { status: 404 });
    }),
  );
  URL.createObjectURL = vi.fn(() => "blob:codigo");
  URL.revokeObjectURL = vi.fn();
  cliques = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    cliques.push({ href: this.href, download: this.download });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CodigoDeConduta", () => {
  it("mostra a versão mais nova com a vigência e o autor, e as anteriores", async () => {
    render(<CodigoDeConduta />);

    expect(await screen.findByText(/Versão 2, vigente desde 01\/12\/2026, por Coordenadora de Teste/)).toBeTruthy();
    expect(screen.getByText(/Versão 1, vigente desde 20\/11\/2026, por Coordenadora de Teste/)).toBeTruthy();
  });

  it("baixa o PDF de uma versão anterior", async () => {
    render(<CodigoDeConduta />);

    const botoes = await screen.findAllByRole("button", { name: /Baixar o PDF/ });
    fireEvent.click(botoes[1]);

    await waitFor(() => expect(cliques).toEqual([{ href: "blob:codigo", download: "codigo-1.pdf" }]));
    expect(chamadas.map((c) => c.url)).toContain(`${ROTA}/arquivo?versao=1`);
  });

  it("publicar manda o PDF e a vigência e recarrega a lista", async () => {
    render(<CodigoDeConduta />);
    await screen.findByText(/Versão 2, vigente desde/);

    const pdf = new File(["%PDF-1.7"], "codigo-2027.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF do Código de Conduta"), { target: { files: [pdf] } });
    fireEvent.change(screen.getByLabelText("Vale a partir de"), { target: { value: "2027-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Publicar nova versão" }));

    await waitFor(() => expect(chamadas.filter((c) => c.url === ROTA && c.init?.method === "GET")).toHaveLength(2));
    const envio = chamadas.find((c) => c.init?.method === "POST");
    const corpo = envio?.init?.body as FormData;
    expect((corpo.get("arquivo") as File).name).toBe("codigo-2027.pdf");
    expect(corpo.get("vigente_desde")).toBe("2027-01-01");
  });

  it("mostra a recusa da publicação com a frase da API", async () => {
    render(<CodigoDeConduta />);
    await screen.findByText(/Versão 2, vigente desde/);
    vi.mocked(fetch).mockImplementationOnce(
      async () => new Response(JSON.stringify({ detail: "A vigência não pode ser antes de hoje." }), { status: 422 }),
    );

    const pdf = new File(["%PDF-1.7"], "codigo.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF do Código de Conduta"), { target: { files: [pdf] } });
    fireEvent.click(screen.getByRole("button", { name: "Publicar nova versão" }));

    expect(await screen.findByText("A vigência não pode ser antes de hoje.")).toBeTruthy();
  });

  it("sem versão publicada, diz que ainda não foi publicado", async () => {
    versoes = [];
    render(<CodigoDeConduta />);

    expect(await screen.findByText("Ainda não publicado.")).toBeTruthy();
  });

  it("quem não é da coordenação não vê o bloco", async () => {
    statusDaLista = 403;
    const { container } = render(<CodigoDeConduta />);

    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(container.textContent).toBe("");
  });
});
