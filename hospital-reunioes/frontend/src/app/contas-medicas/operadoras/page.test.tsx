/**
 * @vitest-environment jsdom
 */

/**
 * A tela Operadoras de Contas médicas (issues #1119 e #1120, PRD #1113).
 *
 * A gestão vê cada operadora com a situação e as tabelas de preço por
 * categoria, e abre os formulários: o envio do arquivo de memória, da tabela
 * de preço, do dicionário de itens, o cadastro dos planos do MV e o dos
 * setores. O backend é um dublê que responde por rota; o que se confere aqui é
 * a fiação da tela: o que ela mostra do que veio e o que ela manda quando a
 * pessoa envia.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OperadorasPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const OPERADORAS = {
  operadoras: [
    {
      sigla: "ALFA",
      nome: "Alfa Saúde",
      situacao: "PARCIAL",
      versao: "1.0",
      regras: { vigentes: 3, pendentes: 2 },
      tabelas: [
        {
          categoria: "MATERIAL",
          tipo: "PROPRIA",
          situacao: "CARREGADA",
          versoes: [
            {
              tabela: "ALFA-MATERIAIS.csv",
              versao: "Anexo I",
              vigencia_inicio: "2026-05-01",
              vigencia_fim: null,
            },
          ],
        },
        {
          categoria: "MEDICAMENTO",
          tipo: "LPM",
          situacao: "CARREGADA",
          versoes: [
            {
              tabela: "ALFA-LPM-OUTUBRO.csv",
              versao: "LPM 01/10/2026",
              vigencia_inicio: "2026-10-01",
              vigencia_fim: null,
            },
            {
              tabela: "ALFA-LPM-SETEMBRO.csv",
              versao: "LPM 01/09/2026",
              vigencia_inicio: "2026-09-01",
              vigencia_fim: "2026-09-30",
            },
          ],
        },
        { categoria: "HONORARIO", tipo: null, situacao: "NAO_CARREGADA", versoes: [] },
        { categoria: "PORTE_ANESTESICO", tipo: "CBHPM", situacao: "NAO_CARREGADA", versoes: [] },
      ],
    },
    {
      sigla: "GAMA",
      nome: "Gama Saúde",
      situacao: "SEM_MEMORIA",
      versao: null,
      regras: { vigentes: 0, pendentes: 0 },
      tabelas: [{ categoria: "MATERIAL", tipo: null, situacao: "NAO_CARREGADA", versoes: [] }],
    },
  ],
};

const TABELA_IMPORTADA = {
  operadora: "ALFA",
  categoria: "MATERIAL",
  formato: "MATERIAIS_COMUM_CARIOCA",
  descricao_formato: "materiais com preço Comum e Carioca",
  itens: 942,
  versao: null,
  vigencia_inicio: "2026-05-01",
  vigencia_fim: null,
};

const IMPORTADA = {
  operadora: "ALFA",
  nome: "Alfa Saúde",
  situacao: "PARCIAL",
  versao: "1.1",
  regras: { total: 5, vigentes: 4, pendentes: 1 },
  parametros: { diaria: { hora_vencimento: "10:00" }, opme: { fornecida_por: "OPERADORA" } },
};

type Chamada = { url: string; metodo: string; corpo: unknown };

let chamadas: Chamada[];
let statusDaLista: number;
let respostaDaMemoria: { status: number; corpo: unknown };
let respostaDaTabela: { status: number; corpo: unknown };
let planos: Array<Record<string, string | null>>;
let setores: Array<Record<string, string | null>>;

function resposta(status: number, corpo: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
}

function backend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      chamadas.push({ url, metodo, corpo });
      if (url === "/api/contas-medicas/operadoras" && metodo === "GET") {
        return resposta(statusDaLista, statusDaLista === 200 ? OPERADORAS : { detail: "Sem permissão" });
      }
      if (url === "/api/contas-medicas/operadoras/memoria" && metodo === "POST") {
        return resposta(respostaDaMemoria.status, respostaDaMemoria.corpo);
      }
      if (url === "/api/contas-medicas/operadoras/ALFA/tabelas" && metodo === "POST") {
        return resposta(respostaDaTabela.status, respostaDaTabela.corpo);
      }
      if (url === "/api/contas-medicas/dicionario" && metodo === "POST") {
        return resposta(201, { termos: 4, novos: 3, atualizados: 1 });
      }
      if (url === "/api/contas-medicas/planos") {
        if (metodo === "POST") {
          const novo = { id: "pl-1", operadora_id: "op-1", ...(corpo as Record<string, string>) };
          planos = [...planos, novo];
          return resposta(201, novo);
        }
        return resposta(200, { planos });
      }
      if (url === "/api/contas-medicas/setores") {
        if (metodo === "POST") {
          const novo = { id: "st-1", ...(corpo as Record<string, string>) };
          setores = [...setores, novo];
          return resposta(201, novo);
        }
        return resposta(200, { setores });
      }
      return resposta(404, { detail: "rota desconhecida no dublê" });
    }),
  );
}

function escolher(rotulo: string, opcao: string) {
  fireEvent.click(screen.getByRole("combobox", { name: rotulo }));
  fireEvent.click(screen.getByRole("option", { name: opcao }));
}

beforeEach(() => {
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao
  // abrir a lista de opções.
  Element.prototype.scrollIntoView = vi.fn();
  chamadas = [];
  statusDaLista = 200;
  respostaDaMemoria = { status: 201, corpo: IMPORTADA };
  respostaDaTabela = { status: 201, corpo: TABELA_IMPORTADA };
  planos = [];
  setores = [];
  backend();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a lista das operadoras", () => {
  it("mostra cada operadora com a situação, a versão da memória, as regras e as tabelas", async () => {
    render(<OperadorasPage />);

    const lista = await screen.findByRole("region", { name: "Operadoras" });
    const alfa = await within(lista).findByTestId("operadora-ALFA");
    expect(alfa.textContent).toContain("Alfa Saúde");
    expect(alfa.textContent).toContain("Parcial");
    expect(alfa.textContent).toContain("Memória versão 1.0");
    expect(alfa.textContent).toContain("3 regras vigentes e 2 pendentes");

    const gama = within(lista).getByTestId("operadora-GAMA");
    expect(gama.textContent).toContain("Sem memória");
    expect(gama.textContent).not.toContain("Memória versão");
  });

  it("mostra, por operadora, cada categoria com a tabela, a versão, a vigência e a situação", async () => {
    render(<OperadorasPage />);

    const tabelas = await screen.findByRole("table", { name: "Tabelas de preço de ALFA" });
    const linhas = within(tabelas)
      .getAllByRole("row")
      .slice(1)
      .map((tr) => within(tr).getAllByRole("cell").map((td) => td.textContent));
    expect(linhas).toEqual([
      ["Materiais", "ALFA-MATERIAIS.csv", "Anexo I", "desde 01/05/2026", "Carregada"],
      ["Medicamentos", "ALFA-LPM-OUTUBRO.csv", "LPM 01/10/2026", "desde 01/10/2026", "Carregada"],
      ["", "ALFA-LPM-SETEMBRO.csv", "LPM 01/09/2026", "01/09/2026 a 30/09/2026", "Carregada"],
      ["Honorários", "", "", "", "Não carregada"],
      ["Porte anestésico", "CBHPM", "", "", "Não carregada"],
    ]);
    const gama = screen.getByRole("table", { name: "Tabelas de preço de GAMA" });
    expect(within(gama).getAllByRole("row")).toHaveLength(2);
  });

  it("diz quando a pessoa não tem a permissão de regra contratual e tabelas", async () => {
    statusDaLista = 403;

    render(<OperadorasPage />);

    expect(await screen.findByText(/não tem a permissão de regra contratual e tabelas/)).toBeTruthy();
  });
});

describe("os formulários", () => {
  it("a tela abre o envio da memória, da tabela e do dicionário, e o cadastro de planos e de setores", async () => {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");

    for (const nome of [
      "Enviar memória",
      "Enviar tabela de preço",
      "Dicionário de itens",
      "Planos do MV",
      "Setores do MV",
    ]) {
      const secao = screen.getByRole("region", { name: nome });
      expect(within(secao).getByRole("form")).toBeTruthy();
    }
  });

  it("envia o arquivo de memória e mostra a versão, a contagem e os parâmetros lidos", async () => {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Enviar memória" });
    const arquivo = new File(["---\noperadora: ALFA\n---\n"], "MEMORIA-ALFA-v1.1.md", { type: "text/markdown" });

    fireEvent.change(within(secao).getByLabelText("Arquivo de memória"), { target: { files: [arquivo] } });
    fireEvent.click(within(secao).getByRole("button", { name: "Enviar memória" }));

    const resultado = await within(secao).findByRole("status");
    expect(resultado.textContent).toContain("ALFA, versão 1.1");
    expect(resultado.textContent).toContain("4 regras vigentes e 1 pendente");
    expect(resultado.textContent).toContain("opme");
    const envio = chamadas.find((c) => c.metodo === "POST" && c.url === "/api/contas-medicas/operadoras/memoria");
    expect(envio).toBeTruthy();
    expect((envio!.corpo as FormData).get("arquivo")).toBe(arquivo);
    // A lista é relida, para a versão nova aparecer sem recarregar a página.
    await waitFor(() =>
      expect(chamadas.filter((c) => c.url === "/api/contas-medicas/operadoras" && c.metodo === "GET").length).toBe(2),
    );
  });

  it("mostra a recusa do servidor como veio, para quem enviou saber o que corrigir", async () => {
    respostaDaMemoria = {
      status: 422,
      corpo: { detail: "O arquivo tem um número no formato de CPF (linha 42)." },
    };
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Enviar memória" });

    fireEvent.change(within(secao).getByLabelText("Arquivo de memória"), {
      target: { files: [new File(["x"], "MEMORIA.md")] },
    });
    fireEvent.click(within(secao).getByRole("button", { name: "Enviar memória" }));

    const alerta = await within(secao).findByRole("alert");
    expect(alerta.textContent).toContain("formato de CPF (linha 42)");
  });

  it("cadastra um plano do MV com a operadora e a coluna, e ele entra na lista", async () => {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Planos do MV" });

    fireEvent.change(within(secao).getByLabelText("Nome no MV"), { target: { value: "Rioserv Max Qc" } });
    escolher("Operadora", "ALFA");
    fireEvent.change(within(secao).getByLabelText("Coluna de preço"), { target: { value: "CARIOCA" } });
    fireEvent.click(within(secao).getByRole("button", { name: "Cadastrar plano" }));

    const linha = await within(secao).findByText("Rioserv Max Qc");
    expect(linha).toBeTruthy();
    const envio = chamadas.find((c) => c.metodo === "POST" && c.url === "/api/contas-medicas/planos");
    expect(envio?.corpo).toEqual({ nome_mv: "Rioserv Max Qc", operadora: "ALFA", coluna_preco: "CARIOCA" });
  });

  it("cadastra um setor do MV com a acomodação, e ele entra na lista", async () => {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Setores do MV" });

    fireEvent.change(within(secao).getByLabelText("Nome no MV"), { target: { value: "CTI1" } });
    escolher("Acomodação", "CTI");
    fireEvent.click(within(secao).getByRole("button", { name: "Cadastrar setor" }));

    expect(await within(secao).findByText("CTI1")).toBeTruthy();
    const envio = chamadas.find((c) => c.metodo === "POST" && c.url === "/api/contas-medicas/setores");
    expect(envio?.corpo).toEqual({ nome_mv: "CTI1", acomodacao: "CTI" });
  });
});

describe("as tabelas de preço e o dicionário", () => {
  async function preencherTabela(arquivo: File) {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Enviar tabela de preço" });
    escolher("Operadora da tabela", "ALFA");
    escolher("Categoria", "Materiais");
    fireEvent.change(within(secao).getByLabelText("Início da vigência"), { target: { value: "2026-05-01" } });
    fireEvent.change(within(secao).getByLabelText("Fim da vigência (opcional)"), { target: { value: "2027-04-30" } });
    fireEvent.change(within(secao).getByLabelText("Arquivo da tabela"), { target: { files: [arquivo] } });
    fireEvent.click(within(secao).getByRole("button", { name: "Enviar tabela" }));
    return secao;
  }

  it("envia o CSV com a categoria e a vigência e mostra quantos itens entraram", async () => {
    const arquivo = new File(["codigo_assim;codigo_tuss\n"], "ALFA-MATERIAIS.csv", { type: "text/csv" });

    const secao = await preencherTabela(arquivo);

    const resultado = await within(secao).findByRole("status");
    expect(resultado.textContent).toContain("942 itens de materiais com preço Comum e Carioca");
    expect(resultado.textContent).toContain("ALFA (Materiais)");
    const envio = chamadas.find(
      (c) => c.metodo === "POST" && c.url === "/api/contas-medicas/operadoras/ALFA/tabelas",
    );
    const corpo = envio!.corpo as FormData;
    expect(corpo.get("categoria")).toBe("MATERIAL");
    expect(corpo.get("vigencia_inicio")).toBe("2026-05-01");
    expect(corpo.get("vigencia_fim")).toBe("2027-04-30");
    expect(corpo.get("arquivo")).toBe(arquivo);
    // A lista é relida, para a tabela nova aparecer sem recarregar a página.
    await waitFor(() =>
      expect(chamadas.filter((c) => c.url === "/api/contas-medicas/operadoras" && c.metodo === "GET").length).toBe(2),
    );
  });

  it("mostra a recusa do formato com as colunas esperadas", async () => {
    respostaDaTabela = {
      status: 422,
      corpo: { detail: "O cabeçalho do CSV (codigo;nome) não é de nenhum formato conhecido. Colunas esperadas: ..." },
    };

    const secao = await preencherTabela(new File(["codigo;nome\n"], "errado.csv"));

    const alerta = await within(secao).findByRole("alert");
    expect(alerta.textContent).toContain("não é de nenhum formato conhecido");
  });

  it("envia o dicionário de itens e mostra a contagem de termos", async () => {
    render(<OperadorasPage />);
    await screen.findByTestId("operadora-ALFA");
    const secao = screen.getByRole("region", { name: "Dicionário de itens" });
    const arquivo = new File(["termo;codigo\n"], "DICIONARIO.csv", { type: "text/csv" });

    fireEvent.change(within(secao).getByLabelText("Arquivo do dicionário"), { target: { files: [arquivo] } });
    fireEvent.click(within(secao).getByRole("button", { name: "Enviar dicionário" }));

    const resultado = await within(secao).findByRole("status");
    expect(resultado.textContent).toContain("4 termos, 3 novos e 1 atualizado");
    const envio = chamadas.find((c) => c.metodo === "POST" && c.url === "/api/contas-medicas/dicionario");
    expect((envio!.corpo as FormData).get("arquivo")).toBe(arquivo);
  });
});
