/**
 * @vitest-environment jsdom
 */

/**
 * A busca do contador de novidades (issue #487, PRD #470, RN-69).
 *
 * Três coisas se provam aqui, e as três são de correção, não de tela:
 *
 * * quem não é da Ouvidoria não pergunta. O servidor recusa de qualquer jeito,
 *   mas uma tela que bate numa porta fechada a cada navegação enche o log de
 *   403 e o rate limiter de ruído;
 * * o número cai quando o caso é aberto, e isso só acontece porque a contagem
 *   é refeita a cada navegação: sem o refetch, o distintivo ficaria congelado
 *   no número da primeira carga;
 * * resposta que não deu para ler não vira zero, em nenhum dos caminhos de
 *   falha (rede, HTTP, ou o `total: null` do próprio servidor).
 */

import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  esquecerNovidades,
  JANELA_DE_REUSO_MS,
  useNovidadesOuvidoria,
} from "./useNovidadesOuvidoria";

const rota = vi.hoisted(() => ({ atual: "/dashboard" }));
const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
  token: "tok-123" as string | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => rota.atual,
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: sessao.participante,
    loading: false,
    error: null,
  }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: {
          session: sessao.token ? { access_token: sessao.token } : null,
        },
      }),
    },
  }),
}));

function ouvidor(): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Marta Ouvidora",
    email: "marta@hsm",
    access_profile: null,
    perfil_ouvidoria: "ouvidor",
  };
}

/** Uma resposta do servidor, do jeito que o `fetch` a entrega. */
function resposta(corpo: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => corpo,
  } as Response;
}

let buscar: ReturnType<typeof vi.fn>;

beforeEach(() => {
  buscar = vi.fn(async () => resposta({ total: 0, degradado: [] }));
  vi.stubGlobal("fetch", buscar);
  // Só o relógio é falso: `setTimeout` continua real, senão o `waitFor` do
  // testing-library nunca avança.
  vi.useFakeTimers({ toFake: ["Date"] });
  esquecerNovidades();
});

afterEach(() => {
  vi.useRealTimers();
  esquecerNovidades();
  vi.unstubAllGlobals();
  rota.atual = "/dashboard";
  sessao.participante = null;
  sessao.token = "tok-123";
});

describe("useNovidadesOuvidoria", () => {
  it("traz o total que o servidor contou", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 4, degradado: [] }));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 4 })
    );
  });

  it("quem não tem o Perfil da Ouvidoria não pergunta o número", async () => {
    sessao.participante = { ...ouvidor(), perfil_ouvidoria: null };

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() => expect(result.current.estado).toBe("sem_contagem"));
    expect(buscar).not.toHaveBeenCalled();
  });

  it("sair da tela do caso reconta na hora, que é o que faz o número cair", async () => {
    sessao.participante = ouvidor();
    rota.atual = "/ouvidoria/m/2026-0007";
    buscar.mockResolvedValue(resposta({ total: 2, degradado: [] }));

    const { result, rerender } = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 2 })
    );

    // Abrir o caso carimbou o visto no servidor. A janela de reuso ainda está
    // aberta, e mesmo assim a volta tem que recontar: senão o ouvidor fecha o
    // caso e continua vendo o número de antes.
    buscar.mockResolvedValue(resposta({ total: 1, degradado: [] }));
    rota.atual = "/ouvidoria";
    rerender();

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 1 })
    );
  });

  it("navegar entre telas comuns não repete a contagem dentro da janela", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 3, degradado: [] }));

    const { result, rerender } = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );

    rota.atual = "/pendencias";
    rerender();
    rota.atual = "/reunioes/calendario";
    rerender();

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("passada a janela, a contagem é refeita", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 3, degradado: [] }));

    const { result, rerender } = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );

    vi.setSystemTime(Date.now() + JANELA_DE_REUSO_MS + 1);
    buscar.mockResolvedValue(resposta({ total: 9, degradado: [] }));
    rota.atual = "/pendencias";
    rerender();

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 9 })
    );
    expect(buscar).toHaveBeenCalledTimes(2);
  });

  it("uma segunda tela reaproveita a contagem da primeira, sem ir ao servidor", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 5, degradado: [] }));

    const primeira = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(primeira.result.current).toEqual({ estado: "ok", total: 5 })
    );

    const segunda = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(segunda.result.current).toEqual({ estado: "ok", total: 5 })
    );
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("total nulo do servidor não vira zero", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: null, degradado: ["movimentos"] }));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "indisponivel" })
    );
  });

  it("erro de rede não vira zero", async () => {
    sessao.participante = ouvidor();
    buscar.mockRejectedValue(new Error("rede fora"));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "indisponivel" })
    );
  });

  it("erro do servidor não vira zero", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ detail: "erro" }, 500));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "indisponivel" })
    );
  });

  it("perfil revogado no meio da sessão apaga o número, e não acusa falha", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ detail: "Acesso restrito" }, 403));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() => expect(result.current.estado).toBe("sem_contagem"));
  });
});
