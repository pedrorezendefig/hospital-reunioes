/**
 * @vitest-environment jsdom
 */

/**
 * A conversa da Operadora com o Auditor (issue #1490, PRD #1484, ADR 0081).
 *
 * A tela não decide nada: quem monta o lote, aplica o "ok" numa versão só e
 * refaz o item corrigido é o servidor. O que se trava aqui é o que quem decide
 * vê (as falas, o lote com o motivo, os conflitos e a prova de cada item) e o
 * que cada clique manda (a mensagem, o "ok" e o "corrige o item N").
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import { ConversaDaOperadora, type LoteAplicado } from "./ConversaDaOperadora";

const ROTA = "/api/contas-medicas/operadoras/ALFA/conversa";

const DIA_03 = "Transferência de setor antes das 12h não gera diária extra no setor de origem.";
const DIA_01_ANTES = "A diária vence às 10h e é sempre integral.";
const DIA_01_DEPOIS = "A diária vence às 12h e é sempre integral.";

function prova(campos: Record<string, unknown> = {}) {
  return {
    contas: 10,
    mudaria: true,
    feitas_que_sumiriam: 1,
    aviso: null,
    por_conta: [
      {
        conta_id: "c12",
        numero_atendimento: "31012",
        numero_conta: "N12",
        mudaria: true,
        entrariam: [],
        sairiam: [
          {
            acao: "INCLUIR",
            data: "2026-10-12",
            codigo: "M012",
            descricao: "Seringa de limpeza pronta",
            quantidade_devida: 2,
            regra_codigo: "ALFA-DIA-01",
            feito: true,
          },
        ],
        mudariam: [],
      },
    ],
    ...campos,
  };
}

const LOTE = {
  id: "lote-1",
  itens: [
    {
      numero: 1,
      tipo: "REGRA_NOVA",
      regra_codigo: null,
      proposta: { secao: "DIA", texto: DIA_03, tipo: "CONTRATUAL", origem: "PRÁTICA" },
      motivo: "A transferência antes do meio-dia deixa de gerar diária extra.",
      conflitos: [
        { codigo: "ALFA-DIA-02", texto: "Transferência antes das 10h: gera ou não diária extra.", resolucao: "SUBSTITUIR" },
      ],
      prova: prova(),
    },
    {
      numero: 2,
      tipo: "REGRA_ALTERADA",
      regra_codigo: "ALFA-DIA-01",
      proposta: { secao: "DIA", texto: DIA_01_DEPOIS, tipo: "CONTRATUAL", origem: "PRÁTICA", texto_anterior: DIA_01_ANTES },
      motivo: "A diária passa a vencer ao meio-dia.",
      conflitos: [],
      prova: prova({ mudaria: false, feitas_que_sumiriam: 0, aviso: "A regra não mudaria nada nas 10 últimas contas concluídas.", por_conta: [] }),
    },
    {
      numero: 3,
      tipo: "PARAMETRO",
      regra_codigo: null,
      proposta: { chave: "diaria.hora_vencimento", antes: "10:00", depois: "12:00" },
      motivo: "O cabeçalho acompanha o vencimento novo.",
      conflitos: [],
      prova: null,
    },
  ],
};

const PEDIDO = "Na ALFA a transferência antes do meio-dia não gera diária extra.";
const FALAS = [
  { id: "m1", autor: "PESSOA", autor_nome: "Diretor Teste", texto: PEDIDO, criado_em: null, versao: null },
  { id: "m2", autor: "AUDITOR", autor_nome: null, texto: "Entendi três mudanças.", criado_em: null, versao: null },
];

type Chamada = { url: string; metodo: string; corpo: unknown };
let chamadas: Chamada[];
let leitura: { mensagens: unknown[]; lote: unknown };
let respostaDoEnvio: (texto: string) => { status: number; corpo: unknown };

function resposta(status: number, corpo: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
}

beforeEach(() => {
  chamadas = [];
  leitura = { mensagens: [], lote: null };
  respostaDoEnvio = () => ({ status: 200, corpo: { mensagens: FALAS, lote: LOTE, aplicado: null } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      chamadas.push({ url, metodo, corpo });
      if (url === ROTA && metodo === "GET") return resposta(200, leitura);
      if (url === ROTA && metodo === "POST") {
        const { status, corpo: devolvido } = respostaDoEnvio((corpo as { texto: string }).texto);
        return resposta(status, devolvido);
      }
      return resposta(404, { detail: "rota desconhecida no dublê" });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrir(aoAplicar: (aplicado: LoteAplicado) => Promise<void> = async () => {}) {
  render(
    <ToastProvider>
      <ConversaDaOperadora sigla="ALFA" token="token-de-teste" aoAplicar={aoAplicar} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Falar com o auditor" }));
  return screen.findByRole("region", { name: "Falar com o auditor" });
}

async function mandar(conversa: HTMLElement, texto: string) {
  fireEvent.change(within(conversa).getByLabelText("Mensagem para o auditor"), { target: { value: texto } });
  fireEvent.click(within(conversa).getByRole("button", { name: "Enviar ao auditor" }));
  return within(conversa).findByRole("region", { name: "Lote do Auditor" });
}

function enviados(): string[] {
  return chamadas.filter((c) => c.metodo === "POST").map((c) => (c.corpo as { texto: string }).texto);
}

describe("o lote do Auditor", () => {
  it("o texto vira o lote, com a proposta, o motivo, os conflitos e a prova de cada item", async () => {
    const conversa = await abrir();
    expect(chamadas[0]).toMatchObject({ url: ROTA, metodo: "GET" });

    const lote = await mandar(conversa, PEDIDO);

    expect(enviados()).toEqual([PEDIDO]);
    expect(conversa.textContent).toContain("Entendi três mudanças.");
    const nova = within(lote).getByRole("article", { name: "Item 1" });
    expect(nova.textContent).toContain("Regra nova");
    expect(nova.textContent).toContain(DIA_03);
    expect(nova.textContent).toContain("A transferência antes do meio-dia deixa de gerar diária extra.");
    expect(nova.textContent).toContain("Conflita com ALFA-DIA-02, propõe substituir");
    const provaDaNova = within(nova).getByRole("region", { name: "Prova da regra" });
    expect(within(provaDaNova).getByRole("alert").textContent).toContain("1 linha já feita pela faturista sumiria.");

    const alterada = within(lote).getByRole("article", { name: "Item 2" });
    expect(alterada.textContent).toContain("Regra alterada ALFA-DIA-01");
    expect(alterada.textContent).toContain(`Antes: ${DIA_01_ANTES}`);
    expect(alterada.textContent).toContain(`Depois: ${DIA_01_DEPOIS}`);
    expect(alterada.textContent).toContain("A regra não mudaria nada nas 10 últimas contas concluídas.");

    const parametro = within(lote).getByRole("article", { name: "Item 3" });
    expect(parametro.textContent).toContain("diaria.hora_vencimento: de 10:00 para 12:00");
    expect(within(parametro).queryByRole("region", { name: "Prova da regra" })).toBeNull();
  });

  it("a conversa guardada aparece ao abrir, com a fala ligada à versão que gerou", async () => {
    leitura = {
      mensagens: [
        { ...FALAS[0], versao: "1.3" },
        { id: "m3", autor: "AUDITOR", autor_nome: null, texto: "Lote aplicado: versão 1.3.", criado_em: null, versao: "1.3" },
      ],
      lote: null,
    };

    const conversa = await abrir();

    const falas = await within(conversa).findAllByRole("listitem");
    expect(falas[0].textContent).toContain("Diretor Teste");
    expect(falas[0].textContent).toContain(PEDIDO);
    expect(falas[0].textContent).toContain("Gerou a versão 1.3");
    expect(within(conversa).queryByRole("region", { name: "Lote do Auditor" })).toBeNull();
  });

  it("Ok, aplicar o lote manda ok e avisa a versão nova", async () => {
    const aoAplicar = vi.fn(async () => {});
    const conversa = await abrir(aoAplicar);
    const lote = await mandar(conversa, PEDIDO);
    respostaDoEnvio = () => ({
      status: 200,
      corpo: { mensagens: FALAS, lote: null, aplicado: { versao: "1.3", regras: ["ALFA-DIA-03"], contas_com_regra_nova: 2 } },
    });

    fireEvent.click(within(lote).getByRole("button", { name: "Ok, aplicar o lote" }));

    await waitFor(() => expect(aoAplicar).toHaveBeenCalledWith({ versao: "1.3", regras: ["ALFA-DIA-03"], contas_com_regra_nova: 2 }));
    expect(enviados()).toEqual([PEDIDO, "ok"]);
    expect(within(conversa).queryByRole("region", { name: "Lote do Auditor" })).toBeNull();
  });

  it("com um item de regra sem prova o ok fica travado até a correção provar de novo", async () => {
    respostaDoEnvio = () => ({
      status: 200,
      corpo: { mensagens: FALAS, lote: { ...LOTE, itens: [{ ...LOTE.itens[0], prova: null }, LOTE.itens[1], LOTE.itens[2]] }, aplicado: null },
    });
    const conversa = await abrir();
    const lote = await mandar(conversa, PEDIDO);

    const ok = within(lote).getByRole("button", { name: "Ok, aplicar o lote" }) as HTMLButtonElement;

    expect(ok.disabled).toBe(true);
    expect(lote.textContent).toContain("O ok fica travado enquanto o item 1 estiver sem prova.");
  });

  it("Corrigir o item 2 manda corrige o item 2 com o que mudar e mostra o item refeito", async () => {
    const conversa = await abrir();
    const lote = await mandar(conversa, PEDIDO);
    const refeito = { ...LOTE.itens[1], proposta: { ...LOTE.itens[1].proposta, texto: "A diária vence às 11h." } };
    respostaDoEnvio = () => ({
      status: 200,
      corpo: { mensagens: FALAS, lote: { ...LOTE, itens: [LOTE.itens[0], refeito, LOTE.itens[2]] }, aplicado: null },
    });

    const item = within(lote).getByRole("article", { name: "Item 2" });
    fireEvent.click(within(item).getByRole("button", { name: "Corrigir o item 2" }));
    fireEvent.change(within(item).getByLabelText("O que corrigir no item 2"), { target: { value: "vence às 11h" } });
    fireEvent.click(within(item).getByRole("button", { name: "Mandar a correção" }));

    await waitFor(() => expect(enviados()).toEqual([PEDIDO, "corrige o item 2: vence às 11h"]));
    await waitFor(() =>
      expect(within(screen.getByRole("article", { name: "Item 2" })).getByText("Depois: A diária vence às 11h.")).toBeTruthy(),
    );
    expect(screen.getByRole("article", { name: "Item 1" }).textContent).toContain(DIA_03);
  });

  it("mostra a recusa do servidor como veio", async () => {
    respostaDoEnvio = () => ({
      status: 503,
      corpo: { detail: "O Auditor não respondeu agora. Nada foi gravado: tente de novo em alguns minutos." },
    });
    const conversa = await abrir();

    fireEvent.change(within(conversa).getByLabelText("Mensagem para o auditor"), { target: { value: PEDIDO } });
    fireEvent.click(within(conversa).getByRole("button", { name: "Enviar ao auditor" }));

    expect((await within(conversa).findByRole("alert")).textContent).toContain("O Auditor não respondeu agora.");
  });
});

describe("revisar as Regras pendentes (issue #1494)", () => {
  const PRI_03 = "Edição do Brasíndice usada pela operadora.";
  const DIA_02 = "Transferência de setor antes das 10h: gera ou não diária extra.";
  const pendente = (numero: number, codigo: string, decisao: string, antes: string, depois: string) => ({
    numero,
    tipo: "REGRA_ALTERADA",
    regra_codigo: codigo,
    proposta: { decisao, secao: "PRI", texto: depois, tipo: "CONTRATUAL", origem: "CONTRATO", texto_anterior: antes },
    motivo: `Motivo de ${codigo}.`,
    conflitos: [],
    prova: prova({ mudaria: false, feitas_que_sumiriam: 0, por_conta: [] }),
  });
  const LOTE_DAS_PENDENTES = {
    id: "lote-2",
    itens: [
      pendente(1, "ALFA-DIA-02", "ALTERAR", DIA_02, "Transferência antes das 10h não gera diária extra."),
      pendente(2, "ALFA-PRI-03", "DESCARTAR", PRI_03, PRI_03),
      pendente(3, "ALFA-PRI-04", "VALIDAR", "Brasíndice da edição vigente.", "Brasíndice da edição vigente."),
    ],
  };

  it("Revisar pendentes manda a mensagem e cada item mostra a decisão sugerida", async () => {
    respostaDoEnvio = () => ({ status: 200, corpo: { mensagens: FALAS, lote: LOTE_DAS_PENDENTES, aplicado: null } });
    const conversa = await abrir();

    fireEvent.click(within(conversa).getByRole("button", { name: "Revisar pendentes" }));

    const lote = await within(conversa).findByRole("region", { name: "Lote do Auditor" });
    expect(enviados()).toEqual(["revisar pendentes"]);
    const alterar = within(lote).getByRole("article", { name: "Item 1" });
    expect(alterar.textContent).toContain("Regra pendente ALFA-DIA-02, alterar");
    expect(alterar.textContent).toContain(`Antes: ${DIA_02}`);
    const descartar = within(lote).getByRole("article", { name: "Item 2" });
    expect(descartar.textContent).toContain("Regra pendente ALFA-PRI-03, descartar");
    expect(descartar.textContent).toContain(`Sai da memória: ${PRI_03}`);
    const validar = within(lote).getByRole("article", { name: "Item 3" });
    expect(validar.textContent).toContain("Regra pendente ALFA-PRI-04, validar");
    expect(validar.textContent).toContain("Fica vigente como está: Brasíndice da edição vigente.");
  });
});

describe("o atalho da tabela", () => {
  it("Enviar tabela abre o envio de tabela da tela Operadoras já com a operadora", async () => {
    const conversa = await abrir();

    const atalho = within(conversa).getByRole("link", { name: "Enviar tabela" });

    expect(atalho.getAttribute("href")).toBe("/contas-medicas/operadoras?tabela=ALFA");
  });
});
