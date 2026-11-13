/**
 * @vitest-environment jsdom
 */

/**
 * A decisão sobre o Núcleo de Segurança do Paciente na validação (issue #1621,
 * ADR 0088, decisão 4).
 *
 * Quando o agente aponta o caso, "Validar e acionar" só conclui depois de o
 * ouvidor confirmar o envio ao Núcleo ou descartar com o motivo. A recusa é do
 * backend (`test_ouvidoria_nucleo_seguranca_paciente.py`); aqui se prova que a
 * tela mostra o alerta, não deixa clicar sem decidir e manda a decisão.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidarModal } from "./ValidarModal";

const JUSTIFICATIVA = "O relato descreve uma queda de paciente internado.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-21",
    protocolo: "2026-0021",
    tipo_manifestacao: "reclamacao" as const,
    categoria: "",
    setor: "Recepcao",
    sigilo_reforcado: false,
    gravidade: "medio",
    extrato_para_o_setor: "Apurar o atendimento do plantao noturno.",
    nsp_sugerido: true,
    nsp_justificativa_simples: JUSTIFICATIVA,
    nsp_decisao: null,
    ...overrides,
  };
}

const fetchMock = vi.fn();

function montar(manifestacao: Record<string, unknown>) {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.includes("/setores")) return { ok: true, json: async () => ["Recepcao"] } as Response;
    if (url.includes("/responsaveis")) return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
    return { ok: true, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <ValidarModal manifestacao={manifestacao as never} token="t" onClose={vi.fn()} onAcionada={vi.fn()} />
  );
}

function botaoDeValidar() {
  return screen.getByRole("button", { name: "Enviar à área" }) as HTMLButtonElement;
}

function corpoDaValidacao(): Record<string, unknown> {
  const chamada = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/validar"));
  expect(chamada, "a validação não foi chamada").toBeTruthy();
  return JSON.parse((chamada![1] as RequestInit).body as string);
}

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("o apontamento do agente na validação", () => {
  it("mostra o alerta com o porquê do agente", () => {
    montar(caso());

    expect(screen.getByText("Possível evento de segurança do paciente")).toBeTruthy();
    expect(screen.getByText(JUSTIFICATIVA)).toBeTruthy();
  });

  it("não deixa validar sem decidir sobre o Núcleo", async () => {
    montar(caso());
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    expect(botaoDeValidar().disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Confirmar envio ao NSP"));
    expect(botaoDeValidar().disabled).toBe(false);
  });

  it("descartar pede o motivo, e o motivo vai junto", async () => {
    montar(caso());
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    fireEvent.click(screen.getByLabelText("Descartar"));
    expect(botaoDeValidar().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Motivo do descarte/), {
      target: { value: "Queda sem dano, ja notificada pela enfermagem." },
    });
    fireEvent.click(botaoDeValidar());

    await waitFor(() => expect(corpoDaValidacao().nsp_decisao).toBe("descartado"));
    expect(corpoDaValidacao().nsp_motivo).toBe("Queda sem dano, ja notificada pela enfermagem.");
  });

  it("confirmar manda a decisão confirmada", async () => {
    montar(caso());
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    fireEvent.click(screen.getByLabelText("Confirmar envio ao NSP"));
    fireEvent.click(botaoDeValidar());

    await waitFor(() => expect(corpoDaValidacao().nsp_decisao).toBe("confirmado"));
  });

  it("aberta pela fila, que traz só as marcas, também pede a decisão", async () => {
    // A linha da fila não carrega a justificativa (ela fica no Dossiê), e a
    // validação é recusada do mesmo jeito sem a decisão.
    const linhaDaFila: Record<string, unknown> = caso();
    delete linhaDaFila.nsp_justificativa_simples;
    montar(linhaDaFila);
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    expect(screen.getByText("Possível evento de segurança do paciente")).toBeTruthy();
    expect(botaoDeValidar().disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Confirmar envio ao NSP"));
    expect(botaoDeValidar().disabled).toBe(false);
  });

  it("sem apontamento, a validação segue como sempre, sem perguntar do Núcleo", async () => {
    montar(caso({ nsp_sugerido: false, nsp_justificativa_simples: null }));
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    expect(screen.queryByText("Possível evento de segurança do paciente")).toBeNull();
    expect(botaoDeValidar().disabled).toBe(false);
  });

  it("o caso já decidido não pergunta de novo", async () => {
    montar(caso({ nsp_decisao: "descartado" }));
    await waitFor(() => expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao"));

    expect(screen.queryByLabelText("Confirmar envio ao NSP")).toBeNull();
    expect(botaoDeValidar().disabled).toBe(false);
  });
});
