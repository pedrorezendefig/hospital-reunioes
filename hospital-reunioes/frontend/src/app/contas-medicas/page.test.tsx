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
let respostaDoDescarte: () => Response;
/** O que a rota Analisar de novo responde (issue #1339); por padrão, a conta vai para a fila. */
let aoAnalisarDeNovo: (url: string) => Response;
const chamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  filaDoServidor = FILA;
  permissoes = [ENVIAR, ANALISAR];
  respostaDoDescarte = () => new Response(JSON.stringify({ descartada: "erro" }));
  aoAnalisarDeNovo = () => new Response(JSON.stringify({ situacao: "NA_FILA" }));
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
      if (url.endsWith("/descartar")) return respostaDoDescarte();
      if (url.endsWith("/analisar-de-novo")) return aoAnalisarDeNovo(url);
      if (url.endsWith("/analisar-assim-mesmo")) return aoAnalisarDeNovo(url);
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

  it("o Atendimento N de cada linha da lista sai em caixa alta, a pedido do diretor (PR #1411)", async () => {
    render(<ContasMedicasPage />);

    const itens = await linhas();
    for (const item of itens) {
      expect(within(item).getByText(/^Atendimento /).className.split(" ")).toContain("uppercase");
    }
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
    expect(within(itens[1]).getByRole("link", { name: "Continuar" }).getAttribute("href")).toBe(
      "/contas-medicas/guia/retorno",
    );
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
    expect(itens[2].textContent).toContain("Processando");
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

describe("o cartão do envio (issue #1336)", () => {
  const ENVIOS: ItemDaFila[] = [
    conta({ id: "na-fila", numero_atendimento: "31302", numero_conta: "48001", prontuario_paginas: 212 }),
    conta({
      id: "falta-pront",
      numero_atendimento: "31318",
      numero_conta: "48018",
      situacao: "AGUARDANDO_ARQUIVO",
      falta: "prontuario",
    }),
    conta({
      id: "falta-conta",
      numero_atendimento: "31320",
      numero_conta: null,
      periodo_inicio: null,
      periodo_fim: null,
      situacao: "AGUARDANDO_ARQUIVO",
      falta: "conta",
      prontuario_paginas: 1,
    }),
    conta({ id: "rodando", numero_atendimento: "31310", situacao: "PROCESSANDO", prontuario_paginas: 40 }),
    conta({ id: "erro", numero_atendimento: "31260", situacao: "ERRO", erro_motivo: "Não consegui ler a conta inteira" }),
  ];

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: ENVIOS };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  function quadrado(cartao: HTMLElement, nome: "Conta" | "Prontuário"): HTMLElement {
    return within(cartao).getByRole("region", { name: nome });
  }

  it("cada conta vira um cartão com o quadrado Conta e o quadrado Prontuário", async () => {
    const itens = await cartoes();

    for (const cartao of itens) {
      expect(quadrado(cartao, "Conta")).toBeTruthy();
      expect(quadrado(cartao, "Prontuário")).toBeTruthy();
    }
  });

  it("o Atendimento N de cada cartão sai em caixa alta, a pedido do diretor (PR #1411)", async () => {
    const itens = await cartoes();

    for (const cartao of itens) {
      expect(within(cartao).getByText(/^Atendimento /).className.split(" ")).toContain("uppercase");
    }
  });

  it("o arquivo que chegou fica verde, com o número e o período da conta e as páginas do prontuário", async () => {
    const [chegou] = await cartoes();

    const daConta = quadrado(chegou, "Conta");
    const doProntuario = quadrado(chegou, "Prontuário");
    expect(daConta.getAttribute("data-estado")).toBe("chegou");
    expect(daConta.className).toContain("bg-emerald-50");
    expect(daConta.textContent).toContain("48001");
    expect(daConta.textContent).toContain("01/10 a 05/10");
    expect(doProntuario.getAttribute("data-estado")).toBe("chegou");
    expect(doProntuario.textContent).toContain("212 páginas");
    expect(chegou.textContent).not.toContain("Falta enviar");
    expect(within(chegou).queryByRole("button", { name: /^Enviar (a conta|o prontuário)$/ })).toBeNull();
  });

  it("uma página só sai no singular", async () => {
    const itens = await cartoes();

    expect(quadrado(itens[2], "Prontuário").textContent).toContain("1 página");
    expect(quadrado(itens[2], "Prontuário").textContent).not.toContain("1 páginas");
  });

  it("o arquivo que falta fica tracejado, diz Falta enviar e tem o botão só dele", async () => {
    const itens = await cartoes();

    const semProntuario = quadrado(itens[1], "Prontuário");
    expect(semProntuario.getAttribute("data-estado")).toBe("falta");
    expect(semProntuario.className).toContain("border-dashed");
    expect(semProntuario.textContent).toContain("Falta enviar");
    expect(within(semProntuario).getByRole("button", { name: "Enviar o prontuário" })).toBeTruthy();
    expect(quadrado(itens[1], "Conta").getAttribute("data-estado")).toBe("chegou");
    expect(quadrado(itens[1], "Conta").textContent).toContain("48018");

    const semConta = quadrado(itens[2], "Conta");
    expect(semConta.getAttribute("data-estado")).toBe("falta");
    expect(semConta.textContent).toContain("Falta enviar");
    expect(within(semConta).getByRole("button", { name: "Enviar a conta" })).toBeTruthy();
    expect(within(itens[2]).queryByRole("button", { name: "Enviar o prontuário" })).toBeNull();
  });

  it("o botão do quadrado que falta abre o seletor de arquivos", async () => {
    const abrir = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    const itens = await cartoes();

    fireEvent.click(within(quadrado(itens[1], "Prontuário")).getByRole("button", { name: "Enviar o prontuário" }));
    expect(abrir).toHaveBeenCalledTimes(1);
    fireEvent.click(within(quadrado(itens[2], "Conta")).getByRole("button", { name: "Enviar a conta" }));
    expect(abrir).toHaveBeenCalledTimes(2);
    abrir.mockRestore();
  });

  it("a borda do cartão segue a situação, nas cores da Ouvidoria", async () => {
    const itens = await cartoes();
    const borda = (cartao: HTMLElement) => cartao.querySelector("article")?.className ?? "";

    expect(borda(itens[0])).toContain("border-l-slate-300");
    expect(borda(itens[1])).toContain("border-l-amber-500");
    expect(borda(itens[3])).toContain("border-l-emerald-500");
    expect(borda(itens[4])).toContain("border-l-red-500");
  });

  it("no celular os quadrados ficam um embaixo do outro, lado a lado só da tela pequena para cima", async () => {
    const [cartao] = await cartoes();

    const grade = quadrado(cartao, "Conta").parentElement as HTMLElement;
    expect(grade.className.split(" ")).toEqual(expect.arrayContaining(["grid", "grid-cols-1", "sm:grid-cols-2"]));
    expect(grade.className).not.toMatch(/(^| )grid-cols-2/);
  });

  it("Fila, Minhas e Concluídas continuam na linha, sem os quadrados", async () => {
    filaDoServidor = { ...FILA, meus_envios: ENVIOS };
    render(<ContasMedicasPage />);
    await linhas();

    for (const nome of [/^Fila/, /^Minhas/, /Concluídas/]) {
      aba(nome);
      const itens = await linhas();
      for (const item of itens) {
        expect(within(item).queryByRole("region", { name: "Conta" })).toBeNull();
        expect(item.querySelector("article")).toBeNull();
      }
    }
  });
});

describe("os dados da conta e do prontuário no cartão (issue #1419)", () => {
  const ENVIOS: ItemDaFila[] = [
    conta({
      id: "na-fila",
      numero_atendimento: "31302",
      operadora: "ASSIM",
      dias_internacao: 4,
      prontuario_paginas: 1946,
      prontuario_paginas_ocr: 37,
    }),
    conta({
      id: "de-antes",
      numero_atendimento: "31303",
      operadora: "ASSIM",
      dias_internacao: 1,
      prontuario_paginas: 212,
      prontuario_paginas_ocr: null,
    }),
    // A conta que voltou para a fila guarda a nota e o valor da análise de
    // antes; as contagens o backend só manda na conta pronta, que não fica aqui.
    conta({
      id: "de-volta",
      numero_atendimento: "31304",
      operadora: "ASSIM",
      dias_internacao: 4,
      prontuario_paginas: 300,
      prontuario_paginas_ocr: 1,
      nota_entrada: 74,
      valor_apontado: 584.6,
      itens_total: 9,
    }),
    conta({ id: "sem-escaneada", numero_atendimento: "31305", prontuario_paginas: 80, prontuario_paginas_ocr: 0 }),
  ];

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: ENVIOS };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  function quadrado(cartao: HTMLElement, nome: "Conta" | "Prontuário"): HTMLElement {
    return within(cartao).getByRole("region", { name: nome });
  }

  it("o quadrado da Conta mostra a operadora e os dias de internação", async () => {
    const [naFila, deAntes] = await cartoes();

    expect(quadrado(naFila, "Conta").textContent).toContain("ASSIM");
    expect(quadrado(naFila, "Conta").textContent).toContain("4 dias de internação");
    expect(quadrado(deAntes, "Conta").textContent).toContain("1 dia de internação");
  });

  it("o quadrado do Prontuário mostra as páginas escaneadas, e o de antes desta fatia não desenha a linha", async () => {
    const [naFila, deAntes, deVolta] = await cartoes();

    expect(quadrado(naFila, "Prontuário").textContent).toContain("37 escaneadas, lidas por OCR");
    expect(quadrado(deVolta, "Prontuário").textContent).toContain("1 escaneada, lida por OCR");
    expect(quadrado(deAntes, "Prontuário").textContent).toContain("212 páginas");
    expect(quadrado(deAntes, "Prontuário").textContent).not.toMatch(/escanead|OCR/);
  });

  it("a conta pronta vai para a Fila com as contagens na linha, sem desenhar nada na que veio antes desta fatia", async () => {
    filaDoServidor = {
      ...FILA,
      fila: [
        conta({ id: "pronta", numero_atendimento: "31304", situacao: "A_FAZER", itens_lidos: 42, eventos_lidos: 15 }),
        conta({ id: "de-antes", numero_atendimento: "31303", situacao: "A_FAZER" }),
      ],
    };
    render(<ContasMedicasPage />);

    const [pronta, deAntes] = await linhas();
    expect(pronta.textContent).toContain("42 itens, 15 eventos");
    expect(deAntes.textContent).not.toMatch(/itens|eventos/);
  });

  it("o prontuário sem folha escaneada diz que nenhuma vai por OCR", async () => {
    const itens = await cartoes();

    expect(quadrado(itens[3], "Prontuário").textContent).toContain("nenhuma escaneada");
    expect(quadrado(itens[3], "Prontuário").textContent).not.toContain("0 escaneadas");
  });

  it("nenhum valor em reais aparece no cartão", async () => {
    const itens = await cartoes();

    for (const cartao of itens) {
      expect(cartao.textContent).not.toContain("R$");
      expect(cartao.textContent).not.toContain("584,60");
    }
  });
});

describe("o Código do erro no cartão (issue #1337)", () => {
  const DETALHE = "OverloadedError, HTTP 529, etapa passo_a (leitura do prontuário pela IA), ia.py:497";
  const ENVIOS: ItemDaFila[] = [
    conta({
      id: "erro-ia",
      numero_atendimento: "31260",
      numero_conta: "48001",
      situacao: "ERRO",
      prontuario_paginas: 212,
      erro_motivo: "A IA está fora do ar ou sobrecarregada agora.",
      erro_codigo: "CM-IA-FORA-DO-AR",
      erro_detalhe: DETALHE,
      erro_em: "2026-11-01T17:32:00+00:00",
      erro_arquivo: "prontuario",
      erro_acao: "analisar_de_novo",
    }),
    conta({
      id: "erro-conta",
      numero_atendimento: "31261",
      numero_conta: "48002",
      situacao: "ERRO",
      prontuario_paginas: 40,
      erro_motivo: "Não consegui ler a conta inteira: os itens lidos somam R$ 3.091,70 e o total da conta é R$ 3.101,70.",
      erro_codigo: "CM-ARQ-SOMA",
      erro_detalhe: "FalhaDeLeitura, etapa leitura_da_conta (leitura da conta), processamento.py:396",
      erro_em: "2026-11-01T12:05:00+00:00",
      erro_arquivo: "conta",
      erro_acao: "enviar_de_novo",
    }),
    conta({ id: "na-fila", numero_atendimento: "31302", prontuario_paginas: 10 }),
  ];

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: ENVIOS };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  function quadrado(cartao: HTMLElement, nome: "Conta" | "Prontuário"): HTMLElement {
    return within(cartao).getByRole("region", { name: nome });
  }

  function areaDeTransferencia(writeText: (texto: string) => Promise<void>) {
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  }

  it("o quadrado do arquivo em que a análise parou fica vermelho, e o outro continua verde", async () => {
    const [daIA, daConta] = await cartoes();

    expect(quadrado(daIA, "Prontuário").getAttribute("data-estado")).toBe("erro");
    expect(quadrado(daIA, "Prontuário").className).toContain("bg-red-50");
    expect(quadrado(daIA, "Prontuário").textContent).toContain("212 páginas");
    expect(quadrado(daIA, "Conta").getAttribute("data-estado")).toBe("chegou");
    expect(quadrado(daConta, "Conta").getAttribute("data-estado")).toBe("erro");
    expect(quadrado(daConta, "Conta").textContent).toContain("48002");
    expect(quadrado(daConta, "Prontuário").getAttribute("data-estado")).toBe("chegou");
  });

  it("a frase e o código aparecem embaixo dos quadrados", async () => {
    const [daIA, daConta] = await cartoes();

    expect(daIA.textContent).toContain("A IA está fora do ar ou sobrecarregada agora.");
    expect(within(daIA).getByText("CM-IA-FORA-DO-AR")).toBeTruthy();
    expect(daConta.textContent).toContain("os itens lidos somam R$ 3.091,70 e o total da conta é R$ 3.101,70.");
    expect(within(daConta).getByText("CM-ARQ-SOMA")).toBeTruthy();
  });

  it("Ver detalhes abre o detalhe técnico para a TI", async () => {
    const [daIA] = await cartoes();
    const ver = within(daIA).getByRole("button", { name: "Ver detalhes" });
    expect(ver.getAttribute("aria-expanded")).toBe("false");
    expect(daIA.textContent).not.toContain(DETALHE);

    fireEvent.click(ver);

    expect(ver.getAttribute("aria-expanded")).toBe("true");
    expect(daIA.textContent).toContain(DETALHE);
  });

  it("Copiar para a TI leva o código, o atendimento, a conta, a data e a hora e o detalhe", async () => {
    const writeText = vi.fn<(texto: string) => Promise<void>>(async () => {});
    areaDeTransferencia(writeText);
    const [daIA] = await cartoes();

    fireEvent.click(within(daIA).getByRole("button", { name: "Copiar para a TI" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toBe(
      [
        "Código do erro: CM-IA-FORA-DO-AR",
        "Atendimento: 31260",
        "Conta: 48001",
        "Data e hora: 01/11/2026 14:32",
        `Detalhe: ${DETALHE}`,
      ].join("\n"),
    );
    expect(await within(daIA).findByText("Copiado. Cole na conversa com a TI.")).toBeTruthy();
  });

  it("quando o navegador não copia, o texto fica numa caixa para copiar à mão", async () => {
    areaDeTransferencia(async () => {
      throw new Error("negado");
    });
    const [, daConta] = await cartoes();

    fireEvent.click(within(daConta).getByRole("button", { name: "Copiar para a TI" }));

    const caixa = (await within(daConta).findByRole("textbox")) as HTMLTextAreaElement;
    expect(caixa.value).toContain("Código do erro: CM-ARQ-SOMA");
    expect(caixa.value).toContain("Data e hora: 01/11/2026 09:05");
    expect(daConta.textContent).toContain("copie com Ctrl+C");
  });

  it("a folha digitalizada que não deu para ler deixa o prontuário vermelho, com a frase, o código e Enviar de novo (issue #1400)", async () => {
    const frase =
      "Não dá para analisar esta conta: a ficha de anestesia (página 214) é uma folha digitalizada que não consegui ler. Digitalize de novo, com a folha em pé, e envie o prontuário de novo.";
    filaDoServidor = {
      ...FILA,
      meus_envios: [
        conta({
          id: "erro-digitalizada",
          numero_atendimento: "31262",
          numero_conta: "48003",
          situacao: "ERRO",
          prontuario_paginas: 300,
          erro_motivo: frase,
          erro_codigo: "CM-ARQ-DIGITALIZADO",
          erro_detalhe: "FalhaDeLeitura, etapa leitura_do_prontuario (leitura do prontuário), processamento.py:441",
          erro_em: "2026-11-03T12:05:00+00:00",
          erro_arquivo: "prontuario",
          erro_acao: "enviar_de_novo",
        }),
      ],
    };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    const [cartao] = await linhas();

    expect(quadrado(cartao, "Prontuário").getAttribute("data-estado")).toBe("erro");
    expect(quadrado(cartao, "Conta").getAttribute("data-estado")).toBe("chegou");
    expect(cartao.textContent).toContain(frase);
    expect(within(cartao).getByText("CM-ARQ-DIGITALIZADO")).toBeTruthy();
    expect(within(cartao).getByRole("button", { name: "Enviar de novo" })).toBeTruthy();
    expect(within(cartao).queryByRole("button", { name: "Analisar de novo" })).toBeNull();
  });

  it("a conta que não está em Erro não tem código nem os botões da TI", async () => {
    const itens = await cartoes();

    expect(within(itens[2]).queryByRole("button", { name: "Ver detalhes" })).toBeNull();
    expect(within(itens[2]).queryByRole("button", { name: "Copiar para a TI" })).toBeNull();
    expect(quadrado(itens[2], "Conta").getAttribute("data-estado")).toBe("chegou");
  });
});

describe("Descartar um envio (issue #1338)", () => {
  const ENVIOS: ItemDaFila[] = [
    conta({ id: "erro", numero_atendimento: "31260", situacao: "ERRO", pode_descartar: true }),
    conta({ id: "falta-pront", numero_atendimento: "31318", situacao: "AGUARDANDO_ARQUIVO", falta: "prontuario", pode_descartar: true }),
    conta({ id: "falta-conta", numero_atendimento: "31320", situacao: "AGUARDANDO_ARQUIVO", falta: "conta", pode_descartar: true }),
    conta({ id: "na-fila", numero_atendimento: "31302", situacao: "NA_FILA", pode_descartar: false }),
    conta({ id: "rodando", numero_atendimento: "31310", situacao: "PROCESSANDO", pode_descartar: false }),
    // O envio de outra pessoa que a lista trouxesse sem permissão de descartar.
    conta({ id: "da-outra", numero_atendimento: "31330", situacao: "ERRO", pode_descartar: false }),
  ];

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: ENVIOS };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  const descartes = () => chamadas.filter((c) => c.url.endsWith("/descartar"));

  afterEach(() => vi.restoreAllMocks());

  it("o botão aparece no Erro e no arquivo faltando que a pessoa pode descartar, e em nenhum outro", async () => {
    const itens = await cartoes();
    const tem = (cartao: HTMLElement) => within(cartao).queryByRole("button", { name: "Descartar" }) !== null;

    expect(itens.map(tem)).toEqual([true, true, true, false, false, false]);
  });

  it("pergunta antes de apagar, e cancelar não apaga nada", async () => {
    const perguntar = vi.spyOn(window, "confirm").mockReturnValue(false);
    const itens = await cartoes();

    fireEvent.click(within(itens[0]).getByRole("button", { name: "Descartar" }));

    expect(perguntar).toHaveBeenCalledWith("Descartar o atendimento 31260? Os arquivos serão apagados.");
    await new Promise((r) => setTimeout(r, 0));
    expect(descartes()).toEqual([]);
  });

  it("confirmado, chama a rota da conta e relê a lista", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const itens = await cartoes();
    const leiturasAntes = chamadas.filter((c) => c.url === "/api/contas-medicas/meus-envios").length;

    fireEvent.click(within(itens[1]).getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(descartes()).toHaveLength(1));
    const [descarte] = descartes();
    expect(descarte.url).toBe("/api/contas-medicas/contas/falta-pront/descartar");
    expect(descarte.init?.method).toBe("POST");
    expect(new Headers(descarte.init?.headers).get("Authorization")).toBe("Bearer token-de-teste");
    await waitFor(() =>
      expect(chamadas.filter((c) => c.url === "/api/contas-medicas/meus-envios").length).toBeGreaterThan(leiturasAntes),
    );
  });

  it("a recusa do servidor aparece com a frase dele", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    respostaDoDescarte = () =>
      new Response(JSON.stringify({ detail: "A conta já tem Guia e não pode ser descartada." }), { status: 409 });
    const itens = await cartoes();

    fireEvent.click(within(itens[0]).getByRole("button", { name: "Descartar" }));

    expect((await screen.findByRole("alert")).textContent).toContain("A conta já tem Guia e não pode ser descartada.");
  });
});

describe("Analisar de novo sem anexar o PDF (issue #1339)", () => {
  const DA_IA = conta({
    id: "erro-ia",
    numero_atendimento: "31260",
    situacao: "ERRO",
    erro_motivo: "A IA está fora do ar ou sobrecarregada agora.",
    erro_codigo: "CM-IA-FORA-DO-AR",
    erro_arquivo: "prontuario",
    erro_acao: "analisar_de_novo",
  });
  const DO_ARQUIVO = conta({
    id: "erro-conta",
    numero_atendimento: "31261",
    situacao: "ERRO",
    erro_motivo: "Não consegui ler a conta inteira",
    erro_codigo: "CM-ARQ-SOMA",
    erro_arquivo: "conta",
    erro_acao: "enviar_de_novo",
  });

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: [DA_IA, DO_ARQUIVO] };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  it("o erro da IA mostra Analisar de novo no lugar de Enviar de novo, e o erro do arquivo continua com Enviar de novo", async () => {
    const [daIA, doArquivo] = await cartoes();

    expect(within(daIA).getByRole("button", { name: "Analisar de novo" })).toBeTruthy();
    expect(within(daIA).queryByRole("button", { name: "Enviar de novo" })).toBeNull();
    expect(within(doArquivo).getByRole("button", { name: "Enviar de novo" })).toBeTruthy();
    expect(within(doArquivo).queryByRole("button", { name: "Analisar de novo" })).toBeNull();
  });

  it("o clique chama a rota da conta, sem arquivo, e o cartão passa para Na fila", async () => {
    aoAnalisarDeNovo = () => {
      filaDoServidor = {
        ...FILA,
        meus_envios: [conta({ id: "erro-ia", numero_atendimento: "31260", situacao: "NA_FILA" }), DO_ARQUIVO],
      };
      return new Response(JSON.stringify({ situacao: "NA_FILA" }));
    };
    const [daIA] = await cartoes();

    fireEvent.click(within(daIA).getByRole("button", { name: "Analisar de novo" }));

    await waitFor(async () => expect((await linhas())[0].textContent).toContain("Na fila"));
    const chamada = chamadas.find((c) => c.url.endsWith("/analisar-de-novo"));
    expect(chamada?.url).toBe("/api/contas-medicas/contas/erro-ia/analisar-de-novo");
    expect(chamada?.init?.method).toBe("POST");
    expect(chamada?.init?.body).toBeUndefined();
    expect((chamada?.init?.headers as Record<string, string>).Authorization).toBe("Bearer token-de-teste");
    expect(within((await linhas())[0]).queryByRole("button", { name: "Analisar de novo" })).toBeNull();
  });

  it("a recusa do servidor aparece no cartão com a frase dele", async () => {
    aoAnalisarDeNovo = () =>
      new Response(JSON.stringify({ detail: "O PDF já passou dos 7 dias e saiu do sistema. Envie de novo." }), {
        status: 409,
      });
    const [daIA] = await cartoes();

    fireEvent.click(within(daIA).getByRole("button", { name: "Analisar de novo" }));

    expect((await within(daIA).findByRole("alert")).textContent).toBe(
      "O PDF já passou dos 7 dias e saiu do sistema. Envie de novo.",
    );
  });

  it("Descartar convive com Analisar de novo e com Enviar de novo no cartão em Erro (issues #1338 e #1339)", async () => {
    filaDoServidor = {
      ...FILA,
      meus_envios: [{ ...DA_IA, pode_descartar: true }, { ...DO_ARQUIVO, pode_descartar: true }],
    };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    const [daIA, doArquivo] = await linhas();
    const botoes = (cartao: HTMLElement) =>
      within(cartao)
        .getAllByRole("button")
        .map((b) => b.textContent)
        .filter((t) => t === "Analisar de novo" || t === "Enviar de novo" || t === "Descartar");

    expect(botoes(daIA)).toEqual(["Analisar de novo", "Descartar"]);
    expect(botoes(doArquivo)).toEqual(["Enviar de novo", "Descartar"]);
  });
});

describe("Analisar assim mesmo a conta parada por folha escaneada ilegível (issue #1401)", () => {
  const DIGITALIZADO = conta({
    id: "erro-digitalizado",
    numero_atendimento: "31262",
    situacao: "ERRO",
    erro_motivo: "Não dá para analisar esta conta: 3 das 10 páginas do prontuário deste período são folhas digitalizadas que não consegui ler.",
    erro_codigo: "CM-ARQ-DIGITALIZADO",
    erro_arquivo: "prontuario",
    erro_acao: "enviar_de_novo",
    pode_analisar_assim_mesmo: true,
  });
  const SEM_PODER = { ...DIGITALIZADO, id: "erro-vencido", numero_atendimento: "31263", pode_analisar_assim_mesmo: false };
  const DO_ARQUIVO = conta({
    id: "erro-conta",
    numero_atendimento: "31261",
    situacao: "ERRO",
    erro_motivo: "Não consegui ler a conta inteira",
    erro_codigo: "CM-ARQ-SOMA",
    erro_arquivo: "conta",
    erro_acao: "enviar_de_novo",
  });

  async function cartoes(): Promise<HTMLElement[]> {
    filaDoServidor = { ...FILA, meus_envios: [DIGITALIZADO, SEM_PODER, DO_ARQUIVO] };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);
    return linhas();
  }

  const botoes = (cartao: HTMLElement) =>
    within(cartao)
      .getAllByRole("button")
      .map((b) => b.textContent)
      .filter((t) => t === "Analisar assim mesmo" || t === "Analisar de novo" || t === "Enviar de novo");

  it("aparece ao lado de Enviar de novo só quando o servidor deixa", async () => {
    const [digitalizado, semPoder, doArquivo] = await cartoes();

    expect(botoes(digitalizado)).toEqual(["Enviar de novo", "Analisar assim mesmo"]);
    expect(botoes(semPoder)).toEqual(["Enviar de novo"]);
    expect(botoes(doArquivo)).toEqual(["Enviar de novo"]);
  });

  it("o clique chama a rota da conta, sem arquivo, e o cartão passa para Na fila", async () => {
    aoAnalisarDeNovo = () => {
      filaDoServidor = {
        ...FILA,
        meus_envios: [conta({ id: "erro-digitalizado", numero_atendimento: "31262", situacao: "NA_FILA" })],
      };
      return new Response(JSON.stringify({ situacao: "NA_FILA" }));
    };
    const [digitalizado] = await cartoes();

    fireEvent.click(within(digitalizado).getByRole("button", { name: "Analisar assim mesmo" }));

    await waitFor(async () => expect((await linhas())[0].textContent).toContain("Na fila"));
    const chamada = chamadas.find((c) => c.init?.method === "POST");
    expect(chamada?.url).toBe("/api/contas-medicas/contas/erro-digitalizado/analisar-assim-mesmo");
    expect(chamada?.init?.body).toBeUndefined();
    expect((chamada?.init?.headers as Record<string, string>).Authorization).toBe("Bearer token-de-teste");
  });

  it("a recusa do servidor aparece no cartão com a frase dele", async () => {
    aoAnalisarDeNovo = () =>
      new Response(JSON.stringify({ detail: "O PDF já passou dos 7 dias e saiu do sistema. Envie de novo." }), {
        status: 409,
      });
    const [digitalizado] = await cartoes();

    fireEvent.click(within(digitalizado).getByRole("button", { name: "Analisar assim mesmo" }));

    expect((await within(digitalizado).findByRole("alert")).textContent).toBe(
      "O PDF já passou dos 7 dias e saiu do sistema. Envie de novo.",
    );
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

describe("o Processamento visível (issue #1416)", () => {
  // Quatro minutos e uns segundos antes: a pílula diz "há 4 min".
  const DESDE = new Date(Date.now() - 4 * 60_000 - 5_000).toISOString();
  const RODANDO = conta({
    id: "rodando",
    numero_atendimento: "31310",
    situacao: "PROCESSANDO",
    etapa: "IA_LENDO_PRONTUARIO",
    parte: 3,
    partes: 7,
    processando_desde: DESDE,
    tentativa: 2,
  });
  const ESPERANDO = conta({ id: "na-fila", numero_atendimento: "31302", situacao: "NA_FILA" });

  function leiturasDosEnvios(): number {
    return chamadas.filter((c) => c.url === "/api/contas-medicas/meus-envios").length;
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it("a pílula diz Processando, a etapa, a parte e o tempo, e o cartão diz a tentativa", async () => {
    filaDoServidor = { ...FILA, meus_envios: [RODANDO] };
    render(<ContasMedicasPage />);
    await linhas();
    aba(/^Meus envios/);

    const [cartao] = await linhas();

    expect(cartao.textContent).toContain("Processando, IA lendo o prontuário, parte 3 de 7, há 4 min");
    expect(cartao.textContent).toContain("tentativa 2 de 3");
    expect(cartao.textContent).not.toContain("Pronta em instantes");
  });

  it("com conta Processando, a tela relê a cada 5 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    filaDoServidor = { ...FILA, meus_envios: [RODANDO, ESPERANDO] };
    render(<ContasMedicasPage />);
    await linhas();
    const antes = leiturasDosEnvios();

    await vi.advanceTimersByTimeAsync(5_000);

    expect(leiturasDosEnvios()).toBe(antes + 1);
  });

  it("sem nenhuma conta Processando, a tela relê a cada 20 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    filaDoServidor = { ...FILA, meus_envios: [ESPERANDO] };
    render(<ContasMedicasPage />);
    await linhas();
    const antes = leiturasDosEnvios();

    await vi.advanceTimersByTimeAsync(5_000);
    expect(leiturasDosEnvios()).toBe(antes);

    await vi.advanceTimersByTimeAsync(15_000);
    expect(leiturasDosEnvios()).toBe(antes + 1);
  });

  it("a conta que some da lista por ter ficado pronta avisa que foi para a Fila", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    filaDoServidor = { ...FILA, meus_envios: [RODANDO, ESPERANDO] };
    render(<ContasMedicasPage />);
    await linhas();
    expect(screen.queryByText(/foi para a Fila/)).toBeNull();

    filaDoServidor = { ...FILA, meus_envios: [ESPERANDO] };
    await vi.advanceTimersByTimeAsync(5_000);

    expect((await screen.findByText(/foi para a Fila/)).textContent).toBe("Atendimento 31310 pronto, foi para a Fila");
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
