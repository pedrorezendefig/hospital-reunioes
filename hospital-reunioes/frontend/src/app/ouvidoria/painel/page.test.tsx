/**
 * @vitest-environment jsdom
 */

/**
 * O painel da Ouvidoria, na tela (issue #438, PRD #402).
 *
 * A régua de quem entra em cada bloco já tem teste próprio em
 * `lib/ouvidoria/painel.ts`. O que faltava esteira era justamente o que só
 * existe aqui dentro, e que hoje só um humano olhando a tela pegaria se
 * sumisse:
 *
 * * a marca de sigilo na linha do caso, que separa a denúncia protegida da
 *   reclamação comum numa tela feita para ficar aberta e ser projetada (RN-40);
 * * o contador de falhas seguidas, que espaça as tentativas e precisa VOLTAR ao
 *   intervalo normal na primeira resposta boa, senão o painel fica lento pelo
 *   resto da sessão por causa de um soluço de rede;
 * * a recarga imediata na volta da aba, sem a qual quem volta encara a foto
 *   antiga por um intervalo inteiro, que na sequência de falhas chega a dez
 *   minutos.
 *
 * O `usePolling` entra dublado de propósito: ele é um `setInterval`, e o que se
 * quer provar não é que o relógio anda, e sim COM QUE intervalo o painel pede
 * para ele andar. O dublê guarda o que o componente pediu a cada render.
 */

import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALO_BASE_MS } from "@/lib/ouvidoria/painel";
import PainelEmTempoRealPage from "./page";

const polling = vi.hoisted(() => ({
  intervalos: [] as number[],
  ativos: [] as boolean[],
  /** A própria função de carga do painel, para simular um tick sem esperar o relógio. */
  carga: null as null | (() => Promise<void> | void),
}));

vi.mock("@/hooks/usePolling", () => ({
  usePolling: (callback: () => Promise<void> | void, intervalMs: number, enabled: boolean) => {
    polling.carga = callback;
    polling.intervalos.push(intervalMs);
    polling.ativos.push(enabled);
  },
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "p1", nome_completo: "Ouvidora", email: "o@hsm", perfil_ouvidoria: "ouvidor" },
    loading: false,
  }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

// O `Link` do App Router pede o contexto do roteador, que não existe fora do
// Next. Aqui ele é só a âncora que a tela desenha.
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

/**
 * Um caso já vencido: `prazo_estourado` vem do motor do servidor, então a linha
 * cai no bloco "Já venceu" em qualquer dia em que a suíte rodar.
 */
function casoVencido(overrides: Record<string, unknown> = {}) {
  return {
    id: "id-1",
    protocolo: "OUV-2026-0001",
    status: "aguardando_area",
    setor: "enfermagem",
    resumo: "Resumo do caso.",
    gravidade: "medio",
    prazo_area_em: "2026-01-05T20:00:00+00:00",
    prazo_resposta: "2026-01-05",
    prazo_estourado: true,
    rotulo_prazo: "vencido ha 2 dias uteis",
    sigilo_reforcado: false,
    ...overrides,
  };
}

const METRICAS_VAZIAS = { degradado: [], pendencias_por_area: [] };

/** Uma resposta de fetch com corpo JSON, no mínimo que o componente lê. */
function resposta(corpo: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => corpo };
}

interface Roteiro {
  metricas: ReturnType<typeof resposta>;
  protocolos: ReturnType<typeof resposta>;
}

/** O que cada uma das duas portas responde. Trocável no meio do teste. */
let roteiro: Roteiro;

beforeEach(() => {
  polling.intervalos = [];
  polling.ativos = [];
  polling.carga = null;
  roteiro = {
    metricas: resposta(METRICAS_VAZIAS),
    protocolos: resposta({ protocolos: [] }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).includes("/metricas") ? roteiro.metricas : roteiro.protocolos
    )
  );
  visibilidade("visible");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** O jsdom não deixa escrever `visibilityState`, então ele é redefinido. */
function visibilidade(estado: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => estado,
  });
}

/** Monta o painel e espera a primeira carga terminar. */
async function abrirOPainel() {
  render(<PainelEmTempoRealPage />);
  await screen.findByText("Painel em tempo real");
}

describe("a marca de sigilo na linha do painel", () => {
  it("marca a linha do caso sigiloso, e só ela", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({ id: "id-1", protocolo: "OUV-2026-0001", sigilo_reforcado: true }),
        casoVencido({ id: "id-2", protocolo: "OUV-2026-0002", sigilo_reforcado: false }),
      ],
    });

    await abrirOPainel();

    // A marca aparece uma vez para dois casos na mesma lista: a porta do outro
    // caso fica aberta de propósito, para o teste não passar por um painel que
    // marca tudo.
    const marcas = await screen.findAllByText("Sigiloso");
    expect(marcas).toHaveLength(1);

    const linha = marcas[0].closest("li");
    expect(linha).not.toBeNull();
    expect(within(linha as HTMLElement).getByText("OUV-2026-0001")).toBeTruthy();
  });

  it("nenhuma linha é marcada quando nenhum caso é sigiloso", async () => {
    roteiro.protocolos = resposta({
      protocolos: [casoVencido({ sigilo_reforcado: false })],
    });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(screen.queryByText("Sigiloso")).toBeNull();
  });
});

describe("o calendário de feriados que a listagem não conseguiu ler (issue #449)", () => {
  it("a frase em dias úteis sai da linha quando a própria listagem declara a falha", async () => {
    // A porta das métricas fica ABERTA de propósito, sem degradado nenhum: era
    // ela a única fonte da marca, e por isso a falha da listagem passava sem
    // deixar rastro na tela. O teste mede a listagem sozinha.
    roteiro.metricas = resposta(METRICAS_VAZIAS);
    roteiro.protocolos = resposta({ protocolos: [casoVencido()], degradado: ["feriados"] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(screen.queryByText(/vencido ha 2 dias uteis/)).toBeNull();
    expect(screen.getByText(/sem confirmação do calendário/)).toBeTruthy();
  });

  it("o banner de aviso aparece com o texto da falha do calendário, vindo só da listagem", async () => {
    // A outra metade da mudança, e a que não tinha dente: a linha do caso e o
    // banner do topo saem de dois cálculos diferentes na tela. Reverter só a
    // união que alimenta o banner deixava os outros testes verdes.
    roteiro.metricas = resposta(METRICAS_VAZIAS);
    roteiro.protocolos = resposta({ protocolos: [casoVencido()], degradado: ["feriados"] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(screen.getByText("Parte dos números não pôde ser medida")).toBeTruthy();
    expect(screen.getByText(/O calendário de feriados não pôde ser lido/)).toBeTruthy();
  });

  it("sem falha em nenhuma das duas leituras, o banner não aparece", async () => {
    // A contraprova: o banner não é uma coisa que a tela mostra sempre.
    roteiro.metricas = resposta(METRICAS_VAZIAS);
    roteiro.protocolos = resposta({ protocolos: [casoVencido()], degradado: [] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(screen.queryByText("Parte dos números não pôde ser medida")).toBeNull();
    expect(screen.queryByText(/O calendário de feriados não pôde ser lido/)).toBeNull();
  });

  it("com as duas leituras confirmando o calendário, a frase fica", async () => {
    roteiro.metricas = resposta(METRICAS_VAZIAS);
    roteiro.protocolos = resposta({ protocolos: [casoVencido()], degradado: [] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(screen.getByText(/vencido ha 2 dias uteis/)).toBeTruthy();
    expect(screen.queryByText(/sem confirmação do calendário/)).toBeNull();
  });
});

describe("o espaçamento entre as tentativas", () => {
  it("volta ao intervalo normal na primeira resposta boa", async () => {
    // Uma porta cai: o painel passa a tentar mais espaçado.
    roteiro.metricas = resposta(null, false, 500);

    await abrirOPainel();
    await waitFor(() => expect(polling.intervalos.at(-1)).toBe(INTERVALO_BASE_MS * 2));

    // A rede volta, e a próxima tentativa é a mesma função que o relógio chama.
    roteiro.metricas = resposta(METRICAS_VAZIAS);
    await act(async () => {
      await polling.carga?.();
    });

    expect(polling.intervalos.at(-1)).toBe(INTERVALO_BASE_MS);
  });

  it("continua espaçando enquanto a falha se repete", async () => {
    roteiro.metricas = resposta(null, false, 500);

    await abrirOPainel();
    await waitFor(() => expect(polling.intervalos.at(-1)).toBe(INTERVALO_BASE_MS * 2));

    await act(async () => {
      await polling.carga?.();
    });

    expect(polling.intervalos.at(-1)).toBe(INTERVALO_BASE_MS * 4);
  });
});

describe("a volta para a aba", () => {
  it("recarrega na hora, sem esperar o intervalo inteiro", async () => {
    await abrirOPainel();
    const leiturasIniciais = vi.mocked(fetch).mock.calls.length;

    visibilidade("hidden");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(vi.mocked(fetch).mock.calls.length).toBe(leiturasIniciais);

    visibilidade("visible");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    // As duas portas do painel, lidas de novo assim que a aba voltou.
    expect(vi.mocked(fetch).mock.calls.length).toBe(leiturasIniciais + 2);
  });

  it("para de repuxar enquanto a aba está escondida", async () => {
    await abrirOPainel();
    expect(polling.ativos.at(-1)).toBe(true);

    visibilidade("hidden");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(polling.ativos.at(-1)).toBe(false);
  });
});
