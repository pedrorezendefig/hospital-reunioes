/**
 * @vitest-environment jsdom
 */

/**
 * Os próprios números de 90 dias e o que foi entregue (issue #1946, PRD #1932,
 * ADR 0104 decisões 7 e 9).
 *
 * A conta (no prazo, fora, a Repactuação vencida, a janela) vem pronta do
 * servidor e tem os testes da régua em `backend/tests/test_inicio_entregas.py`.
 * Aqui se trava o que a pessoa vê: os dois números, a lista dos últimos 7
 * dias só para quem está em dia, o bloco que some para quem não tem número e
 * a falha que fica no bloco.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InicioPage from "@/app/inicio/page";

import type { InicioDaPessoa } from "./MinhaFila";
import type { MeusNumerosDaPessoa } from "./MeusNumeros";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const EM_DIA: InicioDaPessoa = {
  hoje: "2026-11-18",
  frase: { titulo: "Ana, você está em dia.", apoio: "O próximo prazo é 30/11." },
  em_dia: true,
  contadores: { passou_do_prazo: 0, ate_48_horas: 0, proximos_7_dias: 0 },
  itens: [],
  avisos: [],
  trilho: [],
  filas_do_papel: [],
};

const COM_VENCIDO: InicioDaPessoa = {
  ...EM_DIA,
  frase: { titulo: "Ana, um prazo seu venceu.", apoio: "Ele espera há 2 dias." },
  em_dia: false,
  contadores: { passou_do_prazo: 1, ate_48_horas: 0, proximos_7_dias: 0 },
};

const NUMEROS: MeusNumerosDaPessoa = {
  numeros_90_dias: { no_prazo: 7, fora_do_prazo: 2 },
  entregues_7_dias: [
    { id: "A2", titulo: "Revisar o estoque", concluida_em: "2026-11-17", no_prazo: false },
    { id: "A1", titulo: "Trocar o filtro", concluida_em: "2026-11-12", no_prazo: true },
  ],
};

type Resposta = { status: number; corpo: unknown };

function servidor(rotas: Record<string, Resposta>) {
  const chamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      chamadas.push(url);
      const { status, corpo } = rotas[url] ?? { status: 404, corpo: null };
      return { ok: status < 300, status, json: async () => corpo } as Response;
    })
  );
  return chamadas;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrir(inicio: InicioDaPessoa, numeros: Resposta = { status: 200, corpo: NUMEROS }) {
  const chamadas = servidor({
    "/api/inicio": { status: 200, corpo: inicio },
    "/api/inicio/meus-numeros": numeros,
    "/api/inicio/quem-responde": { status: 200, corpo: null },
  });
  render(<InicioPage />);
  await screen.findByText(inicio.frase.titulo);
  return chamadas;
}

describe("os próprios números de 90 dias", () => {
  it("mostram as entregas no prazo e fora, pedidas só para quem está olhando", async () => {
    const chamadas = await abrir(COM_VENCIDO);

    const bloco = await screen.findByRole("region", { name: "Seus últimos 90 dias" });
    expect(within(bloco).getByTestId("no-prazo").textContent).toBe("7entregas no prazo");
    expect(within(bloco).getByTestId("fora-do-prazo").textContent).toBe("2entregas fora do prazo");
    // A rota não leva identificação de pessoa: o servidor responde por quem pede.
    expect(chamadas).toContain("/api/inicio/meus-numeros");
    expect(chamadas.filter((url) => url.includes("meus-numeros"))).toEqual(["/api/inicio/meus-numeros"]);
  });

  it("quem tem prazo vencido não vê a lista do que entregou", async () => {
    await abrir(COM_VENCIDO);

    await screen.findByRole("region", { name: "Seus últimos 90 dias" });
    expect(screen.queryByRole("list", { name: "Entregue nos últimos 7 dias" })).toBeNull();
    expect(screen.queryByText("Trocar o filtro")).toBeNull();
  });

  it("não aparecem para quem não tem número", async () => {
    await abrir(COM_VENCIDO, { status: 200, corpo: null });

    await vi.waitFor(() => expect(screen.queryByText("Carregando os seus números")).toBeNull());
    expect(screen.queryByRole("region", { name: "Seus últimos 90 dias" })).toBeNull();
  });

  it("a falha fica no bloco e o resto do Início continua", async () => {
    await abrir(COM_VENCIDO, { status: 500, corpo: null });

    const bloco = await screen.findByRole("region", { name: "Seus últimos 90 dias" });
    expect(within(bloco).getByRole("status").textContent).toBe(
      "Não foi possível carregar os seus números agora. Tente de novo em instantes."
    );
    expect(screen.getByText("Ana, um prazo seu venceu.")).toBeTruthy();
  });
});

describe("o que foi entregue nos últimos 7 dias", () => {
  it("quem está em dia vê a lista, da mais recente para a mais antiga, com a data e se foi no prazo", async () => {
    await abrir(EM_DIA);

    const lista = await screen.findByRole("list", { name: "Entregue nos últimos 7 dias" });
    expect(within(lista).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Revisar o estoqueEntregue em 17/11, fora do prazo",
      "Trocar o filtroEntregue em 12/11, no prazo",
    ]);
  });

  it("quem está em dia e não entregou nada nos 7 dias lê isso", async () => {
    await abrir(EM_DIA, { status: 200, corpo: { ...NUMEROS, entregues_7_dias: [] } });

    expect(await screen.findByText("Nada entregue nos últimos 7 dias.")).toBeTruthy();
  });
});
