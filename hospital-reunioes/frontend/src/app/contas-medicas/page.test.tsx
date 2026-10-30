/**
 * @vitest-environment jsdom
 */

/**
 * A tela Contas de Contas médicas (issues #1114, #1123 e #1308, PRD #1113).
 *
 * A tela não decide nada: o servidor pareia, recusa e ordena. O que se trava
 * aqui é o que a faturista vê (a fila, as situações, o "Último envio"), o que
 * soltar os arquivos dispara (a rota e os arquivos no corpo) e que cada bloco
 * aparece pela permissão que `/contas-medicas/me` devolve.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Fila, ItemDaFila, RespostaDoEnvio } from "@/lib/contas-medicas/envio";

import ContasMedicasPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

function conta(campos: Partial<ItemDaFila>): ItemDaFila {
  return {
    id: "c-1",
    numero_atendimento: "31302",
    numero_conta: "48001",
    situacao: "NA_FILA",
    falta: null,
    periodo_inicio: "2026-10-01",
    periodo_fim: "2026-10-05",
    nota_entrada: null,
    valor_apontado: null,
    itens_feitos: 0,
    itens_total: 0,
    pendencias: 0,
    erro_motivo: null,
    ...campos,
  };
}

const FILA: Fila = {
  todas: false,
  fila: [
    conta({
      id: "a-fazer",
      numero_atendimento: "31245",
      numero_conta: "48811",
      situacao: "A_FAZER",
      nota_entrada: 74,
      valor_apontado: 584.6,
      itens_total: 9,
    }),
    conta({ id: "a-fazer-2", numero_atendimento: "31246", situacao: "A_FAZER" }),
  ],
  minhas: [
    conta({ id: "em-correcao", numero_atendimento: "31250", situacao: "EM_CORRECAO", itens_feitos: 3, itens_total: 5 }),
    conta({ id: "retorno", numero_atendimento: "31251", situacao: "RETORNO" }),
  ],
  meus_envios: [
    conta({ id: "na-fila", numero_atendimento: "31302", situacao: "NA_FILA" }),
    conta({ id: "falta", numero_atendimento: "31318", numero_conta: "48018", situacao: "AGUARDANDO_ARQUIVO", falta: "prontuario" }),
    conta({ id: "rodando", numero_atendimento: "31310", situacao: "PROCESSANDO" }),
    conta({ id: "erro", numero_atendimento: "31260", situacao: "ERRO", erro_motivo: "Não consegui ler a conta inteira" }),
  ],
  concluidas: [
    conta({ id: "feita", numero_atendimento: "31200", situacao: "CONCLUIDA_COM_PENDENCIA", nota_entrada: 80, pendencias: 2 }),
  ],
};

const RESPOSTA_DO_ENVIO: RespostaDoEnvio = {
  envio_id: "envio-1",
  ultimo_envio: [
    { numero_atendimento: "31302", frase: "conta e prontuário", texto: "31302, conta e prontuário", aviso: null },
    {
      numero_atendimento: "31310",
      frase: "2 parciais e prontuário",
      texto: "31310, 2 parciais e prontuário",
      aviso: "O período da conta vai até 20/10/2026 e o prontuário no sistema, até 10/10/2026. Envie o prontuário atualizado.",
    },
    { numero_atendimento: "31318", frase: "falta o prontuário", texto: "31318, falta o prontuário", aviso: null },
  ],
  recusas: [{ arquivo: "conta-unimed.pdf", numero_atendimento: "31399", motivo: "Plano UNIMED RIO ENF ainda não configurado" }],
};

const ENVIAR = "enviar_contas";
const ANALISAR = "enviar_corrigir_contas";

let filaDoServidor: Fila;
let permissoes: string[];
const chamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  filaDoServidor = FILA;
  permissoes = [ENVIAR, ANALISAR];
  chamadas.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      // Cada rota devolve só as listas dela, como o backend (issue #1308).
      const { todas, fila, minhas, meus_envios, concluidas } = filaDoServidor;
      if (url === "/api/contas-medicas/fila") return new Response(JSON.stringify({ todas, fila, minhas, concluidas }));
      if (url === "/api/contas-medicas/meus-envios") return new Response(JSON.stringify({ todas, meus_envios }));
      if (url === "/api/contas-medicas/envios") return new Response(JSON.stringify(RESPOSTA_DO_ENVIO));
      if (url === "/api/contas-medicas/me") return new Response(JSON.stringify({ perfil: "faturista", permissoes }));
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function pdf(nome: string): File {
  return new File(["%PDF-1.4"], nome, { type: "application/pdf" });
}

async function linhas(): Promise<HTMLElement[]> {
  const fila = await screen.findByRole("region", { name: "Fila de contas" });
  await waitFor(() => expect(within(fila).getAllByRole("listitem").length).toBeGreaterThan(0));
  return within(fila).getAllByRole("listitem");
}

function aba(nome: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name: nome }));
}

describe("a fila comum", () => {
  it("sem nenhuma conta livre, diz isso com todas as letras", async () => {
    filaDoServidor = { todas: false, fila: [], minhas: [], meus_envios: [], concluidas: [] };
    render(<ContasMedicasPage />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Contas médicas");
    const fila = await screen.findByRole("region", { name: "Fila de contas" });
    await waitFor(() => expect(fila.textContent).toContain("Nenhuma conta livre na fila"));
  });

  it("as quatro abas trazem a contagem de cada lista", async () => {
    render(<ContasMedicasPage />);
    await linhas();

    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Fila (2)",
      "Minhas (2)",
      "Meus envios (4)",
      "Concluídas (1)",
    ]);
  });

  it("a Fila mostra as livres pelo atendimento, na ordem do servidor, e Abrir puxa a conta pelo Guia", async () => {
    render(<ContasMedicasPage />);

    const itens = await linhas();
    expect(itens.map((li) => within(li).getByText(/^Atendimento /).textContent)).toEqual([
      "Atendimento 31245",
      "Atendimento 31246",
    ]);
    expect(itens[0].textContent).toContain("conta 48811");
    expect(itens[0].textContent).toContain("A fazer");
    expect(itens[0].textContent).toContain("Nota 74, R$ 584,60, 0 de 9");
    expect(within(itens[0]).getByRole("link", { name: "Abrir" }).getAttribute("href")).toBe(
      "/contas-medicas/guia/a-fazer",
    );
  });

  it("Minhas mostra as que a faturista puxou, com Continuar", async () => {
    render(<ContasMedicasPage />);
    await linhas();

    aba(/^Minhas/);

    const itens = await linhas();
    expect(itens.map((li) => within(li).getByText(/^Atendimento /).textContent)).toEqual([
      "Atendimento 31250",
      "Atendimento 31251",
    ]);
    expect(within(itens[0]).getByRole("link", { name: "Continuar" }).getAttribute("href")).toBe(
      "/contas-medicas/guia/em-correcao",
    );
    expect(itens[1].textContent).toContain("Retorno");
  });

  it("Meus envios mostra o que ainda não ficou pronto, e o erro traz o motivo com Enviar de novo", async () => {
    render(<ContasMedicasPage />);
    await linhas();

    aba(/^Meus envios/);

    const itens = await linhas();
    expect(itens.map((li) => within(li).getByText(/^Atendimento /).textContent)).toEqual([
      "Atendimento 31302",
      "Atendimento 31318",
      "Atendimento 31310",
      "Atendimento 31260",
    ]);
    expect(itens[0].textContent).toContain("Na fila");
    expect(itens[1].textContent).toContain("Falta o prontuário");
    expect(itens[2].textContent).toContain("Pronta em instantes");
    expect(itens[3].textContent).toContain("Não consegui ler a conta inteira");
    expect(within(itens[3]).getByRole("button", { name: "Enviar de novo" })).toBeTruthy();
    expect(within(itens[0]).queryByRole("button", { name: "Enviar de novo" })).toBeNull();
    expect(within(itens[0]).queryByRole("link")).toBeNull();
  });

  it("Enviar de novo abre o seletor de arquivos", async () => {
    const abrir = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    const itens = await linhas();

    fireEvent.click(within(itens[3]).getByRole("button", { name: "Enviar de novo" }));

    expect(abrir).toHaveBeenCalled();
    abrir.mockRestore();
  });

  it("a aba Concluídas mostra as concluídas, com as pendências", async () => {
    render(<ContasMedicasPage />);
    await linhas();

    aba(/Concluídas/);

    const itens = await linhas();
    expect(itens).toHaveLength(1);
    expect(itens[0].textContent).toContain("Atendimento 31200");
    expect(itens[0].textContent).toContain("Concluída com pendência");
    expect(itens[0].textContent).toContain("Nota 80, 2 pendências");
  });

  it("quem tem o painel completo vê com quem está cada conta", async () => {
    filaDoServidor = {
      ...FILA,
      todas: true,
      minhas: [conta({ id: "da-ana", numero_atendimento: "31250", situacao: "EM_CORRECAO", com: "Ana Faturista" })],
    };
    render(<ContasMedicasPage />);
    await linhas();

    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Fila (2)",
      "Em análise (1)",
      "Envios (4)",
      "Concluídas (1)",
    ]);
    aba(/^Em análise/);

    const [item] = await linhas();
    expect(item.textContent).toContain("com Ana Faturista");
  });
});

describe("cada bloco pela permissão de /contas-medicas/me", () => {
  it("quem só envia vê o envio e Meus envios, e a tela nem pede a Fila", async () => {
    permissoes = [ENVIAR];
    render(<ContasMedicasPage />);

    const itens = await linhas();

    expect(screen.getByRole("region", { name: "Envio de contas" })).toBeTruthy();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Meus envios (4)"]);
    expect(within(itens[0]).getByText(/^Atendimento /).textContent).toBe("Atendimento 31302");
    expect(chamadas.some((c) => c.url === "/api/contas-medicas/fila")).toBe(false);
  });

  it("quem só analisa vê Fila, Minhas e Concluídas, sem o envio e sem Meus envios", async () => {
    permissoes = [ANALISAR];
    render(<ContasMedicasPage />);

    await linhas();

    expect(screen.queryByRole("region", { name: "Envio de contas" })).toBeNull();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Fila (2)", "Minhas (2)", "Concluídas (1)"]);
    expect(chamadas.some((c) => c.url === "/api/contas-medicas/meus-envios")).toBe(false);
  });

  it("quem não tem nenhuma das duas (o credenciamento) não vê envio nem lista", async () => {
    permissoes = ["contratos_avisos"];
    render(<ContasMedicasPage />);

    await waitFor(() => expect(chamadas.some((c) => c.url === "/api/contas-medicas/me")).toBe(true));

    await waitFor(() => expect(screen.queryByText("Carregando a fila")).toBeNull());
    expect(screen.queryByRole("region", { name: "Envio de contas" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Fila de contas" })).toBeNull();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("quem tem as duas vê o envio e as quatro abas", async () => {
    render(<ContasMedicasPage />);

    await linhas();

    expect(screen.getByRole("region", { name: "Envio de contas" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(4);
  });
});

describe("o envio", () => {
  it("soltar os PDFs envia todos e mostra o Último envio com as recusas", async () => {
    render(<ContasMedicasPage />);
    await linhas();
    const area = screen.getByRole("region", { name: "Envio de contas" });

    fireEvent.drop(area, { dataTransfer: { files: [pdf("conta.pdf"), pdf("prontuario.pdf")] } });

    const ultimo = await screen.findByRole("region", { name: "Último envio" });
    await waitFor(() => expect(ultimo.textContent).toContain("31302, conta e prontuário"));
    expect(ultimo.textContent).toContain("31310, 2 parciais e prontuário");
    expect(ultimo.textContent).toContain("31318, falta o prontuário");
    expect(ultimo.textContent).toContain("Envie o prontuário atualizado.");
    expect(ultimo.textContent).toContain("Plano UNIMED RIO ENF ainda não configurado");
    expect(ultimo.textContent).toContain("conta-unimed.pdf");

    const envio = chamadas.find((c) => c.url === "/api/contas-medicas/envios");
    expect(envio?.init?.method).toBe("POST");
    expect(((envio?.init?.body as FormData).getAll("arquivos") as File[]).map((f) => f.name)).toEqual([
      "conta.pdf",
      "prontuario.pdf",
    ]);
    await waitFor(() => expect(chamadas.filter((c) => c.url === "/api/contas-medicas/meus-envios")).toHaveLength(2));
  });

  it("Selecionar arquivos envia o que foi escolhido", async () => {
    render(<ContasMedicasPage />);
    await linhas();

    fireEvent.change(screen.getByLabelText("Arquivos da conta e do prontuário"), {
      target: { files: [pdf("conta.pdf")] },
    });

    const ultimo = await screen.findByRole("region", { name: "Último envio" });
    await waitFor(() => expect(ultimo.textContent).toContain("31302, conta e prontuário"));
    expect(screen.getByRole("button", { name: "Selecionar arquivos" })).toBeTruthy();
  });
});
