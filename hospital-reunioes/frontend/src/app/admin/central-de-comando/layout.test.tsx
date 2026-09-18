/**
 * O `layout.tsx` da seção Central de Comando (issue #814, ADR 0058, decisão 1).
 *
 * A decisão de quem entra é do guard (`lib/central-de-comando/guard.test.ts`);
 * aqui se prova a ligação: toda tela da seção passa pelo guard antes de
 * existir, e quem ele redireciona não recebe a página.
 */

import { describe, expect, it, vi } from "vitest";

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

describe("o layout da seção Central de Comando", () => {
  it("entrega a tela a quem o guard deixa entrar", async () => {
    guarda.decisao = "entra";

    const pagina = await CentralDeComandoLayout({ children: "a tela" });

    expect(requireSuperAdminNaCentral).toHaveBeenCalled();
    expect(pagina).toBeTruthy();
  });

  it("não entrega a tela a quem o guard redireciona", async () => {
    guarda.decisao = "/dashboard";

    await expect(CentralDeComandoLayout({ children: "a tela" })).rejects.toThrow("/dashboard");
  });
});
