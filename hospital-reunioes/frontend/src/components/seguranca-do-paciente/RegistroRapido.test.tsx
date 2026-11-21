/**
 * @vitest-environment jsdom
 */

/**
 * O registro rápido do Núcleo (issue #1998, PRD #1979).
 *
 * Numa tela só, quatro campos: relato, setor, data e origem (busca ativa,
 * ronda, reunião rápida, auditoria, outra). Quem registrou é o autor pela
 * sessão; a tela não manda nome nem contato. Quem pode registrar o servidor
 * decide (`backend/tests/test_seguranca_do_paciente_registro_rapido.py`); a
 * tela mostra a recusa que vier.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegistroRapido } from "./RegistroRapido";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

interface Chamada {
  url: string;
  metodo: string;
  corpo: Record<string, unknown> | null;
  autorizacao: string | null;
}

let chamadas: Chamada[] = [];
let respostaDoEnvio: { status: number; corpo: unknown };

beforeEach(() => {
  chamadas = [];
  respostaDoEnvio = { status: 201, corpo: { protocolo: "NSP-2026-0012", criado_em: "2026-11-20T10:00:00+00:00" } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({
        url,
        metodo: init?.method ?? "GET",
        corpo: init?.body ? JSON.parse(String(init.body)) : null,
        autorizacao: new Headers(init?.headers).get("Authorization"),
      });
      if (url === "/api/nsp/publico/setores") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ setores: [{ id: "setor-uti", nome: "UTI Adulto" }] }),
        } as Response;
      }
      const { status, corpo } = respostaDoEnvio;
      return { ok: status < 300, status, json: async () => corpo } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const RELATO = "Na ronda, a pulseira do leito 7 estava sem o nome da mãe.";

async function abrir(aoRegistrar = vi.fn()) {
  render(<RegistroRapido aoRegistrar={aoRegistrar} />);
  await screen.findByRole("option", { name: "UTI Adulto" });
  return aoRegistrar;
}

function registrar() {
  return screen.getByRole("button", { name: "Registrar" }) as HTMLButtonElement;
}

function preencher({ origem = "Ronda", data = "2026-11-19" } = {}) {
  fireEvent.change(screen.getByLabelText("O que foi encontrado"), { target: { value: RELATO } });
  fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "setor-uti" } });
  fireEvent.change(screen.getByLabelText("Data"), { target: { value: data } });
  fireEvent.click(within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: origem }));
}

describe("os quatro campos", () => {
  it("registra relato, setor, data e origem, com a sessão, e mostra o protocolo", async () => {
    const aoRegistrar = await abrir();
    preencher({ origem: "Reunião rápida" });
    fireEvent.click(registrar());

    expect(await screen.findByText("Registrado com o protocolo NSP-2026-0012.")).toBeTruthy();
    const envio = chamadas.find((c) => c.metodo === "POST");
    expect(envio?.url).toBe("/api/nsp/notificacoes/registro-rapido");
    expect(envio?.autorizacao).toBe("Bearer token-de-teste");
    expect(envio?.corpo).toEqual({
      relato: RELATO,
      setor_id: "setor-uti",
      data_ocorrencia: "2026-11-19",
      origem: "reuniao_rapida",
    });
    expect(aoRegistrar).toHaveBeenCalledTimes(1);
  });

  it("as cinco origens, com o valor que o servidor grava", async () => {
    await abrir();
    const grupo = screen.getByRole("group", { name: "Origem" });
    expect(within(grupo).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Busca ativa",
      "Ronda",
      "Reunião rápida",
      "Auditoria",
      "Outra",
    ]);
    preencher({ origem: "Busca ativa" });
    fireEvent.click(registrar());

    await screen.findByText(/Registrado com o protocolo/);
    expect(chamadas.find((c) => c.metodo === "POST")?.corpo?.origem).toBe("busca_ativa");
  });

  it("sem um dos quatro campos, o Registrar fica desligado", async () => {
    await abrir();
    expect(registrar().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("O que foi encontrado"), { target: { value: RELATO } });
    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "setor-uti" } });
    expect(registrar().disabled).toBe(true);

    fireEvent.click(within(screen.getByRole("group", { name: "Origem" })).getByRole("button", { name: "Auditoria" }));
    expect(registrar().disabled).toBe(false);

    fireEvent.change(screen.getByLabelText("Data"), { target: { value: "" } });
    expect(registrar().disabled).toBe(true);
  });

  it("depois de registrar, a tela fica limpa para o próximo", async () => {
    await abrir();
    preencher();
    fireEvent.click(registrar());

    await screen.findByText(/Registrado com o protocolo/);
    expect((screen.getByLabelText("O que foi encontrado") as HTMLTextAreaElement).value).toBe("");
    expect(registrar().disabled).toBe(true);
  });

  it("a recusa do servidor aparece e o relato continua na tela", async () => {
    respostaDoEnvio = { status: 403, corpo: { detail: "Conteúdo restrito ao Núcleo de Segurança do Paciente" } };
    const aoRegistrar = await abrir();
    preencher();
    fireEvent.click(registrar());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Conteúdo restrito ao Núcleo de Segurança do Paciente"
    );
    expect((screen.getByLabelText("O que foi encontrado") as HTMLTextAreaElement).value).toBe(RELATO);
    expect(aoRegistrar).not.toHaveBeenCalled();
  });
});

describe("cabe numa tela a 375 px", () => {
  it("todo controle tem alvo de toque de 44 px", async () => {
    await abrir();
    const controles = [
      ...screen.getAllByRole("button"),
      ...screen.getAllByRole("combobox"),
      screen.getByLabelText("Data"),
    ];
    for (const controle of controles) {
      expect(controle.className, controle.textContent ?? "").toContain("min-h-[44px]");
    }
  });

  it("as origens empilham em duas colunas e nada tem largura fixa maior que a tela", async () => {
    const { container } = render(<RegistroRapido aoRegistrar={vi.fn()} />);
    await screen.findByRole("option", { name: "UTI Adulto" });

    const grupo = screen.getByRole("group", { name: "Origem" });
    expect(grupo.className.split(/\s+/)).toContain("grid-cols-2");
    // Setor e data lado a lado só a partir do `sm`.
    const ondeEQuando = screen.getByLabelText("Setor").closest("[data-linha]")!;
    expect(ondeEQuando.className.split(/\s+/)).toEqual(expect.arrayContaining(["grid-cols-1", "sm:grid-cols-2"]));
    for (const elemento of Array.from(container.querySelectorAll("[class]"))) {
      const classes = elemento.getAttribute("class") ?? "";
      for (const [, px] of classes.matchAll(/(?:^|\s)(?:w|min-w)-\[(\d+)px\]/g)) {
        expect(Number(px)).toBeLessThanOrEqual(375);
      }
    }
    // O relato é curto: três linhas, para o Registrar ficar à vista.
    expect((screen.getByLabelText("O que foi encontrado") as HTMLTextAreaElement).rows).toBe(3);
  });
});
