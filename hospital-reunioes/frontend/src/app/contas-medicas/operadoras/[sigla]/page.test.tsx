/**
 * @vitest-environment jsdom
 */

/**
 * A tela Memória da operadora (issue #1140, PRD #1129, ADR 0070).
 *
 * A tela não decide nada: quem cria a versão nova, guarda o texto anterior e
 * confere a permissão do tipo da regra é o servidor. O que se trava aqui é o
 * que a gestão vê (cabeçalho, abas, botões por tipo e situação, tabelas,
 * histórico) e o que cada clique manda (a URL e o corpo).
 *
 * Todo teste de ausência tem irmão de presença no mesmo estado.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MemoriaDaOperadoraPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ sigla: "ALFA" }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ROTA = "/api/contas-medicas/operadoras/ALFA";

function regra(campos: Record<string, unknown>) {
  return {
    id: `id-${campos.codigo}`,
    secao: String(campos.codigo).split("-")[1],
    tipo: "CONTRATUAL",
    origem: "PRÁTICA",
    status: "VIGENTE",
    validado_por: "Diretor Teste",
    validado_em: "2026-10-06",
    modelo_id: null,
    ...campos,
  };
}

function memoria(permissoes: string[]) {
  return {
    sigla: "ALFA",
    nome: "Alfa Saúde",
    situacao: "PARCIAL",
    versao: "1.2",
    data: "2026-10-12T14:30:00+00:00",
    contrato: {
      assinatura: "2015-10-01",
      ultimo_aditivo: { numero: 12, inicio_vigencia: "2026-05-01" },
      aviso_antecedencia_dias: 60,
    },
    regras_contagem: { vigentes: 4, pendentes: 1 },
    regras: [
      regra({ codigo: "ALFA-DIA-01", texto: "A diária vence às 12h e é sempre integral." }),
      regra({ codigo: "ALFA-DIA-02", texto: "Transferência antes das 10h não gera diária extra." }),
      regra({ codigo: "ALFA-INS-01", texto: "Cateter periférico, 1 a cada 96 h.", tipo: null }),
      regra({
        codigo: "ALFA-PRI-01",
        texto: "Identificar sempre pelo número do atendimento.",
        tipo: "OPERACIONAL",
        modelo_id: "HSM-PRI-01",
      }),
      regra({
        codigo: "ALFA-PRI-03",
        texto: "Edição do Brasíndice usada pela operadora.",
        origem: "CONTRATO",
        status: "PENDENTE",
        validado_por: null,
        validado_em: null,
      }),
    ],
    tabelas: [
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
            em_uso: true,
          },
          {
            tabela: "ALFA-LPM-SETEMBRO.csv",
            versao: "LPM 01/09/2026",
            vigencia_inicio: "2026-09-01",
            vigencia_fim: null,
            em_uso: false,
          },
        ],
      },
      { categoria: "HONORARIO", tipo: null, situacao: "NAO_CARREGADA", versoes: [] },
    ],
    historico: [
      {
        versao: "1.2",
        vigente: true,
        criado_em: "2026-10-12T14:30:00+00:00",
        autor: "Diretor Teste",
        resumo: "ALFA-DIA-02 decidida (vigente)",
        mudancas: [
          {
            codigo: "ALFA-DIA-02",
            texto_anterior: "Transferência antes das 10h: gera ou não diária extra.",
            texto_novo: "Transferência antes das 10h não gera diária extra.",
          },
        ],
      },
      {
        versao: "1.0",
        vigente: false,
        criado_em: "2026-10-01T09:00:00+00:00",
        autor: "Gestão Teste",
        resumo: "5 regras: 3 vigentes e 2 pendentes",
        mudancas: [],
      },
    ],
    permissoes,
  };
}

type Chamada = { url: string; metodo: string; corpo: unknown };

let chamadas: Chamada[];
let permissoes: string[];
let statusDaMemoria: number;
let respostaDaMudanca: { status: number; corpo: unknown };

function resposta(status: number, corpo: unknown, cabecalhos: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => corpo,
    blob: async () => new Blob([String(corpo)]),
    headers: new Headers(cabecalhos),
  } as Response;
}

function backend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      chamadas.push({ url, metodo, corpo });
      if (url === ROTA && metodo === "GET") {
        return resposta(statusDaMemoria, statusDaMemoria === 200 ? memoria(permissoes) : { detail: "Sem permissão" });
      }
      if (url === `${ROTA}/memoria` && metodo === "GET") {
        return resposta(200, "---\noperadora: ALFA\n---\n", {
          "content-disposition": 'attachment; filename="MEMORIA-ALFA-v1.2.md"',
        });
      }
      if (url.startsWith(`${ROTA}/regras/`) && (metodo === "PUT" || metodo === "POST")) {
        return resposta(respostaDaMudanca.status, respostaDaMudanca.corpo);
      }
      return resposta(404, { detail: "rota desconhecida no dublê" });
    }),
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  chamadas = [];
  permissoes = ["incluir_regra_operacional", "regra_contratual_tabelas"];
  statusDaMemoria = 200;
  respostaDaMudanca = {
    status: 200,
    corpo: { operadora: "ALFA", versao: "1.3", regra: "ALFA-DIA-01", outras_operadoras: [] },
  };
  backend();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrir() {
  render(<MemoriaDaOperadoraPage />);
  return screen.findByRole("table", { name: "Regras da memória" });
}

function linhaDa(codigo: string): HTMLElement {
  return screen.getByTestId(`regra-${codigo}`);
}

function codigosNaTabela(): string[] {
  return within(screen.getByRole("table", { name: "Regras da memória" }))
    .queryAllByTestId(/^regra-/)
    .map((tr) => tr.getAttribute("data-testid")!.replace("regra-", ""));
}

function leiturasDaMemoria(): number {
  return chamadas.filter((c) => c.url === ROTA && c.metodo === "GET").length;
}

describe("o cabeçalho", () => {
  it("mostra a operadora, a versão, a data, o contrato e o aditivo, a situação e os pendentes", async () => {
    await abrir();

    const cabecalho = screen.getByRole("region", { name: "Cabeçalho da memória" });
    expect(within(cabecalho).getByRole("heading", { name: "Memória da operadora ALFA" })).toBeTruthy();
    const texto = cabecalho.textContent ?? "";
    expect(texto).toContain("Alfa Saúde");
    expect(texto).toContain("Versão 1.2, de 12/10/2026");
    expect(texto).toContain("Contrato assinado em 01/10/2015");
    expect(texto).toContain("aditivo 12, vigente desde 01/05/2026");
    expect(texto).toContain("Parcial");
    expect(texto).toContain("1 regra pendente");
  });

  it("diz quando a pessoa não tem permissão para a memória", async () => {
    statusDaMemoria = 403;

    render(<MemoriaDaOperadoraPage />);

    expect(await screen.findByText(/não tem permissão para mudar as regras da memória/)).toBeTruthy();
  });
});

describe("as abas", () => {
  it("tem as oito abas e cada uma filtra as regras da seção; Pendentes mostra só as pendentes", async () => {
    await abrir();

    const abas = within(screen.getByRole("tablist")).getAllByRole("tab").map((t) => t.textContent);
    expect(abas).toEqual([
      "Todas",
      "Diárias",
      "Pacotes",
      "Taxas e aluguéis",
      "Insumos por tempo",
      "Medicamentos",
      "Honorários",
      "Pendentes (1)",
    ]);
    expect(codigosNaTabela()).toEqual(["ALFA-DIA-01", "ALFA-DIA-02", "ALFA-INS-01", "ALFA-PRI-01", "ALFA-PRI-03"]);

    fireEvent.click(screen.getByRole("tab", { name: "Diárias" }));
    expect(codigosNaTabela()).toEqual(["ALFA-DIA-01", "ALFA-DIA-02"]);

    fireEvent.click(screen.getByRole("tab", { name: "Insumos por tempo" }));
    expect(codigosNaTabela()).toEqual(["ALFA-INS-01"]);

    fireEvent.click(screen.getByRole("tab", { name: "Pendentes (1)" }));
    expect(codigosNaTabela()).toEqual(["ALFA-PRI-03"]);

    fireEvent.click(screen.getByRole("tab", { name: "Pacotes" }));
    expect(codigosNaTabela()).toEqual([]);
    expect(screen.getByText("Nenhuma regra nesta aba.")).toBeTruthy();
  });

  it("cada linha traz a regra, a origem, quem validou, a data e a situação", async () => {
    await abrir();

    const celulas = within(linhaDa("ALFA-DIA-02"))
      .getAllByRole("cell")
      .map((td) => td.textContent);
    expect(celulas.slice(0, 5)).toEqual([
      "ALFA-DIA-02Transferência antes das 10h não gera diária extra.",
      "PRÁTICA",
      "Diretor Teste",
      "06/10/2026",
      "Vigente",
    ]);
    expect(within(linhaDa("ALFA-PRI-03")).getAllByRole("cell")[4].textContent).toBe("Pendente");
  });
});

describe("os botões de cada linha", () => {
  it("vigente tem Editar e pendente tem Decidir, só no tipo que a pessoa pode mudar", async () => {
    permissoes = ["incluir_regra_operacional"];

    await abrir();

    expect(within(linhaDa("ALFA-PRI-01")).getByRole("button", { name: "Editar" })).toBeTruthy();
    expect(within(linhaDa("ALFA-DIA-01")).queryByRole("button", { name: "Editar" })).toBeNull();
    // Regra sem tipo é de preço, diária ou tabela: pede a contratual.
    expect(within(linhaDa("ALFA-INS-01")).queryByRole("button", { name: "Editar" })).toBeNull();
    expect(within(linhaDa("ALFA-PRI-03")).queryByRole("button", { name: "Decidir" })).toBeNull();
  });

  it("com as duas permissões, a contratual vigente tem Editar e a pendente tem Decidir, e não o contrário", async () => {
    await abrir();

    expect(within(linhaDa("ALFA-DIA-01")).getByRole("button", { name: "Editar" })).toBeTruthy();
    expect(within(linhaDa("ALFA-DIA-01")).queryByRole("button", { name: "Decidir" })).toBeNull();
    expect(within(linhaDa("ALFA-PRI-03")).getByRole("button", { name: "Decidir" })).toBeTruthy();
    expect(within(linhaDa("ALFA-PRI-03")).queryByRole("button", { name: "Editar" })).toBeNull();
  });
});

describe("editar e decidir", () => {
  it("editar manda o texto, o tipo e a origem, mostra a versão nova e relê a memória", async () => {
    await abrir();

    fireEvent.click(within(linhaDa("ALFA-DIA-01")).getByRole("button", { name: "Editar" }));
    const formulario = screen.getByRole("form", { name: "Editar a regra ALFA-DIA-01" });
    expect((within(formulario).getByLabelText("Texto da regra") as HTMLTextAreaElement).value).toBe(
      "A diária vence às 12h e é sempre integral.",
    );
    fireEvent.change(within(formulario).getByLabelText("Texto da regra"), {
      target: { value: "A diária vence às 14h e é sempre integral." },
    });
    fireEvent.change(within(formulario).getByLabelText("Origem"), { target: { value: "ADITIVO 12" } });
    // Regra que não veio do modelo HSM não oferece aplicar a todas.
    expect(within(formulario).queryByLabelText("Aplicar a todas as operadoras que têm esta regra")).toBeNull();
    fireEvent.click(within(formulario).getByRole("button", { name: "Salvar" }));

    const aviso = await screen.findByRole("status");
    expect(aviso.textContent).toContain("Versão 1.3 da memória criada");
    const envio = chamadas.find((c) => c.metodo === "PUT");
    expect(envio?.url).toBe(`${ROTA}/regras/ALFA-DIA-01`);
    expect(envio?.corpo).toEqual({
      texto: "A diária vence às 14h e é sempre integral.",
      tipo: "CONTRATUAL",
      origem: "ADITIVO 12",
      aplicar_a_todas: false,
    });
    await waitFor(() => expect(leiturasDaMemoria()).toBe(2));
  });

  it("a regra do modelo HSM oferece aplicar a todas, e o aviso diz quais operadoras ganharam versão", async () => {
    respostaDaMudanca = {
      status: 200,
      corpo: {
        operadora: "ALFA",
        versao: "1.3",
        regra: "ALFA-PRI-01",
        outras_operadoras: [{ operadora: "GAMA", versao: "2.1" }],
      },
    };
    await abrir();

    fireEvent.click(within(linhaDa("ALFA-PRI-01")).getByRole("button", { name: "Editar" }));
    const formulario = screen.getByRole("form", { name: "Editar a regra ALFA-PRI-01" });
    fireEvent.click(within(formulario).getByLabelText("Aplicar a todas as operadoras que têm esta regra"));
    fireEvent.click(within(formulario).getByRole("button", { name: "Salvar" }));

    const aviso = await screen.findByRole("status");
    expect(aviso.textContent).toContain("GAMA (versão 2.1)");
    expect((chamadas.find((c) => c.metodo === "PUT")?.corpo as Record<string, unknown>).aplicar_a_todas).toBe(true);
  });

  it("Deixar pendente fecha sem gravar, e Validar regra manda a decisão", async () => {
    await abrir();

    fireEvent.click(within(linhaDa("ALFA-PRI-03")).getByRole("button", { name: "Decidir" }));
    fireEvent.click(screen.getByRole("button", { name: "Deixar pendente" }));
    expect(screen.queryByRole("form", { name: "Decidir a regra ALFA-PRI-03" })).toBeNull();
    expect(chamadas.filter((c) => c.metodo === "POST")).toEqual([]);

    fireEvent.click(within(linhaDa("ALFA-PRI-03")).getByRole("button", { name: "Decidir" }));
    const formulario = screen.getByRole("form", { name: "Decidir a regra ALFA-PRI-03" });
    fireEvent.change(within(formulario).getByLabelText("Texto da regra"), {
      target: { value: "A operadora usa o Brasíndice da data do atendimento." },
    });
    fireEvent.click(within(formulario).getByRole("button", { name: "Validar regra" }));

    await screen.findByRole("status");
    const decisao = chamadas.find((c) => c.metodo === "POST");
    expect(decisao?.url).toBe(`${ROTA}/regras/ALFA-PRI-03/decisao`);
    expect(decisao?.corpo).toEqual({
      texto: "A operadora usa o Brasíndice da data do atendimento.",
      tipo: "CONTRATUAL",
      origem: "CONTRATO",
    });
  });

  it("mostra a recusa do servidor como veio", async () => {
    respostaDaMudanca = { status: 403, corpo: { detail: "Sem permissão para mudar este tipo de regra." } };
    await abrir();

    fireEvent.click(within(linhaDa("ALFA-DIA-01")).getByRole("button", { name: "Editar" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Sem permissão para mudar este tipo de regra.");
  });
});

describe("tabelas, histórico e exportação", () => {
  it("mostra as tabelas de preço por categoria com a versão e a situação", async () => {
    await abrir();

    const tabelas = screen.getByRole("table", { name: "Tabelas de preço da operadora" });
    const linhas = within(tabelas)
      .getAllByRole("row")
      .slice(1)
      .map((tr) => within(tr).getAllByRole("cell").map((td) => td.textContent));
    expect(linhas).toEqual([
      ["Medicamentos", "ALFA-LPM-OUTUBRO.csv", "LPM 01/10/2026", "desde 01/10/2026", "Em uso"],
      ["", "ALFA-LPM-SETEMBRO.csv", "LPM 01/09/2026", "desde 01/09/2026", "Guardada"],
      ["Honorários", "", "", "", "Não carregada"],
    ]);
  });

  it("o histórico de versões mostra o que mudou, quem, quando e o texto anterior", async () => {
    await abrir();

    const historico = screen.getByRole("region", { name: "Histórico de versões" });
    const versoes = within(historico).getAllByRole("listitem");
    expect(versoes).toHaveLength(2);
    const nova = versoes[0].textContent ?? "";
    expect(nova).toContain("Versão 1.2");
    expect(nova).toContain("vigente");
    expect(nova).toContain("12/10/2026");
    expect(nova).toContain("Diretor Teste");
    expect(nova).toContain("ALFA-DIA-02 decidida (vigente)");
    expect(nova).toContain("Antes: Transferência antes das 10h: gera ou não diária extra.");
    expect(nova).toContain("Depois: Transferência antes das 10h não gera diária extra.");
    expect(versoes[1].textContent).toContain("5 regras: 3 vigentes e 2 pendentes");
  });

  it("Exportar baixa o arquivo da memória com o nome que o servidor deu", async () => {
    const criar = vi.fn(() => "blob:memoria");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() }));
    const clique = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: "Exportar" }));

    await waitFor(() => expect(clique).toHaveBeenCalled());
    expect(chamadas.some((c) => c.url === `${ROTA}/memoria` && c.metodo === "GET")).toBe(true);
    expect((clique.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe("MEMORIA-ALFA-v1.2.md");
    clique.mockRestore();
  });
});
