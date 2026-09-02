/**
 * @vitest-environment jsdom
 */

/**
 * A fila em linha de dois níveis (issue #495, PRD #471, RN-70 a RN-74).
 *
 * A tela era uma tabela de sete colunas com rolagem horizontal: o resumo
 * quebrava linha num corredor estreito e a ação principal ficava fora da área
 * visível. Esta suíte trava o que substituiu a tabela, e o que ela trava é
 * comportamento, não pixel: qual botão cada estado oferece, o que a cobrança
 * dispara, e que o resumo é cortado em vez de empurrar a linha para fora da
 * tela.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "./page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: "ouvidor" as string | null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      perfil_ouvidoria: sessao.perfilOuvidoria,
    },
    loading: false,
  }),
}));

const RESUMO_LONGO =
  "Paciente relata espera de mais de três horas na recepção do ambulatório, sem nenhuma " +
  "informação sobre a fila e sem lugar para sentar durante todo o período de espera.";

const BASE = {
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-12-31",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: RESUMO_LONGO,
  conversa_id: "",
  gravidade: "alto",
  prazo_area_em: null,
  prazo_estourado: false,
  rotulo_prazo: "",
  minutos_uteis_restantes: null,
  tem_novidade: false,
};

function caso(numero: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    ...BASE,
    id: `uuid-${numero}`,
    numero,
    protocolo: `2026-${String(numero).padStart(4, "0")}`,
    status,
    ...extra,
  };
}

const TITULAR = {
  id: "r1",
  setor: "Recepção",
  papel: "titular",
  nome: "Carlos Titular",
  email: "carlos@hsm.br",
  vigencia_inicio: "2020-01-01",
  vigencia_fim: null,
};

const ACIONAMENTO = {
  id: "notificacao-do-acionamento",
  gatilho: "nova_demanda",
  criada_em: "2026-08-15T12:00:00Z",
};

/** As chamadas que a tela fez, para as asserções de cobrança. */
let chamadas: { url: string; metodo: string }[] = [];

function montar(
  protocolos: ReturnType<typeof caso>[],
  opcoes: { responsaveis?: unknown[]; notificacoes?: unknown[] } = {}
) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const endereco = String(url);
      chamadas.push({ url: endereco, metodo: init?.method ?? "GET" });
      if (endereco.includes("/reenviar")) {
        return { ok: true, status: 201, json: async () => ({ entregue: true }) } as Response;
      }
      if (endereco.includes("/notificacoes")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ notificacoes: opcoes.notificacoes ?? [ACIONAMENTO] }),
        } as Response;
      }
      if (endereco.includes("/responsaveis")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ responsaveis: opcoes.responsaveis ?? [TITULAR] }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ protocolos }) } as Response;
    })
  );
  render(<OuvidoriaPage />);
}

async function linhaDe(protocolo: string): Promise<HTMLElement> {
  await screen.findByText(protocolo);
  const linha = document.querySelector<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (!linha) throw new Error(`sem linha para o protocolo ${protocolo}`);
  return linha;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  sessao.perfilOuvidoria = "ouvidor";
  vi.unstubAllGlobals();
});

describe("a linha de dois níveis substitui a tabela (RN-72, RN-73)", () => {
  it("a fila não é mais uma tabela", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    expect(screen.queryByRole("table")).toBeNull();
  });

  it("nada rola para o lado: nenhum contêiner da fila esconde conteúdo no eixo x", async () => {
    // A tabela antiga vivia dentro de um `overflow-x-auto`, e era ele que
    // levava a ação principal para fora da área visível (D-06). Em jsdom não
    // há layout para medir, então o que se trava é a causa: nenhum ancestral
    // da linha pode voltar a oferecer o corredor lateral.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    for (let no = linha.parentElement; no && no !== document.body; no = no.parentElement) {
      expect(no.className).not.toContain("overflow-x-auto");
      expect(no.className).not.toContain("overflow-x-scroll");
    }
  });

  it("o resumo é cortado em uma linha, com o texto inteiro no tooltip", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const resumo = within(linha).getByText(RESUMO_LONGO);
    expect(resumo.className).toContain("truncate");
    expect(resumo.getAttribute("title")).toBe(RESUMO_LONGO);
  });

  it("o nível 2 diz o setor, quem responde por ele e o prazo", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByText("Recepção")).toBeTruthy();
    await waitFor(() => expect(within(linha).getByText("Carlos Titular")).toBeTruthy());
  });

  it("setor sem responsável vigente é dito na linha, e não deixado em branco", async () => {
    montar([caso(7, "aguardando_area")], { responsaveis: [] });
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByText("Sem responsável")).toBeTruthy();
  });

  it("a gravidade aparece na pílula, e é a única cor de urgência da linha", async () => {
    montar([caso(7, "aguardando_area", { gravidade: "critico" })]);
    const linha = await linhaDe("2026-0007");

    const pilula = within(linha).getByText("Crítico");
    expect(pilula.className).toContain("red");
    // O nome do estado é da faixa do grupo (RN-71), nunca da linha.
    expect(within(linha).queryByText("Aguardando área")).toBeNull();
  });
});

describe("a ação primária de cada estado, sempre visível (RN-74, D-06)", () => {
  it("caso em classificação oferece validar e acionar", async () => {
    montar([caso(7, "em_classificacao")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Validar e acionar" })).toBeTruthy();
  });

  it("caso com a área oferece cobrar", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Cobrar" })).toBeTruthy();
  });

  it("caso respondido oferece encerrar", async () => {
    montar([caso(7, "respondido")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();
  });

  it("caso encerrado oferece só o caminho do Dossiê, sem menu nenhum", async () => {
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("link", { name: "Abrir manifestação" })).toBeTruthy();
    expect(within(linha).queryByRole("button", { name: /Mais ações/ })).toBeNull();
  });

  it("o que sobra fica no menu, e não na linha", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).queryByRole("button", { name: "Encerrar" })).toBeNull();
    expect(within(linha).queryByRole("link", { name: "Abrir manifestação" })).toBeNull();

    fireEvent.click(within(linha).getByRole("button", { name: /Mais ações/ }));

    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();
    expect(within(linha).getByRole("link", { name: "Abrir manifestação" })).toBeTruthy();
  });

  it("quem está fora da Ouvidoria vê a linha e nenhuma ação", async () => {
    sessao.perfilOuvidoria = null;
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).queryByRole("button")).toBeNull();
    expect(within(linha).queryByRole("link")).toBeNull();
  });
});

describe("cobrar é reenviar o acionamento (RN-74)", () => {
  it("manda de novo o acionamento do caso, pela rota de reenvio", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    await waitFor(() =>
      expect(
        chamadas.some(
          (c) =>
            c.metodo === "POST" &&
            c.url ===
              "/api/ouvidoria/manifestacoes/uuid-7/notificacoes/notificacao-do-acionamento/reenviar"
        )
      ).toBe(true)
    );
    expect(await within(linha).findByText("Acionamento reenviado ao responsável")).toBeTruthy();
  });

  it("não reenvia a cobrança de prazo no lugar do acionamento", async () => {
    // O caso acumula notificações (véspera, prazo rompido, escalonamento).
    // Cobrar é acordar o setor com o mesmo acionamento, não repetir o último
    // email que saiu.
    montar([caso(7, "aguardando_area")], {
      notificacoes: [
        { id: "n-prazo", gatilho: "prazo_rompido", criada_em: "2026-08-30T12:00:00Z" },
        ACIONAMENTO,
      ],
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST")).toBe(true));
    expect(chamadas.filter((c) => c.metodo === "POST").map((c) => c.url)).toEqual([
      "/api/ouvidoria/manifestacoes/uuid-7/notificacoes/notificacao-do-acionamento/reenviar",
    ]);
  });

  it("caso sem acionamento registrado avisa, e não dispara envio nenhum", async () => {
    montar([caso(7, "aguardando_area")], { notificacoes: [] });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(
      await within(linha).findByText("Este caso não tem acionamento registrado para reenviar")
    ).toBeTruthy();
    expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);
  });
});

describe("a faixa de cada grupo (RN-70, RN-71)", () => {
  it("o cabeçalho do grupo é uma faixa na cor do estado, com o contador", async () => {
    montar([caso(7, "aguardando_area"), caso(8, "aguardando_area")]);
    await linhaDe("2026-0007");

    const faixa = screen.getByText("Aguardando área").closest("header");
    expect(faixa).not.toBeNull();
    expect(faixa!.className).toContain("bg-amber-100");
    expect(within(faixa!).getByText("2 manifestações")).toBeTruthy();
  });

  it("o rótulo do estado sobe em caixa alta pelo estilo, e não pelo texto", async () => {
    // Caixa alta escrita no texto é o que o leitor de tela soletra letra a
    // letra, e o que a issue #489 teria de desfazer depois.
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const rotulo = screen.getByText("Aguardando área");
    expect(rotulo.className).toContain("uppercase");
  });
});
