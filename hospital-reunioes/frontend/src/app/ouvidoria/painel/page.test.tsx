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

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALO_BASE_MS } from "@/lib/ouvidoria/painel";
import { ALTURA_DE_TOQUE } from "@/lib/toque";
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
    assunto: "Demora no resultado de exame",
    tipo_manifestacao: "reclamacao",
    data_abertura: "2025-12-29",
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
  revisar: ReturnType<typeof resposta>;
  cobrar: ReturnType<typeof resposta>;
}

/** O que cada porta responde. Trocável no meio do teste. */
let roteiro: Roteiro;

/** As URLs que o painel pediu, na ordem. */
let urls: string[] = [];

/** As escritas (POST) que o painel fez, com a URL. */
let escritas: string[] = [];

beforeEach(() => {
  polling.intervalos = [];
  polling.ativos = [];
  polling.carga = null;
  urls = [];
  escritas = [];
  roteiro = {
    metricas: resposta(METRICAS_VAZIAS),
    protocolos: resposta({ protocolos: [] }),
    revisar: resposta({ total: 0 }),
    cobrar: resposta({ id: "n1", destinatario: "Carlos Titular", entregue: true }, true, 201),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const endereco = String(url);
      if (init?.method === "POST") {
        escritas.push(endereco);
        return roteiro.cobrar;
      }
      urls.push(endereco);
      if (endereco.includes("/metricas")) return roteiro.metricas;
      if (endereco.includes("/avaliacoes/para-revisar")) return roteiro.revisar;
      return roteiro.protocolos;
    })
  );
  visibilidade("visible");
});

/** A URL da listagem que o painel pediu na carga mais recente. */
function ultimaListagem(): string {
  const listagens = urls.filter((url) => url.includes("/protocolos"));
  if (listagens.length === 0) throw new Error("o painel não pediu a listagem");
  return listagens[listagens.length - 1];
}

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

describe("a orientação embutida do painel (issue #1629, regra T1)", () => {
  it("abre com a frase do topo da seção 4.14", async () => {
    await abrirOPainel();

    expect(screen.getByText("O que precisa de atenção agora, do mais urgente ao menos urgente.")).toBeTruthy();
  });

  it("sem caso a vencer, a faixa diz por que está vazia (regra T7)", async () => {
    await abrirOPainel();

    expect(
      within(faixa("Próximos vencimentos")).getByText("Nenhum caso aberto com prazo correndo agora.")
    ).toBeTruthy();
  });
});

describe("o painel conta o hospital inteiro, arquivados inclusive (issue #592, ADR 0047)", () => {
  it("pede a listagem com o recorte que inclui o arquivo", async () => {
    await abrirOPainel();

    expect(ultimaListagem()).toContain("arquivados=todos");
  });

  it("o contador Encerrada, acumulado desde sempre, saiu do painel (issue #1628)", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({ id: "id-1", protocolo: "OUV-2026-0001", status: "encerrado" }),
        casoVencido({ id: "id-2", protocolo: "OUV-2026-0002", status: "encerrado" }),
      ],
    });

    await abrirOPainel();

    expect(screen.queryByText("Encerrada")).toBeNull();
  });
});

/** Os títulos das faixas, na ordem em que a tela os desenha. */
function titulosDasFaixas(): string[] {
  return screen.getAllByRole("heading", { level: 2 }).map((titulo) => titulo.textContent ?? "");
}

/** A faixa pelo título dela. */
function faixa(titulo: string): HTMLElement {
  const cabecalho = screen.getByRole("heading", { level: 2, name: titulo });
  const secao = cabecalho.closest("section");
  if (!secao) throw new Error(`a faixa ${titulo} não é uma seção`);
  return secao;
}

describe("as seis faixas, da mais urgente para a menos urgente (issue #1628, seção 4.11)", () => {
  it("aparecem na ordem do anexo", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(titulosDasFaixas()).toEqual([
      "Críticos",
      "Números do agora",
      "Atrasos das áreas",
      "Atrasos da Ouvidoria",
      "Próximos vencimentos",
      "Por área",
    ]);
  });

  it("sem crítico, a faixa de críticos é uma linha discreta, sem o vermelho", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido({ gravidade: "medio" })] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    const criticos = faixa("Críticos");
    expect(within(criticos).getByText("Nenhum caso crítico aberto.")).toBeTruthy();
    expect(within(criticos).queryByRole("list")).toBeNull();
    expect(criticos.className).not.toMatch(/red|B3352B/);
  });

  it("com um crítico aberto, a faixa fica vermelha e mostra o caso", async () => {
    roteiro.protocolos = resposta({
      protocolos: [casoVencido({ id: "id-9", protocolo: "OUV-2026-0009", gravidade: "critico" })],
    });

    await abrirOPainel();
    await screen.findAllByText("OUV-2026-0009");

    const criticos = faixa("Críticos");
    expect(within(criticos).getByText("OUV-2026-0009")).toBeTruthy();
    expect(within(criticos).queryByText("Nenhum caso crítico aberto.")).toBeNull();
    expect(criticos.className).toMatch(/B3352B/);
  });

  it("o atraso da área e o da Ouvidoria saem em faixas separadas", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({ id: "id-1", protocolo: "OUV-2026-0001" }),
        casoVencido({
          id: "id-2",
          protocolo: "OUV-2026-0002",
          status: "em_classificacao",
          gravidade: null,
          prazo_area_em: null,
          prazo_estourado: false,
          prazo_resposta: "2026-01-05",
        }),
      ],
    });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(within(faixa("Atrasos das áreas")).getByText("OUV-2026-0001")).toBeTruthy();
    expect(within(faixa("Atrasos das áreas")).queryByText("OUV-2026-0002")).toBeNull();
    expect(within(faixa("Atrasos da Ouvidoria")).getByText("OUV-2026-0002")).toBeTruthy();
    expect(within(faixa("Atrasos da Ouvidoria")).queryByText("OUV-2026-0001")).toBeNull();
  });

  it("o elogio com o prazo de referência passado não aparece em faixa de atraso nenhuma", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({
          tipo_manifestacao: "elogio",
          prazo_area_em: null,
          prazo_estourado: false,
          prazo_resposta: "2026-01-05",
        }),
      ],
    });

    await abrirOPainel();

    expect(within(faixa("Atrasos das áreas")).queryByText("OUV-2026-0001")).toBeNull();
    expect(within(faixa("Atrasos da Ouvidoria")).queryByText("OUV-2026-0001")).toBeNull();
  });

  it("tocar em Atrasados mostra a lista daqueles casos logo abaixo dos números", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    const numeros = faixa("Números do agora");
    fireEvent.click(within(numeros).getByRole("button", { name: /Atrasados/ }));

    expect(within(numeros).getByText("OUV-2026-0001")).toBeTruthy();
  });

  it("o contador Para revisar mostra o total e leva à aba Avaliações filtrada", async () => {
    roteiro.revisar = resposta({ total: 3 });

    await abrirOPainel();
    const link = await within(faixa("Números do agora")).findByRole("link", { name: /Para revisar/ });

    expect(link.getAttribute("href")).toBe("/ouvidoria/avaliacoes?revisar=1");
    expect(link.textContent).toContain("3");
  });

  it("a tabela por área traz o % no prazo do mês", async () => {
    roteiro.metricas = resposta({
      ...METRICAS_VAZIAS,
      pendencias_por_area: [
        { setor: "enfermagem", responsavel: "Carlos Titular", pendentes: 2, vencidas: 1, dias_uteis_de_atraso: 2 },
      ],
      prazo_por_area: [
        { setor: "enfermagem", responsavel: "Carlos Titular", medidos: 4, cumpridos: 3, percentual_cumprido: 75 },
      ],
    });

    await abrirOPainel();

    expect(within(faixa("Por área")).getAllByText("75%").length).toBeGreaterThan(0);
  });
});

describe("o Cobrar no card do atraso da área (issue #1628)", () => {
  it("reenvia a cobrança pela rota que grava no histórico e diz para quem foi", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    const atrasos = faixa("Atrasos das áreas");
    fireEvent.click(within(atrasos).getByRole("button", { name: /Cobrar/ }));

    await within(atrasos).findByText("Acionamento reenviado a Carlos Titular");
    expect(escritas).toEqual(["/api/ouvidoria/manifestacoes/id-1/cobrar-setor"]);
  });

  it("o card do atraso da Ouvidoria não tem Cobrar: a dívida é da própria triagem", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({ status: "novo", gravidade: null, prazo_area_em: null, prazo_estourado: false }),
      ],
    });

    await abrirOPainel();

    expect(within(faixa("Atrasos da Ouvidoria")).getByText("OUV-2026-0001")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Cobrar/ })).toBeNull();
  });
});

describe("nenhum nome de paciente no painel (issue #1628, regra T3)", () => {
  it("o card mostra o assunto do agente, e nunca o começo do relato", async () => {
    roteiro.protocolos = resposta({
      protocolos: [
        casoVencido({
          gravidade: "critico",
          resumo: "Maria Aparecida da Silva caiu da maca no quarto 12",
          assunto: "Queda de paciente na internação",
        }),
      ],
    });

    await abrirOPainel();
    await screen.findAllByText("Queda de paciente na internação");

    expect(document.body.textContent).not.toContain("Maria Aparecida");
  });

  it("o caso sem assunto diz que ele não foi gerado, em vez de cair no relato", async () => {
    roteiro.protocolos = resposta({
      protocolos: [casoVencido({ resumo: "Joana Pereira reclama da espera", assunto: null })],
    });

    await abrirOPainel();

    expect(within(faixa("Atrasos das áreas")).getByText("Assunto não gerado")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Joana Pereira");
  });
});

describe("o painel a 375 px (issue #1628, regra T4)", () => {
  it("o Cobrar tem o alvo de toque de 44 px no celular", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    const cobrar = within(faixa("Atrasos das áreas")).getByRole("button", { name: /Cobrar/ });

    for (const classe of ALTURA_DE_TOQUE.split(" ")) {
      expect(cobrar.className.split(/\s+/)).toContain(classe);
    }
  });

  it("nada no painel rola para o lado: a tabela por área vira lista abaixo do md", async () => {
    roteiro.metricas = resposta({
      ...METRICAS_VAZIAS,
      pendencias_por_area: [
        { setor: "enfermagem", responsavel: "Carlos Titular", pendentes: 2, vencidas: 1, dias_uteis_de_atraso: 2 },
      ],
    });
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    expect(document.querySelector("[class*='overflow-x']")).toBeNull();
    const porArea = faixa("Por área");
    const tabela = porArea.querySelector("table");
    expect(tabela?.className.split(/\s+/)).toEqual(expect.arrayContaining(["hidden", "md:table"]));
    const lista = within(porArea).getByRole("list");
    expect(lista.className.split(/\s+/)).toContain("md:hidden");
    expect(within(lista).getByText("enfermagem")).toBeTruthy();
  });

  it("os números do agora cabem em duas colunas no celular, e nada tem largura maior que a tela", async () => {
    roteiro.protocolos = resposta({ protocolos: [casoVencido()] });

    await abrirOPainel();
    await screen.findByText("OUV-2026-0001");

    const grade = within(faixa("Números do agora")).getByRole("button", { name: /Atrasados/ }).parentElement;
    expect(grade?.className.split(/\s+/)).toContain("grid-cols-2");
    // Largura fixa em pixels, sem prefixo de tela, acima do que sobra de 375 px
    // depois do respiro da página. O piso de toque de 44 px não conta.
    const largas = Array.from(document.querySelectorAll("[class]")).flatMap((no) =>
      (no.getAttribute("class") ?? "")
        .split(/\s+/)
        .filter((classe) => /^(min-)?w-\[(\d+)px\]$/.test(classe))
        .filter((classe) => Number(/\[(\d+)px\]/.exec(classe)?.[1]) > 343)
    );
    expect(largas).toEqual([]);
  });
});

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

    // As três portas do painel (métricas, listagem e o contador Para
    // revisar), lidas de novo assim que a aba voltou.
    expect(vi.mocked(fetch).mock.calls.length).toBe(leiturasIniciais + 3);
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
