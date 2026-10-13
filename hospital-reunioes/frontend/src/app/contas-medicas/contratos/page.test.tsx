/**
 * @vitest-environment jsdom
 */

/**
 * A tela Contratos de Contas médicas (issue #1144, PRD #1129).
 *
 * Uma linha por operadora, com a cor da situação (vermelho Vencido, âmbar
 * Negociar reajuste, verde Em dia, cinza Sem contrato), o vencimento marcado
 * "calculado" quando veio da vigência mais um ano, e o envio do contrato ou do
 * aditivo: a IA preenche os campos e nada vale antes do "Confirmar". O backend
 * é um dublê que responde por rota; quem decide é ele (guard, cerca do
 * arquivo). O que se confere aqui é a fiação.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContratosPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

type Linha = {
  sigla: string;
  nome: string;
  contrato: Record<string, unknown> | null;
  dias: number | null;
  situacao: string;
  data_aviso: string | null;
};

function contrato(campos: Record<string, unknown>): Record<string, unknown> {
  return {
    data_assinatura: "2015-10-01",
    aditivo_numero: "110",
    aditivo_data: null,
    vigencia_inicio: "2026-05-01",
    vencimento: "2027-05-01",
    vencimento_calculado: false,
    vencimento_e_negociacao: false,
    arquivo: null,
    ...campos,
  };
}

const LINHAS: Linha[] = [
  {
    sigla: "ASSIM",
    nome: "Assim Saúde",
    contrato: contrato({ vencimento_calculado: true }),
    dias: 60,
    situacao: "NEGOCIAR",
    data_aviso: "2027-03-02",
  },
  {
    sigla: "GAMA",
    nome: "Gama Saúde",
    contrato: contrato({ vencimento: "2027-03-01" }),
    dias: -1,
    situacao: "VENCIDO",
    data_aviso: "2026-12-31",
  },
  {
    sigla: "LEVE",
    nome: "Leve Saúde",
    contrato: contrato({ vencimento: "2027-08-01", vencimento_e_negociacao: true }),
    dias: 152,
    situacao: "EM_DIA",
    data_aviso: "2027-06-02",
  },
  { sigla: "BETA", nome: "Beta Saúde", contrato: null, dias: null, situacao: "SEM_CONTRATO", data_aviso: null },
];

let podeEditar: boolean;
let proposta: Record<string, unknown>;
let chamadas: { url: string; metodo: string; corpo: unknown }[];

function resposta(status: number, corpo: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
}

beforeEach(() => {
  podeEditar = true;
  chamadas = [];
  proposta = {
    arquivo: "contratos/op-assim/abc.pdf",
    tem_texto: true,
    aviso: null,
    campos: {
      data_assinatura: "2015-10-01",
      aditivo_numero: "111",
      aditivo_data: "2027-04-20",
      vigencia_inicio: "2027-05-01",
      vencimento: "2028-05-01",
      vencimento_calculado: true,
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      chamadas.push({ url, metodo, corpo });
      if (url === "/api/contas-medicas/contratos") return resposta(200, { contratos: LINHAS, pode_editar: podeEditar });
      if (url === "/api/contas-medicas/contratos/ASSIM/arquivo" && metodo === "POST") return resposta(200, proposta);
      if (url === "/api/contas-medicas/contratos/ASSIM" && metodo === "POST") return resposta(200, corpo);
      return resposta(404, { detail: "rota desconhecida" });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function linha(sigla: string): Promise<HTMLElement> {
  render(<ContratosPage />);
  return screen.findByRole("listitem", { name: sigla });
}

describe("a tela Contratos", () => {
  it("mostra uma linha por operadora com a cor de cada situação", async () => {
    render(<ContratosPage />);

    const cores = {
      ASSIM: ["Negociar reajuste", "amber"],
      GAMA: ["Vencido", "red"],
      LEVE: ["Em dia", "emerald"],
      BETA: ["Sem contrato", "slate"],
    };
    for (const [sigla, [rotulo, cor]] of Object.entries(cores)) {
      const item = await screen.findByRole("listitem", { name: sigla });
      expect(within(item).getByText(rotulo)).toBeTruthy();
      expect(item.className).toContain(`border-${cor}-`);
    }
  });

  it("mostra as datas, os dias que faltam e a marca de calculado", async () => {
    const assim = await linha("ASSIM");

    expect(within(assim).getByText("01/10/2015")).toBeTruthy();
    expect(within(assim).getByText("nº 110")).toBeTruthy();
    expect(within(assim).getByText("01/05/2027")).toBeTruthy();
    expect(within(assim).getByText("calculado")).toBeTruthy();
    expect(within(assim).getByText("faltam 60 dias")).toBeTruthy();
    expect(within(screen.getByRole("listitem", { name: "GAMA" })).getByText("venceu há 1 dia")).toBeTruthy();
  });

  it("na data que não é vencimento, diz que é o início do debate do reajuste", async () => {
    const leve = await linha("LEVE");

    expect(within(leve).getByText("Início do debate do reajuste")).toBeTruthy();
    expect(within(leve).queryByText("calculado")).toBeNull();
  });

  it("quem só vê não tem o botão de enviar", async () => {
    podeEditar = false;

    const assim = await linha("ASSIM");

    expect(within(assim).queryByRole("button", { name: "Enviar contrato ou aditivo" })).toBeNull();
  });

  it("envia o arquivo, mostra os campos da IA e só grava no Confirmar", async () => {
    const assim = await linha("ASSIM");

    fireEvent.click(within(assim).getByRole("button", { name: "Enviar contrato ou aditivo" }));
    const arquivo = new File(["%PDF-1.4"], "aditivo-111.pdf", { type: "application/pdf" });
    fireEvent.change(within(assim).getByLabelText("Arquivo do contrato ou aditivo"), {
      target: { files: [arquivo] },
    });

    await waitFor(() => expect((within(assim).getByLabelText("Número do aditivo") as HTMLInputElement).value).toBe("111"));
    expect((within(assim).getByLabelText("Vencimento") as HTMLInputElement).value).toBe("2028-05-01");
    const envio = chamadas.find((c) => c.url === "/api/contas-medicas/contratos/ASSIM/arquivo");
    expect(envio?.metodo).toBe("POST");
    expect((envio?.corpo as FormData).get("arquivo")).toBe(arquivo);
    expect(chamadas.some((c) => c.url === "/api/contas-medicas/contratos/ASSIM")).toBe(false);

    fireEvent.click(within(assim).getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(chamadas.find((c) => c.url === "/api/contas-medicas/contratos/ASSIM")?.corpo).toEqual({
        ...(proposta.campos as object),
        arquivo: "contratos/op-assim/abc.pdf",
      }),
    );
  });

  it("arquivo sem texto deixa os campos vazios para digitar, com o aviso", async () => {
    proposta = {
      arquivo: "contratos/op-assim/img.png",
      tem_texto: false,
      aviso: "O arquivo não tem texto para ler (é imagem). Digite os campos e confirme.",
      campos: {
        data_assinatura: null,
        aditivo_numero: null,
        aditivo_data: null,
        vigencia_inicio: null,
        vencimento: null,
        vencimento_calculado: false,
      },
    };
    const assim = await linha("ASSIM");

    fireEvent.click(within(assim).getByRole("button", { name: "Enviar contrato ou aditivo" }));
    fireEvent.change(within(assim).getByLabelText("Arquivo do contrato ou aditivo"), {
      target: { files: [new File(["x"], "contrato.png", { type: "image/png" })] },
    });

    expect(await within(assim).findByText(/Digite os campos e confirme/)).toBeTruthy();
    expect((within(assim).getByLabelText("Vencimento") as HTMLInputElement).value).toBe("");
  });

  it("o vencimento digitado pela pessoa deixa de ser calculado", async () => {
    const assim = await linha("ASSIM");
    fireEvent.click(within(assim).getByRole("button", { name: "Enviar contrato ou aditivo" }));
    fireEvent.change(within(assim).getByLabelText("Arquivo do contrato ou aditivo"), {
      target: { files: [new File(["%PDF"], "a.pdf", { type: "application/pdf" })] },
    });
    await waitFor(() => expect((within(assim).getByLabelText("Vencimento") as HTMLInputElement).value).toBe("2028-05-01"));

    fireEvent.change(within(assim).getByLabelText("Vencimento"), { target: { value: "2028-03-31" } });
    fireEvent.click(within(assim).getByRole("button", { name: "Confirmar" }));

    await waitFor(() => {
      const corpo = chamadas.find((c) => c.url === "/api/contas-medicas/contratos/ASSIM")?.corpo as Record<string, unknown>;
      expect(corpo?.vencimento).toBe("2028-03-31");
      expect(corpo?.vencimento_calculado).toBe(false);
    });
  });
});
