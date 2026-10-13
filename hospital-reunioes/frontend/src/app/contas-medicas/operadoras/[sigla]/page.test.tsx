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

import { ToastProvider } from "@/components/ui/Toast";

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
    contas_com_regra_nova: contasComRegraNova,
  };
}

const PROPOSTA = {
  regra: {
    secao: "DIA",
    texto: "Transferência de setor antes das 12h não gera diária extra no setor de origem.",
    tipo: "CONTRATUAL",
    origem: "PRÁTICA",
  },
  parametro: { chave: "diaria.hora_vencimento", antes: "10:00", depois: "12:00" },
  conflitos: [{ codigo: "ALFA-DIA-02", texto: "Transferência antes das 10h não gera diária extra." }],
  efeito_no_guia: "A diária do dia da transferência deixa de ser cobrada no setor de origem.",
};

type Chamada = { url: string; metodo: string; corpo: unknown };

let chamadas: Chamada[];
let permissoes: string[];
let statusDaMemoria: number;
let respostaDaMudanca: { status: number; corpo: unknown };
let respostaDaProposta: { status: number; corpo: unknown };
let respostaDoEnsino: { status: number; corpo: unknown };
let contasComRegraNova: unknown[];

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
      if (url === `${ROTA}/regras/proposta` && metodo === "POST") {
        return resposta(respostaDaProposta.status, respostaDaProposta.corpo);
      }
      if (url === `${ROTA}/regras` && metodo === "POST") {
        return resposta(respostaDoEnsino.status, respostaDoEnsino.corpo);
      }
      if (url.endsWith("/reanalisar") && metodo === "POST") {
        return resposta(200, { situacao: "NA_FILA" });
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
  respostaDaProposta = { status: 200, corpo: PROPOSTA };
  respostaDoEnsino = {
    status: 200,
    corpo: { operadora: "ALFA", versao: "1.3", regra: "ALFA-DIA-03", contas_com_regra_nova: 2 },
  };
  contasComRegraNova = [];
  backend();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrir() {
  render(
    <ToastProvider>
      <MemoriaDaOperadoraPage />
    </ToastProvider>,
  );
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

    render(
      <ToastProvider>
        <MemoriaDaOperadoraPage />
      </ToastProvider>,
    );

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

describe("ensinar uma regra nova (issue #1141)", () => {
  async function proporRegra() {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Ensinar uma regra nova" }));
    fireEvent.change(screen.getByLabelText("A regra, em linguagem comum"), {
      target: { value: "Na ALFA a transferência antes do meio-dia não gera diária extra." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Propor regra" }));
    return screen.findByRole("form", { name: "Proposta da regra nova" });
  }

  it("a proposta mostra antes e depois, os conflitos e o efeito no Guia, sem gravar nada", async () => {
    const proposta = await proporRegra();

    expect(chamadas.find((c) => c.url === `${ROTA}/regras/proposta`)?.corpo).toEqual({
      texto: "Na ALFA a transferência antes do meio-dia não gera diária extra.",
    });
    const antes = within(proposta).getByRole("region", { name: "Antes" }).textContent ?? "";
    expect(antes).toContain("diaria.hora_vencimento: 10:00");
    expect(antes).toContain("ALFA-DIA-02");
    expect(antes).toContain("Transferência antes das 10h não gera diária extra.");
    const depois = within(proposta).getByRole("region", { name: "Depois" }).textContent ?? "";
    expect(depois).toContain("Transferência de setor antes das 12h não gera diária extra no setor de origem.");
    expect(depois).toContain("diaria.hora_vencimento: 12:00");
    expect(within(proposta).getByRole("region", { name: "Conflitos" }).textContent).toContain("ALFA-DIA-02");
    expect(proposta.textContent).toContain("A diária do dia da transferência deixa de ser cobrada no setor de origem.");
    expect(chamadas.some((c) => c.url === `${ROTA}/regras` && c.metodo === "POST")).toBe(false);
  });

  it("Validar regra manda a regra editada e o parâmetro, avisa a versão e as contas marcadas e relê a memória", async () => {
    const proposta = await proporRegra();
    fireEvent.change(within(proposta).getByLabelText("Texto da regra"), {
      target: { value: "Transferência de setor antes das 12h não gera diária extra na origem." },
    });
    fireEvent.click(within(proposta).getByRole("button", { name: "Validar regra" }));

    const aviso = await screen.findByRole("status");
    expect(aviso.textContent).toContain("Versão 1.3 da memória criada com a regra ALFA-DIA-03");
    expect(aviso.textContent).toContain("2 contas abertas");
    expect(chamadas.find((c) => c.url === `${ROTA}/regras` && c.metodo === "POST")?.corpo).toEqual({
      secao: "DIA",
      texto: "Transferência de setor antes das 12h não gera diária extra na origem.",
      tipo: "CONTRATUAL",
      origem: "PRÁTICA",
      parametro: { chave: "diaria.hora_vencimento", valor: "12:00" },
    });
    await waitFor(() => expect(leiturasDaMemoria()).toBe(2));
  });

  it("sem marcar o parâmetro, a regra vai sem ele; Descartar fecha sem gravar", async () => {
    let proposta = await proporRegra();
    fireEvent.click(within(proposta).getByRole("button", { name: "Descartar" }));
    expect(screen.queryByRole("form", { name: "Proposta da regra nova" })).toBeNull();
    expect(chamadas.some((c) => c.url === `${ROTA}/regras` && c.metodo === "POST")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Propor regra" }));
    proposta = await screen.findByRole("form", { name: "Proposta da regra nova" });
    fireEvent.click(within(proposta).getByLabelText(/Mudar também o parâmetro diaria.hora_vencimento/));
    fireEvent.click(within(proposta).getByRole("button", { name: "Validar regra" }));

    await screen.findByRole("status");
    const envio = chamadas.find((c) => c.url === `${ROTA}/regras` && c.metodo === "POST");
    expect((envio?.corpo as Record<string, unknown>).parametro).toBeNull();
  });

  it("mostra a recusa da proposta como veio", async () => {
    respostaDaProposta = { status: 503, corpo: { detail: "A IA não respondeu agora. Tente de novo em alguns minutos." } };
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Ensinar uma regra nova" }));
    fireEvent.change(screen.getByLabelText("A regra, em linguagem comum"), { target: { value: "Qualquer regra." } });
    fireEvent.click(screen.getByRole("button", { name: "Propor regra" }));

    expect((await screen.findByRole("alert")).textContent).toContain("A IA não respondeu agora.");
  });
});

describe("as contas com regra nova desde a análise (issue #1141)", () => {
  const CONTA = { id: "conta-1", numero_atendimento: "31245", numero_conta: "48811", situacao: "EM_CORRECAO" };

  it("lista a conta com a marca e Reanalisar com a regra nova manda a conta para a fila", async () => {
    contasComRegraNova = [CONTA];
    await abrir();

    const secao = screen.getByRole("region", { name: "Contas com regra nova desde a análise" });
    expect(secao.textContent).toContain("31245");
    expect(secao.textContent).toContain("conta 48811");
    expect(secao.textContent).toContain("Regra nova desde a análise");
    fireEvent.click(within(secao).getByRole("button", { name: "Reanalisar com a regra nova" }));

    await waitFor(() => expect(leiturasDaMemoria()).toBe(2));
    expect(chamadas.find((c) => c.url.endsWith("/reanalisar"))?.url).toBe(
      "/api/contas-medicas/contas/conta-1/reanalisar",
    );
  });

  it("sem a permissão de regra contratual, a conta aparece sem o botão", async () => {
    contasComRegraNova = [CONTA];
    permissoes = ["incluir_regra_operacional"];
    await abrir();

    const secao = screen.getByRole("region", { name: "Contas com regra nova desde a análise" });
    expect(secao.textContent).toContain("31245");
    expect(within(secao).queryByRole("button", { name: "Reanalisar com a regra nova" })).toBeNull();
  });

  it("sem conta marcada, a seção não aparece", async () => {
    await abrir();

    expect(screen.queryByRole("region", { name: "Contas com regra nova desde a análise" })).toBeNull();
  });
});

describe("o Ditar ao ensinar uma regra nova (issue #1145)", () => {
  it("o campo da regra em linguagem comum tem o Ditar com o aviso de paciente ao lado", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Ensinar uma regra nova" }));

    const botao = screen.getByRole("button", { name: "Ditar: A regra, em linguagem comum" });
    expect(botao.parentElement?.textContent).toContain("Não dite nome nem dado de paciente.");
  });
});
