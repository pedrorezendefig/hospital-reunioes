/**
 * @vitest-environment jsdom
 */

/**
 * A tela Coordenação de Contas médicas (issue #1143, PRD #1129).
 *
 * Três números no topo, a lista por conta com os lembretes (cenário, data e
 * setor, evidência, insumos que faltam com o código que copia, quantidade e
 * valor), os botões Incluído e Não se aplica com a observação opcional, e a
 * aba Cenários só para quem cadastra, com a proposta da IA e o código fora da
 * tabela apontado. O backend é um dublê que responde por rota: quem decide é
 * ele. O que se confere aqui é a fiação.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AbaDeCenarios, Conferencia } from "@/lib/contas-medicas/coordenacao";

import { ToastProvider } from "@/components/ui/Toast";

import CoordenacaoPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ROTA = "/api/contas-medicas/coordenacao";

function conferencia(podeCadastrar: boolean): Conferencia {
  return {
    numeros: { lembretes_abertos: 2, contas_com_lembrete: 1, valor_a_conferir: 37.5 },
    pode_cadastrar: podeCadastrar,
    contas: [
      {
        conta_id: "conta-1",
        numero_atendimento: "31245",
        paciente_rotulo: "Maria S.",
        numero_conta: "48811",
        operadora: "ALFA",
        situacao: "CONCLUIDA",
        concluida_em: "2026-10-09T14:00:00+00:00",
        periodo_inicio: "2026-10-02",
        periodo_fim: "2026-10-06",
        lembretes: [
          {
            id: "lembrete-1",
            cenario: { codigo: "CEN-001", nome: "Sondagem vesical com equipo", orientacao: "Confira o equipo do dia." },
            data: "2026-10-03",
            setor: "CTI ADULTO",
            evidencia_pagina: 2,
            evidencia_trecho: "Chegou com acesso venoso periférico",
            etiquetas: [],
            criado_em: "2026-10-12T10:00:00+00:00",
            insumos: [
              { codigo: "70000002", descricao: "EQUIPO MACROGOTAS", quantidade: 2, preco_tabela: 12.5, valor: 25 },
            ],
          },
          {
            id: "lembrete-2",
            cenario: { codigo: "CEN-003", nome: "Lidocaína gel", orientacao: null },
            data: "2026-10-04",
            setor: null,
            evidencia_pagina: 5,
            evidencia_trecho: "Sondagem com lidocaína",
            etiquetas: ["conferir evidência"],
            criado_em: "2026-10-12T10:00:01+00:00",
            insumos: [
              { codigo: "70000003", descricao: "LIDOCAINA GEL", quantidade: 1, preco_tabela: 12.5, valor: 12.5 },
            ],
          },
        ],
      },
    ],
  };
}

const ABA: AbaDeCenarios = {
  operadoras: [{ sigla: "ALFA", nome: "Alfa Saúde" }],
  cenarios: [
    {
      id: "cn-1",
      codigo: "CEN-001",
      nome: "Sondagem vesical com equipo",
      operadora_sigla: null,
      gatilho_texto: "Cateterismo vesical",
      orientacao: "Confira o equipo do dia.",
      ativo: true,
      insumos: [{ codigo: "70000002", descricao: "EQUIPO MACROGOTAS", quantidade: 2 }],
    },
  ],
};

const PROPOSTA = {
  campos: {
    nome: "Lidocaína gel em sondagem ou cirurgia",
    operadora_sigla: null,
    gatilho_texto: "Cateterismo vesical, ou cirurgia com lidocaína gel",
    orientacao: null,
    ativo: true,
    insumos: [
      { codigo: "70000001", descricao: "AGULHA", quantidade: 1, na_tabela: true },
      { codigo: "79999999", descricao: "COLETOR DE URINA", quantidade: 1, na_tabela: false },
    ],
  },
  codigos_fora_da_tabela: ["79999999"],
};

type Pedido = { url: string; metodo: string; corpo: unknown };

function servidor(podeCadastrar = false) {
  const pedidos: Pedido[] = [];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const metodo = init?.method ?? "GET";
    pedidos.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
    let corpo: unknown = {};
    if (url === ROTA) corpo = conferencia(podeCadastrar);
    else if (url === `${ROTA}/cenarios` && metodo === "GET") corpo = ABA;
    else if (url === `${ROTA}/cenarios/proposta`) corpo = PROPOSTA;
    else if (url.startsWith(`${ROTA}/cenarios`)) corpo = { cenario: ABA.cenarios[0], codigos_fora_da_tabela: ["79999999"] };
    else if (url.includes("/marcacao")) corpo = { id: "lembrete-1", estado: "INCLUIDO" };
    return { ok: true, status: metodo === "POST" && url === `${ROTA}/cenarios` ? 201 : 200, json: async () => corpo };
  });
  vi.stubGlobal("fetch", fetch);
  return pedidos;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// O Toast é o de verdade: o Ditar avisa por ele (issue #1145).
function abrir() {
  render(
    <ToastProvider>
      <CoordenacaoPage />
    </ToastProvider>,
  );
}

describe("a tela Coordenação", () => {
  it("mostra os três números e os lembretes por conta, com evidência, código e valor", async () => {
    servidor();
    const copiar = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: copiar }, configurable: true });

    abrir();

    const abertos = await screen.findByRole("region", { name: "Lembretes abertos" });
    expect(abertos.textContent).toContain("2");
    expect(screen.getByRole("region", { name: "Contas com lembrete" }).textContent).toContain("1");
    expect(screen.getByRole("region", { name: "R$ a conferir" }).textContent).toContain("R$ 37,50");

    const conta = screen.getByRole("region", { name: /Atendimento 31245/ });
    expect(conta.textContent).toContain("Maria S.");
    expect(conta.textContent).toContain("ALFA");
    expect(conta.textContent).toContain("concluída em 09/10");

    const sondagem = within(conta).getByRole("article", { name: "Sondagem vesical com equipo" });
    expect(sondagem.textContent).toContain("03/10 · CTI ADULTO");
    expect(sondagem.textContent).toContain("Confira o equipo do dia.");
    expect(sondagem.textContent).toContain("EQUIPO MACROGOTAS");
    expect(sondagem.textContent).toContain("R$ 25,00");
    expect(sondagem.textContent).not.toContain("conferir evidência");
    fireEvent.click(within(sondagem).getByRole("button", { name: "Copiar código 70000002" }));
    expect(copiar).toHaveBeenCalledWith("70000002");
    fireEvent.click(within(sondagem).getByRole("button", { name: "Ver evidência" }));
    expect(sondagem.textContent).toContain("Prontuário, p. 2");
    expect(sondagem.textContent).toContain("Chegou com acesso venoso periférico");

    const lidocaina = within(conta).getByRole("article", { name: "Lidocaína gel" });
    expect(lidocaina.textContent).toContain("conferir evidência");
  });

  it("Incluído e Não se aplica mandam a marcação com a observação e releem a lista", async () => {
    const pedidos = servidor();

    abrir();

    const sondagem = await screen.findByRole("article", { name: "Sondagem vesical com equipo" });
    fireEvent.change(within(sondagem).getByLabelText("Observação (opcional)"), {
      target: { value: "Equipo lançado no MV." },
    });
    fireEvent.click(within(sondagem).getByRole("button", { name: "Incluído" }));
    await waitFor(() => expect(pedidos.filter((p) => p.url === ROTA)).toHaveLength(2));
    const lidocaina = screen.getByRole("article", { name: "Lidocaína gel" });
    fireEvent.click(within(lidocaina).getByRole("button", { name: "Não se aplica" }));

    await waitFor(() => expect(pedidos.filter((p) => p.url.endsWith("/marcacao"))).toHaveLength(2));
    const marcacoes = pedidos.filter((p) => p.url.endsWith("/marcacao"));
    expect(marcacoes[0]).toEqual({
      url: `${ROTA}/lembretes/lembrete-1/marcacao`,
      metodo: "POST",
      corpo: { estado: "INCLUIDO", observacao: "Equipo lançado no MV." },
    });
    expect(marcacoes[1]).toEqual({
      url: `${ROTA}/lembretes/lembrete-2/marcacao`,
      metodo: "POST",
      corpo: { estado: "NAO_SE_APLICA", observacao: null },
    });
  });

  it("a aba Cenários só aparece para quem cadastra", async () => {
    servidor(false);

    abrir();

    await screen.findByRole("region", { name: "Lembretes abertos" });
    expect(screen.queryByRole("tab", { name: "Cenários" })).toBeNull();
  });

  it("na aba Cenários, desativar manda o cenário inteiro com ativo falso", async () => {
    const pedidos = servidor(true);

    abrir();

    fireEvent.click(await screen.findByRole("tab", { name: "Cenários" }));
    const linha = await screen.findByRole("article", { name: /CEN-001/ });
    expect(linha.textContent).toContain("Todas as operadoras");
    expect(linha.textContent).toContain("70000002");
    fireEvent.click(within(linha).getByRole("button", { name: "Desativar" }));

    await waitFor(() => expect(pedidos.some((p) => p.metodo === "PUT")).toBe(true));
    const edicao = pedidos.find((p) => p.metodo === "PUT");
    expect(edicao?.url).toBe(`${ROTA}/cenarios/cn-1`);
    expect(edicao?.corpo).toMatchObject({ nome: "Sondagem vesical com equipo", ativo: false });
  });

  it("no cenário novo, a IA preenche, o código fora da tabela é apontado e salvar manda o que a pessoa conferiu", async () => {
    const pedidos = servidor(true);

    abrir();

    fireEvent.click(await screen.findByRole("tab", { name: "Cenários" }));
    fireEvent.click(await screen.findByRole("button", { name: "Novo cenário" }));
    fireEvent.change(screen.getByLabelText("Escreva o cenário"), {
      target: { value: "Sondagem vesical ou cirurgia com lidocaína gel: conferir agulha e coletor." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preencher com a IA" }));

    const nome = (await screen.findByDisplayValue("Lidocaína gel em sondagem ou cirurgia")) as HTMLInputElement;
    expect(nome).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("79999999");
    expect(pedidos.find((p) => p.url.endsWith("/proposta"))?.corpo).toEqual({
      texto: "Sondagem vesical ou cirurgia com lidocaína gel: conferir agulha e coletor.",
    });

    fireEvent.change(screen.getByLabelText("Código do insumo 2"), { target: { value: "70000009" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar cenário" }));

    await waitFor(() => expect(pedidos.some((p) => p.metodo === "POST" && p.url === `${ROTA}/cenarios`)).toBe(true));
    const salvo = pedidos.find((p) => p.metodo === "POST" && p.url === `${ROTA}/cenarios`);
    expect(salvo?.corpo).toMatchObject({
      nome: "Lidocaína gel em sondagem ou cirurgia",
      gatilho_texto: "Cateterismo vesical, ou cirurgia com lidocaína gel",
      insumos: [
        { codigo: "70000001", descricao: "AGULHA", quantidade: 1 },
        { codigo: "70000009", descricao: "COLETOR DE URINA", quantidade: 1 },
      ],
    });
  });

  it("falha ao carregar mostra o erro, e não fica carregando para sempre", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("rede fora");
      }),
    );

    abrir();

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar");
    expect(screen.queryByText(/Carregando/)).toBeNull();
  });
});

describe("o Ditar na Coordenação (issue #1145)", () => {
  it("a observação do lembrete tem o Ditar com o aviso de paciente ao lado", async () => {
    servidor();
    abrir();

    const sondagem = await screen.findByRole("article", { name: "Sondagem vesical com equipo" });
    const botao = within(sondagem).getByRole("button", { name: "Ditar: Observação do lembrete" });
    expect(botao.parentElement?.textContent).toContain("Não dite nome nem dado de paciente.");
  });

  it("o cadastro de cenário tem o Ditar com o aviso de paciente ao lado", async () => {
    servidor(true);
    abrir();

    fireEvent.click(await screen.findByRole("tab", { name: "Cenários" }));
    fireEvent.click(await screen.findByRole("button", { name: "Novo cenário" }));

    const botao = screen.getByRole("button", { name: "Ditar: Cenário" });
    expect(botao.parentElement?.textContent).toContain("Não dite nome nem dado de paciente.");
  });
});
