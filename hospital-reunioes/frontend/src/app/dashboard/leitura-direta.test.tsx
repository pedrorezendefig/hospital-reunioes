/**
 * @vitest-environment jsdom
 */

/**
 * O 406 que sujava o console (issue #492, PRD #471).
 *
 * A tela inicial lia a tabela `participantes` direto no PostgREST, do
 * navegador, com a chave anônima. Só que a `participantes` tem RLS
 * default-deny desde a migration 009 e nunca ganhou policy de SELECT: a
 * leitura do navegador volta SEMPRE com zero linha. Com `.single()`, o
 * postgrest-js manda `Accept: application/vnd.pgrst.object+json` e zero linha
 * vira `406 Not Acceptable` (PGRST116) gritando no console de toda sessão,
 * inclusive enquanto se navega pela Ouvidoria, que entra por aqui.
 *
 * O papel do usuário vem do backend (`GET /api/participantes/me`, o
 * `useCurrentParticipante`), que lê com service_role. Esta suíte trava a
 * invariante: a tela inicial não fala com o PostgREST. Sem ela, alguém
 * reintroduz a leitura direta e o 406 volta calado.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./page";

// Toda tabela que a tela pedir ao PostgREST fica registrada aqui.
const postgrest = vi.hoisted(() => ({ tabelasLidas: [] as string[] }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/participantes", () => ({
  fetchParticipantesAtivos: async () => [],
}));

// Os gráficos não são o assunto desta suíte, e o recharts não roda em jsdom.
vi.mock("@/components/dashboard/KpiCards", () => ({ default: () => null }));
vi.mock("@/components/dashboard/DashboardFilters", () => ({ default: () => null }));
vi.mock("@/components/dashboard/StatusPieChart", () => ({ default: () => null }));
vi.mock("@/components/dashboard/SetorBarChart", () => ({ default: () => null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: {
          session: {
            access_token: "token-de-teste",
            user: { id: "auth-user-1", email: "marta@hsm", user_metadata: {} },
          },
        },
      }),
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe: () => {} } },
      }),
    },
    // Réplica do PostgREST com a tabela em default-deny: zero linha, e o
    // `.single()` devolvendo o 406 que aparecia no console.
    from: (tabela: string) => {
      postgrest.tabelasLidas.push(tabela);
      const resposta = {
        data: null,
        error: {
          code: "PGRST116",
          details: "The result contains 0 rows",
          hint: null,
          message: "JSON object requested, multiple (or no) rows returned",
        },
        status: 406,
        statusText: "Not Acceptable",
      };
      const cadeia = {
        select: () => cadeia,
        eq: () => cadeia,
        single: () => cadeia,
        maybeSingle: () => cadeia,
        then: (cb: (r: typeof resposta) => unknown) => Promise.resolve(cb(resposta)),
      };
      return cadeia;
    },
  }),
}));

beforeEach(() => {
  postgrest.tabelasLidas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response)
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("tela inicial e o PostgREST", () => {
  it("não lê tabela nenhuma direto do navegador (o 406 da issue #492)", async () => {
    render(<DashboardPage />);

    // Espera a inicialização terminar: sem isto, a asserção passaria só por
    // chegar antes da consulta.
    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled();
    });

    expect(postgrest.tabelasLidas).toEqual([]);
  });

  it("monta a tela inteira sem depender de consulta ao PostgREST", async () => {
    render(<DashboardPage />);

    // A tela chega ao fim da inicialização e desenha o cabeçalho sem nunca
    // acionar o `from`: o papel do usuário não é mais pré-requisito de nada
    // aqui. Antes do fix, o mesmo caminho passava pela consulta que voltava
    // vazia e virava 406.
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Olá, marta" })).toBeTruthy();
    });
    expect(postgrest.tabelasLidas).toEqual([]);
  });
});

/**
 * A tela inicial é onde o 406 morava, mas a armadilha é do frontend inteiro.
 * A `participantes` está em default-deny desde a migration 009, sem policy de
 * SELECT. As poucas tabelas que têm policy (`user_preferences` na 012,
 * `audit_log` e `bulk_jobs` na 023) resolvem o dono por subquery justamente na
 * `participantes`, que o navegador também não enxerga: na prática, leitura
 * direta do navegador volta vazia em toda tabela que o app usa hoje.
 *
 * Com `.single()` isso vira 406 no console. SEM ele é pior: volta 200 com
 * array vazio, e uma tela que mostra "nenhum resultado" quando deveria mostrar
 * dados não acusa nada a ninguém. Por isso o guard pega os dois: o `.single()`
 * e a leitura direta que nem chega a pedir uma linha só.
 *
 * Precisa mesmo de uma leitura direta? Fora do navegador (rota de servidor com
 * service_role) a regra não vale, mas o guard não distingue quem chama. Então
 * a saída é explícita: some o caminho a `EXCECOES` abaixo, com o motivo por
 * escrito, para a próxima pessoa saber por que aquele arquivo pode.
 */
// O vitest roda com a raiz do frontend como cwd (é onde está o vitest.config).
const RAIZ_SRC = join(process.cwd(), "src");

// Ancorado no caminho, não no basename: um `leitura-direta.test.tsx` em outra
// pasta não escapa da varredura por homonímia.
const EXCECOES = [join("app", "dashboard", "leitura-direta.test.tsx")];

// `.single()` manda Accept: application/vnd.pgrst.object+json e vira 406 com
// zero linha; `.from("tabela")` é a leitura direta em si, que volta vazia em
// silêncio. A aspa exigida depois do parêntese é o que separa a chamada do
// PostgREST de todo `Array.from(...)` do repo.
const LEITURA_DIRETA = [/\.single\s*\(/, /\.from\s*\(\s*["'`]/];

function arquivosDeCodigo(diretorio: string): string[] {
  return readdirSync(diretorio, { withFileTypes: true }).flatMap((entrada) => {
    const caminho = join(diretorio, entrada.name);
    if (entrada.isDirectory()) return arquivosDeCodigo(caminho);
    if (!/\.tsx?$/.test(entrada.name)) return [];
    if (EXCECOES.includes(caminho.slice(RAIZ_SRC.length + 1))) return [];
    return [caminho];
  });
}

describe("o frontend e o PostgREST", () => {
  it("não fala com o PostgREST de lugar nenhum", () => {
    const culpados = arquivosDeCodigo(RAIZ_SRC).filter((caminho) => {
      const codigo = readFileSync(caminho, "utf8");
      return LEITURA_DIRETA.some((padrao) => padrao.test(codigo));
    });

    expect(
      culpados.map((c) => c.slice(RAIZ_SRC.length)),
      "Leitura direta do navegador volta vazia em toda tabela que o app usa " +
        "hoje: com `.single()` isso é o 406 da issue #492, sem ele é um array " +
        "vazio silencioso. Leia pelo backend, que usa service_role."
    ).toEqual([]);
  });
});
