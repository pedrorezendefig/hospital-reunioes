/**
 * O gate server-side do painel da Ouvidoria (issue #344, critério 3).
 *
 * O critério "demais papéis não veem o painel" não pode viver num `if` do
 * navegador: a página precisa deixar de existir para quem não é da Ouvidoria,
 * antes de chegar ao cliente. Estes testes exercitam a decisão do servidor.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const redirecionamentos: string[] = [];

/** O `redirect` do Next interrompe o fluxo lançando; o dublê faz o mesmo. */
class RedirecionouError extends Error {}

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => {
    redirecionamentos.push(destino);
    throw new RedirecionouError(destino);
  },
}));

let usuario: { id: string } | null = { id: "u1" };
let token: string | null = "jwt-de-teste";

vi.mock("../supabase/server", () => ({
  createClient: async () => ({
    auth: {
      getUser: async () => ({ data: { user: usuario } }),
      getSession: async () => ({ data: { session: token ? { access_token: token } : null } }),
    },
  }),
}));

import { requirePainelOuvidoriaAccess } from "./guard";

/** O `/api/participantes/me`, que é a fonte única dos eixos de permissão. */
function respondeMe(corpo: Record<string, unknown>, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => corpo })),
  );
}

async function tentarEntrar(): Promise<"entrou" | string> {
  try {
    await requirePainelOuvidoriaAccess();
    return "entrou";
  } catch (e) {
    if (e instanceof RedirecionouError) return e.message;
    throw e;
  }
}

beforeEach(() => {
  redirecionamentos.length = 0;
  usuario = { id: "u1" };
  token = "jwt-de-teste";
});

describe("quem o servidor deixa entrar no painel", () => {
  it("deixa passar os dois perfis da Ouvidoria", async () => {
    respondeMe({ perfil_ouvidoria: "ouvidor" });
    expect(await tentarEntrar()).toBe("entrou");

    respondeMe({ perfil_ouvidoria: "diretoria_executiva" });
    expect(await tentarEntrar()).toBe("entrou");
  });

  it("devolve à fila quem tem papel em Reuniões mas nenhum na Ouvidoria", async () => {
    // O pior caso é o super admin de Reuniões: ele passa em tudo do outro
    // contexto e na listagem que alimenta esta tela, e o gate da Ouvidoria não
    // tem bypass para ele (ADR 0034, decisão 8).
    respondeMe({ access_profile: "super_admin", perfil_ouvidoria: null });

    expect(await tentarEntrar()).toBe("/ouvidoria");
  });

  it("devolve à fila quem não tem perfil nenhum na Ouvidoria", async () => {
    respondeMe({ perfil_ouvidoria: null });
    expect(await tentarEntrar()).toBe("/ouvidoria");

    respondeMe({});
    expect(await tentarEntrar()).toBe("/ouvidoria");
  });

  it("não abre a porta quando o perfil não pôde ser lido", async () => {
    // Falha de leitura não é permissão: sem saber quem é, a resposta é a fila
    // da Ouvidoria, que é onde a pessoa já estava.
    respondeMe({ perfil_ouvidoria: "ouvidor" }, false);

    expect(await tentarEntrar()).toBe("/ouvidoria");
  });

  it("manda para o login quem não tem sessão", async () => {
    respondeMe({ perfil_ouvidoria: "ouvidor" });

    usuario = null;
    expect(await tentarEntrar()).toBe("/login");

    usuario = { id: "u1" };
    token = null;
    expect(await tentarEntrar()).toBe("/login");
  });
});
