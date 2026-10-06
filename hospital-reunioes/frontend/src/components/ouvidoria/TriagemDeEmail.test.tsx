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

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  // O item aberto não traz a contagem da lista: traz os anexos em si.
  const cabecalho: Record<string, unknown> = { ...resumo };
  delete cabecalho.quantidade_de_anexos;
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

  it("anexo recusado pelo teto mostra o motivo no lugar do link", async () => {
    montar({
      e1: item(JOANA, {
        anexos: [
          {
            id: "a3",
            filename: "gravacao.wav",
            content_type: "audio/wav",
            tamanho_bytes: 31457280,
            disponivel: false,
            motivo_indisponivel: "acima de 20 MB, o original está na caixa ouvidoria@",
          },
        ],
      }),
    });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    expect(await within(painel).findByText("gravacao.wav")).toBeTruthy();
    expect(within(painel).getByText("acima de 20 MB, o original está na caixa ouvidoria@")).toBeTruthy();
    expect(within(painel).queryByText("não veio do provedor")).toBeNull();
    expect(within(painel).queryByRole("button", { name: /gravacao\.wav/ })).toBeNull();
  });

  it("os anexos além do teto de quantidade aparecem como um aviso, sem virar anexo", async () => {
    const motivo = "passa de 20 anexos por e-mail, o original está na caixa ouvidoria@";
    montar({ e1: item(JOANA, { anexos_excedentes: 980, motivo_dos_excedentes: motivo }) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    expect(await within(painel).findByText(`Mais 980 anexos: ${motivo}`)).toBeTruthy();
    // O único anexo da lista continua sendo o laudo, com o link dele.
    expect(within(painel).getAllByRole("listitem")).toHaveLength(1);
    expect(within(painel).getByRole("button", { name: /laudo\.pdf/ })).toBeTruthy();
  });

  it("sem excedente, não há aviso", async () => {
    montar({ e1: item(JOANA, { anexos_excedentes: 0, motivo_dos_excedentes: null }) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = await screen.findByRole("region", { name: "E-mail recebido" });
    await within(painel).findByText("Esperei três horas na recepção sem informação nenhuma.");
    expect(within(painel).queryByText(/^Mais /)).toBeNull();
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

// ─── Virar manifestação (issue #650) ─────────────────────────────────────────

const PRE_CARGA = {
  email_recebido_id: "e1",
  canal: "email",
  contato_em: "2026-09-10T14:02:10.000Z",
  manifestante_nome: "Joana da Silva",
  manifestante_contato: "joana.silva@gmail.com",
  resumo: "",
  relato_integral: "Esperei três horas na recepção sem informação nenhuma.",
  anexos: [
    { id: "a1", filename: "laudo.pdf", content_type: "application/pdf", tamanho_bytes: 2048, disponivel: true },
  ],
};

let registros: Record<string, unknown>[] = [];

/** A tela com o backend dublado para o gesto inteiro: lista, item, pré-carga,
 *  setores e o registro manual. */
function montarParaVirar(itens: Record<string, unknown>, statusDoRegistro = 201) {
  chamadas = [];
  registros = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(url);
      if (url === "/api/ouvidoria/triagem-email") return respostaJson({ emails: [JOANA] });
      if (url === "/api/ouvidoria/triagem-email/e1/pre-carga") return respostaJson(PRE_CARGA);
      if (url === "/api/participantes/setores") return respostaJson(["Recepção", "Faturamento"]);
      if (url === "/api/ouvidoria/manifestacoes" && init?.method === "POST") {
        registros.push(JSON.parse(String(init.body)));
        return statusDoRegistro === 201
          ? respostaJson({ id: "caso-7", protocolo: "2026-0007" }, 201)
          : respostaJson({ detail: "Este e-mail já foi decidido na triagem" }, statusDoRegistro);
      }
      const id = url.replace("/api/ouvidoria/triagem-email/", "");
      return itens[id] ? respostaJson(itens[id]) : respostaJson({ detail: "E-mail não encontrado" }, 404);
    })
  );
  return render(<TriagemDeEmail token="token-de-teste" />);
}

async function abrirOModal() {
  fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
  fireEvent.click(await screen.findByRole("button", { name: /virar manifestação/i }));
  const modal = await screen.findByRole("dialog");
  // O formulário é preenchido no efeito de abertura do modal.
  await within(modal).findByDisplayValue("Esperei três horas na recepção sem informação nenhuma.");
  return modal;
}

function completarEsalvar(modal: HTMLElement) {
  fireEvent.change(within(modal).getByLabelText("Tipo da manifestação"), { target: { value: "reclamacao" } });
  fireEvent.change(within(modal).getByLabelText("Setor"), { target: { value: "Recepção" } });
  fireEvent.change(within(modal).getByLabelText("Resumo"), { target: { value: "Espera longa na recepção." } });
  fireEvent.click(within(modal).getByRole("button", { name: /registrar manifestação/i }));
}

describe("virar manifestação (issue #650)", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("o modal Nova manifestação abre com os campos do e-mail preenchidos", async () => {
    montarParaVirar({ e1: item(JOANA) });

    const modal = await abrirOModal();

    expect(within(modal).getByText("Nova manifestação")).toBeTruthy();
    expect((within(modal).getByLabelText("Canal de origem") as HTMLSelectElement).value).toBe("email");
    // A chegada do e-mail em hora de Brasília, e não a hora do clique.
    // O campo guarda os segundos (o jsdom ainda normaliza com milissegundos).
    expect((within(modal).getByLabelText("Data e hora do contato") as HTMLInputElement).value).toMatch(
      /^2026-09-10T11:02:10/
    );
    expect((within(modal).getByLabelText("Quem manifestou") as HTMLInputElement).value).toBe("Joana da Silva");
    expect((within(modal).getByLabelText("Contato") as HTMLInputElement).value).toBe("joana.silva@gmail.com");
    expect((within(modal).getByLabelText("Relato integral") as HTMLTextAreaElement).value).toBe(
      "Esperei três horas na recepção sem informação nenhuma."
    );
    expect((within(modal).getByLabelText("Resumo") as HTMLInputElement).value).toBe("");
    // Os anexos do e-mail vão com o caso, sem o ouvidor subir de novo.
    expect(within(modal).getByText("laudo.pdf")).toBeTruthy();
  });

  it("nenhum campo é trava: o que vale é o que o ouvidor salvou", async () => {
    montarParaVirar({ e1: item(JOANA) });
    const modal = await abrirOModal();

    fireEvent.change(within(modal).getByLabelText("Contato"), { target: { value: "joana.pereira@exemplo.com" } });
    fireEvent.change(within(modal).getByLabelText("Canal de origem"), { target: { value: "telefone" } });
    completarEsalvar(modal);

    await screen.findByText("Protocolo gerado");
    const [registro] = registros;
    expect(registro.email_recebido_id).toBe("e1");
    expect(registro.manifestante_contato).toBe("joana.pereira@exemplo.com");
    expect(registro.canal).toBe("telefone");
    expect(registro.contato_em).toBe("2026-09-10T11:02:10");
  });

  it("ao salvar, o item sai dos pendentes e o painel mostra o protocolo com link para o Dossiê", async () => {
    montarParaVirar({ e1: item(JOANA) });
    const modal = await abrirOModal();

    completarEsalvar(modal);
    expect(await within(modal).findByText("2026-0007")).toBeTruthy();
    // O botão do rodapé (o X do cabeçalho também se chama Fechar).
    fireEvent.click(within(modal).getByText("Fechar"));

    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    const link = within(painel).getByRole("link", { name: /2026-0007/ });
    expect(link.getAttribute("href")).toBe("/ouvidoria/m/2026-0007");
    expect(within(painel).queryByRole("button", { name: /virar manifestação/i })).toBeNull();
    // O item sai dos pendentes e vai para os decididos, com a marca.
    const lista = screen.getByRole("region", { name: "E-mails recebidos" });
    expect(within(lista).queryByText("Demora na recepção do ambulatório")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Decididos" }));
    const linha = within(lista).getByText("Demora na recepção do ambulatório").closest("button") as HTMLElement;
    expect(within(linha).getByText("Virou manifestação")).toBeTruthy();
  });

  it("e-mail que já virou caso não oferece virar de novo", async () => {
    montarParaVirar({ e1: item({ ...JOANA, estado: "virou_manifestacao" }) });

    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
    await screen.findByText("Esperei três horas na recepção sem informação nenhuma.");

    expect(screen.queryByRole("button", { name: /virar manifestação/i })).toBeNull();
  });

  it("e-mail decidido em outra aba recebe a recusa, e não um caso a mais", async () => {
    montarParaVirar({ e1: item(JOANA) }, 409);
    const modal = await abrirOModal();

    completarEsalvar(modal);

    expect(await within(modal).findByText(/já foi decidido na triagem/i)).toBeTruthy();
    expect(within(modal).queryByText("Protocolo gerado")).toBeNull();
  });
});

// ─── Descartar (issue #649) ──────────────────────────────────────────────────

const SPAM = {
  id: "e3",
  remetente_endereco: "promo@lojaqualquer.com",
  remetente_nome: "Loja Qualquer",
  assunto: "Ofertas da semana",
  recebido_em: "2026-09-09T12:00:00.000Z",
  estado: "descartado",
  incompleto: false,
  interno: false,
  quantidade_de_anexos: 0,
  decidido_em: "2026-09-09T13:10:00.000Z",
  decidido_por_nome: "Marta Ouvidora",
};

/** O item como a API devolve depois do descarte: só o cabeçalho. */
function descartado(resumo: typeof JOANA) {
  return item(
    { ...resumo, estado: "descartado" },
    {
      corpo_texto: null,
      anexos: [],
      cabecalhos: {},
      destinatarios: [],
      decidido_em: "2026-09-10T15:00:00.000Z",
      decidido_por_nome: "Marta Ouvidora",
    }
  );
}

let descartes: string[] = [];

function montarParaDescartar(itens: Record<string, unknown>, statusDoDescarte = 200) {
  chamadas = [];
  descartes = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(url);
      if (url === "/api/ouvidoria/triagem-email") return respostaJson({ emails: [JOANA, SPAM] });
      const descarte = url.match(/^\/api\/ouvidoria\/triagem-email\/([^/]+)\/descarte$/);
      if (descarte && init?.method === "POST") {
        descartes.push(descarte[1]);
        return statusDoDescarte === 200
          ? respostaJson(descartado(JOANA))
          : respostaJson({ detail: "Este e-mail já virou manifestação" }, statusDoDescarte);
      }
      const id = url.replace("/api/ouvidoria/triagem-email/", "");
      return itens[id] ? respostaJson(itens[id]) : respostaJson({ detail: "E-mail não encontrado" }, 404);
    })
  );
  return render(<TriagemDeEmail token="token-de-teste" />);
}

async function pedirDescarte() {
  fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
  await screen.findByText("Esperei três horas na recepção sem informação nenhuma.");
  fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
  return screen.findByRole("dialog");
}

describe("descartar (issue #649)", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("a lista abre nos pendentes, e o filtro Decididos mostra o descartado só com o cabeçalho", async () => {
    montarParaDescartar({});

    const lista = await screen.findByRole("region", { name: "E-mails recebidos" });
    await within(lista).findByText("Demora na recepção do ambulatório");
    expect(within(lista).queryByText("Ofertas da semana")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Decididos" }));

    const linha = within(lista).getByText("Ofertas da semana").closest("button") as HTMLElement;
    expect(within(linha).getByText("Descartado")).toBeTruthy();
    expect(within(lista).queryByText("Demora na recepção do ambulatório")).toBeNull();
  });

  it("o botão Descartar pede confirmação do app, e não do navegador", async () => {
    const confirmDoNavegador = vi.spyOn(window, "confirm");
    montarParaDescartar({ e1: item(JOANA) });

    const dialogo = await pedirDescarte();

    expect(within(dialogo).getByText(/descartar este e-mail/i)).toBeTruthy();
    expect(confirmDoNavegador).not.toHaveBeenCalled();
    expect(descartes).toEqual([]);
  });

  it("cancelar a confirmação não descarta nada", async () => {
    montarParaDescartar({ e1: item(JOANA) });
    const dialogo = await pedirDescarte();

    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    expect(descartes).toEqual([]);
    expect(screen.getByText("Esperei três horas na recepção sem informação nenhuma.")).toBeTruthy();
  });

  it("confirmado, o item sai dos pendentes e o painel fica só com o cabeçalho e quem descartou", async () => {
    montarParaDescartar({ e1: item(JOANA) });
    const dialogo = await pedirDescarte();

    fireEvent.click(within(dialogo).getByRole("button", { name: "Descartar" }));

    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    expect(await within(painel).findByText(/Descartado por Marta Ouvidora/)).toBeTruthy();
    expect(descartes).toEqual(["e1"]);
    expect(within(painel).queryByText("Esperei três horas na recepção sem informação nenhuma.")).toBeNull();
    expect(within(painel).queryByText("O corpo deste e-mail não veio do provedor.")).toBeNull();
    expect(within(painel).queryByRole("button", { name: "Descartar" })).toBeNull();
    expect(within(painel).queryByRole("button", { name: /virar manifestação/i })).toBeNull();
    const lista = screen.getByRole("region", { name: "E-mails recebidos" });
    expect(within(lista).queryByText("Demora na recepção do ambulatório")).toBeNull();
  });

  it("descarte recusado pelo servidor mostra o motivo e não muda o item", async () => {
    montarParaDescartar({ e1: item(JOANA) }, 409);
    const dialogo = await pedirDescarte();

    fireEvent.click(within(dialogo).getByRole("button", { name: "Descartar" }));

    expect(await screen.findByText(/não pode ser descartado/i)).toBeTruthy();
    expect(screen.getByText("Esperei três horas na recepção sem informação nenhuma.")).toBeTruthy();
  });
});

describe("descarte que não terminou (issue #649)", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("o descartado que ainda tem anexo oferece terminar o descarte", async () => {
    const comSobra = {
      ...descartado(JOANA),
      anexos: [
        { id: "a1", filename: "laudo.pdf", content_type: "application/pdf", tamanho_bytes: 2048, disponivel: true },
      ],
    };
    // Descartado numa visita anterior, com um anexo que o storage não soltou.
    montarParaDescartar({ e1: comSobra });
    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    await within(painel).findByText(/Descartado por Marta Ouvidora/);
    expect(within(painel).getByRole("button", { name: "Terminar o descarte" })).toBeTruthy();
    expect(within(painel).queryByText(/foram apagados/)).toBeNull();
  });

  it("o descartado limpo não oferece descartar de novo", async () => {
    montarParaDescartar({ e1: descartado(JOANA) });
    fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));

    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    await within(painel).findByText(/Descartado por Marta Ouvidora/);
    expect(within(painel).queryByRole("button", { name: /descart/i })).toBeNull();
  });
});

// ─── Juntar a um caso (issue #651) ───────────────────────────────────────────

const CASO_12 = { id: "caso-12", protocolo: "2026-0012", status: "aguardando_area", setor: "Recepção" };
const CASO_30 = { id: "caso-30", protocolo: "2026-0030", status: "encerrado", setor: "Faturamento" };

let juntadas: Record<string, unknown>[] = [];

/** A tela com o backend dublado para a juntada: a sugestão (que pode vir
 *  vazia), o resumo do protocolo digitado e a juntada em si. */
function montarParaJuntar(sugestao: typeof CASO_12 | null, statusDaJuntada = 200, detalhe = "") {
  chamadas = [];
  juntadas = [];
  const casos: Record<string, typeof CASO_12> = { "2026-0012": CASO_12, "2026-0030": CASO_30 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(url);
      if (url === "/api/ouvidoria/triagem-email") return respostaJson({ emails: [JOANA] });
      if (url === "/api/ouvidoria/triagem-email/e1/caso-para-juntar") return respostaJson({ caso: sugestao });
      const digitado = url.match(/caso-para-juntar\?protocolo=(.+)$/);
      if (digitado) return respostaJson({ caso: casos[decodeURIComponent(digitado[1])] ?? null });
      if (url === "/api/ouvidoria/triagem-email/e1/juntada" && init?.method === "POST") {
        juntadas.push(JSON.parse(String(init.body)));
        return statusDaJuntada === 200
          ? respostaJson(item({ ...JOANA, estado: "juntado" }, { anexos: [] }))
          : respostaJson({ detail: detalhe }, statusDaJuntada);
      }
      if (url === "/api/ouvidoria/triagem-email/e1") return respostaJson(item(JOANA));
      return respostaJson({ detail: "não encontrado" }, 404);
    })
  );
  return render(<TriagemDeEmail token="token-de-teste" />);
}

async function abrirJuntar() {
  fireEvent.click(await linhaDe("Demora na recepção do ambulatório"));
  await screen.findByText("Esperei três horas na recepção sem informação nenhuma.");
  fireEvent.click(screen.getByRole("button", { name: "Juntar a um caso" }));
  return screen.findByRole("dialog");
}

describe("juntar a um caso (issue #651)", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("o campo de protocolo vem com a sugestão e a confirmação mostra o resumo do caso", async () => {
    montarParaJuntar(CASO_12);

    const modal = await abrirJuntar();

    const campo = (await within(modal).findByDisplayValue("2026-0012")) as HTMLInputElement;
    expect(campo).toBeTruthy();
    const resumo = within(modal).getByRole("region", { name: "Caso escolhido" });
    expect(within(resumo).getByText("2026-0012")).toBeTruthy();
    expect(within(resumo).getByText("Aguardando área")).toBeTruthy();
    expect(within(resumo).getByText("Recepção")).toBeTruthy();
    expect(within(modal).getByText(/sugerido pelo assunto/i)).toBeTruthy();
  });

  it("sem sugestão o campo vem vazio, e o protocolo digitado mostra o resumo antes de juntar", async () => {
    montarParaJuntar(null);
    const modal = await abrirJuntar();
    const campo = within(modal).getByLabelText("Protocolo do caso") as HTMLInputElement;
    expect(campo.value).toBe("");
    expect(within(modal).getByRole("button", { name: "Juntar ao caso" })).toHaveProperty("disabled", true);

    fireEvent.change(campo, { target: { value: "2026-0030" } });
    fireEvent.click(within(modal).getByRole("button", { name: "Conferir" }));

    const resumo = await within(modal).findByRole("region", { name: "Caso escolhido" });
    expect(within(resumo).getByText("Encerrada")).toBeTruthy();
    expect(within(resumo).getByText("Faturamento")).toBeTruthy();
    fireEvent.click(within(modal).getByRole("button", { name: "Juntar ao caso" }));

    await waitFor(() => expect(juntadas).toEqual([{ manifestacao_id: "caso-30" }]));
  });

  it("protocolo que não é de caso nenhum avisa e não deixa juntar", async () => {
    montarParaJuntar(null);
    const modal = await abrirJuntar();

    fireEvent.change(within(modal).getByLabelText("Protocolo do caso"), { target: { value: "2026-0999" } });
    fireEvent.click(within(modal).getByRole("button", { name: "Conferir" }));

    expect(await within(modal).findByText(/nenhum caso com este protocolo/i)).toBeTruthy();
    expect(within(modal).getByRole("button", { name: "Juntar ao caso" })).toHaveProperty("disabled", true);
  });

  it("trocar o protocolo depois de conferir exige conferir de novo", async () => {
    montarParaJuntar(CASO_12);
    const modal = await abrirJuntar();
    await within(modal).findByRole("region", { name: "Caso escolhido" });

    fireEvent.change(within(modal).getByLabelText("Protocolo do caso"), { target: { value: "2026-0030" } });

    expect(within(modal).queryByRole("region", { name: "Caso escolhido" })).toBeNull();
    expect(within(modal).getByRole("button", { name: "Juntar ao caso" })).toHaveProperty("disabled", true);
  });

  it("juntado, o item sai dos pendentes e o painel mostra o caso com link para o Dossiê", async () => {
    montarParaJuntar(CASO_12);
    const modal = await abrirJuntar();
    await within(modal).findByRole("region", { name: "Caso escolhido" });

    fireEvent.click(within(modal).getByRole("button", { name: "Juntar ao caso" }));

    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    const link = await within(painel).findByRole("link", { name: /2026-0012/ });
    expect(link.getAttribute("href")).toBe("/ouvidoria/m/2026-0012");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(painel).queryByRole("button", { name: "Juntar a um caso" })).toBeNull();
    const lista = screen.getByRole("region", { name: "E-mails recebidos" });
    expect(within(lista).queryByText("Demora na recepção do ambulatório")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Decididos" }));
    const linha = within(lista).getByText("Demora na recepção do ambulatório").closest("button") as HTMLElement;
    expect(within(linha).getByText("Juntado a um caso")).toBeTruthy();
  });

  it("caso apagado recusado pelo servidor mostra o motivo e o e-mail continua pendente", async () => {
    montarParaJuntar(CASO_12, 409, "Este caso foi apagado e não pode mais ser completado com um e-mail.");
    const modal = await abrirJuntar();
    await within(modal).findByRole("region", { name: "Caso escolhido" });

    fireEvent.click(within(modal).getByRole("button", { name: "Juntar ao caso" }));

    expect(await within(modal).findByText(/foi apagado e não pode mais ser completado/)).toBeTruthy();
    const painel = screen.getByRole("region", { name: "E-mail recebido" });
    expect(within(painel).getByRole("button", { name: "Juntar a um caso" })).toBeTruthy();
  });
});
