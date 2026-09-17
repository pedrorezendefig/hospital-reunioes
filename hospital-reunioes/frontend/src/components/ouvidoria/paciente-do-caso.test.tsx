/**
 * @vitest-environment jsdom
 */

/**
 * O Paciente do caso na janela "Nova manifestação" (issue #663, PRD #659).
 *
 * A montagem do corpo já tem teste próprio em `lib/ouvidoria/registro.ts`. O
 * que só existe aqui dentro é a fiação da tela: os dois campos existirem, o
 * ouvidor conseguir digitar neles, e eles NÃO sumirem quando ele marca a
 * manifestação como anônima (decisão 3 do ADR 0052: quem o anonimato protege é
 * quem manifesta, e o paciente é outra pessoa). Sem este arquivo, alguém que
 * pendurasse os campos no mesmo `!anonimo` de "Quem manifestou" manteria a
 * suíte verde e o ouvidor perderia a tela justamente no caso do acompanhante
 * anônimo, que é o que motivou a fatia.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NovaManifestacaoModal } from "./NovaManifestacaoModal";

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

const NOME = "Nome do paciente (opcional)";
// O rótulo do campo sai em caixa alta, e a régua da casa (RN-76, D-19) só
// deixa rótulo curto passar: quem carrega a pergunta inteira é o placeholder.
const REFERENCIA = "Referência do atendimento (opcional)";
const PERGUNTA_DA_REFERENCIA = "Quando ou onde foi: data, setor ou leito";

describe("paciente do caso no registro manual (issue #663)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respostaJson({ setores: [] }))
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function abrir() {
    render(<NovaManifestacaoModal aberto token="token-de-teste" onClose={() => {}} onRegistrada={() => {}} />);
  }

  it("oferece os dois campos do paciente, vazios e opcionais", async () => {
    abrir();

    const nome = (await screen.findByLabelText(NOME)) as HTMLInputElement;
    const referencia = screen.getByLabelText(REFERENCIA) as HTMLInputElement;

    expect(nome.value).toBe("");
    expect(referencia.value).toBe("");
    expect(nome.required).toBe(false);
    expect(referencia.required).toBe(false);
    expect(referencia.placeholder).toBe(PERGUNTA_DA_REFERENCIA);
  });

  it("guarda o que o ouvidor digitou nos dois campos", async () => {
    abrir();

    const nome = (await screen.findByLabelText(NOME)) as HTMLInputElement;
    const referencia = screen.getByLabelText(REFERENCIA) as HTMLInputElement;
    fireEvent.change(nome, { target: { value: "Maria Souza" } });
    fireEvent.change(referencia, { target: { value: "Leito 12, dia 09/09" } });

    expect(nome.value).toBe("Maria Souza");
    expect(referencia.value).toBe("Leito 12, dia 09/09");
  });

  it("mantém os campos do paciente com a manifestação anônima marcada", async () => {
    abrir();

    const nome = (await screen.findByLabelText(NOME)) as HTMLInputElement;
    fireEvent.change(nome, { target: { value: "Maria Souza" } });
    fireEvent.click(screen.getByLabelText(/Manifestação anônima/));

    // Quem sai da tela é a identificação de quem manifestou, não o paciente.
    expect(screen.queryByLabelText("Quem manifestou")).toBeNull();
    expect((screen.getByLabelText(NOME) as HTMLInputElement).value).toBe("Maria Souza");
    expect(screen.getByLabelText(REFERENCIA)).toBeTruthy();
  });
});
