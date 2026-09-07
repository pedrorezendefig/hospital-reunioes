/**
 * @vitest-environment jsdom
 */

/**
 * O Arquivo na lista da Ouvidoria (issue #592, PRD #591, ADR 0047).
 *
 * A lista nasce sem os arquivados e os mostra atrás de um filtro próprio. A
 * linha do caso encerrado ganha "Arquivar"; com o filtro ligado, ela oferece
 * "Desarquivar". A tela não decide nada: quem recusa é o servidor, com 409, e
 * o que se trava aqui é o que o ouvidor vê e o que o clique dispara.
 *
 * Duas armadilhas de teste vazio moram aqui:
 *
 * * afirmar que a lista "filtrou" com um caso só na tela passa mesmo se a
 *   chamada tivesse falhado. Por isso as asserções de filtro olham a URL que a
 *   tela pediu, que é a única coisa que ela realmente controla;
 * * afirmar que um botão sumiu é vazio se ele nunca existiu. Por isso todo
 *   teste de ausência tem irmão de presença, no mesmo estado e no mesmo modo.
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

const BASE = {
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-12-31",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: "Paciente relata espera acima de duas horas na recepção.",
  conversa_id: "",
  gravidade: "alto",
  prazo_area_em: null,
  prazo_estourado: false,
  rotulo_prazo: "",
  minutos_uteis_restantes: null,
  tem_novidade: false,
};

function caso(numero: number, status: string) {
  return {
    ...BASE,
    id: `uuid-${numero}`,
    numero,
    protocolo: `2026-${String(numero).padStart(4, "0")}`,
    status,
  };
}

/** As chamadas que a tela fez, na ordem. */
let chamadas: { url: string; metodo: string }[] = [];

/** As respostas de listagem seguradas, na ordem em que a tela as pediu. */
let presos: (() => void)[] = [];

/**
 * Monta a tela com o servidor falso. `viva` é a lista de trabalho e `arquivada`
 * é o que o filtro mostra: são DUAS listas, e o fake as separa pela URL, que é
 * exatamente a decisão que a tela precisa acertar.
 */
function montar(
  viva: ReturnType<typeof caso>[],
  arquivada: ReturnType<typeof caso>[] = [],
  opcoes: {
    // A recusa que o SERVIDOR devolve ao arquivar, com o status e a frase
    // dele: é ela que o ouvidor precisa ler na tela.
    recusaDoArquivo?: { status: number; detail?: string };
    // Segura a resposta da listagem até quem chamou soltar. É assim que a
    // corrida do filtro entra no teste.
    segurarListagem?: boolean;
    // Segura a resposta de arquivar. É a janela em que o dedo bate duas vezes
    // no mesmo botão.
    segurarArquivo?: boolean;
  } = {}
) {
  chamadas = [];
  const vivos = [...viva];
  const arquivados = [...arquivada];
  presos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const endereco = String(url);
      const metodo = init?.method ?? "GET";
      chamadas.push({ url: endereco, metodo });
      if (endereco.includes("/arquivo")) {
        if (opcoes.recusaDoArquivo) {
          return {
            ok: false,
            status: opcoes.recusaDoArquivo.status,
            json: async () => ({ detail: opcoes.recusaDoArquivo!.detail }),
          } as Response;
        }
        const id = endereco.split("/manifestacoes/")[1].split("/")[0];
        const mover = (de: typeof vivos, para: typeof vivos) => {
          const i = de.findIndex((c) => c.id === id);
          if (i >= 0) para.push(...de.splice(i, 1));
        };
        if (metodo === "POST") mover(vivos, arquivados);
        if (metodo === "DELETE") mover(arquivados, vivos);
        const feito = { ok: true, status: 200, json: async () => ({}) } as Response;
        if (!opcoes.segurarArquivo) return feito;
        return new Promise<Response>((soltar) => presos.push(() => soltar(feito)));
      }
      if (endereco.includes("/responsaveis")) {
        return { ok: true, status: 200, json: async () => ({ responsaveis: [] }) } as Response;
      }
      const querArquivados = endereco.includes("arquivados=sim");
      const corpo = {
        ok: true,
        status: 200,
        // Cópia, e não o próprio array: a tela guarda o que a resposta trouxe,
        // e mutar essa mesma lista depois (o `splice` de arquivar) mexeria no
        // estado do React pelas costas dele.
        json: async () => ({ protocolos: [...(querArquivados ? arquivados : vivos)] }),
      } as Response;
      if (!opcoes.segurarListagem) return corpo;
      // A resposta fica presa até o teste soltar, na ordem que ele quiser.
      return new Promise<Response>((soltar) => presos.push(() => soltar(corpo)));
    })
  );
  render(<OuvidoriaPage />);
}

async function linhaDe(protocolo: string): Promise<HTMLElement> {
  await screen.findByText(protocolo);
  const linhas = document.querySelectorAll<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (linhas.length === 0) throw new Error(`sem linha para o protocolo ${protocolo}`);
  if (linhas.length > 1) throw new Error(`${linhas.length} linhas para o protocolo ${protocolo}`);
  return linhas[0];
}

/**
 * O botão do filtro. É `find`, e não `get`, porque a tela abre carregando: com
 * `get`, o teste que começa com a lista vazia falharia por chegar cedo demais,
 * e não pelo que ele quer afirmar.
 */
function filtro(): Promise<HTMLElement> {
  return screen.findByRole("button", { name: /arquivados/i });
}

/** Espera a tela ter pedido `quantas` listagens que ainda estão presas. */
async function esperarListagens(quantas: number) {
  await waitFor(() => expect(presos.length).toBe(quantas));
}

/** As listagens que a tela pediu, só elas, na ordem. */
function listagens(): string[] {
  return chamadas.filter((c) => c.url.includes("/protocolos")).map((c) => c.url);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  sessao.perfilOuvidoria = "ouvidor";
  vi.unstubAllGlobals();
});

describe("o filtro Arquivados nasce desligado (ADR 0047, decisão 4)", () => {
  it("a primeira carga pede a lista de trabalho, sem o parâmetro do arquivo", async () => {
    montar([caso(7, "encerrado")], [caso(8, "encerrado")]);
    await linhaDe("2026-0007");

    expect(listagens()).toHaveLength(1);
    expect(listagens()[0]).not.toContain("arquivados=sim");
    // A contraprova: o arquivado existe no servidor falso e mesmo assim não
    // está na tela. Sem ela, o teste passaria com uma base vazia.
    expect(screen.queryByText("2026-0008")).toBeNull();
  });

  it("o filtro se anuncia desligado para quem usa leitor de tela", async () => {
    montar([caso(7, "encerrado")]);
    await linhaDe("2026-0007");

    expect((await filtro()).getAttribute("aria-pressed")).toBe("false");
  });

  it("ligar o filtro pede a outra lista e troca o que está na tela", async () => {
    montar([caso(7, "encerrado")], [caso(8, "encerrado")]);
    await linhaDe("2026-0007");

    fireEvent.click(await filtro());

    await linhaDe("2026-0008");
    expect(listagens().at(-1)).toContain("arquivados=sim");
    expect(screen.queryByText("2026-0007")).toBeNull();
    expect((await filtro()).getAttribute("aria-pressed")).toBe("true");
  });

  it("desligar o filtro volta para a lista de trabalho", async () => {
    montar([caso(7, "encerrado")], [caso(8, "encerrado")]);
    await linhaDe("2026-0007");
    fireEvent.click(await filtro());
    await linhaDe("2026-0008");

    fireEvent.click(await filtro());

    await linhaDe("2026-0007");
    expect(listagens().at(-1)).not.toContain("arquivados=sim");
    expect(screen.queryByText("2026-0008")).toBeNull();
  });

  it("quem está fora da Ouvidoria não recebe o filtro", async () => {
    // O arquivo é ato da Ouvidoria, e a lista do arquivo é a outra metade
    // dele. O gate de verdade é o backend; a tela só não oferece o caminho.
    sessao.perfilOuvidoria = null;
    montar([caso(7, "encerrado")]);
    await linhaDe("2026-0007");

    expect(screen.queryByRole("button", { name: /arquivados/i })).toBeNull();
  });
});

describe("Arquivar na linha do caso encerrado", () => {
  it("o caso encerrado oferece Arquivar", async () => {
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Arquivar" })).toBeTruthy();
  });

  it("o caso em andamento não oferece Arquivar", async () => {
    // O irmão do teste acima, no mesmo desenho de linha: o botão existe, e o
    // que muda é só o estado do caso.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).queryByRole("button", { name: "Arquivar" })).toBeNull();
  });

  it("o clique chama a rota de arquivar e recarrega a lista sem o caso", async () => {
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Arquivar" }));

    await waitFor(() => expect(screen.queryByText("2026-0007")).toBeNull());
    expect(chamadas).toContainEqual({
      url: "/api/ouvidoria/manifestacoes/uuid-7/arquivo",
      metodo: "POST",
    });
  });
});

describe("Desarquivar só existe com o filtro ligado", () => {
  it("a linha do arquivo oferece Desarquivar, e não Arquivar", async () => {
    montar([], [caso(8, "encerrado")]);
    fireEvent.click(await filtro());
    const linha = await linhaDe("2026-0008");

    expect(within(linha).getByRole("button", { name: "Desarquivar" })).toBeTruthy();
    expect(within(linha).queryByRole("button", { name: "Arquivar" })).toBeNull();
  });

  it("na lista de trabalho não há Desarquivar em lugar nenhum", async () => {
    montar([caso(7, "encerrado")]);
    await linhaDe("2026-0007");

    expect(screen.queryByRole("button", { name: "Desarquivar" })).toBeNull();
  });

  it("o clique chama a rota de desarquivar e o caso sai da lista do arquivo", async () => {
    montar([], [caso(8, "encerrado")]);
    fireEvent.click(await filtro());
    const linha = await linhaDe("2026-0008");

    fireEvent.click(within(linha).getByRole("button", { name: "Desarquivar" }));

    await waitFor(() => expect(screen.queryByText("2026-0008")).toBeNull());
    expect(chamadas).toContainEqual({
      url: "/api/ouvidoria/manifestacoes/uuid-8/arquivo",
      metodo: "DELETE",
    });
  });
});

describe("a recusa do servidor chega ao ouvidor", () => {
  it("a frase do servidor aparece na tela quando o arquivamento é recusado", async () => {
    // O caso da revogação de perfil com a aba aberta: 403 do servidor. Sem
    // isto, a linha fica idêntica e o ouvidor clica de novo sem saber por quê.
    montar([caso(7, "encerrado")], [], {
      recusaDoArquivo: { status: 403, detail: "Acesso restrito à Ouvidoria" },
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Arquivar" }));

    expect(await screen.findByRole("status")).toHaveProperty(
      "textContent",
      expect.stringContaining("Acesso restrito à Ouvidoria") as unknown as string
    );
  });

  it("o 409 da corrida com a reabertura também é lido na tela", async () => {
    montar([caso(7, "encerrado")], [], {
      recusaDoArquivo: {
        status: 409,
        detail: "O caso mudou de estado agora mesmo: recarregue o painel antes de arquivar.",
      },
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Arquivar" }));

    const aviso = await screen.findByRole("status");
    expect(aviso.textContent).toContain("mudou de estado agora mesmo");
  });

  it("erro sem frase confiável do servidor vira frase da casa, e não vazio", async () => {
    // 500 não é recusa explicada: repassar o `detail` dele poria um
    // "Internal Server Error" na tela do ouvidor.
    montar([caso(7, "encerrado")], [], {
      recusaDoArquivo: { status: 500, detail: "Internal Server Error" },
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Arquivar" }));

    const aviso = await screen.findByRole("status");
    expect(aviso.textContent).toContain("Não foi possível");
    expect(aviso.textContent).not.toContain("Internal Server Error");
  });

  it("sem recusa nenhuma, nada de aviso na tela", async () => {
    // A contraprova dos três acima: o aviso não é decoração permanente.
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Arquivar" }));

    await waitFor(() => expect(screen.queryByText("2026-0007")).toBeNull());
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("o duplo clique não dispara dois arquivamentos", () => {
  it("o segundo clique, com o primeiro ainda em voo, não vira uma segunda chamada", async () => {
    // A resposta de arquivar fica presa: enquanto ela não volta, a chamada
    // segue em voo, e é aí que o segundo clique acontece.
    montar([caso(7, "encerrado")], [], { segurarArquivo: true });
    await linhaDe("2026-0007");
    const posts = () => chamadas.filter((c) => c.metodo === "POST");
    // Reconsultado a cada uso: o rerender troca o nó, e uma referência guardada
    // apontaria para um botão que já saiu da árvore.
    const botao = () => screen.getByRole("button", { name: "Arquivar" });

    fireEvent.click(botao());
    await waitFor(() => expect(posts().length).toBe(1));
    fireEvent.click(botao());

    // A contraprova de que o teste não passou por o botão ter sumido da tela:
    // ele foi encontrado de novo acima, e mesmo assim o POST não se repetiu.
    expect(posts()).toHaveLength(1);
  });
});

describe("a corrida do filtro Arquivados", () => {
  it("a resposta vencida não pinta a lista", async () => {
    // Liga e desliga o filtro depressa: duas listagens ficam no ar. A da lista
    // do arquivo responde POR ÚLTIMO, e mesmo assim não pode pintar nada,
    // porque o ouvidor já voltou para a lista de trabalho.
    montar([caso(7, "encerrado")], [caso(8, "encerrado")], { segurarListagem: true });
    await esperarListagens(1);
    presos[0]!(); // a carga inicial
    await linhaDe("2026-0007");

    fireEvent.click(await filtro()); // liga: pede o arquivo
    await esperarListagens(2);
    fireEvent.click(await filtro()); // desliga: pede a lista de trabalho
    await esperarListagens(3);

    presos[2]!(); // a lista de trabalho responde primeiro
    await waitFor(() => expect(screen.queryByText("2026-0007")).not.toBeNull());
    presos[1]!(); // a do arquivo chega atrasada, e é a resposta abandonada

    await waitFor(() => expect(screen.queryByText("2026-0008")).toBeNull());
    expect(screen.queryByText("2026-0007")).not.toBeNull();
    expect((await filtro()).getAttribute("aria-pressed")).toBe("false");
  });
});

describe("a tipografia e os sinais da casa", () => {
  it("os rótulos do arquivo não trazem seta, chevron nem travessão", async () => {
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");
    const arquivar = within(linha).getByRole("button", { name: "Arquivar" });

    for (const texto of [arquivar.textContent ?? "", (await filtro()).textContent ?? ""]) {
      expect(texto).not.toMatch(/[—–]/);
      expect(texto).not.toMatch(/[→←↑↓»«›‹>]/);
    }
  });

  it("a lista vazia do arquivo diz que o arquivo está vazio, e não que não há caso nenhum", async () => {
    montar([caso(7, "encerrado")], []);
    await linhaDe("2026-0007");

    fireEvent.click(await filtro());

    expect(await screen.findByText(/nenhuma manifestação arquivada/i)).toBeTruthy();
  });
});
