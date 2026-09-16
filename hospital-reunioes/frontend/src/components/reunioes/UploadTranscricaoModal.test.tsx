/**
 * @vitest-environment jsdom
 */

/**
 * O par na tela da recusa por tamanho (issue #758).
 *
 * O backend passou a ler `.pdf` e `.docx` num processo separado, com teto de
 * memória e prazo. Quando o filho é morto, a rota devolve 422 com uma frase que
 * existe para a pessoa distinguir "este arquivo é grande ou complexo demais" de
 * "deu erro" e saber o que fazer (mandar .txt, dividir o documento).
 *
 * Carimbo de backend sem par na tela some em silêncio, e neste repo isso já
 * mordeu mais de uma vez. O que se prova aqui é uma coisa só: a frase que o
 * backend mandou é a frase que aparece, inteira. Um refactor que trocasse o
 * `detail` por uma mensagem genérica ("Erro ao enviar arquivo") deixaria a
 * pessoa sem saber que o caminho é dividir o documento, e derruba este teste.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadTranscricaoModal } from "./UploadTranscricaoModal";

// A frase é do backend (`MENSAGEM_GRANDE_DEMAIS` em transcricao_extractor.py).
// Está copiada aqui de propósito: é o contrato entre os dois lados, e o teste
// tem que falhar se um lado mudar sem o outro.
const FRASE_DO_BACKEND =
  "Este arquivo é grande ou complexo demais para ser lido. Não é defeito no arquivo: " +
  "a leitura foi interrompida antes de comprometer o sistema. Envie a transcrição em " +
  ".txt, ou divida o documento em partes menores.";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "tok" } } }),
    },
  }),
}));

afterEach(() => {
  // O vitest deste projeto nao roda com `globals: true`, entao a limpeza
  // automatica do testing-library nao entra sozinha.
  cleanup();
  vi.restoreAllMocks();
});

function anexar(nome: string) {
  const entrada = document.querySelector('input[type="file"]') as HTMLInputElement;
  const arquivo = new File(["conteudo"], nome, { type: "application/pdf" });
  Object.defineProperty(entrada, "files", { value: [arquivo], configurable: true });
  fireEvent.change(entrada);
}

function responderCom(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status < 400,
      status,
      json: async () => corpo,
    })),
  );
}

describe("UploadTranscricaoModal, a recusa que a pessoa lê", () => {
  it("mostra a frase do backend inteira quando o arquivo é grande demais", async () => {
    responderCom(422, { detail: FRASE_DO_BACKEND });
    render(<UploadTranscricaoModal onClose={() => {}} onSuccess={() => {}} />);

    anexar("orcamento.pdf");
    fireEvent.submit(screen.getByRole("button", { name: /processar com ia/i }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(FRASE_DO_BACKEND)).toBeDefined();
    });
  });

  it("nao troca a recusa do backend por uma mensagem generica de HTTP", async () => {
    responderCom(422, { detail: FRASE_DO_BACKEND });
    render(<UploadTranscricaoModal onClose={() => {}} onSuccess={() => {}} />);

    anexar("orcamento.pdf");
    fireEvent.submit(screen.getByRole("button", { name: /processar com ia/i }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(FRASE_DO_BACKEND)).toBeDefined();
    });
    // A frase genérica do `catch` continua existindo para resposta sem corpo,
    // mas não pode aparecer no lugar de uma recusa que o backend explicou.
    expect(screen.queryByText(/HTTP 422/)).toBeNull();
  });
});
