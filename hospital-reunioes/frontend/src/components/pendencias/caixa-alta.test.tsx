/**
 * @vitest-environment jsdom
 */

/**
 * Caixa alta no detalhe da Pendência (ADR 0080, issue #1454).
 *
 * A regra base do `globals.css` põe botão e etiqueta em caixa alta. O nome do
 * responsável aparece dentro do botão do seletor, e é dado do banco: ele leva
 * `normal-case` e sai como foi escrito.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { apareceComoFoiEscrito } from "@/lib/caixa-alta";
import type { Pendencia } from "@/types";

import { PendenciaDetailModal } from "./PendenciaDetailModal";
import { StatusBadge } from "./StatusBadge";

const PENDENCIA: Pendencia = {
  id_acao: "AC_1",
  descricao_acao: "Revisar a escala do plantão",
  responsavel_id: "P_1",
  responsavel_nome: "Maria da Silva",
  status: "PENDENTE",
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("detalhe da Pendência", () => {
  it("o nome do responsável aparece como foi escrito dentro do seletor", async () => {
    render(
      <ToastProvider>
        <PendenciaDetailModal
          pendencia={PENDENCIA}
          token="tok"
          participantes={[{ id: "P_1", nome_completo: "Maria da Silva" }]}
          onClose={() => {}}
        />
      </ToastProvider>,
    );

    const nome = await screen.findByText("Maria da Silva");
    expect(nome.closest("button")).not.toBeNull();
    expect(apareceComoFoiEscrito(nome)).toBe(true);
  });

  it("a etiqueta de situação é Texto curto", () => {
    render(<StatusBadge status="EM_PROGRESSO" />);

    expect(apareceComoFoiEscrito(screen.getByText("EM PROGRESSO"))).toBe(false);
  });
});
