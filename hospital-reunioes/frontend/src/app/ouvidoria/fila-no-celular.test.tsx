/**
 * @vitest-environment jsdom
 */

/**
 * A fila da Ouvidoria no celular (issue #496, PRD #471, RN-75, RN-77, D-02,
 * D-16).
 *
 * A linha de dois níveis da issue #495 resolveu o desktop e deixou o telefone
 * de fora: os dois níveis lado a lado num corredor de 360px espremem o resumo
 * a nada, e o botão da ação primária fica com metade do alvo de toque que um
 * dedo precisa. Aqui se trava o empilhamento, os 44px e a barra de atalhos.
 *
 * jsdom não tem layout, então nada aqui mede pixel: o que se trava é a causa,
 * que são as classes responsivas e o alvo de toque declarado. O ponto de corte
 * é o `md` do Tailwind, 768px, o mesmo que o resto da casa usa para separar o
 * celular do computador (`components/layout/Header`).
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BREAKPOINT_DA_BARRA } from "@/lib/ouvidoria/atalhos";

import OuvidoriaPage from "./page";

/**
 * Até onde o piso de 44px sobrevive, lido das classes.
 *
 * `min-h-[44px] md:min-h-0` devolve "md": o piso morre ali, e do `md` para
 * cima o controle fica só com a caixa de linha dele. Sem piso nenhum devolve
 * `null`, e um piso sem cancelamento devolve "sempre". jsdom não calcula
 * layout, e esta é a coisa mais próxima de altura efetiva que dá para afirmar
 * aqui: quem cancela o piso e a partir de que largura.
 */
function ateOndeOPisoDeToqueVale(className: string): string | null {
  const classes = className.split(/\s+/);
  if (!classes.includes("min-h-[44px]")) return null;
  const cancela = classes.find((c) => /^[a-z]+:min-h-0$/.test(c));
  return cancela ? cancela.split(":")[0] : "sempre";
}

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

function montar(protocolos: ReturnType<typeof caso>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const endereco = String(url);
      if (endereco.includes("/responsaveis")) {
        return { ok: true, status: 200, json: async () => ({ responsaveis: [] }) } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ protocolos }) } as Response;
    })
  );
  render(<OuvidoriaPage />);
}

async function linhaDe(protocolo: string): Promise<HTMLElement> {
  await screen.findByText(protocolo);
  const linhas = document.querySelectorAll<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (linhas.length === 0) throw new Error(`sem linha para o protocolo ${protocolo}`);
  if (linhas.length > 1) {
    throw new Error(`${linhas.length} linhas para o protocolo ${protocolo}: escolha qual`);
  }
  return linhas[0];
}

afterEach(async () => {
  // A leitura do cadastro de responsáveis continua em voo depois que a linha
  // aparece, e quase nenhum teste daqui espera por ela. Sem deixá-la pousar
  // antes de desmontar, o `setState` dela chega com a árvore já fora do ar e o
  // erro vaza para o arquivo de teste seguinte.
  await act(async () => {});
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  sessao.perfilOuvidoria = "ouvidor";
  vi.unstubAllGlobals();
});

describe("a linha empilha em três alturas abaixo de 768px (RN-75, D-02)", () => {
  it("a linha é coluna no celular e volta a ser linha no computador", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(linha.className).toContain("flex-col");
    expect(linha.className).toContain("md:flex-row");
  });

  it("o resumo ganha altura própria no celular, abaixo do protocolo", async () => {
    // No desktop protocolo, gravidade e resumo dividem o nível 1. Num corredor
    // de 360px isso sobra um punhado de pixels para o resumo, que é justamente
    // o que o ouvidor lê para decidir se abre o caso.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const resumo = within(linha).getByText(RESUMO_LONGO);
    const nivel1 = resumo.parentElement!;
    expect(nivel1.className).toContain("flex-col");
    expect(nivel1.className).toContain("md:flex-row");
    // A altura de cima é o grupo do protocolo, irmão do resumo e não pai dele.
    expect(nivel1.firstElementChild!.textContent).toContain("2026-0007");
    expect(nivel1.firstElementChild!.textContent).not.toContain(RESUMO_LONGO);
  });

  it("o resumo continua cortado em uma linha mesmo empilhado", async () => {
    // Empilhar não pode virar desculpa para o texto inteiro voltar: uma linha
    // de resumo com cinco alturas afunda a fila do mesmo jeito que a tabela.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByText(RESUMO_LONGO).className).toContain("truncate");
  });

  it("nada dentro da linha oferece corredor lateral (RN-73)", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    for (const no of linha.querySelectorAll("*")) {
      expect(no.className.toString()).not.toContain("overflow-x-auto");
      expect(no.className.toString()).not.toContain("overflow-x-scroll");
    }
  });
});

describe("a ação primária vira botão de largura total com 44px de toque (RN-75)", () => {
  it("o botão do estado ocupa a linha inteira no celular", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const botao = within(linha).getByRole("button", { name: "Cobrar" });
    expect(botao.className).toContain("flex-1");
    expect(botao.className).toContain("md:flex-none");
    expect(botao.className).toContain("min-h-[44px]");
    expect(botao.className).toContain("md:min-h-0");
  });

  it("o bloco de ações é largura total no celular e encolhe no computador", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const acoes = within(linha).getByRole("button", { name: "Cobrar" }).parentElement!;
    expect(acoes.className).toContain("w-full");
    expect(acoes.className).toContain("md:w-auto");
  });

  it("abrir o Dossiê é link, e o link também é botão de largura total", async () => {
    // Caso encerrado não tem botão nenhum: a ação primária dele é o link do
    // Dossiê, e um link de 20px de altura no celular não se acerta com o dedo.
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    const link = within(linha).getByRole("link", { name: "Abrir manifestação" });
    expect(link.className).toContain("flex-1");
    expect(link.className).toContain("min-h-[44px]");
  });

  it("o gatilho do menu de mais ações tem 44px nos dois lados", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const gatilho = within(linha).getByRole("button", { name: /Mais ações/ });
    expect(gatilho.className).toContain("min-w-[44px]");
    expect(gatilho.className).toContain("min-h-[44px]");
    expect(gatilho.className).toContain("md:min-w-0");
    expect(gatilho.className).toContain("md:min-h-0");
  });

  it("cada item do menu também é alvo de 44px", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: /Mais ações/ }));
    const itens = [
      within(linha).getByRole("button", { name: "Encerrar" }),
      within(linha).getByRole("link", { name: "Abrir manifestação" }),
    ];
    for (const item of itens) {
      expect(item.className).toContain("min-h-[44px]");
    }
  });
});

describe("a barra de atalhos numa linha só (RN-77, D-16)", () => {
  it("os atalhos vivem numa nav própria, que some onde a linha não os comporta", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    expect(nav.className).toContain("hidden");
    // `lg`, e não `md`: o sidebar do AppShell entra no `md` e come 256px da
    // linha, e a barra não cabia nos 384px que sobravam (issue #489). A conta
    // e o teto vivem em `lib/ouvidoria/atalhos`.
    expect(nav.className).toContain("lg:flex");
    // Uma linha só: o contêiner não pode ter permissão para quebrar.
    expect(nav.className).not.toContain("flex-wrap");
  });

  it("nenhuma pílula quebra o texto dela em duas linhas", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    const pilulas = within(nav).getAllByRole("link");
    expect(pilulas).toHaveLength(5);
    for (const pilula of pilulas) {
      expect(pilula.className).toContain("whitespace-nowrap");
    }
  });

  it("a pílula mostra o rótulo curto e diz o nome inteiro a quem não a vê", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    const painel = within(nav).getByRole("link", { name: "Painel em tempo real" });
    expect(painel.textContent).toBe("Painel");
  });

  it("cada perfil vê só as portas dele", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    expect(within(nav).getByRole("link", { name: "Painel em tempo real" })).toBeTruthy();
    expect(within(nav).queryByRole("link", { name: "Tabela de prazos" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "Responsáveis por setor" })).toBeNull();
  });

  it("quem está fora da Ouvidoria não vê barra de atalhos nenhuma", async () => {
    sessao.perfilOuvidoria = null;
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    expect(screen.queryByRole("navigation", { name: /atalhos da ouvidoria/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Atalhos" })).toBeNull();
  });
});

describe("no celular os atalhos colapsam em menu (RN-77)", () => {
  function gatilhoDosAtalhos() {
    return screen.getByRole("button", { name: "Atalhos" });
  }

  it("o gatilho do menu só existe onde a barra não cabe, e é alvo de 44px ali inteiro", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const gatilho = gatilhoDosAtalhos();
    // Ele é o par exato da `nav`: some onde ela aparece, e não um degrau antes
    // (issue #489).
    expect(gatilho.parentElement!.className).toContain("lg:hidden");
    // E o piso de 44px tem que durar o mesmo tanto. Procurar a substring
    // `min-h-[44px]` não prova nada: ela continua escrita enquanto um
    // `md:min-h-0` ao lado a cancela, e foi assim que este teste ficou verde
    // afirmando 44px onde sobravam 20. O que se lê aqui é ATÉ ONDE o piso
    // sobrevive.
    expect(ateOndeOPisoDeToqueVale(gatilho.className)).toBe(BREAKPOINT_DA_BARRA);
  });

  it("o menu nasce fechado e abre com as portas do perfil, pelo nome inteiro", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const gatilho = gatilhoDosAtalhos();
    const flutuante = gatilho.parentElement!;
    expect(within(flutuante).queryAllByRole("link")).toHaveLength(0);
    expect(gatilho.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(gatilho);
    expect(gatilho.getAttribute("aria-expanded")).toBe("true");
    const itens = within(flutuante).getAllByRole("link");
    expect(itens).toHaveLength(5);
    // No menu há largura: o nome inteiro é o texto, e não só o rótulo curto.
    expect(itens[0].textContent).toBe("Painel em tempo real");
    for (const item of itens) {
      // O mesmo piso do gatilho, e pela mesma razão: entre 768px e 1023px
      // estes links são a única porta para as cinco telas, e o menu lateral do
      // AppShell não as lista (issue #489).
      expect(ateOndeOPisoDeToqueVale(item.className)).toBe(BREAKPOINT_DA_BARRA);
    }
  });

  it("o menu fecha no Escape, como o resto dos flutuantes da casa", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const gatilho = gatilhoDosAtalhos();
    const flutuante = gatilho.parentElement!;
    fireEvent.click(gatilho);
    expect(within(flutuante).getAllByRole("link").length).toBeGreaterThan(0);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(within(flutuante).queryAllByRole("link")).toHaveLength(0);
  });

  it("o menu fecha ao clicar fora dele", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const gatilho = gatilhoDosAtalhos();
    const flutuante = gatilho.parentElement!;
    fireEvent.click(gatilho);
    expect(within(flutuante).getAllByRole("link").length).toBeGreaterThan(0);

    fireEvent.mouseDown(document.body);
    expect(within(flutuante).queryAllByRole("link")).toHaveLength(0);
  });
});

describe("o indicador de volume não é atalho de navegação (RN-77, D-16)", () => {
  it("o contador de casos em andamento fica fora da nav dos atalhos", async () => {
    // Ele parecia uma pílula igual às outras e o olho o lia como mais uma
    // porta. Informação e navegação são coisas diferentes, e agora moram em
    // caixas diferentes.
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    const indicador = screen.getByText(/em andamento/);
    expect(nav.contains(indicador)).toBe(false);
    expect(indicador.tagName).not.toBe("A");
  });

  it("o indicador de prazo estourado acompanha o de volume, e não os atalhos", async () => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    montar([caso(7, "aguardando_area", { prazo_estourado: true, prazo_area_em: "2020-01-01T12:00:00Z" })]);
    await linhaDe("2026-0007");

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    const estourado = await screen.findByText(/com prazo estourado/);
    expect(nav.contains(estourado)).toBe(false);
    expect(estourado.parentElement).toBe(screen.getByText(/em andamento/).parentElement);
  });
});
