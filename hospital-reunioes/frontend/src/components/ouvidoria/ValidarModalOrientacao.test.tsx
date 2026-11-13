/**
 * @vitest-environment jsdom
 */

/**
 * A orientação embutida de Validar e acionar (issue #1629, PRD #1527, regra
 * T1 e seção 4.14 da especificação da Diretoria): a frase do topo, o nome da
 * ação em português comum e o "?" dos campos.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidarModal } from "./ValidarModal";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-29",
    protocolo: "2026-0029",
    tipo_manifestacao: "reclamacao" as const,
    categoria: "",
    setor: "Recepcao",
    sigilo_reforcado: false,
    gravidade: "medio",
    extrato_para_o_setor: "Apurar o atendimento do plantao noturno.",
    nsp_sugerido: false,
    nsp_justificativa_simples: null,
    nsp_decisao: null,
    ...overrides,
  };
}

function montar(manifestacao: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/setores")) return { ok: true, json: async () => ["Recepcao"] } as Response;
      if (url.includes("/responsaveis")) return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    })
  );
  render(
    <ValidarModal
      manifestacao={manifestacao as never}
      token="t"
      onClose={vi.fn()}
      onAcionada={vi.fn()}
      {...extra}
    />
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Validar e acionar explica o que fazer", () => {
  it("abre com a frase do topo da seção 4.14", () => {
    montar(caso());

    expect(
      screen.getByText("Confira o tipo, o setor e, se houver alerta, a decisão sobre o NSP. Depois, envie à área.")
    ).toBeTruthy();
  });

  it("o botão principal diz a ação em português comum: Enviar à área", () => {
    // Regra T1: "Enviar à área", não "Acionar".
    montar(caso());

    expect(screen.getByRole("button", { name: "Enviar à área" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /acionar/i })).toBeNull();
  });

  it("o redirecionamento continua com a frase e o botão dele", () => {
    // A frase de 4.14 é da validação. Quem veio de "Encaminhar para outra
    // área" está noutro ato, e a tela se apresenta por ele (issue #601).
    montar(caso({ status: "aguardando_area" }), { modo: "redirecionamento" });

    expect(
      screen.queryByText("Confira o tipo, o setor e, se houver alerta, a decisão sobre o NSP. Depois, envie à área.")
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Redirecionar para a área nova" })).toBeTruthy();
  });

  it("a área responsável e a gravidade têm o ? com uma linha de explicação", () => {
    montar(caso());

    fireEvent.click(screen.getByRole("button", { name: "O que é: Área responsável" }));
    expect(screen.getByText("Quem vai apurar e responder. O lugar de onde o relato veio não decide a área.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "O que é: Gravidade" }));
    expect(screen.getByText("A gravidade decide o prazo que a área recebe.")).toBeTruthy();
  });
});
