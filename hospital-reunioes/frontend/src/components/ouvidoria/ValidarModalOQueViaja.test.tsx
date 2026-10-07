/**
 * @vitest-environment jsdom
 */

/**
 * O texto de ajuda do Extrato para o setor diz o que vai à área neste caso
 * (issue #769).
 *
 * A frase antiga dizia "é este texto que vai no email do responsável, e só
 * ele" em todo caso, e no caso comum vão também o resumo, o relato integral e
 * o nome de quem manifestou. O ouvidor decide o que escrever olhando para ela,
 * então ela acompanha a marca de sigilo ao vivo.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidarModal } from "./ValidarModal";

// Trechos que só a frase de cada variante tem: o teste não copia a frase
// inteira, que é conferida contra o contrato em `o-que-viaja.test.ts`.
const COMUM = /do relato integral, do nome de quem manifestou/;
const ANONIMO = /Manifestação anônima: vai no email/;
const SIGILO = /Sigilo reforçado: é este texto que vai no email e na tela do responsável, e só ele/;

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    tipo_manifestacao: "reclamacao" as const,
    categoria: "Demora no atendimento",
    setor: "Recepcao",
    sigilo_reforcado: false,
    anonimo: false,
    ...overrides,
  };
}

function montar(manifestacao: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/setores")) {
        return { ok: true, json: async () => ["Recepcao"] } as Response;
      }
      return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
    })
  );
  render(
    <ValidarModal manifestacao={manifestacao as never} token="token-de-teste" onClose={vi.fn()} onAcionada={vi.fn()} />
  );
}

function ajuda(): string {
  // O texto de ajuda é o parágrafo logo abaixo do campo.
  const campo = screen.getByLabelText(/Extrato para o setor/);
  return campo.nextElementSibling?.textContent ?? "";
}

describe("o texto de ajuda do extrato diz o que vai à área (issue #769)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("no caso comum, diz que o relato integral e o nome também vão", () => {
    montar(caso());

    expect(ajuda()).toMatch(COMUM);
    expect(ajuda()).not.toMatch(/e só ele|não sai daqui/);
  });

  it("no caso anônimo, diz que o relato vai e a identificação não", () => {
    montar(caso({ anonimo: true }));

    expect(ajuda()).toMatch(ANONIMO);
  });

  it("no caso sob sigilo reforçado, diz que só o extrato vai", () => {
    montar(caso({ sigilo_reforcado: true }));

    expect(ajuda()).toMatch(SIGILO);
  });

  it("ligar o sigilo no modal troca a frase na hora, e desligar volta", () => {
    montar(caso());
    const marca = screen.getByRole("checkbox");

    fireEvent.click(marca);
    expect(ajuda()).toMatch(SIGILO);

    fireEvent.click(marca);
    expect(ajuda()).toMatch(COMUM);
  });

  it("o tipo sigiloso por natureza trava a marca e troca a frase, e voltar o tipo devolve", () => {
    montar(caso({ anonimo: true }));
    const tipo = screen.getByLabelText(/Tipo da manifestação/);

    fireEvent.change(tipo, { target: { value: "denuncia" } });
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(ajuda()).toMatch(SIGILO);

    fireEvent.change(tipo, { target: { value: "reclamacao" } });
    expect(ajuda()).toMatch(ANONIMO);
  });
});
