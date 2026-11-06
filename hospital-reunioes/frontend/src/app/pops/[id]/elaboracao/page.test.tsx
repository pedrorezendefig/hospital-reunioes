/**
 * @vitest-environment jsdom
 */

/**
 * A Elaboração de POP no celular (issue #1458, conferência da caixa alta do
 * PRD #1428).
 *
 * A passada de prints a 390px achou a tela com 417px de largura. Abaixo de
 * `lg`, a grade do POP vivo com o chat não tinha coluna declarada: a coluna
 * implícita é `auto` e cresce até a largura mínima do conteúdo do chat (391px
 * no Chrome), empurrando tudo para fora do celular. Com `grid-cols-1`
 * (`minmax(0, 1fr)`), a coluna fica na largura da tela: no Chrome a 390px a
 * página passou de 417px para 390px. O jsdom não mede layout; o que dá para
 * provar aqui é a coluna declarada na grade que a tela monta.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import ElaboracaoPopPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "pop-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const ELABORACAO = {
  pop: {
    id: "pop-1",
    codigo: "HSM_CTI-002",
    nome: "POP Aspiração de Vias Aéreas",
    setor_nome: "Centro de Terapia Intensiva",
    setor_sigla: "CTI",
    criticidade: "ALTA",
    base_normativa: null,
    periodicidade_revisao: "1_ano",
    prazo_elaboracao_dias: 5,
    prazo_revisao_dias: 5,
    elaborador_id: "P1",
    revisor_id: "P2",
    validador_id: "P3",
    elaborador_nome: "Rafael Pimenta",
    revisor_nome: "Marina Alves",
    validador_nome: "Helena Duarte",
  },
  versao: { id: "v-1", numero_versao: "1.0", estado: "EM_ELABORACAO" },
  rascunho: { secoes: [] },
  periodicidade_sugerida: null,
  devolucoes: [],
  materiais: [],
};

beforeEach(() => {
  // O jsdom não rola; o chat rola até a última mensagem ao montar.
  Element.prototype.scrollTo = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(ELABORACAO), { status: 200 })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Elaboração de POP no celular", () => {
  it("a grade do POP vivo com o chat tem uma coluna na largura da tela abaixo de lg", async () => {
    render(
      <ToastProvider>
        <ElaboracaoPopPage />
      </ToastProvider>,
    );

    const grade = (await screen.findByRole("main")) as HTMLElement;
    expect(grade.classList.contains("grid")).toBe(true);
    expect(grade.classList.contains("grid-cols-1")).toBe(true);
  });
});
