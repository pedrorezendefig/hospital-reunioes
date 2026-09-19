/**
 * @vitest-environment jsdom
 */

/**
 * A galeria dos Objetivos da Central de Comando (issue #820, ADR 0058).
 *
 * O servidor é falso e a conta fica com ele: a tela escreve o que o payload
 * trouxe. As asserções olham o que o Super admin lê para um dado payload e a
 * chamada que a tela faz (endereço e token).
 *
 * Porte de `objetivo-screen.test.ts`: a galeria lista os seis Objetivos, com o
 * número de hoje dos quatro navegáveis e os dois em construção sem número nem
 * destino. E o princípio da Central: sem credencial (503) ou com a fonte fora
 * (502), a tela diz o que houve e não mostra número.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type GaleriaPayload, Objetivos } from "./Objetivos";

const sessao = vi.hoisted(() => ({ token: "token-de-teste" as string | null, carregando: false }));

vi.mock("@/hooks/useAuth", () => ({
  getAuthToken: () =>
    sessao.carregando ? new Promise<string | undefined>(() => {}) : Promise.resolve(sessao.token ?? undefined),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function galeria(): GaleriaPayload {
  return {
    objetivos: [
      {
        id: "site-visitantes",
        nome: "Atrair mais visitantes pro site",
        descricao: "Mais gente conhecendo o hospital pelo site.",
        em_construcao: false,
        numero: { chave: "visitors", rotulo: "Visitantes", valor: 12345 },
      },
      {
        id: "instagram-seguidores",
        nome: "Crescer no Instagram",
        descricao: "Aumentar o número de seguidores da conta.",
        em_construcao: false,
        numero: { chave: "followers", rotulo: "Seguidores", valor: 18420 },
      },
      {
        id: "instagram-engajamento",
        nome: "Aumentar o engajamento no Instagram",
        descricao: "Mais gente curtindo, comentando e salvando.",
        em_construcao: false,
        numero: { chave: "interactions", rotulo: "Interações", valor: 7820 },
      },
      {
        id: "site-area",
        nome: "Levar mais gente para uma Área do site",
        descricao: "Aumentar as visitas de uma área específica do site.",
        em_construcao: true,
        numero: null,
      },
      {
        id: "contatos",
        nome: "Gerar mais contatos",
        descricao: "Mais pessoas agendando e entrando em contato.",
        em_construcao: false,
        numero: { chave: "contatos", rotulo: "Contatos medidos", valor: 6786 },
      },
      {
        id: "google-reputacao",
        nome: "Melhorar a nota no Google",
        descricao: "Melhorar a reputação e as avaliações no Google Meu Negócio.",
        em_construcao: true,
        numero: null,
      },
    ],
    frescor: { atualizado_em: "2026-09-18T13:45:00+00:00", atualizacao_falhou: false, motivo: null },
  };
}

type Chamada = { url: string; autorizacao: string | null };
let chamadas: Chamada[] = [];

function servidor(status: number, corpo: unknown) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      chamadas.push({ url, autorizacao: cabecalhos.get("Authorization") });
      return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
}

beforeEach(() => {
  sessao.token = "token-de-teste";
  sessao.carregando = false;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a galeria dos Objetivos", () => {
  it("lista os seis Objetivos com o número de hoje dos quatro navegáveis", async () => {
    servidor(200, galeria());

    render(<Objetivos />);

    expect(await screen.findByText("Crescer no Instagram")).toBeTruthy();
    expect(screen.getByText("12.345")).toBeTruthy();
    expect(screen.getByText("18.420")).toBeTruthy();
    expect(screen.getByText("7.820")).toBeTruthy();
    expect(screen.getByText("6.786")).toBeTruthy();
  });

  it("os quatro navegáveis levam à lente e os dois em construção não", async () => {
    servidor(200, galeria());

    render(<Objetivos />);
    await screen.findByText("Crescer no Instagram");

    const destinos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    for (const navegavel of ["site-visitantes", "instagram-seguidores", "instagram-engajamento", "contatos"]) {
      expect(destinos).toContain(`/admin/central-de-comando/objetivos/${navegavel}`);
    }
    for (const emConstrucao of ["site-area", "google-reputacao"]) {
      expect(destinos).not.toContain(`/admin/central-de-comando/objetivos/${emConstrucao}`);
    }
  });

  it("marca os dois Objetivos em construção", async () => {
    servidor(200, galeria());

    render(<Objetivos />);
    await screen.findByText("Crescer no Instagram");

    expect(screen.getAllByText("Em construção")).toHaveLength(2);
  });

  it("pede a galeria ao backend com o token da sessão", async () => {
    servidor(200, galeria());

    render(<Objetivos />);
    await screen.findByText("Crescer no Instagram");

    expect(chamadas).toEqual([
      { url: "/api/admin/central-de-comando/objetivos", autorizacao: "Bearer token-de-teste" },
    ]);
  });

  it("não chama nenhum Objetivo de meta", async () => {
    // O nome antigo da Área do site é varrido pelo `vocabulario-da-central`,
    // que lê o código da seção inteira; aqui basta guardar a palavra "meta".
    servidor(200, galeria());

    render(<Objetivos />);
    await screen.findByText("Crescer no Instagram");

    const texto = document.body.textContent ?? "";
    expect(/\bmeta\b/i.test(texto)).toBe(false);
  });

  it("sem credencial (503) diz o que falta e não mostra número", async () => {
    servidor(503, { detail: "A Central ainda não está ligada à fonte." });

    render(<Objetivos />);

    expect(await screen.findByText("A Central ainda não está ligada à fonte.")).toBeTruthy();
    expect(screen.getByText("Sem ligação com a fonte dos números")).toBeTruthy();
    expect(screen.queryByText("12.345")).toBeNull();
  });

  it("com a fonte fora (502) avisa e não mostra número", async () => {
    servidor(502, { detail: "A fonte não respondeu no tempo esperado." });

    render(<Objetivos />);

    expect(await screen.findByText("A fonte não respondeu no tempo esperado.")).toBeTruthy();
    expect(screen.getByText(/Não foi possível carregar os Objetivos/)).toBeTruthy();
  });

  it("sem sessão, não pede nada e diz por quê", async () => {
    servidor(200, galeria());
    sessao.token = null;

    render(<Objetivos />);

    expect(await screen.findByText(/sessão não está ativa/)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });
});
