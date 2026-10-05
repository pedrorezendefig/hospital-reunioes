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

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AVISO_PACIENTE_PODE_IDENTIFICAR } from "@/lib/ouvidoria/publico";

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

  /** O mínimo que destrava o botão de registrar, sem nada do paciente. */
  function preencherObrigatorios() {
    fireEvent.change(screen.getByLabelText("Data e hora do contato"), {
      target: { value: "2026-08-14T16:50" },
    });
    fireEvent.change(screen.getByLabelText("Tipo da manifestação"), { target: { value: "reclamacao" } });
    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "Recepção" } });
    fireEvent.change(screen.getByLabelText("Resumo"), { target: { value: "Espera de duas horas." } });
    fireEvent.change(screen.getByLabelText("Relato integral"), {
      target: { value: "Cheguei às 8h e só fui atendido às 10h30." },
    });
  }

  it("oferece os dois campos do paciente, vazios e opcionais", async () => {
    abrir();

    const nome = (await screen.findByLabelText(NOME)) as HTMLInputElement;
    const referencia = screen.getByLabelText(REFERENCIA) as HTMLInputElement;

    expect(nome.value).toBe("");
    expect(referencia.value).toBe("");
    expect(referencia.placeholder).toBe(PERGUNTA_DA_REFERENCIA);
  });

  it("trava os dois campos em 200 caracteres, que é o teto do banco", async () => {
    // O teto do backend é 200, e passar dele é 422 depois de o ouvidor ter
    // digitado tudo. O atributo na tela é o que impede colar o relato inteiro
    // na referência, e some com uma linha apagada sem nenhum teste reclamar.
    abrir();

    const nome = (await screen.findByLabelText(NOME)) as HTMLInputElement;
    const referencia = screen.getByLabelText(REFERENCIA) as HTMLInputElement;

    expect(nome.maxLength).toBe(200);
    expect(referencia.maxLength).toBe(200);
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

  it("avisa que o paciente pode indicar quem manifestou, e só no anônimo", async () => {
    // O ADR 0052 escreve a contrapartida nas consequências: "o formulário diz
    // isso à pessoa no aviso do campo, e a escolha é dela". Aqui quem lê é o
    // ouvidor, que digita em nome de quem ligou e é quem pode confirmar antes.
    // No caso identificado o nome de quem manifestou já está gravado, e repetir
    // o alerta viraria ruído.
    abrir();

    expect(await screen.findByLabelText(NOME)).toBeTruthy();
    expect(screen.queryByText(AVISO_PACIENTE_PODE_IDENTIFICAR)).toBeNull();

    fireEvent.click(screen.getByLabelText(/Manifestação anônima/));

    expect(screen.getByText(AVISO_PACIENTE_PODE_IDENTIFICAR)).toBeTruthy();
  });

  it("leva o paciente no corpo da requisição do registro", async () => {
    // A costura tela para corpo: `montarRegistro` tem teste próprio como função
    // pura, e os campos têm teste como input. O que ninguém prova sem isto é
    // que os dois estão LIGADOS, e um estado esquecido no `VAZIO` do modal
    // mandaria string vazia para sempre com a suíte verde.
    const chamadas: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        if (String(url).includes("/api/ouvidoria/manifestacoes")) {
          return respostaJson({ id: "uuid-1", protocolo: "2026-0007" });
        }
        return respostaJson(["Recepção"]);
      })
    );
    abrir();

    fireEvent.change(await screen.findByLabelText(NOME), { target: { value: "Maria Souza" } });
    fireEvent.change(screen.getByLabelText(REFERENCIA), { target: { value: "Leito 12, dia 09/09" } });
    preencherObrigatorios();
    fireEvent.click(screen.getByText("Registrar manifestação"));

    await waitFor(() => {
      const envio = chamadas.find((c) => c.url.endsWith("/api/ouvidoria/manifestacoes"));
      expect(envio).toBeTruthy();
      expect(envio!.body).toMatchObject({
        paciente_nome: "Maria Souza",
        paciente_referencia: "Leito 12, dia 09/09",
      });
    });
  });

  it("o 422 diz ao ouvidor que o paciente tem limite, e não só que falta campo", async () => {
    // Os campos do paciente são os únicos do formulário capazes de gerar um 422
    // que a frase antiga ("relato, tipo, setor e resumo são obrigatórios") não
    // explica: o ouvidor releria os campos certos e não acharia nada.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/ouvidoria/manifestacoes")) {
          return { ok: false, status: 422, json: async () => ({}) } as Response;
        }
        return respostaJson(["Recepção"]);
      })
    );
    abrir();

    expect(await screen.findByLabelText(NOME)).toBeTruthy();
    preencherObrigatorios();
    fireEvent.click(screen.getByText("Registrar manifestação"));

    const erro = await screen.findByText(/no máximo 200 caracteres/);
    expect(erro.textContent).toContain("o nome do paciente e a referência do atendimento");
  });
});
