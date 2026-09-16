/**
 * @vitest-environment jsdom
 */

/**
 * A página de Nova Demanda (issue #727, PRD #726, ADR 0056).
 *
 * O que é dela, e não dos dois componentes que ela hospeda: o gate de Super
 * admin, a alternância para o formulário de sempre, e para onde se vai depois
 * que a Demanda nasce.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NovaDemandaPage from "./page";

const sessao = vi.hoisted(() => ({ token: "tok" as string | null, loading: false }));
const perfil = vi.hoisted(() => ({
  participante: { id: "p1", nome_completo: "Pedro", email: "p@hsm.com", access_profile: "super_admin" } as Record<
    string,
    unknown
  > | null,
  loading: false,
}));
const navegacao = vi.hoisted(() => ({ empurrou: [] as string[] }));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: sessao.token, userId: "u1", userEmail: "p@hsm.com", loading: sessao.loading }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({ participante: perfil.participante, loading: perfil.loading, error: null }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: (url: string) => navegacao.empurrou.push(url) }),
}));

const PRODUTOS = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "Site antigo", ativo: false },
];

let criadaComAviso: string | null = null;

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/produtos")) {
        return { ok: true, status: 200, json: async () => PRODUTOS } as unknown as Response;
      }
      if (url.endsWith("/demandas") && init?.method === "POST") {
        return {
          ok: true,
          status: 201,
          json: async () => ({ id: "d-nova", aviso_por_email: criadaComAviso }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ reply: "ok", rascunho: {}, demanda_parecida: null }),
      } as unknown as Response;
    }),
  );
  return render(<NovaDemandaPage />);
}

beforeEach(() => {
  sessao.token = "tok";
  sessao.loading = false;
  perfil.participante = { id: "p1", nome_completo: "Pedro", email: "p@hsm.com", access_profile: "super_admin" };
  perfil.loading = false;
  navegacao.empurrou = [];
  criadaComAviso = null;
  Element.prototype.scrollIntoView = vi.fn();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("O gate da página", () => {
  it("quem não é Super admin não alcança a tela", () => {
    perfil.participante = { id: "p2", nome_completo: "Outra", email: "o@hsm.com", access_profile: "regular" };
    montar();

    expect(screen.getByText(/Sem acesso à aba Tecnologia/)).toBeTruthy();
    expect(screen.queryByLabelText("Mensagem")).toBeNull();
  });

  it("o Super admin alcança", () => {
    // O par de presença: uma página que recusasse todo mundo passaria no teste
    // acima sozinha.
    montar();

    expect(screen.queryByText(/Sem acesso à aba Tecnologia/)).toBeNull();
    expect(screen.getByLabelText("Mensagem")).toBeTruthy();
  });
});

describe("Prefiro preencher à mão", () => {
  it("troca o assistente pelo formulário de sempre, na mesma página", async () => {
    montar();
    expect(screen.getByLabelText("Mensagem")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /prefiro preencher à mão/ }));

    // O formulário entrou e o chat saiu: é uma tela, não duas.
    expect(await screen.findByRole("button", { name: "Abrir Demanda" })).toBeTruthy();
    expect(screen.queryByLabelText("Mensagem")).toBeNull();
  });

  it("dá para voltar ao assistente", () => {
    montar();
    fireEvent.click(screen.getByRole("button", { name: /prefiro preencher à mão/ }));

    fireEvent.click(screen.getByRole("button", { name: /voltar ao assistente/ }));

    expect(screen.getByLabelText("Mensagem")).toBeTruthy();
  });
});

describe("Depois que a Demanda nasce", () => {
  async function criarPeloFormulario() {
    fireEvent.click(screen.getByRole("button", { name: /prefiro preencher à mão/ }));
    await screen.findByRole("button", { name: "Abrir Demanda" });
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Encerrar conversas" } });
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
    fireEvent.click(screen.getByRole("button", { name: "Abrir Demanda" }));
  }

  it("a tela vai ao Quadro com a Demanda aberta pela URL", async () => {
    montar();
    await waitFor(() => expect(screen.getByRole("button", { name: /prefiro preencher à mão/ })).toBeTruthy());

    await criarPeloFormulario();

    await waitFor(() => expect(navegacao.empurrou).toEqual(["/admin/tecnologia?demanda=d-nova"]));
  });

  it("com aviso de e-mail, a tela NÃO navega sozinha: a frase se perderia", async () => {
    criadaComAviso = "A Demanda foi criada, mas o aviso por e-mail nao saiu.";
    montar();
    await waitFor(() => expect(screen.getByRole("button", { name: /prefiro preencher à mão/ })).toBeTruthy());

    await criarPeloFormulario();

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("nao saiu");
    expect(within(alerta).getByRole("link").getAttribute("href")).toBe("/admin/tecnologia?demanda=d-nova");
    expect(navegacao.empurrou).toEqual([]);
  });
});
