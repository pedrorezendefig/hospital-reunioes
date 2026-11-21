/**
 * @vitest-environment jsdom
 */

/**
 * A tela única da triagem (issue #1992).
 *
 * O relato, as respostas e os anexos à esquerda; a sugestão à direita, marcada
 * como "Sugestão", com a justificativa, a confiança em palavras e os alertas à
 * vista. Nas faixas A e B e na revisão forçada, Confirmar só libera com cada
 * campo marcado, e não há "aceitar tudo"; nas faixas C, D e E é um clique. A
 * notificação para classificar manualmente abre sem sugestão, com os campos em
 * branco. O que o sistema calcula aparece na tela.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CAMPOS } from "@/lib/seguranca-do-paciente/triagem";

// O texto literal da seção 17 da especificação (tela "Triagem de caso grave"),
// e não a constante: trocar o texto da tela tem que quebrar este teste.
const LINHA_DO_CASO_GRAVE = "Caso grave: confirme cada campo. O prazo legal já está correndo.";
import { TriagemDoCaso } from "./TriagemDoCaso";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "P1", nome_completo: "Pessoa", email: "p@hsm", recursos_nsp: ["triagem"] },
    loading: false,
    error: null,
  }),
}));

const CASO = {
  id: "c1",
  protocolo: "NSP-2026-0007",
  estado: "recebida",
  origem: "qr",
  relato: "A bomba de infusão alarmou e ninguém ouviu.",
  leito_ou_atendimento: "Leito 4",
  setor: "UTI Adulto",
  data_ocorrencia: "2026-11-09",
  turno: "noite",
  chegou_ao_paciente: "sem_dano",
  grave_ou_morte: null,
  criado_em: "2026-11-10T13:00:00+00:00",
  anexos: [],
};

const SUGESTAO = {
  assunto: "Alarme de bomba de infusão sem resposta",
  natureza: "incidente_sem_dano",
  grau_de_dano: "nenhum",
  categoria: "EQP",
  incidente: "Alarme inoperante",
  evento: { situacao: "nao", item: null, motivo: "Nenhum item da lista." },
  iras: false,
  risco_de_imagem: false,
  protocolo_basico: "nenhum",
  canais: ["NSP"],
  motivo_do_encaminhamento: null,
  faixa: "D",
  revisao: "confirmacao_simples",
  justificativa: "O alarme não foi atendido e o paciente não teve dano.",
  confianca: "media",
  motivo_da_confianca: "O relato não diz quanto tempo durou.",
  alertas: ["Confira se houve outro alarme no mesmo turno."],
  perguntas_ao_notificante: [],
  divergencias: null,
  frequencia: null,
  prioridade: null,
};

const CONTEXTO = {
  recorrencia: 3,
  janela_da_recorrencia_dias: 60,
  parecidos: [
    { id: "p1", protocolo: "NSP-2026-0001", data_ocorrencia: "2026-10-30", estado: "classificada", assunto: "Monitor sem alarme" },
  ],
  anteriores: 2,
  frequencia: "ocasional",
  prioridade: "baixa",
  cortes: { janela_meses: 12, incomum_a_partir: 1, ocasional_a_partir: 2, frequente_a_partir: 4 },
};

function tela(campoACampo: boolean, extra: Record<string, unknown> = {}) {
  return {
    caso: CASO,
    sugestao: SUGESTAO,
    decisao: null,
    pendente: true,
    classificar_manualmente: false,
    motivo_classificar_manualmente: null,
    conferencia: { campo_a_campo: campoACampo, motivos: campoACampo ? ["faixa"] : [], campos: CAMPOS.map((c) => c.campo) },
    contexto: CONTEXTO,
    opcoes: {
      categorias: [
        { codigo: "MED", nome: "Medicamentos e soluções" },
        { codigo: "EQP", nome: "Equipamentos e materiais" },
      ],
      eventos: [{ item: 11, evento: "Óbito associado a queda do paciente durante o atendimento" }],
    },
    ...extra,
  };
}

let resposta: unknown;
const enviados: { url: string; body: unknown }[] = [];

beforeEach(() => {
  enviados.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        enviados.push({ url, body: JSON.parse(String(init.body)) });
        return { ok: true, status: 201, json: async () => ({ estado: "classificada", triagem: SUGESTAO }) } as Response;
      }
      if (url.includes("/contexto")) {
        return { ok: true, status: 200, json: async () => CONTEXTO } as Response;
      }
      return { ok: true, status: 200, json: async () => resposta } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a tela de triagem", () => {
  it("mostra o relato à esquerda e a sugestão marcada, com justificativa, confiança e alertas à vista", async () => {
    resposta = tela(false);
    render(<TriagemDoCaso id="c1" />);

    const relato = await screen.findByRole("region", { name: "Relato" });
    expect(within(relato).getByText(CASO.relato)).toBeTruthy();
    const sugestao = screen.getByRole("region", { name: "Sugestão" });
    expect(within(sugestao).getByText(SUGESTAO.justificativa)).toBeTruthy();
    expect(within(sugestao).getByText(/Confiança média/)).toBeTruthy();
    expect(within(sugestao).getByText(SUGESTAO.alertas[0])).toBeTruthy();
    expect(screen.queryByText(LINHA_DO_CASO_GRAVE)).toBeNull();
  });

  it("mostra a recorrência, os casos parecidos, a frequência e a prioridade calculadas", async () => {
    resposta = tela(false);
    render(<TriagemDoCaso id="c1" />);

    const calculo = await screen.findByRole("region", { name: "Calculado pelo sistema" });
    expect(within(calculo).getByText("3ª ocorrência desta categoria neste setor em 60 dias")).toBeTruthy();
    expect(within(calculo).getByText(/Ocasional/)).toBeTruthy();
    expect(within(calculo).getByText(/Prioridade: Baixa/)).toBeTruthy();
    expect(within(calculo).getByRole("link", { name: /NSP-2026-0001/ }).getAttribute("href")).toBe(
      "/seguranca-do-paciente/notificacoes/p1"
    );
  });

  it("nas faixas C, D e E, Confirmar é um clique", async () => {
    resposta = tela(false);
    render(<TriagemDoCaso id="c1" />);

    const confirmar = await screen.findByRole("button", { name: "Confirmar" });
    expect(confirmar.hasAttribute("disabled")).toBe(false);
    fireEvent.click(confirmar);

    await screen.findByText(/Triagem confirmada/);
    expect(enviados).toEqual([{ url: "/api/nsp/triagem/c1", body: { conferidos: [] } }]);
  });

  it("no caso grave, Confirmar só libera com cada campo marcado, e não há aceitar tudo", async () => {
    resposta = tela(true, { sugestao: { ...SUGESTAO, faixa: "A", grau_de_dano: "obito" } });
    render(<TriagemDoCaso id="c1" />);

    expect(await screen.findByText(LINHA_DO_CASO_GRAVE)).toBeTruthy();
    const confirmar = screen.getByRole("button", { name: "Confirmar" });
    expect(screen.queryByRole("button", { name: /aceitar tudo|marcar todos/i })).toBeNull();

    const caixas = screen.getAllByRole("checkbox", { name: /^Conferi/ });
    expect(caixas).toHaveLength(CAMPOS.length);
    caixas.slice(0, -1).forEach((caixa) => fireEvent.click(caixa));
    expect(confirmar.hasAttribute("disabled")).toBe(true);

    fireEvent.click(caixas[caixas.length - 1]);
    expect(confirmar.hasAttribute("disabled")).toBe(false);
    fireEvent.click(confirmar);

    await screen.findByText(/Triagem confirmada/);
    expect((enviados[0].body as { conferidos: string[] }).conferidos.sort()).toEqual(
      CAMPOS.map((c) => c.campo).sort()
    );
  });

  it("Ajustar envia a classificação da pessoa", async () => {
    resposta = tela(false);
    render(<TriagemDoCaso id="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Ajustar" }));
    fireEvent.change(screen.getByLabelText("Categoria"), { target: { value: "MED" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar o ajuste" }));

    await screen.findByText(/Triagem confirmada/);
    const { classificacao } = enviados[0].body as { classificacao: Record<string, unknown> };
    expect(classificacao.categoria).toBe("MED");
    expect(classificacao.natureza).toBe("incidente_sem_dano");
  });

  it("a notificação para classificar manualmente abre sem sugestão, com os campos em branco", async () => {
    resposta = tela(false, {
      sugestao: null,
      classificar_manualmente: true,
      motivo_classificar_manualmente: "agente_fora",
      contexto: { ...CONTEXTO, recorrencia: null, parecidos: [], frequencia: null, prioridade: null },
    });
    render(<TriagemDoCaso id="c1" />);

    expect(await screen.findByText(/sem sugestão do agente/i)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Sugestão" })).toBeNull();
    expect((screen.getByLabelText("Assunto") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Natureza") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("Categoria") as HTMLSelectElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Confirmar a classificação" }).hasAttribute("disabled")).toBe(true);
  });
});
