/**
 * @vitest-environment jsdom
 */

/**
 * O Assistente de Tecnologia na tela (issue #727, PRD #726, ADR 0056).
 *
 * O servidor é falso, mas as REGRAS ficam com ele: a tela não decide o Tipo
 * nem escreve o rascunho, ela mostra o que a rota devolveu e manda de volta o
 * que a pessoa editou. As asserções olham duas coisas: o que aparece na tela e
 * o corpo que o clique dispara.
 *
 * Armadilha de teste vazio evitada aqui: "o rascunho volta do armazenamento de
 * sessão" passaria numa tela que nunca grava nada e sempre mostra o mesmo
 * texto; por isso o teste grava um valor ESPECÍFICO e remonta o componente.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssistenteDeTecnologia } from "./AssistenteDeTecnologia";
import { AVISO_DE_IA, CHAVE_DA_SESSAO, NAO_INFORMADO, RASCUNHO_VAZIO, RascunhoDaDemanda } from "./assistente";
import { Demanda, ProdutoDaEscolha } from "./demandas";

type Chamada = { url: string; metodo: string; corpo: Record<string, unknown> | undefined };

const PRODUTOS: ProdutoDaEscolha[] = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
  { id: "prod-3", nome: "Site antigo", ativo: false },
];

const RASCUNHO_DO_ASSISTENTE: RascunhoDaDemanda = {
  titulo: "Ana não responde de madrugada",
  tipo: "defeito",
  produto_id: "prod-1",
  prioridade: "normal",
  prazo: null,
  descricao: "Onde: no WhatsApp",
};

let chamadas: Chamada[] = [];
let criadas: { demanda: Demanda; aviso: string | null }[] = [];

type Opcoes = {
  /** O rascunho que a rota do chat devolve. */
  rascunhoDaResposta?: RascunhoDaDemanda;
  reply?: string;
  recusaDoChat?: { status: number; detail: string };
};

function servidor(opcoes: Opcoes) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const corpo = init?.body ? JSON.parse(String(init.body)) : undefined;
    chamadas.push({ url, metodo: init?.method ?? "GET", corpo });
    if (url.endsWith("/assistente/chat")) {
      if (opcoes.recusaDoChat) {
        return {
          ok: false,
          status: opcoes.recusaDoChat.status,
          json: async () => ({ detail: opcoes.recusaDoChat!.detail }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          reply: opcoes.reply ?? "Entendi. Onde isso aconteceu?",
          rascunho: opcoes.rascunhoDaResposta ?? RASCUNHO_DO_ASSISTENTE,
          demanda_parecida: null,
        }),
      } as unknown as Response;
    }
    return {
      ok: true,
      status: 201,
      json: async () => ({ id: "d-nova", aviso_por_email: null }),
    } as unknown as Response;
  });
}

function montar(opcoes: Opcoes = {}) {
  vi.stubGlobal("fetch", servidor(opcoes));
  return render(
    <AssistenteDeTecnologia
      token="tok"
      produtos={PRODUTOS}
      onCriada={(demanda, aviso) => criadas.push({ demanda, aviso })}
    />,
  );
}

function doChat(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/assistente/chat"));
}

function criacoes(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/demandas"));
}

async function falar(texto: string) {
  fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: texto } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(doChat().length).toBeGreaterThan(0));
}

beforeEach(() => {
  chamadas = [];
  criadas = [];
  Element.prototype.scrollIntoView = vi.fn();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A conversa", () => {
  it("abre com a fala do assistente e com o aviso de que uma IA lê o que for escrito", () => {
    montar();

    expect(screen.getByText(AVISO_DE_IA)).toBeTruthy();
    expect(within(screen.getByRole("log")).getAllByText(/Me conta o que você precisa/)).toHaveLength(1);
  });

  it("a resposta do chat atualiza o rascunho", async () => {
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).value).toBe("Onde: no WhatsApp");
    expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy();
  });

  it("a edição à mão vai no corpo da chamada seguinte", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "título escrito à mão" } });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "é isso" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => expect(doChat()).toHaveLength(2));
    const rascunhoEnviado = doChat()[1].corpo?.rascunho as RascunhoDaDemanda;
    expect(rascunhoEnviado.titulo).toBe("título escrito à mão");
    // O resto do rascunho segue junto, senão a correção do título apagaria o
    // que o assistente já tinha montado.
    expect(rascunhoEnviado.tipo).toBe("defeito");
  });

  it("a conversa inteira vai no corpo, com os papéis certos", async () => {
    montar();

    await falar("a Ana tá estranha");

    const messages = doChat()[0].corpo?.messages as { role: string; content: string }[];
    expect(messages[messages.length - 1]).toEqual({ role: "user", content: "a Ana tá estranha" });
    expect(messages[0].role).toBe("assistant");
  });

  it("a recusa do servidor chega a quem está conversando", async () => {
    montar({ recusaDoChat: { status: 429, detail: "Muitas mensagens em pouco tempo. Espere um minuto." } });

    await falar("a Ana tá estranha");

    expect((await screen.findByRole("alert")).textContent).toContain("Muitas mensagens");
  });

  it("sem recusa, nenhum aviso vermelho aparece", async () => {
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Criar Demanda", () => {
  it("só libera com título e Produto", async () => {
    montar();
    const botao = () => screen.getByRole("button", { name: "Criar Demanda" }) as HTMLButtonElement;
    expect(botao().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Alguma coisa" } });
    expect(botao().disabled).toBe(true);

    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
    expect(botao().disabled).toBe(false);
  });

  it("chama a rota de criação com o payload de hoje", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criacoes()).toHaveLength(1));
    expect(criacoes()[0].url).toBe("/api/admin/tecnologia/demandas");
    expect(criacoes()[0].metodo).toBe("POST");
    expect(criacoes()[0].corpo).toEqual({
      titulo: "Ana não responde de madrugada",
      tipo: "defeito",
      produto_id: "prod-1",
      prioridade: "normal",
      // Os quatro rótulos do roteiro de Defeito que ficaram em branco saem
      // como "não informado"; "Onde" não, porque foi respondido.
      descricao: [
        "Onde: no WhatsApp",
        `O que aconteceu: ${NAO_INFORMADO}`,
        `O que esperava: ${NAO_INFORMADO}`,
        `Quando: ${NAO_INFORMADO}`,
        `Como repetir: ${NAO_INFORMADO}`,
      ].join("\n"),
      prazo: null,
    });
  });

  it("entrega a Demanda criada a quem hospeda a tela", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].demanda.id).toBe("d-nova");
  });

  it("criar limpa o armazenamento de sessão", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull());
  });
});

describe("O armazenamento de sessão", () => {
  it("o rascunho volta ao remontar a tela", async () => {
    const { unmount } = montar();
    await falar("a Ana tá estranha");
    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );

    unmount();
    cleanup();
    montar();

    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );
    expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy();
  });

  it("sem nada guardado, a tela nasce com o rascunho vazio", () => {
    // O par de ausência do teste acima: uma tela que sempre mostra o mesmo
    // título passaria naquele sozinha.
    montar();

    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe(RASCUNHO_VAZIO.titulo);
  });
});

describe("Descartar", () => {
  it("limpa conversa, rascunho e o que estava guardado", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: /Descartar/ }));

    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText("Entendi. Onde isso aconteceu?")).toBeNull();
    expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull();
  });
});

describe("O painel do rascunho", () => {
  it("é recolhível, e nasce aberto", () => {
    montar();
    const alavanca = screen.getByRole("button", { name: /Recolher/ });
    expect(alavanca.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(alavanca);

    expect(screen.getByRole("button", { name: /Abrir/ }).getAttribute("aria-expanded")).toBe("false");
  });

  it("só oferece Produto ativo", () => {
    montar();
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Ana", "POPs"]);
  });

  it("vem antes do chat no DOM, que é o que o põe no topo no celular", () => {
    // As duas colunas viram uma pilha abaixo de `lg`, e a pilha segue a ordem
    // do DOM: o rascunho primeiro, o chat embaixo (PRD #726, história 3).
    montar();

    const rascunho = screen.getByLabelText("Título");
    const chat = screen.getByLabelText("Mensagem");
    expect(rascunho.compareDocumentPosition(chat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
