/**
 * A FIAÇÃO do destino no login, e não a régua (issue #477, RN-54).
 *
 * A régua de o que é destino interno tem teste próprio em `lib/login/destino`.
 * O que só existe aqui é a ligação: o `login` ler o campo do formulário, passar
 * pela régua e mandar a pessoa para lá. Sem este arquivo, trocar a última linha
 * da action por `redirect("/dashboard")` fixo deixaria a suíte inteira verde e
 * apagaria a funcionalidade em silêncio.
 *
 * O par perigoso também vive aqui: a action re-mede o valor mesmo tendo a tela
 * medido antes. O campo vem de formulário, ou seja, do cliente, e quem entrega
 * o valor é quem monta o link. Uma prova só na tela seria prova nenhuma.
 *
 * Supabase entra dublado no ponto único por onde a action fala com ele. Não há
 * rede e não há cookie: o que está sob teste é para onde a pessoa vai.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const signOut = vi.fn();
const redirect = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => redirect(destino),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({ auth: { signInWithPassword, signOut } }),
}));

import { login } from "./auth";

function formulario(destino?: string): FormData {
  const dados = new FormData();
  dados.set("email", "ouvidor@hsm.test");
  dados.set("password", "senha-correta");
  if (destino !== undefined) dados.set("redirect", destino);
  return dados;
}

describe("para onde o login devolve a pessoa", () => {
  beforeEach(() => {
    signInWithPassword.mockReset();
    redirect.mockReset();
    signInWithPassword.mockResolvedValue({ error: null });
  });

  it("devolve ao destino original quando ele é interno", async () => {
    await login(formulario("/ouvidoria/m/2026-0012"));

    expect(redirect).toHaveBeenCalledWith("/ouvidoria/m/2026-0012");
  });

  it("ignora destino de fora do site e cai no dashboard", async () => {
    await login(formulario("https://evil.com/roubo"));
    expect(redirect).toHaveBeenCalledWith("/dashboard");

    redirect.mockReset();
    await login(formulario("//evil.com"));
    expect(redirect).toHaveBeenCalledWith("/dashboard");

    redirect.mockReset();
    await login(formulario("/\\evil.com"));
    expect(redirect).toHaveBeenCalledWith("/dashboard");
  });

  it("sem destino no formulário, segue indo ao dashboard", async () => {
    await login(formulario());

    expect(redirect).toHaveBeenCalledWith("/dashboard");
  });

  it("não devolve a lugar nenhum quando a autenticação falha", async () => {
    // O destino não pode virar navegação sem sessão: senão o link com
    // `?redirect=` seria um jeito de atravessar a porta com senha errada.
    signInWithPassword.mockResolvedValue({ error: { message: "Invalid login credentials" } });

    const resultado = await login(formulario("/ouvidoria/m/2026-0012"));

    expect(resultado).toEqual({ error: "Invalid login credentials" });
    expect(redirect).not.toHaveBeenCalled();
  });
});
