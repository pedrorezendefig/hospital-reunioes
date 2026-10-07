/**
 * @vitest-environment jsdom
 */

/**
 * O Painel da aba Tecnologia (issue #1059, PRD #1056), no lugar de "Minha vez"
 * e do Histórico (issue #641).
 *
 * O servidor é falso, mas as REGRAS ficam com ele: quem decide de quem é a vez,
 * o que entra nas Entregas, os quatro números e a busca de verdade é o backend,
 * com teste lá. O que se prova aqui é o que a tela pode errar sozinha:
 *
 * - ela pede `/painel` e NÃO manda id de pessoa nenhum;
 * - ela mostra os quatro números e os três blocos com o que veio, cada linha
 *   com o que a issue pede, e o vazio de cada bloco com a frase dele;
 * - os blocos recolhem, e clicar numa linha abre o card;
 * - o termo digitado vira `busca` na URL, depois que a digitação para;
 * - a falha não vira bloco vazio, e duas leituras no ar não pintam a errada.
 *
 * Os blocos são achados pelo USO (a região com o nome do bloco, a lista dentro
 * dela, a frase dentro dela), e não pelo nome do componente: um teste que
 * procurasse a frase de vazio na tela inteira passaria com ela desenhada no
 * bloco errado.
 *
 * Toda asserção de ausência espera a tela terminar de carregar e tem irmã de
 * presença no mesmo render.
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PainelDemandas } from "./PainelDemandas";
import {
  DemandaComVoce,
  DemandaDaEntrega,
  DemandaDoHistorico,
  EU_DESCONHECIDO,
  NumerosDoPainel,
  PainelDaAba,
} from "./demandas";

const PRODUTOS = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
];

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

/** Quantos dias atrás, em texto ISO com hora, como o backend devolve. */
function diasAtras(dias: number): string {
  return new Date(Date.now() - dias * 86_400_000).toISOString();
}

const BASE_DA_DEMANDA = {
  descricao: null,
  tipo: "decisao" as const,
  produto_id: "prod-1",
  produto_nome: "Ana",
  responsavel_id: "P2",
  responsavel_nome: "Sócia Vitta",
  autor_id: "P1",
  prioridade: "normal" as const,
  prazo: null,
  concluida_em: null,
  cancelada_em: null,
};

function comVoce(id: string, titulo: string, extra: Partial<DemandaComVoce> = {}): DemandaComVoce {
  return {
    ...BASE_DA_DEMANDA,
    id,
    titulo,
    estado: "nova",
    criado_em: diasAtras(1),
    motivo: "responsavel",
    ...extra,
  };
}

function entrega(id: string, titulo: string, extra: Partial<DemandaDaEntrega> = {}): DemandaDaEntrega {
  return {
    ...BASE_DA_DEMANDA,
    id,
    titulo,
    estado: "em_andamento",
    criado_em: diasAtras(10),
    etapa: "em_desenvolvimento",
    versao: null,
    ...extra,
  };
}

function fechada(id: string, titulo: string, extra: Partial<DemandaDoHistorico> = {}): DemandaDoHistorico {
  return {
    ...BASE_DA_DEMANDA,
    id,
    titulo,
    estado: "concluida",
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    criado_em: "2026-09-01T09:00:00Z",
    concluida_em: "2026-09-08T15:00:00Z",
    fechada_em: "2026-09-08T15:00:00Z",
    fechada_por_id: "P2",
    fechada_por_nome: "Sócia Vitta",
    ...extra,
  };
}

const ZERO: NumerosDoPainel = { abertas: 0, com_o_hospital: 0, em_desenvolvimento: 0, entregues_30_dias: 0 };

function painel(parcial: Partial<PainelDaAba> = {}): PainelDaAba {
  return { numeros: ZERO, com_voce: [], entregas: [], historico: [], ...parcial };
}

let urls: string[] = [];

function montar(
  dados: PainelDaAba,
  opcoes: {
    recusa?: number;
    // O servidor recusa SÓ quando há termo de busca. É o cenário em que o
    // Painel de antes está na tela e a leitura nova falha.
    recusaNaBusca?: number;
    redeFora?: boolean;
    // A rede CAI só na busca: o `fetch` rejeita, em vez de responder com
    // status de erro. É outro caminho no hook (o `catch`), e o desfecho na
    // tela tem que ser o mesmo.
    redeForaNaBusca?: boolean;
    token?: string | null;
    carregandoAuth?: boolean;
  } = {},
) {
  urls = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      if (opcoes.redeFora) throw new TypeError("Failed to fetch");
      if (url.includes("/conversa")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }
      if (opcoes.redeForaNaBusca && url.includes("busca=")) throw new TypeError("Failed to fetch");
      if (opcoes.recusaNaBusca && url.includes("busca=")) {
        return {
          ok: false,
          status: opcoes.recusaNaBusca,
          json: async () => ({ detail: "não deu" }),
        } as unknown as Response;
      }
      if (opcoes.recusa) {
        return { ok: false, status: opcoes.recusa, json: async () => ({ detail: "não deu" }) } as unknown as Response;
      }
      // Quem busca é o SERVIDOR: uma tela que peneirasse por conta própria
      // receberia tudo aqui e mostraria tudo.
      const termo = (new URLSearchParams(url.split("?")[1] ?? "").get("busca") ?? "").toLowerCase();
      const corpo = {
        ...dados,
        historico: dados.historico.filter((d) => !termo || d.titulo.toLowerCase().includes(termo)),
      };
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  render(
    <PainelDemandas
      token={opcoes.token === undefined ? "token-de-teste" : opcoes.token}
      carregandoAuth={opcoes.carregandoAuth ?? false}
      produtos={PRODUTOS}
      pessoas={PESSOAS}
      eu={EU_DESCONHECIDO}
    />,
  );
}

/** O bloco pelo nome que a pessoa lê no cabeçalho dele. */
const bloco = (nome: string) => screen.getByRole("region", { name: nome });

async function esperarCarregar() {
  await waitFor(() => expect(screen.queryByText("Carregando o Histórico...")).toBeNull());
}

function digitarNaBusca(termo: string) {
  fireEvent.change(screen.getByLabelText("Buscar no Histórico"), { target: { value: termo } });
}

beforeEach(() => {
  urls = [];
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ─── Os números e os blocos ──────────────────────────────────────────────────

describe("Os quatro números", () => {
  it("cada número aparece ao lado do rótulo dele", async () => {
    // Quatro valores diferentes: uma faixa que trocasse dois de lugar passaria
    // com valores repetidos.
    montar(painel({ numeros: { abertas: 7, com_o_hospital: 2, em_desenvolvimento: 3, entregues_30_dias: 4 } }));

    const faixa = await screen.findByRole("list", { name: "Números do Painel" });
    const numeros = within(faixa)
      .getAllByRole("listitem")
      .map((li) => li.textContent);

    expect(numeros).toEqual(["7Abertas", "2Com o hospital", "3Em desenvolvimento", "4Entregues em 30 dias"]);
  });

  it("nenhum número é por pessoa: a faixa tem só os quatro, e o Com você não tem contador", async () => {
    montar(painel({ com_voce: [comVoce("d1", "Decidir o encerramento")] }));

    const faixa = await screen.findByRole("list", { name: "Números do Painel" });
    expect(within(faixa).getAllByRole("listitem")).toHaveLength(4);
    // O cabeçalho do bloco diz só o nome dele, sem "(1)": a contagem do que é
    // de uma pessoa seria um número por pessoa. A irmã de presença é a linha
    // que está no bloco.
    expect(within(bloco("Com você")).getByRole("button", { name: "Com você" })).toBeTruthy();
    expect(within(bloco("Com você")).getByText("Decidir o encerramento")).toBeTruthy();
  });
});

describe("Os três blocos", () => {
  it("cada Demanda aparece no bloco que o servidor disse", async () => {
    montar(
      painel({
        com_voce: [comVoce("d1", "Decidir o encerramento")],
        entregas: [entrega("d2", "Integração com o MV")],
        historico: [fechada("d3", "Trocar o logotipo")],
      }),
    );

    await screen.findByText("Decidir o encerramento");

    const lista = (nomeDoBloco: string) =>
      within(bloco(nomeDoBloco))
        .getAllByRole("listitem")
        .map((li) => within(li).getAllByRole("button")[0].textContent);

    expect(lista("Com você")).toEqual(["Decidir o encerramento"]);
    expect(lista("Entregas")).toEqual(["Integração com o MV"]);
    expect(lista("Histórico")).toEqual(["Trocar o logotipo"]);
  });

  it("o Com você vazio diz que não há nada esperando, dentro do próprio bloco", async () => {
    // A frase está no bloco CERTO, e os outros dois mostram o que têm: uma tela
    // que desenhasse a frase no topo, ou em todos os blocos, falharia aqui.
    montar(painel({ entregas: [entrega("d2", "Integração com o MV")], historico: [fechada("d3", "Trocar o logotipo")] }));
    await esperarCarregar();

    expect(within(bloco("Com você")).getByText(/Nada esperando por você/)).toBeTruthy();
    expect(within(bloco("Entregas")).queryByText(/Nada esperando por você/)).toBeNull();
    expect(within(bloco("Entregas")).getByText("Integração com o MV")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("as Entregas vazias dizem que não há nada em desenvolvimento", async () => {
    montar(painel({ com_voce: [comVoce("d1", "Decidir o encerramento")] }));
    await esperarCarregar();

    expect(within(bloco("Entregas")).getByText(/Nenhuma Demanda aberta está com a Vitta em desenvolvimento/)).toBeTruthy();
    expect(within(bloco("Com você")).getByText("Decidir o encerramento")).toBeTruthy();
  });

  it.each(["Com você", "Entregas", "Histórico"])("o bloco %s recolhe e volta a abrir", async (nome) => {
    montar(
      painel({
        com_voce: [comVoce("d1", "Decidir o encerramento")],
        entregas: [entrega("d2", "Integração com o MV")],
        historico: [fechada("d3", "Trocar o logotipo")],
      }),
    );
    await screen.findByText("Decidir o encerramento");
    const titulos = { "Com você": "Decidir o encerramento", Entregas: "Integração com o MV", Histórico: "Trocar o logotipo" };
    const cabecalho = within(bloco(nome)).getByRole("button", { name: nome });

    expect(cabecalho.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(cabecalho);

    expect(cabecalho.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(titulos[nome as keyof typeof titulos])).toBeNull();
    // A irmã de presença: os outros dois blocos continuam abertos.
    for (const [outro, titulo] of Object.entries(titulos)) {
      if (outro !== nome) expect(screen.getByText(titulo)).toBeTruthy();
    }

    fireEvent.click(cabecalho);
    expect(screen.getByText(titulos[nome as keyof typeof titulos])).toBeTruthy();
  });

  it.each([
    ["Com você", "Decidir o encerramento"],
    ["Entregas", "Integração com o MV"],
    ["Histórico", "Trocar o logotipo"],
  ])("clicar numa linha de %s abre o card da Demanda", async (nome, titulo) => {
    montar(
      painel({
        com_voce: [comVoce("d1", "Decidir o encerramento")],
        entregas: [entrega("d2", "Integração com o MV")],
        historico: [fechada("d3", "Trocar o logotipo")],
      }),
    );
    await screen.findByText(titulo);
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(within(bloco(nome)).getByText(titulo));

    const card = await screen.findByRole("dialog");
    // O card aberto é o da linha clicada, e não um qualquer.
    expect(within(card).getAllByText(titulo).length).toBeGreaterThan(0);
  });
});

// ─── Com você (os casos de "Minha vez") ──────────────────────────────────────

describe("Com você", () => {
  it("mostra o que o servidor devolveu, na ordem em que ele devolveu", async () => {
    // A ordem (prioridade e depois idade) é do backend, e tem teste lá. Aqui o
    // que se prova é que a tela NÃO reordena.
    montar(
      painel({
        com_voce: [
          comVoce("d1", "Decidir o encerramento", { prioridade: "alta" }),
          comVoce("d2", "Conferir os POPs", { prioridade: "baixa" }),
        ],
      }),
    );

    await screen.findByText("Decidir o encerramento");
    const titulos = within(screen.getByRole("list", { name: "Demandas esperando por você" }))
      .getAllByRole("button")
      .map((b) => b.textContent);

    expect(titulos).toEqual(["Decidir o encerramento", "Conferir os POPs"]);
  });

  it("cada linha mostra Produto, responsável, prioridade e idade", async () => {
    montar(
      painel({
        com_voce: [
          comVoce("d1", "Decidir o encerramento", {
            produto_nome: "POPs",
            responsavel_nome: "Pedro Vitta",
            prioridade: "alta",
            criado_em: diasAtras(3),
          }),
        ],
      }),
    );

    const linha = (await screen.findByText("Decidir o encerramento")).closest("li")!;

    expect(within(linha).getByText("POPs")).toBeTruthy();
    expect(within(linha).getByText("Pedro Vitta")).toBeTruthy();
    expect(within(linha).getByText("Alta")).toBeTruthy();
    expect(within(linha).getByText("há 3 dias")).toBeTruthy();
  });

  it("pede /painel e não manda id de pessoa nenhum", async () => {
    // A tela não sabe qual participante é o usuário logado (o `useAuth` carrega
    // o id do Supabase Auth, não o `participantes.id`), e por isso ela NÃO pode
    // ser quem diz de quem é a vez.
    montar(painel({ com_voce: [comVoce("d1", "Decidir o encerramento")] }));

    await screen.findByText("Decidir o encerramento");

    expect(urls[0]).toContain("/admin/tecnologia/painel");
    expect(urls[0]).not.toContain("P1");
    expect(urls[0]).not.toContain("P2");
    expect(urls[0]).not.toContain("responsavel_id");
  });

  it("diz por que cada card está no bloco", async () => {
    montar(
      painel({
        com_voce: [
          comVoce("d1", "Sou eu", { motivo: "responsavel" }),
          comVoce("d2", "Me chamaram", { motivo: "mencao", responsavel_nome: "Pedro Vitta" }),
        ],
      }),
    );

    await screen.findByText("Sou eu");

    expect(within(screen.getByText("Sou eu").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
    expect(within(screen.getByText("Me chamaram").closest("li")!).getByText("Mencionaram você")).toBeTruthy();
  });

  it("mostra o recado da entrega no card que voltou para quem pediu", async () => {
    montar(
      painel({
        com_voce: [
          comVoce("d1", "Entregue para conferir", { motivo: "entregue", estado: "aguardando" }),
          comVoce("d2", "Ainda comigo", { motivo: "responsavel" }),
        ],
      }),
    );

    await screen.findByText("Entregue para conferir");

    expect(
      within(screen.getByText("Entregue para conferir").closest("li")!).getByText("Entregue, confira e conclua"),
    ).toBeTruthy();
    expect(within(screen.getByText("Ainda comigo").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
  });
});

// ─── Entregas ────────────────────────────────────────────────────────────────

describe("Entregas", () => {
  it("cada linha mostra a Etapa e as partes", async () => {
    montar(painel({ entregas: [entrega("d1", "Integração com o MV", { partes_entregues: 1, partes_total: 3 })] }));

    const linha = (await screen.findByText("Integração com o MV")).closest("li")!;

    expect(within(linha).getByText("Em desenvolvimento · 1 de 3 partes")).toBeTruthy();
  });

  it("a versão aparece quando veio, e só nela", async () => {
    // A regra de quando a versão vem é do backend (só em Em produção); a tela
    // mostra o que veio. As duas linhas no mesmo render: uma tela que
    // escrevesse a versão em toda linha passaria com uma só.
    montar(
      painel({
        entregas: [
          entrega("d1", "Já no ar", { etapa: "em_producao", versao: "v0.165.0" }),
          entrega("d2", "Ainda em obra", { etapa: "em_desenvolvimento", versao: null }),
        ],
      }),
    );

    const noAr = (await screen.findByText("Já no ar")).closest("li")!;
    expect(within(noAr).getByText("Em produção")).toBeTruthy();
    expect(within(noAr).getByText(/v0\.165\.0/)).toBeTruthy();

    const emObra = screen.getByText("Ainda em obra").closest("li")!;
    expect(within(emObra).queryByText(/versão/)).toBeNull();
    expect(within(emObra).getByText("Em desenvolvimento")).toBeTruthy();
  });
});

// ─── Histórico ───────────────────────────────────────────────────────────────

describe("Histórico", () => {
  it("mostra o que o servidor devolveu, com o contador", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas"), fechada("d2", "Trocar o logotipo")] }));

    await screen.findByText("Encerrar conversas");

    expect(within(bloco("Histórico")).getByText("2 Demandas fechadas")).toBeTruthy();
    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
  });

  it("cada linha diz quando e por quem a Demanda fechou", async () => {
    montar(
      painel({
        historico: [
          fechada("d1", "Encerrar conversas", { fechada_por_nome: "Sócia Vitta" }),
          fechada("d2", "Trocar o logotipo", {
            estado: "cancelada",
            fechada_em: "2026-09-07T10:00:00Z",
            fechada_por_nome: "Pedro Vitta",
          }),
        ],
      }),
    );

    await screen.findByText("Encerrar conversas");

    const concluida = within(screen.getByText("Encerrar conversas").closest("li")!);
    expect(concluida.getByText(/Concluída/)).toBeTruthy();
    expect(concluida.getByText(/por Sócia Vitta/)).toBeTruthy();

    const cancelada = within(screen.getByText("Trocar o logotipo").closest("li")!);
    expect(cancelada.getByText(/Cancelada/)).toBeTruthy();
    expect(cancelada.getByText(/por Pedro Vitta/)).toBeTruthy();
  });

  it("sem o carimbo de quem fechou, a linha diz que não há registro", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas", { fechada_por_nome: null })] }));

    const linha = within((await screen.findByText("Encerrar conversas")).closest("li")!);

    expect(linha.getByText(/sem registro de quem/)).toBeTruthy();
  });

  it("a caixa diz o que a busca procura", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }));
    await screen.findByText("Encerrar conversas");

    expect(screen.getByPlaceholderText(/título, descrição ou texto da Conversa/)).toBeTruthy();
  });

  it("o termo digitado vira `busca` na chamada", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas"), fechada("d2", "Trocar o logotipo")] }));
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("logotipo");

    await waitFor(() => expect(urls[urls.length - 1]).toContain("/painel?busca=logotipo"));
    expect(await screen.findByText("Trocar o logotipo")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
  });

  it("a busca não esconde os outros blocos", async () => {
    // A busca é do Histórico: o Com você continua desenhado enquanto ela
    // corre e depois que ela volta.
    montar(
      painel({
        com_voce: [comVoce("c1", "Decidir o encerramento")],
        historico: [fechada("d1", "Encerrar conversas"), fechada("d2", "Trocar o logotipo")],
      }),
    );
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("logotipo");

    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    expect(within(bloco("Com você")).getByText("Decidir o encerramento")).toBeTruthy();
  });

  it("termo só de espaços não vira busca", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }));
    await screen.findByText("Encerrar conversas");
    const antes = urls.length;

    digitarNaBusca("   ");

    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    for (const url of urls.slice(antes)) expect(url).not.toContain("busca=");
    expect(screen.getByText("Encerrar conversas")).toBeTruthy();
  });

  it("a busca espera a digitação parar, e não pede uma vez por tecla", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }));
    await screen.findByText("Encerrar conversas");
    const antes = urls.length;

    digitarNaBusca("l");
    digitarNaBusca("lo");
    digitarNaBusca("log");
    digitarNaBusca("logo");

    await waitFor(() => expect(urls.length).toBeGreaterThan(antes));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });

    expect(urls.slice(antes)).toHaveLength(1);
    expect(urls[urls.length - 1]).toContain("busca=logo");
  });

  it("apagar a busca traz o Histórico inteiro de volta", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas"), fechada("d2", "Trocar o logotipo")] }));
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("logotipo");
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    digitarNaBusca("");

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(urls[urls.length - 1]).not.toContain("busca=");
  });

  it("sem busca, o Histórico vazio diz que ainda não fechou nada", async () => {
    montar(painel());
    await esperarCarregar();

    expect(within(bloco("Histórico")).getByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a busca sem resultado cita o termo procurado", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }));
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("ouvidoria");

    expect(await screen.findByText(/"ouvidoria"/)).toBeTruthy();
  });

  it("a frase cita o termo da lista que está na tela, e não o que está sendo digitado", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }));
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("ouvidoria");
    expect(await screen.findByText(/"ouvidoria"/)).toBeTruthy();

    digitarNaBusca("xyz");

    expect(screen.getByText(/"ouvidoria"/)).toBeTruthy();
    expect(screen.queryByText(/"xyz"/)).toBeNull();
    expect(await screen.findByText(/"xyz"/)).toBeTruthy();
  });
});

// ─── Quando não dá para ler ──────────────────────────────────────────────────

describe("Quando não dá para ler", () => {
  it("a autenticação carregando NÃO é sessão ausente", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }`. Ler esse token
    // nulo como "não há sessão" pisca o alerta vermelho em toda abertura da
    // aba, com a sessão perfeitamente válida (foi must-fix na fatia #637).
    montar(painel(), { token: null, carregandoAuth: true });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Carregando o Histórico...")).toBeTruthy();
    // E o Com você não diz "nada esperando" sobre uma leitura que nem começou.
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
  });

  it("resolvida a autenticação, token nulo vira aviso", async () => {
    montar(painel(), { token: null, carregandoAuth: false });

    expect((await screen.findByRole("alert")).textContent).toContain("a sessão não está ativa");
  });

  it("a rede fora vira aviso, e não Painel vazio", async () => {
    montar(painel(), { redeFora: true });

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    // O que não pode acontecer: as frases de boa notícia por cima de uma falha.
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
    expect(screen.queryByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeNull();
    expect(screen.queryByRole("list", { name: "Números do Painel" })).toBeNull();
  });

  it("o erro do servidor vira aviso, e não Painel vazio", async () => {
    montar(painel(), { recusa: 500 });

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar o Painel.");
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
    expect(screen.queryByText(/Nenhuma Demanda foi concluída ou cancelada ainda/)).toBeNull();
  });

  it("a leitura que falha leva o Painel de ANTES junto, com o contador", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }), { recusaNaBusca: 500 });

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(screen.getByText("1 Demanda fechada")).toBeTruthy();

    digitarNaBusca("xyz");

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar o Painel.");
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    expect(screen.queryByText("1 Demanda fechada")).toBeNull();
    expect(screen.queryByText(/Nenhuma Demanda/)).toBeNull();
    // A caixa de busca continua de pé: é por ela que a pessoa sai do erro.
    expect(screen.getByLabelText("Buscar no Histórico")).toBeTruthy();
  });

  it("a REDE fora também leva o Painel de ANTES junto", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }), { redeForaNaBusca: true });

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(screen.getByText("1 Demanda fechada")).toBeTruthy();

    digitarNaBusca("xyz");

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    await waitFor(() => expect(screen.queryByText("Encerrar conversas")).toBeNull());
    expect(screen.queryByText("1 Demanda fechada")).toBeNull();
  });

  it("a leitura seguinte que dá certo apaga o aviso e traz o Painel de volta", async () => {
    montar(painel({ historico: [fechada("d1", "Encerrar conversas")] }), { recusaNaBusca: 500 });
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("xyz");
    await screen.findByRole("alert");

    digitarNaBusca("");

    expect(await screen.findByText("Encerrar conversas")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("1 Demanda fechada")).toBeTruthy();
  });
});

// ─── Duas leituras no ar ao mesmo tempo ──────────────────────────────────────

describe("Duas leituras no ar ao mesmo tempo", () => {
  type Pendente = {
    url: string;
    responder: (dados: DemandaDoHistorico[]) => void;
    recusar: (status: number) => void;
  };

  function filaDeChamadas(): Pendente[] {
    const pendentes: Pendente[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise((resolve) => {
            pendentes.push({
              url,
              responder: (historico) =>
                resolve({
                  ok: true,
                  status: 200,
                  json: async () => painel({ historico }),
                } as unknown as Response),
              recusar: (status) =>
                resolve({ ok: false, status, json: async () => ({ detail: "não deu" }) } as unknown as Response),
            });
          }),
      ),
    );
    return pendentes;
  }

  /** Uma chamada cujos CABEÇALHOS e cujo CORPO chegam em dois tempos. */
  type PendenteComCorpo = {
    url: string;
    /** Resolve o `Response`: daqui em diante o `json()` fica pendurado. */
    responder: () => void;
    /** Resolve o `json()`. */
    entregarCorpo: (dados: DemandaDoHistorico[]) => void;
  };

  function filaDeCorposLentos(): PendenteComCorpo[] {
    const pendentes: PendenteComCorpo[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise((resolverResposta) => {
            let entregar: (dados: PainelDaAba) => void = () => {};
            const corpo = new Promise<PainelDaAba>((r) => {
              entregar = r;
            });
            pendentes.push({
              url,
              responder: () =>
                resolverResposta({ ok: true, status: 200, json: () => corpo } as unknown as Response),
              entregarCorpo: (historico) => entregar(painel({ historico })),
            });
          }),
      ),
    );
    return pendentes;
  }

  function Anfitriao() {
    return (
      <PainelDemandas
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        eu={EU_DESCONHECIDO}
      />
    );
  }

  const ENCERRAR = fechada("d1", "Encerrar conversas");
  const LOGOTIPO = fechada("d2", "Trocar o logotipo");

  async function deixarOReactProcessar() {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  /** `[0]` é a leitura inicial, `[1]` a busca por "encerrar" (VELHA), `[2]` a por "logotipo" (NOVA). */
  async function comDuasBuscasNoAr(): Promise<Pendente[]> {
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder([ENCERRAR, LOGOTIPO]);
    await screen.findByText("Encerrar conversas");

    digitarNaBusca("encerrar");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    digitarNaBusca("logotipo");
    await waitFor(() => expect(pendentes).toHaveLength(3));

    expect(pendentes[1].url).toContain("busca=encerrar");
    expect(pendentes[2].url).toContain("busca=logotipo");
    return pendentes;
  }

  it("a resposta atrasada da busca antiga não repinta a lista da busca nova", async () => {
    const pendentes = await comDuasBuscasNoAr();

    pendentes[2].responder([LOGOTIPO]);
    await screen.findByText("Trocar o logotipo");
    pendentes[1].responder([ENCERRAR]);
    await deixarOReactProcessar();

    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
    expect(screen.queryByText("Encerrar conversas")).toBeNull();
  });

  it("a resposta da busca antiga que chega PRIMEIRO não desliga a espera", async () => {
    const pendentes = await comDuasBuscasNoAr();

    pendentes[1].responder([ENCERRAR]);
    await deixarOReactProcessar();

    expect(screen.getByText("Carregando o Histórico...")).toBeTruthy();
    expect(screen.queryByText("Encerrar conversas")).toBeNull();

    pendentes[2].responder([LOGOTIPO]);
    expect(await screen.findByText("Trocar o logotipo")).toBeTruthy();
    expect(screen.queryByText("Carregando o Histórico...")).toBeNull();
  });

  it("a falha da busca antiga não apaga a lista certa da busca nova", async () => {
    const pendentes = await comDuasBuscasNoAr();

    pendentes[2].responder([LOGOTIPO]);
    await screen.findByText("Trocar o logotipo");
    pendentes[1].recusar(500);
    await deixarOReactProcessar();

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
  });

  it("a falha da busca mais NOVA, essa sim, vira aviso e leva a lista", async () => {
    const pendentes = await comDuasBuscasNoAr();

    pendentes[1].responder([ENCERRAR]);
    pendentes[2].recusar(500);

    expect((await screen.findByRole("alert")).textContent).toContain("Não foi possível carregar o Painel.");
    expect(screen.queryByText("Encerrar conversas")).toBeNull();
  });

  it("o CORPO atrasado da leitura antiga não repinta a lista", async () => {
    // A resposta e o corpo dela chegam em dois tempos, e é entre os dois que
    // mora esta corrida. A ORDEM dos eventos aqui é o teste inteiro: os
    // cabeçalhos do primeiro pedido chegam enquanto ele AINDA É O ÚLTIMO (passa
    // pela primeira conferência do selo e fica pendurado no `json()`); só então
    // nasce o segundo, que chega inteiro; e só depois o corpo do primeiro
    // resolve. Assim é a SEGUNDA conferência do selo que se prova.
    const pendentes = filaDeCorposLentos();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder();
    await deixarOReactProcessar();

    digitarNaBusca("logotipo");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    pendentes[1].responder();
    pendentes[1].entregarCorpo([LOGOTIPO]);
    expect(await screen.findByText("Trocar o logotipo")).toBeTruthy();

    pendentes[0].entregarCorpo([ENCERRAR, LOGOTIPO]);
    await deixarOReactProcessar();

    expect(screen.getByText("Trocar o logotipo")).toBeTruthy();
    expect(screen.queryByText("Encerrar conversas")).toBeNull();
  });
});
