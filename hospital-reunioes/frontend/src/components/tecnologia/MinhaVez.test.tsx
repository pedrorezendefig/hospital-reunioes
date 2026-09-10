/**
 * @vitest-environment jsdom
 */

/**
 * A aba "Minha vez" (issue #641, PRD #634, ADR 0050).
 *
 * O servidor é falso, mas a REGRA fica com ele: quem decide de quem é a vez é
 * o backend, que lê o participante da sessão. O que se prova aqui é o outro
 * lado disso, que é o que a tela pode errar sozinha:
 *
 * - ela pede `/minha-vez` e NÃO manda id de pessoa nenhum (se mandasse, a
 *   lista seria a de quem a tela achasse que é o usuário, e o `useAuth` carrega
 *   o id do Supabase Auth, que não é o `participantes.id`);
 * - ela mostra o que veio, e o porquê de cada card estar ali;
 * - ela não confunde "nada esperando por você" com falha, nem com filtro;
 * - ela sobrevive a duas leituras no ar ao mesmo tempo.
 *
 * Armadilhas de teste vazio evitadas: toda asserção de ausência espera a tela
 * TERMINAR de carregar e tem irmã de presença no mesmo render.
 */

import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MinhaVez } from "./MinhaVez";
import { DemandaDaMinhaVez, EU_DESCONHECIDO, FiltrosDoQuadro, SEM_FILTRO } from "./demandas";

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

function demanda(id: string, titulo: string, extra: Partial<DemandaDaMinhaVez> = {}): DemandaDaMinhaVez {
  return {
    id,
    titulo,
    descricao: null,
    tipo: "decisao",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova",
    responsavel_id: "P2",
    responsavel_nome: "Sócia Vitta",
    autor_id: "P1",
    prioridade: "normal",
    prazo: null,
    criado_em: diasAtras(1),
    concluida_em: null,
    cancelada_em: null,
    motivo: "responsavel",
    ...extra,
  };
}

let urls: string[] = [];

function montar(
  demandas: DemandaDaMinhaVez[],
  opcoes: {
    recusa?: number;
    redeFora?: boolean;
    token?: string | null;
    carregandoAuth?: boolean;
    filtrosIniciais?: FiltrosDoQuadro;
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
      if (opcoes.recusa) {
        return { ok: false, status: opcoes.recusa, json: async () => ({ detail: "não deu" }) } as unknown as Response;
      }
      // Os filtros são do SERVIDOR, como no backend: uma tela que peneirasse
      // por conta própria receberia tudo aqui e mostraria tudo.
      const busca = new URLSearchParams(url.split("?")[1] ?? "");
      const casa = (chave: string, valor: string | null) => !busca.get(chave) || busca.get(chave) === valor;
      const corpo = demandas.filter(
        (d) => casa("tipo", d.tipo) && casa("produto_id", d.produto_id) && casa("responsavel_id", d.responsavel_id),
      );
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );

  /** O dono do estado dos filtros, no lugar do módulo (issue #639). */
  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(opcoes.filtrosIniciais ?? SEM_FILTRO);
    return (
      <MinhaVez
        token={opcoes.token === undefined ? "token-de-teste" : opcoes.token}
        carregandoAuth={opcoes.carregandoAuth ?? false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
        eu={EU_DESCONHECIDO}
      />
    );
  }

  render(<Anfitriao />);
}

/** Espera a tela sair do "Carregando", que é a condição de toda ausência. */
async function esperarCarregar() {
  await waitFor(() => expect(screen.queryByText("Carregando o que espera por você...")).toBeNull());
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

describe("A lista", () => {
  it("mostra o que o servidor devolveu, na ordem em que ele devolveu", async () => {
    // A ordem (prioridade e depois idade) é do backend, e tem teste lá. Aqui o
    // que se prova é que a tela NÃO reordena: se ela ordenasse por conta
    // própria, a regra passaria a existir em dois lugares.
    montar([
      demanda("d1", "Decidir o encerramento", { prioridade: "alta" }),
      demanda("d2", "Conferir os POPs", { prioridade: "baixa" }),
    ]);

    await screen.findByText("Decidir o encerramento");
    const titulos = within(screen.getByRole("list", { name: "Demandas esperando por você" }))
      .getAllByRole("button")
      .map((b) => b.textContent);

    expect(titulos).toEqual(["Decidir o encerramento", "Conferir os POPs"]);
  });

  it("cada linha mostra Produto, responsável, prioridade e idade", async () => {
    montar([
      demanda("d1", "Decidir o encerramento", {
        produto_nome: "POPs",
        responsavel_nome: "Pedro Vitta",
        prioridade: "alta",
        criado_em: diasAtras(3),
      }),
    ]);

    const linha = (await screen.findByText("Decidir o encerramento")).closest("li")!;

    expect(within(linha).getByText("POPs")).toBeTruthy();
    expect(within(linha).getByText("Pedro Vitta")).toBeTruthy();
    expect(within(linha).getByText("Alta")).toBeTruthy();
    expect(within(linha).getByText("há 3 dias")).toBeTruthy();
  });

  it("pede /minha-vez e não manda id de pessoa nenhum", async () => {
    // O critério da aba. A tela não sabe qual participante é o usuário logado
    // (o `useAuth` carrega o id do Supabase Auth, não o `participantes.id`), e
    // por isso ela NÃO pode ser quem diz de quem é a vez.
    montar([demanda("d1", "Decidir o encerramento")]);

    await screen.findByText("Decidir o encerramento");

    expect(urls[0]).toContain("/admin/tecnologia/minha-vez");
    expect(urls[0]).not.toContain("P1");
    expect(urls[0]).not.toContain("P2");
    expect(urls[0]).not.toContain("responsavel_id");
  });

  it("diz por que cada card está na aba", async () => {
    // Sem esta marca, o card de uma Demanda cujo responsável é OUTRA pessoa
    // não explicaria por que está aqui. As duas no mesmo render: uma tela que
    // escrevesse sempre o mesmo rótulo passaria com uma só.
    montar([
      demanda("d1", "Sou eu", { motivo: "responsavel" }),
      demanda("d2", "Me chamaram", { motivo: "mencao", responsavel_nome: "Pedro Vitta" }),
    ]);

    await screen.findByText("Sou eu");

    expect(within(screen.getByText("Sou eu").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
    expect(within(screen.getByText("Me chamaram").closest("li")!).getByText("Mencionaram você")).toBeTruthy();
  });

  it("mostra o recado da entrega no card que voltou para quem pediu", async () => {
    // Issue #679: a Entrega devolve o card e o selo diz o que fazer com ele. O
    // card comum entra no mesmo render: uma tela que escrevesse o recado em
    // todo card passaria com um só.
    montar([
      demanda("d1", "Entregue para conferir", { motivo: "entregue", estado: "aguardando" }),
      demanda("d2", "Ainda comigo", { motivo: "responsavel" }),
    ]);

    await screen.findByText("Entregue para conferir");

    expect(
      within(screen.getByText("Entregue para conferir").closest("li")!).getByText("Entregue, confira e conclua"),
    ).toBeTruthy();
    expect(within(screen.getByText("Ainda comigo").closest("li")!).getByText("Você é o responsável")).toBeTruthy();
  });

  it("abre o modal da Demanda ao clicar na linha", async () => {
    montar([demanda("d1", "Decidir o encerramento")]);

    fireEvent.click(await screen.findByText("Decidir o encerramento"));

    expect(await screen.findByRole("dialog")).toBeTruthy();
  });
});

describe("A lista vazia", () => {
  it("sem filtro, diz que não há nada esperando, e não que falhou", async () => {
    montar([]);
    await esperarCarregar();

    expect(screen.getByText(/Nada esperando por você agora/)).toBeTruthy();
    // A ausência que importa: vazio aqui é boa notícia, e não pode desenhar o
    // alerta vermelho. A espera acima é o que dá valor a esta linha.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("com filtro, diz que há filtro e onde limpar", async () => {
    montar([], { filtrosIniciais: { tipo: "defeito", produto_id: "", responsavel_id: "" } });
    await esperarCarregar();

    expect(screen.getByText(/limpe os filtros acima/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Limpar filtros" })).toBeTruthy();
  });

  it("limpar os filtros refaz a leitura sem filtro nenhum", async () => {
    montar([demanda("d1", "Decidir o encerramento", { tipo: "decisao" })], {
      filtrosIniciais: { tipo: "defeito", produto_id: "", responsavel_id: "" },
    });
    await esperarCarregar();
    expect(screen.queryByText("Decidir o encerramento")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));

    // A irmã de presença da ausência acima: a Demanda estava escondida pelo
    // filtro, e não faltando na resposta.
    expect(await screen.findByText("Decidir o encerramento")).toBeTruthy();
    expect(urls[urls.length - 1]).not.toContain("tipo=");
  });
});

describe("Os filtros herdados das outras abas", () => {
  it("o filtro que veio por prop entra na chamada", async () => {
    montar([demanda("d1", "Decidir o encerramento")], {
      filtrosIniciais: { tipo: "decisao", produto_id: "prod-1", responsavel_id: "P2" },
    });

    await screen.findByText("Decidir o encerramento");

    expect(urls[0]).toContain("tipo=decisao");
    expect(urls[0]).toContain("produto_id=prod-1");
    expect(urls[0]).toContain("responsavel_id=P2");
  });

  it("trocar o filtro aqui refaz a leitura", async () => {
    montar([
      demanda("d1", "Decidir o encerramento", { tipo: "decisao" }),
      demanda("d2", "Consertar o POP", { tipo: "defeito", produto_id: "prod-2" }),
    ]);
    await screen.findByText("Decidir o encerramento");

    fireEvent.click(screen.getByRole("combobox", { name: "Filtrar por tipo" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Defeito"));

    expect(await screen.findByText("Consertar o POP")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Decidir o encerramento")).toBeNull());
  });
});

describe("Quando não dá para ler", () => {
  it("a autenticação carregando NÃO é sessão ausente", async () => {
    // O `useAuth` nasce com `{ token: null, loading: true }`. Ler esse token
    // nulo como "não há sessão" pisca o alerta vermelho em toda abertura da
    // aba, com a sessão perfeitamente válida (foi must-fix na fatia #637).
    montar([], { token: null, carregandoAuth: true });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(screen.queryByRole("alert")).toBeNull();
    // A irmã de presença: a tela diz o que está de fato acontecendo.
    expect(screen.getByText("Carregando o que espera por você...")).toBeTruthy();
  });

  it("resolvida a autenticação, token nulo vira aviso", async () => {
    // O par do teste acima: sem ele, uma tela que engolisse TODO token nulo
    // passaria naquele.
    montar([], { token: null, carregandoAuth: false });

    expect((await screen.findByRole("alert")).textContent).toContain("a sessão não está ativa");
    expect(screen.queryByText("Carregando o que espera por você...")).toBeNull();
  });

  it("a rede fora vira aviso, e não lista vazia", async () => {
    montar([], { redeFora: true });

    expect((await screen.findByRole("alert")).textContent).toContain("Verifique a conexão");
    // O que não pode acontecer: a frase de boa notícia por cima de uma falha.
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
  });

  it("o erro do servidor vira aviso, e não lista vazia", async () => {
    montar([], { recusa: 500 });

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Não foi possível carregar o que espera por você.",
    );
    expect(screen.queryByText(/Nada esperando por você/)).toBeNull();
  });
});

describe("Duas leituras no ar ao mesmo tempo", () => {
  type Pendente = {
    url: string;
    responder: (dados: DemandaDaMinhaVez[]) => void;
    recusar: (status: number) => void;
  };

  /**
   * O `fetch` que NÃO responde sozinho.
   *
   * O servidor falso dos outros testes responde na hora, e por isso não sabe
   * dizer nada sobre ordem de chegada. Aqui cada chamada fica pendurada até o
   * teste mandar responder, que é o único jeito de escrever a ordem em que as
   * respostas voltam, que é onde a corrida mora.
   */
  function filaDeChamadas(): Pendente[] {
    const pendentes: Pendente[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise((resolve) => {
            pendentes.push({
              url,
              responder: (dados) =>
                resolve({ ok: true, status: 200, json: async () => dados } as unknown as Response),
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
    entregarCorpo: (dados: DemandaDaMinhaVez[]) => void;
  };

  /**
   * O `fetch` cujo corpo só resolve quando o teste manda.
   *
   * A fila de cima entrega resposta e corpo de uma vez, e por isso não sabe
   * dizer nada sobre o que acontece ENTRE os dois. É nessa fresta que mora a
   * corrida que a segunda conferência do selo fecha.
   */
  function filaDeCorposLentos(): PendenteComCorpo[] {
    const pendentes: PendenteComCorpo[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise((resolverResposta) => {
            let entregar: (dados: DemandaDaMinhaVez[]) => void = () => {};
            const corpo = new Promise<DemandaDaMinhaVez[]>((r) => {
              entregar = r;
            });
            pendentes.push({
              url,
              responder: () =>
                resolverResposta({ ok: true, status: 200, json: () => corpo } as unknown as Response),
              entregarCorpo: (dados) => entregar(dados),
            });
          }),
      ),
    );
    return pendentes;
  }

  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <MinhaVez
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
        eu={EU_DESCONHECIDO}
      />
    );
  }

  const DECISAO = demanda("d1", "Decidir o encerramento", { tipo: "decisao" });
  const DEFEITO = demanda("d2", "Consertar o POP", { tipo: "defeito" });

  function escolherTipo(rotulo: string) {
    fireEvent.click(screen.getByRole("combobox", { name: "Filtrar por tipo" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText(rotulo));
  }

  /** Deixa o React processar a resposta recém entregue, sem depender de sorte. */
  async function deixarOReactProcessar() {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
  }

  /** `[0]` é a leitura inicial, `[1]` o filtro Decisão (VELHO), `[2]` o Defeito (NOVO). */
  async function comDoisPedidosNoAr(): Promise<Pendente[]> {
    const pendentes = filaDeChamadas();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder([DECISAO, DEFEITO]);
    await screen.findByText("Decidir o encerramento");

    escolherTipo("Decisão");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    escolherTipo("Defeito");
    await waitFor(() => expect(pendentes).toHaveLength(3));

    expect(pendentes[1].url).toContain("tipo=decisao");
    expect(pendentes[2].url).toContain("tipo=defeito");
    return pendentes;
  }

  it("a resposta atrasada do filtro antigo não repinta a lista do filtro novo", async () => {
    const pendentes = await comDoisPedidosNoAr();

    pendentes[2].responder([DEFEITO]);
    await screen.findByText("Consertar o POP");
    pendentes[1].responder([DECISAO]);
    await deixarOReactProcessar();

    expect(screen.getByText("Consertar o POP")).toBeTruthy();
    expect(screen.queryByText("Decidir o encerramento")).toBeNull();
  });

  it("a falha do pedido antigo não apaga a lista certa do pedido novo", async () => {
    // Desde que a leitura que falha passou a LIMPAR a lista, uma recusa velha
    // que escapasse do selo faria pior do que escrever um aviso: apagaria o
    // resultado do filtro que a pessoa está vendo. É a guarda conferida logo na
    // chegada da resposta, antes do corpo, que segura este caso.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[2].responder([DEFEITO]);
    await screen.findByText("Consertar o POP");
    pendentes[1].recusar(500);
    await deixarOReactProcessar();

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Consertar o POP")).toBeTruthy();
  });

  it("a falha do pedido mais NOVO, essa sim, vira aviso e leva a lista", async () => {
    // O par de presença do teste acima: sem ele, uma tela que engolisse TODA
    // falha de leitura passaria naquele.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[1].responder([DECISAO]);
    pendentes[2].recusar(500);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Não foi possível carregar o que espera por você.",
    );
    expect(screen.queryByText("Decidir o encerramento")).toBeNull();
  });

  it("o CORPO atrasado do pedido antigo não repinta a lista", async () => {
    // A resposta e o corpo dela chegam em dois tempos, e é entre os dois que
    // mora esta corrida. A ORDEM dos eventos aqui é o teste inteiro:
    //
    // 1. os cabeçalhos do primeiro pedido chegam enquanto ele AINDA É O
    //    ÚLTIMO. Ele passa pela primeira conferência do selo, a da chegada, e
    //    fica pendurado no `json()`;
    // 2. só ENTÃO nasce o segundo pedido, que chega inteiro e pinta a tela;
    // 3. e só depois o corpo do primeiro resolve.
    //
    // Se o segundo pedido nascesse antes do passo 1 (que é o que acontece
    // quando se troca o filtro duas vezes seguidas), o primeiro pararia logo na
    // conferência da chegada, o `json()` dele nunca seria chamado e a segunda
    // conferência não rodaria: o teste passaria provando a PRIMEIRA guarda duas
    // vezes e a segunda nenhuma. Foi assim que este teste nasceu, em vácuo, e
    // foi assim que o gate final o pegou.
    //
    // Não é hipótese remota nesta aba: o Histórico não pagina e a busca varre a
    // Conversa, então os corpos têm tamanhos bem diferentes e o corpo grande de
    // um pedido velho chega depois da resposta inteira de um pedido novo.
    const pendentes = filaDeCorposLentos();
    render(<Anfitriao />);

    await waitFor(() => expect(pendentes).toHaveLength(1));
    pendentes[0].responder();
    await deixarOReactProcessar();

    escolherTipo("Defeito");
    await waitFor(() => expect(pendentes).toHaveLength(2));
    pendentes[1].responder();
    pendentes[1].entregarCorpo([DEFEITO]);
    expect(await screen.findByText("Consertar o POP")).toBeTruthy();

    pendentes[0].entregarCorpo([DECISAO, DEFEITO]);
    await deixarOReactProcessar();

    // A irmã de presença no mesmo render: a lista certa continua desenhada, e
    // é por isso que a ausência abaixo quer dizer "o corpo velho não entrou", e
    // não "a tela está vazia".
    expect(screen.getByText("Consertar o POP")).toBeTruthy();
    expect(screen.queryByText("Decidir o encerramento")).toBeNull();
  });

  it("a resposta do filtro antigo que chega PRIMEIRO não desliga a espera", async () => {
    // A ordem inversa da anterior, e é ela que exercita a guarda da espera. Sem
    // a guarda, a tela diz "pronto" e mostra a lista de ANTES do filtro, com o
    // campo escrito com o filtro novo, enquanto a leitura de verdade ainda vem.
    const pendentes = await comDoisPedidosNoAr();

    pendentes[1].responder([DECISAO]);
    await deixarOReactProcessar();

    expect(screen.getByText("Carregando o que espera por você...")).toBeTruthy();
    expect(screen.queryByText("Decidir o encerramento")).toBeNull();

    // A irmã de presença: quando o pedido NOVO chega, a espera acaba e a linha
    // certa aparece, então "ainda carregando" acima não é uma tela travada.
    pendentes[2].responder([DEFEITO]);
    expect(await screen.findByText("Consertar o POP")).toBeTruthy();
    expect(screen.queryByText("Carregando o que espera por você...")).toBeNull();
  });
});
