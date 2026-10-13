/**
 * @vitest-environment jsdom
 */

/**
 * O botão "Ditar" de Contas médicas (issue #1145): grava pela rota de voz que
 * o app já tem e devolve o texto para o campo, onde a pessoa revisa. O botão
 * nunca envia o formulário em que está, e o aviso de paciente fica sempre ao
 * lado dele.
 */
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { Ditar, juntarDitado } from "./Ditar";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

class GravadorFalso {
  static ultimo: GravadorFalso | null = null;
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: unknown, opcoes?: { mimeType?: string }) {
    this.mimeType = opcoes?.mimeType ?? "audio/webm";
    GravadorFalso.ultimo = this;
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["bytes-de-audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

type Chamada = { url: string; metodo: string; autorizacao: string | undefined };
let chamadas: Chamada[];
let respostaDaVoz: { status: number; corpo: unknown };

beforeEach(() => {
  chamadas = [];
  respostaDaVoz = { status: 200, corpo: { texto: "a seringa veio sem o kit" } };
  GravadorFalso.ultimo = null;
  vi.stubGlobal("MediaRecorder", GravadorFalso);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [{ stop: vi.fn() }] }) },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const autorizacao = (init?.headers as Record<string, string> | undefined)?.Authorization;
      chamadas.push({ url, metodo, autorizacao });
      const { status, corpo } = respostaDaVoz;
      return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Um formulário de verdade, com envio, para provar que ditar não envia. */
function Formulario({ aoEnviar }: { aoEnviar: (texto: string) => void }) {
  const [texto, setTexto] = useState("Conferir");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        aoEnviar(texto);
      }}
    >
      <textarea aria-label="Motivo" value={texto} onChange={(e) => setTexto(e.target.value)} />
      <Ditar campo="Motivo" aoTranscrever={(ditado) => setTexto((atual) => juntarDitado(atual, ditado))} />
      <button type="submit">Enviar</button>
    </form>
  );
}

async function ditar(campo: string) {
  fireEvent.click(screen.getByRole("button", { name: `Ditar: ${campo}` }));
  await waitFor(() => expect(GravadorFalso.ultimo?.state).toBe("recording"));
  fireEvent.click(screen.getByRole("button", { name: `Parar o ditado: ${campo}` }));
}

describe("o botão Ditar", () => {
  it("mostra o aviso fixo de paciente ao lado do botão", () => {
    render(
      <ToastProvider>
        <Formulario aoEnviar={vi.fn()} />
      </ToastProvider>,
    );

    expect(screen.getByRole("button", { name: "Ditar: Motivo" }).textContent).toContain("Ditar");
    expect(screen.getByText("Não dite nome nem dado de paciente.")).toBeTruthy();
  });

  it("o texto transcrito entra no campo, depois do que já havia, e nada é enviado", async () => {
    const aoEnviar = vi.fn();
    render(
      <ToastProvider>
        <Formulario aoEnviar={aoEnviar} />
      </ToastProvider>,
    );

    await ditar("Motivo");

    await waitFor(() =>
      expect((screen.getByLabelText("Motivo") as HTMLTextAreaElement).value).toBe("Conferir a seringa veio sem o kit"),
    );
    const voz = chamadas.filter((c) => c.url.endsWith("/transcricao/voz"));
    expect(voz).toHaveLength(1);
    expect(voz[0].metodo).toBe("POST");
    expect(voz[0].autorizacao).toBe("Bearer token-de-teste");
    expect(aoEnviar).not.toHaveBeenCalled();
  });

  it("falha na transcrição não deixa o botão preso em Transcrevendo", async () => {
    respostaDaVoz = { status: 502, corpo: { detail: "fora" } };
    render(
      <ToastProvider>
        <Formulario aoEnviar={vi.fn()} />
      </ToastProvider>,
    );

    await ditar("Motivo");

    await waitFor(() => expect(chamadas).toHaveLength(1));
    const botao = (await screen.findByRole("button", { name: "Ditar: Motivo" })) as HTMLButtonElement;
    await waitFor(() => expect(botao.disabled).toBe(false));
    expect((screen.getByLabelText("Motivo") as HTMLTextAreaElement).value).toBe("Conferir");
  });
});

describe("juntarDitado", () => {
  it("campo vazio recebe só o ditado", () => {
    expect(juntarDitado("  ", "texto novo")).toBe("texto novo");
  });
});
