/**
 * @vitest-environment jsdom
 */

/**
 * A resposta da Conversa com imagem (issue #1062, PRD #1056, ADR 0069).
 *
 * A imagem sobe ANTES, pela mesma porta do formulário (`POST /anexos`), com os
 * mesmos limites e as mesmas frases; a resposta vai em seguida com o id do
 * anexo, que é o que a liga à linha. No fio, a imagem aparece junto da resposta
 * pela URL ASSINADA que o servidor mandou.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IMAGEM_FORA_DA_LISTA } from "./assistente";
import { ConversaDaDemanda } from "./ConversaDaDemanda";
import { LinhaDaConversa } from "./demandas";

const URL_ASSINADA = "https://storage.local/anexos-tecnologia/demanda-d1/abc.png?token=assinado&exp=600";

type Chamada = { url: string; metodo: string; corpo: unknown; arquivo?: string; campo?: string };

let chamadas: Chamada[] = [];
let erros: (string | null)[] = [];

function linha(extra: Partial<LinhaDaConversa> = {}): LinhaDaConversa {
  return {
    id: "c1",
    autor_id: "P1",
    autor_nome: "Pedro Vitta",
    linha: "resposta",
    texto: "Segue o print do erro",
    mencoes: [],
    movimento_campo: null,
    criado_em: "2026-10-07T12:00:00Z",
    editado_em: null,
    editavel_ate: null,
    ...extra,
  };
}

function montar(
  opcoes: { linhas?: LinhaDaConversa[]; recusaDoAnexo?: { status: number; detail: string } } = {},
) {
  chamadas = [];
  erros = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const enviado = init?.body;
      const forma = enviado instanceof FormData ? enviado : null;
      const arquivo = forma?.get("imagem");
      chamadas.push({
        url,
        metodo: init?.method ?? "GET",
        corpo: forma || !enviado ? undefined : JSON.parse(String(enviado)),
        arquivo: arquivo instanceof File ? arquivo.name : undefined,
        campo: arquivo instanceof File ? "imagem" : undefined,
      });
      if (url.endsWith("/anexos")) {
        if (opcoes.recusaDoAnexo) {
          return {
            ok: false,
            status: opcoes.recusaDoAnexo.status,
            json: async () => ({ detail: opcoes.recusaDoAnexo!.detail }),
          } as unknown as Response;
        }
        return {
          ok: true,
          status: 201,
          json: async () => ({ id: "anexo-9", nome: "tela.png", url: null }),
        } as unknown as Response;
      }
      return { ok: true, status: 201, json: async () => ({ id: "c-nova" }) } as unknown as Response;
    }),
  );
  return render(
    <ConversaDaDemanda
      demandaId="d1"
      linhas={opcoes.linhas ?? []}
      pessoas={[]}
      token="tok"
      publicada={false}
      onFioMudou={() => {}}
      onErro={(mensagem) => erros.push(mensagem)}
    />,
  );
}

function arquivo(nome: string, tamanho: number, tipo: string): File {
  const falso = new File(["x"], nome, { type: tipo });
  Object.defineProperty(falso, "size", { value: tamanho });
  return falso;
}

function escolherImagem(escolhido: File) {
  fireEvent.change(screen.getByLabelText("Imagem da resposta"), { target: { files: [escolhido] } });
}

function escrever(texto: string) {
  fireEvent.change(screen.getByLabelText("Resposta"), { target: { value: texto } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A resposta com imagem", () => {
  it("sobe a imagem pela porta do anexo e responde com o id dela", async () => {
    montar();
    escolherImagem(arquivo("tela.png", 1000, "image/png"));
    escrever("Segue o print do erro");

    fireEvent.click(screen.getByRole("button", { name: /Responder/ }));

    await waitFor(() => expect(chamadas).toHaveLength(2));
    expect(chamadas[0]).toMatchObject({
      url: "/api/admin/tecnologia/demandas/d1/anexos",
      metodo: "POST",
      arquivo: "tela.png",
      campo: "imagem",
    });
    expect(chamadas[1]).toEqual({
      url: "/api/admin/tecnologia/demandas/d1/conversa",
      metodo: "POST",
      corpo: { texto: "Segue o print do erro", mencoes: [], anexo_id: "anexo-9" },
      arquivo: undefined,
      campo: undefined,
    });
  });

  it("sem imagem escolhida a resposta vai sozinha, como antes", async () => {
    montar();
    escrever("Só texto");

    fireEvent.click(screen.getByRole("button", { name: /Responder/ }));

    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].corpo).toEqual({ texto: "Só texto", mencoes: [] });
  });

  it("imagem fora dos formatos é recusada na escolha, com a frase do Assistente, sem ir à rede", async () => {
    montar();

    escolherImagem(arquivo("animada.gif", 1000, "image/gif"));

    expect(erros.at(-1)).toBe(IMAGEM_FORA_DA_LISTA);
    expect(screen.queryByText("animada.gif")).toBeNull();
    expect(chamadas).toHaveLength(0);
  });

  it("a recusa do servidor chega a quem respondeu e a resposta não sai", async () => {
    montar({ recusaDoAnexo: { status: 422, detail: "Esta Demanda já tem 10 imagens, o máximo por Demanda." } });
    escolherImagem(arquivo("tela.png", 1000, "image/png"));
    escrever("Segue o print do erro");

    fireEvent.click(screen.getByRole("button", { name: /Responder/ }));

    await waitFor(() => expect(erros.at(-1)).toBe("Esta Demanda já tem 10 imagens, o máximo por Demanda."));
    expect(chamadas.filter((c) => c.url.endsWith("/conversa"))).toHaveLength(0);
    expect((screen.getByLabelText("Resposta") as HTMLTextAreaElement).value).toBe("Segue o print do erro");
  });

  it("a imagem escolhida aparece pelo nome e pode ser tirada antes de responder", async () => {
    montar();
    escolherImagem(arquivo("tela.png", 1000, "image/png"));
    expect(screen.getByText("tela.png")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Tirar a imagem" }));
    escrever("Mudei de ideia");
    fireEvent.click(screen.getByRole("button", { name: /Responder/ }));

    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe("/api/admin/tecnologia/demandas/d1/conversa");
  });
});

describe("A imagem no fio", () => {
  it("aparece junto da resposta, pela URL assinada que o servidor mandou", () => {
    montar({
      linhas: [
        linha({
          imagem: {
            id: "a1",
            nome: "tela.png",
            anexado_por_nome: "Pedro Vitta",
            criado_em: null,
            apagado_em: null,
            url: URL_ASSINADA,
          },
        }),
      ],
    });

    const miniatura = screen.getByAltText("tela.png") as HTMLImageElement;
    expect(miniatura.getAttribute("src")).toBe(URL_ASSINADA);
    expect(miniatura.closest("li")!.textContent).toContain("Segue o print do erro");
    expect(screen.getByRole("link", { name: "Abrir tela.png em tamanho real" }).getAttribute("href")).toBe(
      URL_ASSINADA,
    );
  });

  it("a imagem apagada com a Demanda encerrada fica dita, sem imagem nem link", () => {
    montar({
      linhas: [
        linha({
          imagem: {
            id: "a1",
            nome: "tela.png",
            anexado_por_nome: "Pedro Vitta",
            criado_em: null,
            apagado_em: "2026-10-08T12:00:00Z",
            url: null,
          },
        }),
      ],
    });

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("tela.png (apagada)")).toBeTruthy();
  });
});
