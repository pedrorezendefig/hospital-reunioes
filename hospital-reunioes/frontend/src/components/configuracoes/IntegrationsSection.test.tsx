/**
 * @vitest-environment jsdom
 */

/**
 * As Integrações das Configurações e a Caixa alta (issue #1455, ADR 0080).
 *
 * O nome de cada integração vem do servidor (ClickSign, Supabase) e é nome de
 * produto: no título do cartão ele aparece como o servidor manda.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

import IntegrationsSection from "./IntegrationsSection";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Caixa alta nas Integrações", () => {
  it("o nome da integração no título do cartão aparece como o servidor manda", async () => {
    const integracoes = [{ nome: "ClickSign", descricao: "Assinatura das atas.", conectado: true }];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(integracoes), { status: 200 })));

    render(
      <ToastProvider>
        <IntegrationsSection token="token-de-teste" />
      </ToastProvider>,
    );

    const titulo = await screen.findByRole("heading", { level: 3, name: "ClickSign" });
    expect(caixaDoDado(titulo)).toBe("normal-case");
  });
});
