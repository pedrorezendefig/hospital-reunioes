/**
 * @vitest-environment jsdom
 */

/**
 * Caixa alta na Biblioteca de POPs (ADR 0080, issue #1454).
 *
 * O título de cada grupo é o nome do setor, e o título da ficha é o nome do
 * POP: os dois são dado digitado dentro de um título, e saem como foram
 * escritos (`normal-case`), enquanto a regra base põe o resto em caixa alta.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { apareceComoFoiEscrito } from "@/lib/caixa-alta";

import { BibliotecaPops, type BibliotecaItem } from "./BibliotecaPops";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "tok", userId: "U_1", userEmail: null, loading: false }),
}));

const ITEM: BibliotecaItem = {
  pop_id: "POP_1",
  codigo: "POP-ENF-001",
  nome: "Higienização das mãos na UTI",
  setor_id: "S_1",
  setor_nome: "Centro de Terapia Intensiva",
  setor_sigla: null,
  numero_versao: "1.0",
  criticidade: "ALTA",
  periodicidade_revisao: "1_ano",
  elaborador_nome: null,
  revisor_nome: null,
  validador_nome: null,
  criado_em: null,
  elaboracao_concluida_em: null,
  revisao_aprovada_em: null,
  validacao_aprovada_em: null,
  publicado_em: null,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [ITEM] }) as unknown as Response),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function montar() {
  return render(
    <ToastProvider>
      <BibliotecaPops />
    </ToastProvider>,
  );
}

describe("Biblioteca de POPs", () => {
  it("o nome do setor no título do grupo aparece como foi escrito", async () => {
    montar();

    const titulo = await screen.findByRole("heading", { name: /Centro de Terapia Intensiva/ });
    expect(apareceComoFoiEscrito(titulo)).toBe(true);
  });

  it("o nome do POP no título da ficha aparece como foi escrito", async () => {
    montar();

    fireEvent.click(await screen.findByText("Higienização das mãos na UTI"));

    const titulo = await screen.findByRole("heading", { name: "Higienização das mãos na UTI" });
    expect(apareceComoFoiEscrito(titulo)).toBe(true);
  });
});
