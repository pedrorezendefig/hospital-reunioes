/**
 * @vitest-environment jsdom
 */

/**
 * Os prints no card aberto (issue #1061, PRD #1056, ADR 0069).
 *
 * O que se prova é o que o diretor vê: a miniatura e o "abrir em tamanho real"
 * apontam para a URL ASSINADA que o servidor mandou (e não para um endereço
 * montado na tela), e o anexo apagado continua aparecendo com nome, quem,
 * quando e "apagado", sem imagem nem link para o vazio.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnexosDaDemanda } from "./AnexosDaDemanda";
import { AnexoDaDemanda } from "./anexos";
import { momentoLegivel } from "./demandas";

const URL_ASSINADA = "https://storage.local/anexos-tecnologia/demanda-d1/abc.png?token=assinado&exp=600";

const GUARDADO: AnexoDaDemanda = {
  id: "a1",
  nome: "tela de login.png",
  anexado_por_nome: "Diretor do Hospital",
  criado_em: "2026-10-07T13:00:00Z",
  apagado_em: null,
  url: URL_ASSINADA,
};

const APAGADO: AnexoDaDemanda = {
  id: "a2",
  nome: "erro antigo.jpg",
  anexado_por_nome: "Diretor do Hospital",
  criado_em: "2026-10-01T09:30:00Z",
  apagado_em: "2026-10-05T18:00:00Z",
  url: null,
};

let pedidos: { url: string; auth: string | undefined }[] = [];

function montar(resposta: { anexos?: AnexoDaDemanda[]; status?: number; redeFora?: boolean } = {}) {
  pedidos = [];
  if (resposta.redeFora || resposta.status) vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      pedidos.push({ url, auth: (init?.headers as Record<string, string> | undefined)?.Authorization });
      if (resposta.redeFora) throw new TypeError("Failed to fetch");
      return {
        ok: !resposta.status,
        status: resposta.status ?? 200,
        json: async () => resposta.anexos ?? [],
      } as unknown as Response;
    }),
  );
  return render(<AnexosDaDemanda demandaId="d1" token="tok" />);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Os prints no card", () => {
  it("pede a lista da Demanda aberta", async () => {
    montar({ anexos: [GUARDADO] });

    await screen.findByAltText("tela de login.png");
    expect(pedidos).toEqual([{ url: "/api/admin/tecnologia/demandas/d1/anexos", auth: "Bearer tok" }]);
  });

  it("a miniatura e o tamanho real usam a URL assinada que o servidor mandou", async () => {
    montar({ anexos: [GUARDADO] });

    const miniatura = (await screen.findByAltText("tela de login.png")) as HTMLImageElement;
    expect(miniatura.getAttribute("src")).toBe(URL_ASSINADA);

    const abrir = screen.getByRole("link", { name: "Abrir tela de login.png em tamanho real" });
    expect(abrir.getAttribute("href")).toBe(URL_ASSINADA);
    expect(abrir.getAttribute("target")).toBe("_blank");
    expect(abrir.getAttribute("rel")).toContain("noopener");
  });

  it("diz quem anexou e quando", async () => {
    montar({ anexos: [GUARDADO] });

    const item = (await screen.findByAltText("tela de login.png")).closest("li")!;
    expect(item.textContent).toContain("Diretor do Hospital");
    expect(item.textContent).toContain(momentoLegivel(GUARDADO.criado_em));
  });

  it("o apagado mostra nome, quem, quando e apagado, sem imagem nem link", async () => {
    montar({ anexos: [APAGADO] });

    const nome = await screen.findByText("erro antigo.jpg");
    const item = nome.closest("li")!;
    expect(item.textContent).toContain("Diretor do Hospital");
    expect(item.textContent).toContain(momentoLegivel(APAGADO.criado_em));
    expect(item.textContent).toContain("apagado");
    expect(item.querySelector("img")).toBeNull();
    expect(item.querySelector("a")).toBeNull();
  });

  it("o guardado não se diz apagado", async () => {
    // O par de presença do teste acima: um "apagado" cravado em todo item
    // passaria nele.
    montar({ anexos: [GUARDADO] });

    const item = (await screen.findByAltText("tela de login.png")).closest("li")!;
    expect(item.textContent).not.toContain("apagado");
  });

  it("sem anexo, o card não ganha a seção", async () => {
    const { container } = montar({ anexos: [] });

    await waitFor(() => expect(pedidos).toHaveLength(1));
    expect(container.textContent).toBe("");
  });

  it("a falha ao carregar aparece, e não some calada", async () => {
    montar({ status: 503 });

    expect(await screen.findByText(/Não foi possível carregar as imagens/)).toBeTruthy();
  });
});
