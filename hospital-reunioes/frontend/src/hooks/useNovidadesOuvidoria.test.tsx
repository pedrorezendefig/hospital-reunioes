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

import { render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import type { ContagemDeNovidades } from "@/lib/ouvidoria/novidades";
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

/**
 * Os valores que o hook devolveu em cada render, na ordem. O `result.current`
 * do testing-library só mostra o último, e o vazamento desta rodada acontecia
 * no PRIMEIRO: o `useState` semeia antes de qualquer efeito rodar, e o efeito é
 * quem carrega a guarda de perfil.
 */
function renderizarObservandoOsQuadros(): ContagemDeNovidades[] {
  const quadros: ContagemDeNovidades[] = [];
  function Espiao() {
    quadros.push(useNovidadesOuvidoria());
    return null;
  }
  render(<Espiao />);
  return quadros;
}

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

  it("um minuto e um segundo depois, a contagem é refeita", async () => {
    // O relógio anda por um LITERAL, e não pela própria constante: medir a
    // janela com `JANELA_DE_REUSO_MS` fazia o teste passar para qualquer valor
    // dela, inclusive um que congelaria o contador pela sessão inteira.
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 3, degradado: [] }));

    const { result, rerender } = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );

    vi.setSystemTime(Date.now() + 61_000);
    buscar.mockResolvedValue(resposta({ total: 9, degradado: [] }));
    rota.atual = "/pendencias";
    rerender();

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 9 })
    );
    expect(buscar).toHaveBeenCalledTimes(2);
  });

  it("cinquenta e nove segundos depois, ainda vale a contagem de antes", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 3, degradado: [] }));

    const { result, rerender } = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );

    vi.setSystemTime(Date.now() + 59_000);
    buscar.mockResolvedValue(resposta({ total: 9, degradado: [] }));
    rota.atual = "/pendencias";
    rerender();

    await waitFor(() =>
      expect(result.current).toEqual({ estado: "ok", total: 3 })
    );
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("a janela é de um minuto, e o número está escrito no teste", () => {
    // A constante em si, para o par 59s/61s acima continuar querendo dizer o
    // que diz se alguém mexer nela.
    expect(JANELA_DE_REUSO_MS).toBe(60_000);
  });

  it("sair do caso atravessando seção também reconta, mesmo com a casca remontada", async () => {
    // O caminho comum que a primeira versão da exceção não pegava: sair do
    // caso para uma seção com layout próprio remonta a casca, e o "de onde eu
    // vim" morria junto com ela, enquanto a contagem sobrevivia no módulo.
    sessao.participante = ouvidor();
    rota.atual = "/ouvidoria/m/2026-0007";
    buscar.mockResolvedValue(resposta({ total: 2, degradado: [] }));

    const primeira = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(primeira.result.current).toEqual({ estado: "ok", total: 2 })
    );
    primeira.unmount();

    buscar.mockResolvedValue(resposta({ total: 1, degradado: [] }));
    rota.atual = "/admin";
    const segunda = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() =>
      expect(segunda.result.current).toEqual({ estado: "ok", total: 1 })
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

  it("a contagem de quem saiu não pinta o primeiro quadro de quem entrou", async () => {
    // Sair da conta não recarrega a aba, então o módulo sobrevive à troca de
    // usuário. O quadro em que o `useState` semeia é ANTES da guarda de perfil,
    // que mora no efeito: sem chave de dono, o número da ouvidora aparecia
    // desenhado na tela da secretária até o primeiro efeito rodar.
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 7, degradado: [] }));
    const daOuvidoria = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(daOuvidoria.result.current).toEqual({ estado: "ok", total: 7 })
    );
    daOuvidoria.unmount();

    // A secretária entra na mesma aba, com o módulo ainda quente.
    sessao.participante = { ...ouvidor(), id: "p9", perfil_ouvidoria: null };
    const quadros = renderizarObservandoOsQuadros();

    await waitFor(() => expect(quadros.length).toBeGreaterThan(0));
    expect(quadros).not.toContainEqual({ estado: "ok", total: 7 });
    expect(quadros.every((q) => q.estado === "sem_contagem")).toBe(true);
  });

  it("a contagem da própria pessoa segue valendo já no primeiro quadro", async () => {
    // A contraprova do teste acima: se a chave de dono barrasse todo mundo, o
    // distintivo piscaria a cada troca de tela e o teste anterior passaria sem
    // provar nada.
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ total: 7, degradado: [] }));
    const primeira = renderHook(() => useNovidadesOuvidoria());
    await waitFor(() =>
      expect(primeira.result.current).toEqual({ estado: "ok", total: 7 })
    );
    primeira.unmount();

    const quadros = renderizarObservandoOsQuadros();

    expect(quadros[0]).toEqual({ estado: "ok", total: 7 });
  });

  it("perfil revogado no meio da sessão apaga o número, e não acusa falha", async () => {
    sessao.participante = ouvidor();
    buscar.mockResolvedValue(resposta({ detail: "Acesso restrito" }, 403));

    const { result } = renderHook(() => useNovidadesOuvidoria());

    await waitFor(() => expect(result.current.estado).toBe("sem_contagem"));
  });
});
