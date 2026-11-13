/**
 * @vitest-environment jsdom
 */

/**
 * A aba Avaliações da Ouvidoria, na tela (issue #1626, PRD #1527, ADR 0086).
 *
 * Os números chegam prontos do servidor, e as contas têm teste lá. Aqui se
 * prova o que só existe na tela: os indicadores e os gráficos desenhados, o
 * endereço que cada filtro manda, a entrada pelo contador do Painel, as duas
 * ações (converter e arquivar com motivo) e o desenho de celular a 375 px.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AvaliacoesPage from "./page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const quem = vi.hoisted(() => ({ perfil: "ouvidor" as string | null, busca: "" }));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "p1", perfil_ouvidoria: quem.perfil },
    loading: false,
  }),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(quem.busca),
}));

const NUMEROS = {
  periodo: "30d",
  intervalo: { inicio: "2026-10-15", fim: "2026-11-13" },
  indicadores: { volume: 5, nota_media: 3.0, pct_4_e_5: 0.4, pct_pediu_retorno: 0.2 },
  por_ponto: [
    { ponto_id: "pt-c", nome: "Centro médico", nota_media: 1.5, volume: 2 },
    { ponto_id: "pt-e", nome: "Emergência adulta", nota_media: 4.0, volume: 3 },
  ],
  por_turno: [
    { turno: "manha", rotulo: "Manhã", nota_media: 5.0, volume: 1 },
    { turno: "tarde", rotulo: "Tarde", nota_media: 2.0, volume: 1 },
    { turno: "noite", rotulo: "Noite", nota_media: 4.0, volume: 1 },
    { turno: "madrugada", rotulo: "Madrugada", nota_media: 2.0, volume: 2 },
  ],
  por_dia_da_semana: [
    { dia: "seg", rotulo: "Segunda", nota_media: 2.0, volume: 1 },
    { dia: "ter", rotulo: "Terça", nota_media: 1.0, volume: 1 },
    { dia: "qua", rotulo: "Quarta", nota_media: null, volume: 0 },
    { dia: "qui", rotulo: "Quinta", nota_media: 4.0, volume: 3 },
    { dia: "sex", rotulo: "Sexta", nota_media: null, volume: 0 },
    { dia: "sab", rotulo: "Sábado", nota_media: null, volume: 0 },
    { dia: "dom", rotulo: "Domingo", nota_media: null, volume: 0 },
  ],
  por_semana: [
    { semana: "2026-11-02", nota_media: 2.0, volume: 1 },
    { semana: "2026-11-09", nota_media: 3.33, volume: 3 },
  ],
};

const MARCADA = {
  id: "av-1",
  ponto_id: "pt-e",
  ponto_nome: "Emergência adulta",
  nota: 1,
  motivos: ["recepcao", "tempo_espera"],
  comentario: "A recepcionista gritou comigo.",
  criada_em: "2026-11-12T13:00:00+00:00",
  pediu_retorno: false,
  revisar: true,
  revisar_motivo: "Relata desrespeito grave",
  revisao_desfecho: null,
  revisao_motivo: null,
  revisada_em: null,
  para_revisar: true,
  caso: null,
};

const SEM_COMENTARIO = {
  ...MARCADA,
  id: "av-2",
  nota: 5,
  motivos: [],
  comentario: null,
  revisar: false,
  revisar_motivo: null,
  para_revisar: false,
};

interface Chamada {
  url: string;
  metodo: string;
  corpo: unknown;
}

let chamadas: Chamada[] = [];

function resposta(corpo: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => corpo } as Response;
}

beforeEach(() => {
  chamadas = [];
  quem.perfil = "ouvidor";
  quem.busca = "";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.startsWith("/api/ouvidoria/avaliacoes/numeros")) return resposta(NUMEROS);
      if (url.startsWith("/api/ouvidoria/pontos")) {
        return resposta({ pontos: [{ id: "pt-e", ponto: "Hall", nome_publico: "Emergência adulta" }] });
      }
      if (url.endsWith("/conversao")) return resposta({ id: "caso-9", protocolo: "2026-0042" }, 201);
      if (url.endsWith("/arquivamento")) {
        return resposta({ id: "av-1", revisao_desfecho: "arquivada", revisao_motivo: "Tratado por telefone" });
      }
      return resposta({ itens: [MARCADA, SEM_COMENTARIO], total: 2, pagina: 1, por_pagina: 20, para_revisar_total: 1 });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function listas() {
  return chamadas.filter((c) => c.metodo === "GET" && c.url.startsWith("/api/ouvidoria/avaliacoes?"));
}

async function abrir() {
  render(<AvaliacoesPage />);
  await screen.findByText("A recepcionista gritou comigo.");
}

describe("os números do período", () => {
  it("mostra a nota média, a % de 4 e 5, o volume e a % que pediu retorno", async () => {
    await abrir();

    const indicadores = within(screen.getByRole("region", { name: "Indicadores" }));
    expect(indicadores.getByText("Nota média").nextSibling?.textContent).toBe("3,0");
    expect(indicadores.getByText("Notas 4 e 5").nextSibling?.textContent).toBe("40%");
    expect(indicadores.getByText("Avaliações").nextSibling?.textContent).toBe("5");
    expect(indicadores.getByText("Pediram retorno").nextSibling?.textContent).toBe("20%");
  });

  it("desenha a nota média por ponto, turno, dia da semana e semana", async () => {
    await abrir();

    const porPonto = within(screen.getByRole("region", { name: "Nota média por ponto" }));
    expect(porPonto.getByText("Emergência adulta")).toBeTruthy();
    expect(porPonto.getByText("4,0")).toBeTruthy();
    const porTurno = within(screen.getByRole("region", { name: "Nota média por turno" }));
    expect(porTurno.getByText("Madrugada")).toBeTruthy();
    const porDia = within(screen.getByRole("region", { name: "Nota média por dia da semana" }));
    expect(porDia.getByText("Quinta")).toBeTruthy();
    const porSemana = within(screen.getByRole("region", { name: "Evolução semanal" }));
    expect(porSemana.getByText("09/11")).toBeTruthy();
    expect(porSemana.getByText("3,3")).toBeTruthy();
  });

  it("trocar o período pede os números e a lista do período novo", async () => {
    await abrir();

    fireEvent.change(screen.getByLabelText("Período"), { target: { value: "7d" } });

    await waitFor(() =>
      expect(chamadas.some((c) => c.url === "/api/ouvidoria/avaliacoes/numeros?periodo=7d")).toBe(true)
    );
    expect(listas().at(-1)?.url).toBe("/api/ouvidoria/avaliacoes?periodo=7d");
  });
});

describe("a lista com os filtros", () => {
  it("abre nos últimos 30 dias, com nota, motivos, comentário, ponto e data", async () => {
    await abrir();

    expect(listas()[0].url).toBe("/api/ouvidoria/avaliacoes?periodo=30d");
    const card = within(screen.getByRole("article", { name: /avaliação nota 1/i }));
    expect(card.getByText("Recepção")).toBeTruthy();
    expect(card.getByText("Tempo de espera")).toBeTruthy();
    expect(card.getByText("Emergência adulta")).toBeTruthy();
    expect(card.getByText("12/11/2026, 10:00")).toBeTruthy();
    expect(card.getByText(/Relata desrespeito grave/)).toBeTruthy();
  });

  it("cada filtro vai no endereço da lista", async () => {
    await abrir();

    fireEvent.change(screen.getByLabelText("Nota"), { target: { value: "1" } });
    await waitFor(() => expect(listas().at(-1)?.url).toContain("nota=1"));
    fireEvent.click(screen.getByLabelText("Só com comentário"));
    await waitFor(() => expect(listas().at(-1)?.url).toContain("com_comentario=true"));
    fireEvent.click(screen.getByLabelText(/Para revisar/));
    await waitFor(() => expect(listas().at(-1)?.url).toContain("para_revisar=true"));
    fireEvent.change(screen.getByLabelText("Ponto"), { target: { value: "pt-e" } });
    await waitFor(() => expect(listas().at(-1)?.url).toContain("ponto_id=pt-e"));
  });

  it("vinda do contador do Painel, abre só nas marcadas e sem limite de data", async () => {
    quem.busca = "revisar=1";

    await abrir();

    expect(listas()[0].url).toBe("/api/ouvidoria/avaliacoes?periodo=tudo&para_revisar=true");
    expect((screen.getByLabelText(/Para revisar/) as HTMLInputElement).checked).toBe(true);
  });
});

describe("converter em manifestação", () => {
  it("pede a confirmação antes de abrir o caso, que não tem volta", async () => {
    await abrir();
    const card = within(screen.getByRole("article", { name: /avaliação nota 1/i }));

    fireEvent.click(card.getByRole("button", { name: "Converter em manifestação" }));

    expect(card.getByText(/não tem volta/i)).toBeTruthy();
    expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);
    fireEvent.click(card.getByRole("button", { name: "Cancelar" }));
    expect(card.queryByRole("button", { name: "Abrir o caso" })).toBeNull();
  });

  it("abre o caso e mostra o protocolo com o caminho para ele", async () => {
    await abrir();
    const card = within(screen.getByRole("article", { name: /avaliação nota 1/i }));

    fireEvent.click(card.getByRole("button", { name: "Converter em manifestação" }));
    fireEvent.click(card.getByRole("button", { name: "Abrir o caso" }));

    await waitFor(() =>
      expect(chamadas.find((c) => c.metodo === "POST")?.url).toBe("/api/ouvidoria/avaliacoes/av-1/conversao")
    );
    const link = await card.findByRole("link", { name: /2026-0042/ });
    expect(link.getAttribute("href")).toBe("/ouvidoria/m/2026-0042");
  });

  it("a nota sem comentário não oferece converter", async () => {
    await abrir();
    const card = within(screen.getByRole("article", { name: /avaliação nota 5/i }));

    expect(card.queryByRole("button", { name: "Converter em manifestação" })).toBeNull();
  });
});

describe("arquivar a revisão", () => {
  it("exige o motivo antes de arquivar e manda o motivo escrito", async () => {
    await abrir();
    const card = within(screen.getByRole("article", { name: /avaliação nota 1/i }));

    fireEvent.click(card.getByRole("button", { name: "Arquivar revisão" }));
    const confirmar = card.getByRole("button", { name: "Confirmar arquivo" }) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(card.getByLabelText("Motivo do arquivo"), { target: { value: "   " } });
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(card.getByLabelText("Motivo do arquivo"), { target: { value: "Tratado por telefone" } });
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);

    await waitFor(() => expect(chamadas.some((c) => c.url.endsWith("/arquivamento"))).toBe(true));
    expect(chamadas.find((c) => c.url.endsWith("/arquivamento"))?.corpo).toEqual({
      motivo: "Tratado por telefone",
    });
    expect(await card.findByText(/Revisão arquivada: Tratado por telefone/)).toBeTruthy();
    expect(card.queryByText("Para revisar")).toBeNull();
  });

  it("só a nota marcada Para revisar oferece arquivar", async () => {
    await abrir();
    const card = within(screen.getByRole("article", { name: /avaliação nota 5/i }));

    expect(card.queryByRole("button", { name: "Arquivar revisão" })).toBeNull();
  });
});

describe("funciona a 375 px", () => {
  it("todo controle tem alvo de toque de 44 px", async () => {
    await abrir();
    fireEvent.click(
      within(screen.getByRole("article", { name: /avaliação nota 1/i })).getByRole("button", {
        name: "Arquivar revisão",
      })
    );

    const controles = [
      ...screen.getAllByRole("button"),
      ...screen.getAllByRole("combobox"),
      ...screen.getAllByRole("checkbox").map((c) => c.closest("label")!),
    ];
    for (const controle of controles) {
      expect(controle.className, controle.textContent ?? "").toContain("min-h-[44px]");
    }
  });

  it("nada tem largura fixa maior que a tela, e os blocos empilham", async () => {
    const { container } = render(<AvaliacoesPage />);
    await screen.findByText("A recepcionista gritou comigo.");

    for (const elemento of Array.from(container.querySelectorAll("[class]"))) {
      const classes = elemento.getAttribute("class") ?? "";
      for (const [, px] of classes.matchAll(/(?:^|\s)(?:w|min-w)-\[(\d+)px\]/g)) {
        expect(Number(px)).toBeLessThanOrEqual(375);
      }
    }
    // Dois indicadores por linha no celular, quatro do `lg` para cima.
    const indicadores = screen.getByRole("region", { name: "Indicadores" }).querySelector("dl")!;
    expect(indicadores.className.split(/\s+/)).toEqual(expect.arrayContaining(["grid-cols-2", "lg:grid-cols-4"]));
    // Os filtros empilham no celular.
    const filtros = screen.getByRole("group", { name: "Filtros da lista" });
    expect(filtros.className.split(/\s+/)).toEqual(expect.arrayContaining(["grid-cols-1", "sm:grid-cols-2"]));
  });
});

describe("quem vê a aba", () => {
  it("fora da Ouvidoria a tela não pede nada ao servidor e diz por quê", async () => {
    quem.perfil = null;

    render(<AvaliacoesPage />);

    expect(await screen.findByText(/só o ouvidor e a diretoria executiva/i)).toBeTruthy();
    expect(chamadas).toEqual([]);
  });
});
