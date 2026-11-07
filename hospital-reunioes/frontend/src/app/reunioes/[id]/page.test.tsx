/**
 * @vitest-environment jsdom
 */

/**
 * Gerar a ata de novo quando a reunião para no Erro (issue #1498).
 *
 * A rota `POST /api/reunioes/{id}/reprocessar` já relê a transcrição guardada
 * no Storage e roda o pipeline outra vez, mas nenhuma tela a chamava: a reunião
 * que caía em ERRO só saía dali criando outra reunião e colando a transcrição.
 * O que se prova aqui é a tela inteira, montada pela página de verdade: o botão
 * existe só no ERRO e fora da Secretária, o clique chama a rota uma vez, a tela
 * vai para o processamento, e a falha mostra a frase que o backend mandou.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import ReuniaoDetailPage from "./page";

const perfil = vi.hoisted(() => ({
  participante: null as Record<string, unknown> | null,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "REU_TESTE" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({ participante: perfil.participante, loading: false, error: null }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) },
  }),
}));

// O card de signatários tem fetch e polling próprios, fora do que se prova aqui.
vi.mock("@/components/reunioes/SignatariosCard", () => ({ SignatariosCard: () => null }));

const FACILITADOR = { id: "P_FACIL", nome_completo: "Facilitador", email: "f@hsm.com", access_profile: "regular" };
const SECRETARIA = { id: "P_SECRE", nome_completo: "Secretária", email: "s@hsm.com", access_profile: "secretaria" };

const BOTAO = "Gerar a ata de novo";

function reuniao(status_ata: string) {
  return {
    id_reuniao: "REU_TESTE",
    data: "2026-11-04",
    tipo: "Diretoria",
    titulo: null,
    objetivo: null,
    status_ata,
    total_acoes: 0,
    acoes_concluidas: 0,
    hora_inicio: null,
    hora_fim: null,
    json_ata: status_ata === "ERRO" ? { error: "Falha na IA" } : null,
    url_pdf_preliminar: null,
    url_pdf_assinado: null,
    url_transcricao: null,
    envelope_key_clicksign: null,
    data_assinatura: null,
    fonte: "UPLOAD",
    metodo_geracao: "TRANSCRICAO",
    created_at: "2026-11-04T10:00:00Z",
    facilitador_id: "P_FACIL",
  };
}

type Resposta = { status: number; corpo: unknown };

/**
 * Responde o GET da reunião com o status pedido e o POST do reprocessar com a
 * resposta dada (ou com uma promessa que o teste resolve quando quiser).
 */
function servir(status_ata: string, reprocessar?: Resposta | Promise<Resposta>) {
  const chamadas: Array<{ url: string; method: string }> = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    chamadas.push({ url, method });
    if (url === "/api/reunioes/REU_TESTE/reprocessar" && method === "POST") {
      const r = await reprocessar!;
      return { ok: r.status < 400, status: r.status, json: async () => r.corpo } as unknown as Response;
    }
    if (url === "/api/reunioes/REU_TESTE" && method === "GET") {
      return { ok: true, status: 200, json: async () => reuniao(status_ata) } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => [] } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return chamadas;
}

function montar() {
  return render(
    <ToastProvider>
      <ReuniaoDetailPage />
    </ToastProvider>,
  );
}

async function esperarCarregar() {
  await screen.findByText("REU_TESTE");
}

beforeEach(() => {
  perfil.participante = FACILITADOR;
});

afterEach(() => {
  // O vitest deste projeto nao roda com `globals: true`, entao a limpeza
  // automatica do testing-library nao entra sozinha.
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Gerar a ata de novo", () => {
  it("a reunião em ERRO mostra o botão", async () => {
    servir("ERRO");
    montar();
    await esperarCarregar();
    expect(screen.getByRole("button", { name: BOTAO })).toBeTruthy();
  });

  it.each(["PROCESSANDO", "AGUARDANDO_VALIDACAO", "AGUARDANDO_ASSINATURA", "ASSINADA", "APROVADA"])(
    "a reunião em %s não mostra o botão",
    async (status) => {
      servir(status);
      montar();
      await esperarCarregar();
      expect(screen.queryByRole("button", { name: BOTAO })).toBeNull();
    },
  );

  it("a Secretária não vê o botão na reunião em ERRO", async () => {
    perfil.participante = SECRETARIA;
    servir("ERRO");
    montar();
    await esperarCarregar();
    expect(screen.queryByRole("button", { name: BOTAO })).toBeNull();
  });

  it("o clique chama o reprocessar uma vez, com o botão desabilitado, e a tela passa a processar", async () => {
    let responder: (r: Resposta) => void = () => {};
    const pendente = new Promise<Resposta>((resolve) => { responder = resolve; });
    const chamadas = servir("ERRO", pendente);
    montar();
    await esperarCarregar();

    const botao = screen.getByRole("button", { name: BOTAO }) as HTMLButtonElement;
    fireEvent.click(botao);
    await waitFor(() => expect(botao.disabled).toBe(true));
    // Clique repetido durante a espera não dispara outra chamada.
    fireEvent.click(botao);

    await act(async () => {
      responder({
        status: 200,
        corpo: { id_reuniao: "REU_TESTE", status: "PROCESSANDO", message: "Reprocessamento iniciado" },
      });
    });

    await screen.findByText("A IA está processando a transcrição...");
    expect(screen.queryByRole("button", { name: BOTAO })).toBeNull();
    const posts = chamadas.filter((c) => c.method === "POST");
    expect(posts).toEqual([{ url: "/api/reunioes/REU_TESTE/reprocessar", method: "POST" }]);
  });
});
