/**
 * @vitest-environment jsdom
 */

/**
 * O reacionamento do caso devolvido à Ouvidoria (issue #601, PRD #598,
 * ADR 0048, decisão 4).
 *
 * A área devolveu o caso que não era dela, e o ouvidor despacha de novo. O
 * ponto inteiro da fatia é ele NÃO redigitar o que já está no caso: tipo,
 * gravidade e extrato vêm preenchidos, a área anterior aparece marcada, e o que
 * ele faz é trocar a área e confirmar.
 *
 * O extrato em branco é o padrão do primeiro acionamento, e é decisão de
 * domínio (a palavra crua de quem manifestou não pode ir ao setor por engano):
 * o que estes testes garantem é que o caso JÁ acionado não cai nesse padrão.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidarModal } from "./ValidarModal";

const EXTRATO = "Conduta da equipe de enfermagem no plantao noturno. Apurar e responder a Ouvidoria.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    tipo_manifestacao: "reclamacao" as const,
    categoria: "Demora no atendimento",
    setor: "Recepcao",
    sigilo_reforcado: false,
    gravidade: null,
    extrato_para_o_setor: null,
    ...overrides,
  };
}

function montar(manifestacao: Record<string, unknown>, devolvidaPelaArea: string | null = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/setores")) {
        return { ok: true, json: async () => ["Recepcao", "Centro Medico"] } as Response;
      }
      return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
    })
  );
  render(
    <ValidarModal
      manifestacao={manifestacao as never}
      token="token-de-teste"
      devolvidaPelaArea={devolvidaPelaArea}
      onClose={vi.fn()}
      onAcionada={vi.fn()}
    />
  );
}

describe("o reacionamento abre a validação preenchida (issue #601)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("traz gravidade e extrato do acionamento anterior", async () => {
    montar(caso({ gravidade: "medio", extrato_para_o_setor: EXTRATO }), "Recepcao");

    expect((screen.getByLabelText(/Extrato para o setor/) as HTMLTextAreaElement).value).toBe(EXTRATO);
    // A gravidade é escolhida em botões, e o escolhido é o que fica pressionado.
    expect(screen.getByRole("button", { name: /Médio/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("mostra a área anterior marcada, e ela continua trocável", async () => {
    montar(caso({ gravidade: "medio", extrato_para_o_setor: EXTRATO }), "Recepcao");

    await waitFor(() => {
      expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao");
    });
    expect(screen.getByText(/Recepcao devolveu este caso/)).toBeTruthy();
  });

  it("a tela se apresenta pelo ato que o ouvidor clicou", () => {
    // O botão do Dossiê diz "Encaminhar para outra área". Uma tela intitulada
    // "Validar e acionar" faria o ouvidor achar que abriu a coisa errada.
    montar(caso({ gravidade: "medio", extrato_para_o_setor: EXTRATO }), "Recepcao");

    expect(screen.getByText(/Encaminhar 2026-0012 para outra área/)).toBeTruthy();
  });

  it("caso que nunca foi acionado continua abrindo com o extrato em branco", () => {
    // O padrão do primeiro despacho não muda: sem extrato gravado não há o que
    // trazer, e preencher com o resumo mandaria a palavra de quem manifestou ao
    // setor (issue #325).
    montar(caso());

    expect((screen.getByLabelText(/Extrato para o setor/) as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText(/devolveu este caso/)).toBeNull();
  });
});
