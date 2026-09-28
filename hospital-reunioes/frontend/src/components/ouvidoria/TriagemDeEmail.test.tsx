/**
 * @vitest-environment jsdom
 */

/**
 * A tela da Triagem de e-mail (issue #648, PRD #646, ADR 0051).
 *
 * Nesta fatia o ouvidor só lê: a lista (remetente, assunto, chegada, contagem
 * de anexos e as marcas) e o painel do item (corpo em texto e anexos para
 * baixar). O que mais importa aqui é o que a tela NÃO faz: o corpo de um
 * e-mail é texto escrito por qualquer pessoa da internet, e nada dele pode
 * virar marcação na página.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TriagemDeEmail } from "./TriagemDeEmail";

function respostaJson(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body } as Response;
}

const JOANA = {
  id: "e1",
  remetente_endereco: "joana.silva@gmail.com",
  remetente_nome: "Joana da Silva",
  assunto: "Demora na recepção do ambulatório",
  recebido_em: "2026-09-10T14:02:10.000Z",
  estado: "pendente",
  incompleto: false,
  interno: false,
  quantidade_de_anexos: 1,
};

const FATURAMENTO = {
  id: "e2",
  remetente_endereco: "faturamento@hospitalsaomatheus.com.br",
  remetente_nome: null,
  assunto: "Re: protocolo 2026-0012",
  recebido_em: "2026-09-10T15:30:00.000Z",
  estado: "pendente",
  incompleto: true,
  interno: true,
  quantidade_de_anexos: 2,
};

function item(resumo: typeof JOANA, extra: Record<string, unknown> = {}) {
  const { quantidade_de_anexos: _ignorada, ...cabecalho } = resumo;
  return {
    ...cabecalho,
    destinatarios: ["ouvidoria@inbound.hospitalsaomatheus.cloud"],
    corpo_texto: "Esperei três horas na recepção sem informação nenhuma.",
    cabecalhos: { "message-id": "<abc@mail>" },
    anexos: [
      { id: "a1", filename: "laudo.pdf", content_type: "application/pdf", tamanho_bytes: 2048, disponivel: true },
    ],
    ...extra,
  };
}

let chamadas: string[] = [];

function montar(itens: Record<string, unknown>, lista: unknown[] = [JOANA, FATURAMENTO], statusDaLista = 200) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      chamadas.push(url);
      if (url === "/api/ouvidoria/triagem-email") {
        return statusDaLista === 200
          ? respostaJson({ emails: lista })
          : respostaJson({ detail: "Acesso restrito à Ouvidoria" }, statusDaLista);
      }
      const anexo = url.match(/^\/api\/ouvidoria\/triagem-email\/([^/]+)\/anexos\/([^/]+)\/url$/);
      if (anexo) return respostaJson({ url: "https://storage.local/assinado?token=1", filename: "laudo.pdf" });
      const id = url.replace("/api/ouvidoria/triagem-email/", "");
      return itens[id] ? respostaJson(itens[id]) : respostaJson({ detail: "E-mail não encontrado" }, 404);
    })
  );
  return render(<TriagemDeEmail token="token-de-teste" />);
}

async function linhaDe(assunto: string) {
  const texto = await screen.findByText(assunto);
  return texto.closest("button") as HTMLElement;
}

describe("a lista da triagem", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra remetente, assunto, chegada e contagem de anexos de cada e-mail", async () => {
    montar({});

    const joana = await linhaDe("Demora na recepção do ambulatório");
    expect(within(joana).getByText("Joana da Silva")).toBeTruthy();
    expect(within(joana).getByText("10/09/2026 11:02")).toBeTruthy();
    expect(within(joana).getByText("1 anexo")).toBeTruthy();

    // Sem nome no e-mail, o endereço ocupa o lugar dele.
    const area = await linhaDe("Re: protocolo 2026-0012");
    expect(within(area).getByText("faturamento@hospitalsaomatheus.com.br")).toBeTruthy();
    expect(within(area).getByText("2 anexos")).toBeTruthy();
  });

  it("marca o remetente do hospital como interno e o item que não veio inteiro como incompleto", async () => {
    montar({});

    const area = await linhaDe("Re: protocolo 2026-0012");
    expect(within(area).getByText("Interno")).toBeTruthy();
    expect(within(area).getByText("Incompleto")).toBeTruthy();
    const joana = await linhaDe("Demora na recepção do ambulatório");
    expect(within(joana).queryByText("Interno")).toBeNull();
    expect(within(joana).queryByText("Incompleto")).toBeNull();
  });

  it("não oferece ação nenhuma sobre o e-mail nesta fatia", async () => {
    montar({ e1: item(JOANA) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
    await screen.findByText("Esperei três horas na recepção sem informação nenhuma.");

    for (const acao of [/descartar/i, /virar manifestação/i, /juntar/i]) {
      expect(screen.queryByRole("button", { name: acao })).toBeNull();
    }
  });

  it("lista vazia diz que não há e-mail, em vez de uma tela em branco", async () => {
    montar({}, []);

    expect(await screen.findByText("Nenhum e-mail recebido para triar.")).toBeTruthy();
  });

  it("perfil sem Ouvidoria vê a recusa, e não uma lista vazia", async () => {
    montar({}, [], 403);

    expect(await screen.findByText("A Triagem de e-mail é restrita à Ouvidoria.")).toBeTruthy();
    expect(screen.queryByText("Nenhum e-mail recebido para triar.")).toBeNull();
  });
});

describe("o painel do item", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("abre o e-mail com o corpo em texto e os anexos", async () => {
    montar({ e1: item(JOANA) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    expect(await within(painel).findByText("Esperei três horas na recepção sem informação nenhuma.")).toBeTruthy();
    expect(within(painel).getByText("joana.silva@gmail.com")).toBeTruthy();
    expect(within(painel).getByRole("button", { name: /laudo\.pdf/ })).toBeTruthy();
    expect(chamadas).toContain("/api/ouvidoria/triagem-email/e1");
  });

  it("um corpo com HTML malicioso aparece como texto e não executa nada", async () => {
    const malicioso =
      '<img src=x onerror="window.__xssTriagem=1"><script>window.__xssTriagem=2</script>' +
      '<a href="javascript:alert(1)">clique</a>';
    const { container } = montar({ e1: item(JOANA, { corpo_texto: malicioso }) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    // O texto chega inteiro, com os sinais de menor e maior à vista...
    expect(await within(painel).findByText(malicioso)).toBeTruthy();
    // ...e nenhum pedaço dele virou elemento na página.
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect((window as unknown as { __xssTriagem?: number }).__xssTriagem).toBeUndefined();
  });

  it("e-mail sem corpo em texto diz isso, sem inventar conteúdo", async () => {
    montar({ e1: item(JOANA, { corpo_texto: null, incompleto: true }) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    expect(await screen.findByText("O corpo deste e-mail não veio do provedor.")).toBeTruthy();
  });

  it("anexo que não veio aparece pelo nome, sem link para baixar", async () => {
    montar({
      e1: item(JOANA, {
        anexos: [
          { id: "a2", filename: "foto.jpg", content_type: "image/jpeg", tamanho_bytes: null, disponivel: false },
        ],
      }),
    });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    expect(await within(painel).findByText("foto.jpg")).toBeTruthy();
    expect(within(painel).getByText("não veio do provedor")).toBeTruthy();
    expect(within(painel).queryByRole("button", { name: /foto\.jpg/ })).toBeNull();
  });

  it("o anexo abre pela URL assinada que o servidor emite na hora", async () => {
    const aba = { opener: {}, location: { href: "" }, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(aba as unknown as Window);
    montar({ e1: item(JOANA) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
    fireEvent.click(await screen.findByRole("button", { name: /laudo\.pdf/ }));

    await vi.waitFor(() => expect(aba.location.href).toBe("https://storage.local/assinado?token=1"));
    expect(chamadas).toContain("/api/ouvidoria/triagem-email/e1/anexos/a1/url");
    // A aba nova não guarda referência de volta à tela da Ouvidoria.
    expect(aba.opener).toBeNull();
  });
});
