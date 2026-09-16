/**
 * @vitest-environment jsdom
 */

/**
 * O formulário de Nova Demanda, agora fora do Quadro (issue #727).
 *
 * Os testes vieram INTEIROS do `QuadroDemandas.test.tsx`, onde cobriam o mesmo
 * formulário dentro do painel: mesmas asserções, mesmo corpo do POST, mesma
 * recusa chegando como `role="alert"`. O que mudou foi de onde o componente é
 * montado, e é exatamente isso que eles precisam continuar provando.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FormularioNovaDemanda } from "./FormularioNovaDemanda";
import { Demanda, ProdutoDaEscolha } from "./demandas";

type Chamada = { url: string; metodo: string; corpo: unknown };

const PRODUTOS: ProdutoDaEscolha[] = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
  { id: "prod-3", nome: "Site antigo", ativo: false },
];

const CRIADA = { id: "d-nova", titulo: "Encerrar conversas" } as unknown as Demanda;

let chamadas: Chamada[] = [];
let criadas: { demanda: Demanda; aviso: string | null }[] = [];

function montar(opcoes: { recusa?: { status: number; detail: string }; avisoPorEmail?: string } = {}) {
  chamadas = [];
  criadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({
        url,
        metodo: init?.method ?? "GET",
        corpo: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (opcoes.recusa) {
        return {
          ok: false,
          status: opcoes.recusa.status,
          json: async () => ({ detail: opcoes.recusa!.detail }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 201,
        json: async () => ({ ...CRIADA, aviso_por_email: opcoes.avisoPorEmail ?? null }),
      } as unknown as Response;
    }),
  );
  render(
    <FormularioNovaDemanda
      token="tok"
      produtos={PRODUTOS}
      onCriada={(demanda, aviso) => criadas.push({ demanda, aviso })}
    />,
  );
}

function escritas(): Chamada[] {
  return chamadas.filter((c) => c.metodo !== "GET");
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function preencher() {
  fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Encerrar conversas" } });
  fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
  fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
}

describe("Abrir uma Demanda", () => {
  it("manda título, tipo, Produto e prioridade Normal por padrão", async () => {
    montar();
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(escritas()[0]).toEqual({
      url: "/api/admin/tecnologia/demandas",
      metodo: "POST",
      // Sem estado nem responsável: quem decide os dois é o backend, pelo
      // Produto (a Demanda nasce em Nova, com o dono).
      corpo: {
        titulo: "Encerrar conversas",
        tipo: "decisao",
        produto_id: "prod-1",
        prioridade: "normal",
        descricao: "",
      },
    });
  });

  it("o campo Título não deixa passar de 200 caracteres", () => {
    // O backend recusa com frase de gente, mas quem cola um texto longo tem
    // que ser barrado antes de clicar: é o limite do campo que evita a viagem.
    montar();

    expect((screen.getByLabelText("Título") as HTMLInputElement).maxLength).toBe(200);
  });

  it("só oferece Produto ativo", () => {
    montar();
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Ana", "POPs"]);
  });

  it("o botão só libera com título e Produto", () => {
    montar();
    const botao = screen.getByRole("button", { name: "Abrir Demanda" }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Só o título" } });
    expect(botao.disabled).toBe(true);

    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
    expect(botao.disabled).toBe(false);
  });

  it("a recusa do servidor chega ao Super admin", async () => {
    const motivo = "Produto sem dono nao recebe Demanda nova: ela nasceria sem responsavel.";
    montar({ recusa: { status: 422, detail: motivo } });
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Produto sem dono");
    expect(criadas).toHaveLength(0);
  });

  it("sem recusa, nenhum aviso aparece", async () => {
    // O par de presença do teste acima: um `role="alert"` cravado na tela
    // passaria naquele sozinho.
    montar();
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(escritas()).toHaveLength(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("entrega a Demanda criada a quem hospeda o formulário", async () => {
    montar();
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].demanda.id).toBe("d-nova");
    expect(criadas[0].aviso).toBeNull();
  });

  it("o aviso de e-mail que não saiu viaja junto com a Demanda", async () => {
    montar({ avisoPorEmail: "A Demanda foi criada, mas o e-mail de atribuicao nao saiu." });
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].aviso).toContain("nao saiu");
  });
});
