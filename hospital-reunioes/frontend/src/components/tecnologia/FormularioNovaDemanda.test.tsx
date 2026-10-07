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

import { IMAGEM_FORA_DA_LISTA } from "./assistente";
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
let semConfirmacao = 0;

function montar(
  opcoes: {
    recusa?: { status: number; detail: string };
    avisoPorEmail?: string;
    /** 201 com um corpo que o `json()` não lê, ou que lê e não serve. */
    corpoDoCriar?: "ilegivel" | unknown;
    /** A recusa do servidor para uma imagem, pelo nome do arquivo. */
    recusaDaImagem?: Record<string, { status: number; detail: string }>;
  } = {},
) {
  chamadas = [];
  criadas = [];
  semConfirmacao = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const corpo =
        init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : undefined;
      chamadas.push({ url, metodo: init?.method ?? "GET", corpo });
      if (url.endsWith("/anexos")) {
        const arquivo = (corpo as FormData).get("imagem") as File;
        const recusa = opcoes.recusaDaImagem?.[arquivo.name];
        if (recusa) {
          return {
            ok: false,
            status: recusa.status,
            json: async () => ({ detail: recusa.detail }),
          } as unknown as Response;
        }
        return {
          ok: true,
          status: 201,
          json: async () => ({ id: `a-${arquivo.name}`, nome: arquivo.name }),
        } as unknown as Response;
      }
      if (opcoes.recusa) {
        return {
          ok: false,
          status: opcoes.recusa.status,
          json: async () => ({ detail: opcoes.recusa!.detail }),
        } as unknown as Response;
      }
      if (opcoes.corpoDoCriar === "ilegivel") {
        return {
          ok: true,
          status: 201,
          json: async () => {
            throw new SyntaxError("Unexpected token < in JSON");
          },
        } as unknown as Response;
      }
      if ("corpoDoCriar" in opcoes) {
        return { ok: true, status: 201, json: async () => opcoes.corpoDoCriar } as unknown as Response;
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
      onCriadaSemConfirmacao={() => {
        semConfirmacao += 1;
      }}
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

  // O mesmo bug do assistente, na tela ao lado: o corpo entrava por `as` e era
  // desreferenciado sem ninguém conferir. 201 é sucesso, e quem avisa é a
  // página, que TIRA o formulário da tela em vez de reabilitar o botão.
  it.each([
    ["corpo ilegível", "ilegivel"],
    ["corpo null", null],
    ["corpo sem id", { titulo: "Encerrar conversas" }],
    ["corpo que é lista", []],
  ])("201 com %s vira sucesso sem confirmação, e não entrega Demanda nenhuma", async (_nome, corpo) => {
    montar({ corpoDoCriar: corpo });
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(semConfirmacao).toBe(1));
    expect(criadas).toHaveLength(0);
    // E não é recusa: o alerta vermelho do formulário fica calado.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("o 201 dentro do contrato entrega a Demanda, e não avisa sem confirmação", async () => {
    // O par de presença dos quatro acima: um formulário que sempre avisasse
    // "sem confirmação" passaria neles.
    montar();
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(semConfirmacao).toBe(0);
  });

  it("o aviso de e-mail que não saiu viaja junto com a Demanda", async () => {
    montar({ avisoPorEmail: "A Demanda foi criada, mas o e-mail de atribuicao nao saiu." });
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].aviso).toContain("nao saiu");
  });
});

describe("Imagens na criação da Demanda (issue #1061)", () => {
  function imagem(nome: string, tamanho = 16): File {
    return new File([new Uint8Array(tamanho)], nome, { type: "image/png" });
  }

  function escolher(...arquivos: File[]) {
    fireEvent.change(screen.getByLabelText("Anexar imagens"), { target: { files: arquivos } });
  }

  function envios(): Chamada[] {
    return escritas().filter((c) => c.url.endsWith("/anexos"));
  }

  function nomesEnviados(): string[] {
    return envios().map((c) => ((c.corpo as FormData).get("imagem") as File).name);
  }

  it("cada imagem escolhida sobe para a Demanda criada, depois da criação", async () => {
    montar();
    preencher();
    escolher(imagem("tela.png"), imagem("erro.jpg"));

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    // A Demanda primeiro: a imagem precisa de um card para morar.
    expect(escritas()[0].url).toBe("/api/admin/tecnologia/demandas");
    expect(envios().map((c) => c.url)).toEqual([
      "/api/admin/tecnologia/demandas/d-nova/anexos",
      "/api/admin/tecnologia/demandas/d-nova/anexos",
    ]);
    expect(nomesEnviados()).toEqual(["tela.png", "erro.jpg"]);
    expect(criadas[0].aviso).toBeNull();
  });

  it("sem imagem escolhida, só a Demanda é enviada", async () => {
    montar();
    preencher();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(envios()).toHaveLength(0);
  });

  it("mostra as escolhidas e deixa tirar uma antes de criar", async () => {
    montar();
    preencher();
    escolher(imagem("fica.png"), imagem("sai.png"));

    expect(screen.getByText("fica.png")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tirar sai.png" }));
    expect(screen.queryByText("sai.png")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(nomesEnviados()).toEqual(["fica.png"]);
  });

  it("até dez: a décima primeira fica de fora, com aviso", async () => {
    montar();
    preencher();
    escolher(...Array.from({ length: 11 }, (_, i) => imagem(`tela-${i + 1}.png`)));

    expect(screen.getByRole("status").textContent).toContain("10");
    expect(screen.queryByText("tela-11.png")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(nomesEnviados()).toHaveLength(10);
    expect(nomesEnviados()).not.toContain("tela-11.png");
  });

  it("formato fora da lista é recusado na escolha, com a frase do Assistente", () => {
    montar();
    escolher(imagem("relatorio.pdf"));

    expect(screen.getByRole("status").textContent).toContain(IMAGEM_FORA_DA_LISTA);
    expect(screen.queryByText("relatorio.pdf")).toBeNull();
  });

  it("imagem acima de 5 MB é recusada na escolha", () => {
    montar();
    escolher(imagem("enorme.png", 5 * 1024 * 1024 + 1));

    expect(screen.getByRole("status").textContent).toContain("5 MB");
    expect(screen.queryByText("enorme.png")).toBeNull();
  });

  it("a imagem que o servidor recusou vira aviso junto da Demanda criada", async () => {
    const motivo = "O print passou do limite de 5 MB. Anexe uma imagem menor, ou escreva o que aparece na tela.";
    montar({ recusaDaImagem: { "grande.png": { status: 413, detail: motivo } } });
    preencher();
    escolher(imagem("boa.png"), imagem("grande.png"));

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    // A boa entrou; a recusada não some calada: quem criou precisa saber.
    expect(nomesEnviados()).toEqual(["boa.png", "grande.png"]);
    expect(criadas[0].aviso).toContain("grande.png");
    expect(criadas[0].aviso).toContain(motivo);
    expect(criadas[0].aviso).not.toContain("boa.png");
  });

  it("o aviso de e-mail e o da imagem chegam juntos", async () => {
    montar({
      avisoPorEmail: "A Demanda foi criada, mas o e-mail de atribuicao nao saiu.",
      recusaDaImagem: { "grande.png": { status: 413, detail: "grande demais" } },
    });
    preencher();
    escolher(imagem("grande.png"));

    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].aviso).toContain("nao saiu");
    expect(criadas[0].aviso).toContain("grande.png");
  });
});
