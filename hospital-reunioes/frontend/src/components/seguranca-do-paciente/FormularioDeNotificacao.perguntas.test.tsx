/**
 * @vitest-environment jsdom
 */

/**
 * As perguntas de esclarecimento na confirmação (issue #1991, PRD #1979).
 *
 * A notificação já está registrada quando as perguntas aparecem: a
 * confirmação mostra o protocolo na hora e pergunta ao servidor, depois, se o
 * agente propôs alguma. Sem pergunta, nada muda na tela. A régua do servidor
 * está em `backend/tests/test_nsp_perguntas_de_esclarecimento.py`.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FormularioDeNotificacao } from "./FormularioDeNotificacao";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }) },
  }),
}));

const PERGUNTA_1 = "A bomba foi reprogramada por alguém depois do alarme?";
const PERGUNTA_2 = "O paciente precisou de transfusão?";

interface Chamada {
  url: string;
  corpo: Record<string, unknown> | null;
}

type Resposta = { status: number; corpo: unknown };

let chamadas: Chamada[] = [];
let recibo: Record<string, unknown> = {};
/** As respostas do servidor às consultas das perguntas, na ordem; a última se repete. */
let perguntas: Resposta[] = [];
let respostas: Resposta = { status: 200, corpo: { perguntas: [] } };

function responder({ status, corpo }: Resposta): Response {
  return { ok: status < 300, status, json: async () => corpo } as Response;
}

beforeEach(() => {
  chamadas = [];
  recibo = { protocolo: "NSP-2026-0008", criado_em: "2026-11-20T10:00:00+00:00", codigo_acompanhamento: "ABCDE-FGHJK" };
  perguntas = [{ status: 200, corpo: { perguntas: [], aguardando: false } }];
  respostas = { status: 200, corpo: { perguntas: [] } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (url === "/api/nsp/publico/setores") {
        return responder({ status: 200, corpo: { setores: [{ id: "setor-uti", nome: "UTI Adulto" }] } });
      }
      if (url === "/api/nsp/publico/perguntas") {
        return responder(perguntas.length > 1 ? perguntas.shift()! : perguntas[0]);
      }
      if (url === "/api/nsp/publico/respostas") return responder(respostas);
      return responder({ status: 201, corpo: recibo });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function botao(nome: string | RegExp) {
  return screen.getByRole("button", { name: nome }) as HTMLButtonElement;
}

function escrever(rotulo: string | RegExp, valor: string) {
  fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } });
}

function escolher(grupo: string | RegExp, opcao: string) {
  fireEvent.click(within(screen.getByRole("group", { name: grupo })).getByRole("button", { name: opcao }));
}

async function enviar({ anonimo = true }: { anonimo?: boolean } = {}) {
  escrever("O que aconteceu", "A bomba de infusão alarmou e ninguém ouviu.");
  fireEvent.click(botao("Continuar"));
  await waitFor(() => expect(screen.getByRole("option", { name: "UTI Adulto" })).toBeTruthy());
  escrever("Setor", "setor-uti");
  escolher("Turno", "Noite");
  fireEvent.click(botao("Continuar"));
  escolher("O incidente chegou ao paciente?", "Chegou, com dano");
  escolher("Foi grave ou houve morte?", "Sim");
  fireEvent.click(botao("Continuar"));
  if (anonimo) {
    fireEvent.click(botao("Sem me identificar"));
  } else {
    escrever("Nome", "Profissional de Teste");
    escrever("E-mail ou telefone", "profissional@hsm.test");
  }
  fireEvent.click(botao("Enviar notificação"));
  await waitFor(() => expect(screen.getByText(String(recibo.protocolo))).toBeTruthy());
}

function consultasDasPerguntas(): Chamada[] {
  return chamadas.filter((c) => c.url === "/api/nsp/publico/perguntas");
}

describe("as perguntas na confirmação", () => {
  it("aparecem depois do registro, com o Responder depois que leva ao acompanhamento", async () => {
    perguntas = [{ status: 200, corpo: { perguntas: [PERGUNTA_1, PERGUNTA_2], aguardando: false } }];
    render(<FormularioDeNotificacao porta="qr" />);
    await enviar();

    const bloco = await screen.findByRole("region", { name: "Perguntas do Núcleo" });
    expect(within(bloco).getByLabelText(PERGUNTA_1)).toBeTruthy();
    expect(within(bloco).getByLabelText(PERGUNTA_2)).toBeTruthy();
    expect(within(bloco).getByRole("link", { name: "Responder depois" }).getAttribute("href")).toBe(
      "/notificar/acompanhar"
    );
    // O envio veio antes, e a consulta usa a chave do acompanhamento.
    const indiceDoEnvio = chamadas.findIndex((c) => c.url === "/api/nsp/publico/notificacoes");
    const indiceDaConsulta = chamadas.findIndex((c) => c.url === "/api/nsp/publico/perguntas");
    expect(indiceDoEnvio).toBeGreaterThanOrEqual(0);
    expect(indiceDaConsulta).toBeGreaterThan(indiceDoEnvio);
    expect(consultasDasPerguntas()[0].corpo).toEqual({ protocolo: "NSP-2026-0008", codigo: "ABCDE-FGHJK" });
  });

  it("sem pergunta proposta, a confirmação não mostra o bloco", async () => {
    render(<FormularioDeNotificacao porta="qr" />);
    await enviar();

    await waitFor(() => expect(consultasDasPerguntas()).toHaveLength(1));
    expect(screen.queryByRole("region", { name: "Perguntas do Núcleo" })).toBeNull();
    expect(screen.queryByText("Responder depois")).toBeNull();
    expect(screen.getByText("Notificação registrada")).toBeTruthy();
  });

  it("enquanto o agente lê, a confirmação pergunta de novo e mostra quando chegam", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    perguntas = [
      { status: 200, corpo: { perguntas: [], aguardando: true } },
      { status: 200, corpo: { perguntas: [PERGUNTA_2], aguardando: false } },
    ];
    render(<FormularioDeNotificacao porta="qr" />);
    await enviar();
    await waitFor(() => expect(consultasDasPerguntas()).toHaveLength(1));
    expect(screen.queryByRole("region", { name: "Perguntas do Núcleo" })).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    const bloco = await screen.findByRole("region", { name: "Perguntas do Núcleo" });
    expect(within(bloco).getByLabelText(PERGUNTA_2)).toBeTruthy();
  });

  it("a falha ao buscar as perguntas não tira o protocolo da tela", async () => {
    perguntas = [{ status: 503, corpo: { detail: "fora do ar" } }];
    render(<FormularioDeNotificacao porta="qr" />);
    await enviar();

    await waitFor(() => expect(consultasDasPerguntas()).toHaveLength(1));
    expect(screen.getByText("Notificação registrada")).toBeTruthy();
    expect(screen.getByText("ABCDE-FGHJK")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Perguntas do Núcleo" })).toBeNull();
  });

  it("responder manda só o que foi escrito e agradece", async () => {
    perguntas = [{ status: 200, corpo: { perguntas: [PERGUNTA_1, PERGUNTA_2], aguardando: false } }];
    respostas = { status: 200, corpo: { perguntas: [PERGUNTA_2] } };
    // A identificada não recebe código.
    recibo = { protocolo: "NSP-2026-0008", criado_em: "2026-11-20T10:00:00+00:00" };
    render(<FormularioDeNotificacao porta="endereco" />);
    await enviar({ anonimo: false });

    const bloco = await screen.findByRole("region", { name: "Perguntas do Núcleo" });
    expect(consultasDasPerguntas()[0].corpo).toEqual({ protocolo: "NSP-2026-0008", contato: "profissional@hsm.test" });
    expect((within(bloco).getByRole("button", { name: "Enviar respostas" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(bloco).getByLabelText(PERGUNTA_1), { target: { value: " Não, ninguém mexeu. " } });
    fireEvent.click(within(bloco).getByRole("button", { name: "Enviar respostas" }));

    await waitFor(() => expect(screen.getByText("Obrigado. A resposta chegou ao Núcleo.")).toBeTruthy());
    expect(chamadas.find((c) => c.url === "/api/nsp/publico/respostas")?.corpo).toEqual({
      protocolo: "NSP-2026-0008",
      contato: "profissional@hsm.test",
      respostas: [{ pergunta: PERGUNTA_1, resposta: "Não, ninguém mexeu." }],
    });
    expect(screen.queryByLabelText(PERGUNTA_1)).toBeNull();
    expect(screen.getByLabelText(PERGUNTA_2)).toBeTruthy();
  });
});
