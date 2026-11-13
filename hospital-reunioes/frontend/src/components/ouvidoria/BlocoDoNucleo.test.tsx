/**
 * @vitest-environment jsdom
 */

/**
 * O Núcleo de Segurança do Paciente no Dossiê (issue #1621, ADR 0088).
 *
 * O alerta do agente com o porquê, o selo Em análise pelo NSP e o botão Enviar
 * ao NSP, que fica sempre disponível enquanto o caso não foi ao Núcleo. A
 * régua do envio é do backend; aqui se prova o que a tela mostra e a rota que
 * o botão chama.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BlocoDoNucleo } from "./BlocoDoNucleo";

const JUSTIFICATIVA = "O relato descreve uma queda de paciente internado.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-31",
    nsp_sugerido: false,
    nsp_justificativa_simples: null,
    nsp_decisao: null,
    nsp_decisao_motivo: null,
    ...overrides,
  };
}

const fetchMock = vi.fn();

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function montar(dossie: Record<string, unknown>, onEnviado = vi.fn()) {
  vi.stubGlobal("fetch", fetchMock);
  render(<BlocoDoNucleo caso={dossie as never} token="t" onEnviado={onEnviado} />);
  return onEnviado;
}

describe("o Núcleo no Dossiê", () => {
  it("mostra o alerta do agente com o porquê enquanto ninguém decidiu", () => {
    montar(caso({ nsp_sugerido: true, nsp_justificativa_simples: JUSTIFICATIVA }));

    expect(screen.getByText("Possível evento de segurança do paciente")).toBeTruthy();
    expect(screen.getByText(JUSTIFICATIVA)).toBeTruthy();
  });

  it("o caso enviado ganha o selo e perde o botão", () => {
    montar(caso({ nsp_sugerido: true, nsp_decisao: "confirmado" }));

    expect(screen.getByText("Em análise pelo NSP")).toBeTruthy();
    expect(screen.queryByText("Possível evento de segurança do paciente")).toBeNull();
    expect(screen.queryByRole("button", { name: "Enviar ao NSP" })).toBeNull();
  });

  it("o descarte aparece com o motivo, e o botão continua lá", () => {
    montar(caso({ nsp_sugerido: true, nsp_decisao: "descartado", nsp_decisao_motivo: "Queda sem dano." }));

    expect(screen.getByText(/Queda sem dano\./)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enviar ao NSP" })).toBeTruthy();
  });

  it("Enviar ao NSP funciona sem sugestão, depois de confirmar", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ selo: "Em análise pelo NSP" }) });
    const onEnviado = montar(caso());

    fireEvent.click(screen.getByRole("button", { name: "Enviar ao NSP" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar envio ao NSP" }));

    await waitFor(() => expect(onEnviado).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("/api/ouvidoria/manifestacoes/uuid-31/nsp", {
      method: "POST",
      headers: { Authorization: "Bearer t" },
    });
  });

  it("a recusa do servidor aparece na tela", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "O setor do Núcleo de Segurança do Paciente não está configurado." }),
    });
    const onEnviado = montar(caso());

    fireEvent.click(screen.getByRole("button", { name: "Enviar ao NSP" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar envio ao NSP" }));

    await waitFor(() =>
      expect(screen.getByText("O setor do Núcleo de Segurança do Paciente não está configurado.")).toBeTruthy()
    );
    expect(onEnviado).not.toHaveBeenCalled();
  });
});
