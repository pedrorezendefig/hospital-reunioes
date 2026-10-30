/**
 * @vitest-environment jsdom
 */

/**
 * A tela de Habilitação de Contas médicas (issue #1139, PRD #1129).
 *
 * A diretoria vê a matriz com os perfis nas linhas e as permissões nas
 * colunas, liga e desliga cada célula, busca uma pessoa pelo nome e dá, troca
 * ou tira o perfil dela. O backend é um dublê que responde por rota; quem
 * decide é ele (o guard, o registro). O que se confere aqui é a fiação: o que
 * a tela mostra do que veio e o que ela manda quando a pessoa clica.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HabilitacaoPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const PERFIS = [
  "faturista",
  "coordenadora",
  "gestao_contas_medicas",
  "diretoria_medica",
  "diretoria_executiva",
  "credenciamento",
  "apoio_faturamento",
];
const PERMISSOES = [
  "enviar_contas",
  "enviar_corrigir_contas",
  "decidir_validacao",
  "incluir_regra_operacional",
  "regra_contratual_tabelas",
  "contratos_avisos",
  "painel_completo",
  "habilitar_pessoas",
  "conferencia_coordenacao",
];

type Pessoa = { id: string; nome_completo: string; cargo: string | null; setor: string | null; perfil: string | null };

let matriz: Record<string, Record<string, boolean>>;
let statusDaMatriz: number;
let habilitadas: Pessoa[];
let encontradas: Pessoa[];
let chamadas: { url: string; metodo: string; corpo: unknown }[];

function resposta(status: number, corpo: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
}

function backend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      chamadas.push({ url, metodo, corpo });
      if (url === "/api/contas-medicas/habilitacao") {
        if (statusDaMatriz !== 200) return resposta(statusDaMatriz, { detail: "Sem permissão" });
        return resposta(200, { perfis: PERFIS, permissoes: PERMISSOES, matriz });
      }
      if (url === "/api/contas-medicas/habilitacao/matriz" && metodo === "PUT") {
        const { perfil, permissao, ligada } = corpo as { perfil: string; permissao: string; ligada: boolean };
        matriz[perfil][permissao] = ligada;
        return resposta(200, { perfil, permissao, ligada });
      }
      if (url === "/api/contas-medicas/habilitacao/pessoas") return resposta(200, { pessoas: habilitadas });
      if (url.startsWith("/api/contas-medicas/habilitacao/pessoas?busca=")) {
        return resposta(200, { pessoas: encontradas });
      }
      const pessoa = url.match(/^\/api\/contas-medicas\/habilitacao\/pessoas\/(\w+)$/);
      if (pessoa && metodo === "PUT") {
        const alvo = [...habilitadas, ...encontradas].find((p) => p.id === pessoa[1]);
        return resposta(200, { ...alvo, perfil: (corpo as { perfil: string | null }).perfil });
      }
      return resposta(404, { detail: "rota desconhecida no dublê" });
    }),
  );
}

function matrizDaCarga(): Record<string, Record<string, boolean>> {
  const linhas = Object.fromEntries(PERFIS.map((p) => [p, Object.fromEntries(PERMISSOES.map((k) => [k, false]))]));
  linhas.faturista.enviar_contas = true;
  linhas.faturista.enviar_corrigir_contas = true;
  linhas.apoio_faturamento.enviar_contas = true;
  linhas.coordenadora.enviar_corrigir_contas = true;
  linhas.coordenadora.painel_completo = true;
  linhas.diretoria_executiva.habilitar_pessoas = true;
  return linhas;
}

beforeEach(() => {
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao
  // abrir a lista de opções.
  Element.prototype.scrollIntoView = vi.fn();
  matriz = matrizDaCarga();
  statusDaMatriz = 200;
  habilitadas = [{ id: "C1", nome_completo: "Carla Coordenadora", cargo: "Coordenadora", setor: null, perfil: "coordenadora" }];
  encontradas = [{ id: "F9", nome_completo: "Fernanda Faturista", cargo: null, setor: "Faturamento", perfil: null }];
  chamadas = [];
  backend();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a matriz perfil x permissão", () => {
  it("mostra os perfis nas linhas e as permissões nas colunas, cada célula como veio", async () => {
    render(<HabilitacaoPage />);

    const tabela = await screen.findByRole("table", { name: "Perfis e permissões" });
    const cabecalho = within(tabela).getAllByRole("columnheader").map((th) => th.textContent);
    expect(cabecalho).toEqual([
      "Perfil",
      "Enviar contas",
      "Analisar contas",
      "Decidir na validação",
      "Incluir regra operacional",
      "Regra contratual e tabelas",
      "Contratos e avisos",
      "Painel completo",
      "Habilitar pessoas",
      "Conferência da coordenação",
    ]);
    const perfis = within(tabela).getAllByRole("rowheader").map((th) => th.textContent);
    expect(perfis).toEqual([
      "Faturista",
      "Coordenadora de faturamento",
      "Gestão de contas médicas",
      "Diretoria médica",
      "Diretoria executiva",
      "Credenciamento",
      "Apoio ao faturamento",
    ]);
    const painel = within(tabela).getByRole("checkbox", { name: "Painel completo: Coordenadora de faturamento" });
    expect((painel as HTMLInputElement).checked).toBe(true);
    const regra = within(tabela).getByRole("checkbox", { name: "Incluir regra operacional: Coordenadora de faturamento" });
    expect((regra as HTMLInputElement).checked).toBe(false);
  });

  it("desligar uma célula manda a mudança e a célula fica como o servidor respondeu", async () => {
    render(<HabilitacaoPage />);

    const painel = await screen.findByRole("checkbox", { name: "Painel completo: Coordenadora de faturamento" });
    fireEvent.click(painel);

    await waitFor(() => expect((painel as HTMLInputElement).checked).toBe(false));
    expect(chamadas.filter((c) => c.metodo === "PUT")).toEqual([
      {
        url: "/api/contas-medicas/habilitacao/matriz",
        metodo: "PUT",
        corpo: { perfil: "coordenadora", permissao: "painel_completo", ligada: false },
      },
    ]);
  });

  it("sem a permissão de habilitar pessoas, diz isso e não mostra a matriz", async () => {
    statusDaMatriz = 403;

    render(<HabilitacaoPage />);

    expect(await screen.findByText(/não tem a permissão de habilitar pessoas/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("as pessoas", () => {
  it("abre com quem já tem perfil no módulo", async () => {
    render(<HabilitacaoPage />);

    const lista = await screen.findByRole("region", { name: "Pessoas" });
    const carla = await within(lista).findByRole("listitem", { name: "Carla Coordenadora" });
    expect(within(carla).getByRole("combobox", { name: "Perfil" }).textContent).toContain("Coordenadora de faturamento");
  });

  it("busca pelo nome e dá o perfil à pessoa encontrada", async () => {
    render(<HabilitacaoPage />);

    const lista = await screen.findByRole("region", { name: "Pessoas" });
    fireEvent.change(within(lista).getByRole("searchbox", { name: "Buscar pessoa pelo nome" }), {
      target: { value: "Fernanda" },
    });
    fireEvent.click(within(lista).getByRole("button", { name: "Buscar" }));

    const fernanda = await within(lista).findByRole("listitem", { name: "Fernanda Faturista" });
    fireEvent.click(within(fernanda).getByRole("combobox", { name: "Perfil" }));
    fireEvent.click(within(fernanda).getByRole("option", { name: "Faturista" }));

    await waitFor(() =>
      expect(chamadas.filter((c) => c.metodo === "PUT")).toEqual([
        { url: "/api/contas-medicas/habilitacao/pessoas/F9", metodo: "PUT", corpo: { perfil: "faturista" } },
      ]),
    );
    expect(chamadas.some((c) => c.url === "/api/contas-medicas/habilitacao/pessoas?busca=Fernanda")).toBe(true);
    await waitFor(() =>
      expect(within(fernanda).getByRole("combobox", { name: "Perfil" }).textContent).toContain("Faturista"),
    );
  });

  it("tirar do módulo manda o perfil vazio", async () => {
    render(<HabilitacaoPage />);

    const carla = await screen.findByRole("listitem", { name: "Carla Coordenadora" });
    fireEvent.click(within(carla).getByRole("combobox", { name: "Perfil" }));
    fireEvent.click(within(carla).getByRole("option", { name: "Sem perfil no módulo" }));

    await waitFor(() =>
      expect(chamadas.filter((c) => c.metodo === "PUT")).toEqual([
        { url: "/api/contas-medicas/habilitacao/pessoas/C1", metodo: "PUT", corpo: { perfil: null } },
      ]),
    );
  });
});
