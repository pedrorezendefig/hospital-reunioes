/**
 * @vitest-environment jsdom
 */

/**
 * O select "Canal de origem" do registro manual (issue #721, PRD #720).
 *
 * A lista fechada já tem teste próprio em `lib/ouvidoria/registro.ts`. O que só
 * existe aqui dentro é a fiação: o select ler essa lista e o formulário nascer
 * no primeiro item dela. Sem este arquivo, alguém que deixasse o formulário
 * nascendo em "telefone" manteria a suíte verde e o ouvidor continuaria
 * carimbando como telefone o que chega pelo WhatsApp, que é o problema inteiro
 * desta issue.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NovaManifestacaoModal } from "./NovaManifestacaoModal";

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

describe("canal de origem do registro manual (issue #721)", () => {
  beforeEach(() => {
    // O modal carrega setores ao abrir, e nada disso importa para o select.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respostaJson({ setores: [] }))
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("oferece os sete canais do ouvidor, na ordem em que o select mostra", async () => {
    render(<NovaManifestacaoModal aberto token="token-de-teste" onClose={() => {}} onRegistrada={() => {}} />);

    const select = (await screen.findByLabelText("Canal de origem")) as HTMLSelectElement;

    expect([...select.options].map((o) => o.value)).toEqual([
      "whatsapp",
      "telefone",
      "presencial",
      "email",
      "instagram",
      "reclame_aqui",
      "google",
    ]);
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "WhatsApp",
      "Telefone",
      "Presencial (balcão)",
      "Email",
      "Instagram",
      "Reclame Aqui",
      "Google",
    ]);
  });

  it("nasce em WhatsApp, que é de onde mais chega", async () => {
    // História 5 do PRD: o ouvidor esquece de trocar, e o padrão é o que fica
    // gravado. Sem opção vazia: o campo é obrigatório e sempre tem valor.
    render(<NovaManifestacaoModal aberto token="token-de-teste" onClose={() => {}} onRegistrada={() => {}} />);

    const select = (await screen.findByLabelText("Canal de origem")) as HTMLSelectElement;

    expect(select.value).toBe("whatsapp");
  });
});
