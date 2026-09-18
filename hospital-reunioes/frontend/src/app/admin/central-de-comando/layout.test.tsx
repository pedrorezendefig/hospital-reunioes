/**
 * @vitest-environment jsdom
 */

/**
 * O `layout.tsx` da seção Central de Comando (issue #814, ADR 0058, decisão 1).
 *
 * A decisão de quem entra é do guard (`lib/central-de-comando/guard.test.ts`);
 * aqui se prova a ligação: toda tela da seção passa pelo guard antes de
 * existir, quem ele deixa entrar recebe a tela de verdade, e quem ele
 * redireciona não recebe nada.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const guarda = vi.hoisted(() => ({ decisao: "entra" as "entra" | string }));

class RedirecionouError extends Error {}

vi.mock("@/lib/central-de-comando/guard", () => ({
  requireSuperAdminNaCentral: vi.fn(async () => {
    if (guarda.decisao !== "entra") throw new RedirecionouError(guarda.decisao);
    return { user: { id: "u1" } };
  }),
}));

import CentralDeComandoLayout from "./layout";
import { requireSuperAdminNaCentral } from "@/lib/central-de-comando/guard";

beforeEach(() => {
  // A contagem de chamadas do guard é por teste: sem a limpeza, um teste
  // passaria em "chamou o guard" pela chamada que o anterior deixou.
  vi.clearAllMocks();
  guarda.decisao = "entra";
});

afterEach(cleanup);

describe("o layout da seção Central de Comando", () => {
  it("entrega a tela a quem o guard deixa entrar", async () => {
    render(await CentralDeComandoLayout({ children: <p>a tela da Central</p> }));

    expect(requireSuperAdminNaCentral).toHaveBeenCalledTimes(1);
    expect(screen.getByText("a tela da Central")).toBeTruthy();
  });

  it("não entrega a tela a quem o guard redireciona", async () => {
    guarda.decisao = "/dashboard";

    await expect(CentralDeComandoLayout({ children: <p>a tela da Central</p> })).rejects.toThrow("/dashboard");
    expect(requireSuperAdminNaCentral).toHaveBeenCalledTimes(1);
  });
});
