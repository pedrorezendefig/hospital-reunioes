/**
 * @vitest-environment jsdom
 */

/**
 * O Assistente de Tecnologia na tela (issue #727, PRD #726, ADR 0056).
 *
 * O servidor é falso, mas as REGRAS ficam com ele: a tela não decide o Tipo
 * nem escreve o rascunho, ela mostra o que a rota devolveu e manda de volta o
 * que a pessoa editou. As asserções olham duas coisas: o que aparece na tela e
 * o corpo que o clique dispara.
 *
 * Armadilha de teste vazio evitada aqui: "o rascunho volta do armazenamento de
 * sessão" passaria numa tela que nunca grava nada e sempre mostra o mesmo
 * texto; por isso o teste grava um valor ESPECÍFICO e remonta o componente.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssistenteDeTecnologia } from "./AssistenteDeTecnologia";
import {
  AVISO_DE_IA,
  CHAVE_DA_SESSAO,
  CONVERSA_NO_TETO,
  LIMITE_DA_DESCRICAO,
  LIMITE_DA_MENSAGEM,
  LIMITE_DE_MENSAGENS,
  LIMITE_DO_TITULO,
  MensagemDoChat,
  MUITAS_MENSAGENS,
  NAO_INFORMADO,
  RASCUNHO_VAZIO,
  RascunhoDaDemanda,
  RESPOSTA_ILEGIVEL,
  respostaDoChatValida,
  CRIADA_SEM_CONFIRMACAO,
} from "./assistente";
import { Demanda, ProdutoDaEscolha } from "./demandas";

type Chamada = { url: string; metodo: string; corpo: Record<string, unknown> | undefined };

const PRODUTOS: ProdutoDaEscolha[] = [
  { id: "prod-1", nome: "Ana", ativo: true },
  { id: "prod-2", nome: "POPs", ativo: true },
  { id: "prod-3", nome: "Site antigo", ativo: false },
];

const RASCUNHO_DO_ASSISTENTE: RascunhoDaDemanda = {
  titulo: "Ana não responde de madrugada",
  tipo: "defeito",
  produto_id: "prod-1",
  prioridade: "normal",
  prazo: null,
  descricao: "Onde: no WhatsApp",
};

let chamadas: Chamada[] = [];
let criadas: { demanda: Demanda; aviso: string | null }[] = [];

type Opcoes = {
  /** O rascunho que a rota do chat devolve. */
  rascunhoDaResposta?: RascunhoDaDemanda;
  reply?: string;
  /**
   * Segura a resposta do chat: o teste solta quando quiser, e entre o clique e
   * a soltura a tela está com o turno EM VOO, que é onde moram as duas corridas
   * (editar o rascunho e descartar a conversa).
   */
  segurarAResposta?: boolean;
  /**
   * Como o turno segurado termina quando o teste o solta. `"ok"` é o padrão;
   * `"rede"` faz o `fetch` rejeitar (conexão que morreu esperando) e
   * `"ilegivel"` devolve 200 com um corpo que o `json()` não consegue ler
   * (proxy respondendo HTML, conexão que cai depois dos cabeçalhos).
   */
  fimDoTurno?: "ok" | "rede" | "ilegivel";
  /**
   * Um 200 cujo corpo o `JSON.parse` ACEITA mas que não é `{reply, rascunho}`.
   * É o buraco que sobrava quando a fronteira "nunca levanta" valia só para a
   * rede: o corpo passava inteiro e quebrava lá dentro.
   */
  corpoForaDoContrato?: unknown;
  /** A criação responde 201 com um corpo que o `json()` não consegue ler. */
  criacaoIlegivel?: boolean;
  /** A criação responde 201 com um corpo que o `json()` LÊ e que não serve. */
  corpoDaCriacaoForaDoContrato?: unknown;
  /**
   * O corpo CRU da recusa, como cada camada do backend a escreve. Não é um
   * `{detail}` genérico de propósito: o `slowapi` responde `{error: ...}` e o
   * pydantic responde `detail` em LISTA, e um dublê que normalizasse os três
   * provaria um formato que o backend nunca emite.
   */
  recusaDoChat?: { status: number; corpo: unknown };
};

let soltarAResposta: (() => void) | null = null;

function servidor(opcoes: Opcoes) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const corpo = init?.body ? JSON.parse(String(init.body)) : undefined;
    chamadas.push({ url, metodo: init?.method ?? "GET", corpo });
    if (url.endsWith("/assistente/chat") && opcoes.segurarAResposta) {
      await new Promise<void>((resolve) => {
        soltarAResposta = resolve;
      });
    }
    if (url.endsWith("/assistente/chat") && opcoes.fimDoTurno === "rede") {
      throw new Error("rede fora");
    }
    if (url.endsWith("/assistente/chat") && "corpoForaDoContrato" in opcoes) {
      return { ok: true, status: 200, json: async () => opcoes.corpoForaDoContrato } as unknown as Response;
    }
    if (url.endsWith("/assistente/chat") && opcoes.fimDoTurno === "ilegivel") {
      return {
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("Unexpected token < in JSON");
        },
      } as unknown as Response;
    }
    if (url.endsWith("/assistente/chat")) {
      if (opcoes.recusaDoChat) {
        return {
          ok: false,
          status: opcoes.recusaDoChat.status,
          json: async () => opcoes.recusaDoChat!.corpo,
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          reply: opcoes.reply ?? "Entendi. Onde isso aconteceu?",
          rascunho: opcoes.rascunhoDaResposta ?? RASCUNHO_DO_ASSISTENTE,
          demanda_parecida: null,
        }),
      } as unknown as Response;
    }
    if ("corpoDaCriacaoForaDoContrato" in opcoes) {
      return {
        ok: true,
        status: 201,
        json: async () => opcoes.corpoDaCriacaoForaDoContrato,
      } as unknown as Response;
    }
    if (opcoes.criacaoIlegivel) {
      return {
        ok: true,
        status: 201,
        json: async () => {
          throw new SyntaxError("Unexpected token < in JSON");
        },
      } as unknown as Response;
    }
    return {
      ok: true,
      status: 201,
      json: async () => ({ id: "d-nova", aviso_por_email: null }),
    } as unknown as Response;
  });
}

function montar(opcoes: Opcoes = {}) {
  vi.stubGlobal("fetch", servidor(opcoes));
  return render(
    <AssistenteDeTecnologia
      token="tok"
      produtos={PRODUTOS}
      onCriada={(demanda, aviso) => criadas.push({ demanda, aviso })}
    />,
  );
}

function doChat(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/assistente/chat"));
}

function criacoes(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/demandas"));
}

async function falar(texto: string) {
  fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: texto } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(doChat().length).toBeGreaterThan(0));
}

beforeEach(() => {
  chamadas = [];
  criadas = [];
  soltarAResposta = null;
  Element.prototype.scrollIntoView = vi.fn();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("A conversa", () => {
  it("abre com a fala do assistente e com o aviso de que uma IA lê o que for escrito", () => {
    montar();

    expect(screen.getByText(AVISO_DE_IA)).toBeTruthy();
    expect(within(screen.getByRole("log")).getAllByText(/Me conta o que você precisa/)).toHaveLength(1);
  });

  it("a resposta do chat atualiza o rascunho", async () => {
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).value).toBe("Onde: no WhatsApp");
    expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy();
  });

  it("a edição à mão vai no corpo da chamada seguinte", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "título escrito à mão" } });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "é isso" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => expect(doChat()).toHaveLength(2));
    const rascunhoEnviado = doChat()[1].corpo?.rascunho as RascunhoDaDemanda;
    expect(rascunhoEnviado.titulo).toBe("título escrito à mão");
    // O resto do rascunho segue junto, senão a correção do título apagaria o
    // que o assistente já tinha montado.
    expect(rascunhoEnviado.tipo).toBe("defeito");
  });

  it("a conversa inteira vai no corpo, com os papéis certos", async () => {
    montar();

    await falar("a Ana tá estranha");

    const messages = doChat()[0].corpo?.messages as { role: string; content: string }[];
    expect(messages[messages.length - 1]).toEqual({ role: "user", content: "a Ana tá estranha" });
    expect(messages[0].role).toBe("assistant");
  });

  it("o teto de taxa vira frase de gente, e não o inglês do slowapi", async () => {
    // O `slowapi` responde `{"error": "Rate limit exceeded: ..."}`, sem
    // `detail`: passando pelo `motivoDaRecusa`, a pessoa leria "Não foi
    // possível salvar (429)", verbo errado para um chat e sem dizer o que
    // fazer.
    montar({ recusaDoChat: { status: 429, corpo: { error: "Rate limit exceeded: 10 per 1 minute" } } });

    await falar("a Ana tá estranha");

    expect((await screen.findByRole("alert")).textContent).toBe(MUITAS_MENSAGENS);
  });

  it("a recusa que o servidor explica é a dele que a pessoa lê", async () => {
    // O par do teste acima: uma tela que respondesse a MESMA frase a toda
    // recusa passaria naquele sozinha.
    montar({ recusaDoChat: { status: 422, corpo: { detail: "O rascunho chegou sem nada dentro." } } });

    await falar("a Ana tá estranha");

    expect((await screen.findByRole("alert")).textContent).toContain("sem nada dentro");
  });

  it("sem recusa, nenhum aviso vermelho aparece", async () => {
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("O turno em voo", () => {
  /** Manda uma fala e PARA com a resposta pendurada, sem esperar o fim. */
  async function falarESegurar(texto: string) {
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: texto } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));
  }

  it("os campos do rascunho travam enquanto o assistente escreve", async () => {
    // A edição feita agora não caberia no corpo (já serializado) e seria
    // apagada pela resposta: a pessoa perderia o que digitou sem rastro.
    montar({ segurarAResposta: true });
    await falarESegurar("a Ana tá estranha");

    expect((screen.getByLabelText("Título") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).disabled).toBe(true);
    expect(screen.getByText(/O assistente está escrevendo aqui/)).toBeTruthy();
  });

  it("com a resposta na mão, os campos voltam a aceitar edição", async () => {
    // O par de presença: um painel travado desde sempre passaria no teste
    // acima, e o critério de aceite manda editar à mão.
    montar();
    await falar("a Ana tá estranha");

    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).disabled).toBe(false));
    expect(screen.queryByText(/O assistente está escrevendo aqui/)).toBeNull();
  });

  it("descartar no meio do turno não é desfeito pela resposta que chega depois", async () => {
    montar({ segurarAResposta: true });
    await falarESegurar("a Ana tá estranha");

    fireEvent.click(screen.getByRole("button", { name: /Descartar/ }));
    soltarAResposta?.();

    // A conversa descartada não volta, nem o rascunho que ela traria.
    await waitFor(() => expect(screen.queryByText("a Ana tá estranha")).toBeNull());
    expect(screen.queryByText("Entendi. Onde isso aconteceu?")).toBeNull();
    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("");
    expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull();
  });

  it("sem descartar, a resposta do mesmo turno entra normalmente", async () => {
    // O par de presença: uma tela que jogasse fora TODA resposta passaria no
    // teste acima.
    montar({ segurarAResposta: true });
    await falarESegurar("a Ana tá estranha");

    soltarAResposta?.();

    await waitFor(() => expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy());
    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada");
  });
});

/**
 * As tres propriedades do turno (issue #727, rodada 3 da revisao).
 *
 * Elas nao sao tres correcoes: sao o contrato do ponto unico de saida
 * (`encerrarOTurno`). Cada bloco abaixo cobra uma, POR CAMINHO, porque foi
 * justamente "esta valendo num caminho e nao no outro" que produziu duas safras
 * de regressao no mesmo lugar.
 */
describe("Propriedade 1: a tela destrava em todo caminho de saída", () => {
  async function falarESegurar(texto: string) {
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: texto } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));
  }

  /** O painel inteiro, que é o que o `conversando` tranca. */
  function painelTravado(): boolean {
    return (screen.getByLabelText("Título") as HTMLInputElement).disabled;
  }

  it("corpo ilegível destrava a tela e mostra o alarme", async () => {
    // É o caminho que congelava os seis campos e a frase "está escrevendo" para
    // sempre, sem alerta nenhum: o teto novo virando indisponibilidade. A única
    // saída era descartar a conversa ou recarregar a página.
    montar({ fimDoTurno: "ilegivel" });

    await falar("a Ana tá estranha");

    await waitFor(() => expect(painelTravado()).toBe(false));
    expect((await screen.findByRole("alert")).textContent).toBe(RESPOSTA_ILEGIVEL);
    expect(screen.queryByText(/O assistente está escrevendo aqui/)).toBeNull();
  });

  // Os dois corpos que o revisor reproduziu: `null` congelava o painel (o
  // `TypeError` saía do meio do encerramento) e `{}` apagava a PÁGINA no render
  // seguinte, em `rascunho.titulo.trim()`.
  it.each([
    ["null", null],
    ["objeto vazio", {}],
    ["rascunho pela metade", { reply: "oi", rascunho: {} }],
    ["reply que não é texto", { reply: 42, rascunho: RASCUNHO_DO_ASSISTENTE }],
  ])("200 fora do contrato (%s) destrava a tela e mostra o alarme", async (_nome, corpo) => {
    /**
     * O primeiro turno é BOM de propósito: ele enche o rascunho.
     *
     * A versão anterior deste teste asseverava que o Título continuava vazio
     * depois do turno ruim, com um rascunho que já nascia vazio: o estado
     * inicial fazia o trabalho que a asserção dizia fazer, e o mutante que
     * zerasse o rascunho no ramo de erro passava batido. Agora a fixture nasce
     * PREENCHIDA, e a asserção mede o que diz medir.
     */
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );

    vi.stubGlobal("fetch", servidor({ corpoForaDoContrato: corpo }));
    await falar("na verdade é o Vínculo");

    await waitFor(() => expect(painelTravado()).toBe(false));
    expect((await screen.findByRole("alert")).textContent).toBe(RESPOSTA_ILEGIVEL);
    // O rascunho do turno bom SOBREVIVE: corpo que não serve não vira rascunho
    // meio preenchido, nem apaga o que já estava lá.
    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada");
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).value).toBe("Onde: no WhatsApp");
  });

  it("o corpo dentro do contrato passa", async () => {
    // O par de presença: uma fronteira que recusasse TODO corpo passaria nos
    // quatro acima e deixaria o assistente mudo.
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("rede fora destrava a tela", async () => {
    montar({ fimDoTurno: "rede" });

    await falar("a Ana tá estranha");

    await waitFor(() => expect(painelTravado()).toBe(false));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("recusa do servidor destrava a tela", async () => {
    montar({ recusaDoChat: { status: 500, corpo: { detail: "Erro interno" } } });

    await falar("a Ana tá estranha");

    await waitFor(() => expect(painelTravado()).toBe(false));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("o turno que dá certo destrava", async () => {
    // O par de presença dos três acima: uma tela que nunca travasse passaria
    // em todos eles.
    montar({ segurarAResposta: true });
    await falarESegurar("a Ana tá estranha");
    expect(painelTravado()).toBe(true);

    soltarAResposta?.();

    await waitFor(() => expect(painelTravado()).toBe(false));
  });
});

describe("Propriedade 2: a guarda da conversa vem antes de qualquer escrita", () => {
  async function conversarEDescartarNoMeio(opcoes: Opcoes) {
    montar({ ...opcoes, segurarAResposta: true });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "a Ana tá estranha" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: /Descartar/ }));
    soltarAResposta?.();
  }

  it("pelo caminho da rede, a conversa descartada não ressuscita", async () => {
    // O caminho que continuava aberto: o `catch` desfazia o turno sem olhar de
    // quem ele era, ressuscitava o fio e o regravava na sessão, com um alerta
    // vermelho de uma conversa que não existe mais.
    await conversarEDescartarNoMeio({ fimDoTurno: "rede" });

    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull());
    expect(within(screen.getByRole("log")).queryByText("a Ana tá estranha")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect((screen.getByLabelText("Título") as HTMLInputElement).disabled).toBe(false);
  });

  it("pelo caminho do corpo ilegível, também não", async () => {
    await conversarEDescartarNoMeio({ fimDoTurno: "ilegivel" });

    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull());
    expect(within(screen.getByRole("log")).queryByText("a Ana tá estranha")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("pelo caminho da recusa, também não", async () => {
    await conversarEDescartarNoMeio({ recusaDoChat: { status: 429, corpo: { error: "Rate limit exceeded" } } });

    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a conversa viva escreve normalmente", async () => {
    // O par de presença dos três acima: uma tela que jogasse fora TODA resposta
    // passaria em todos eles.
    montar({ segurarAResposta: true });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "a Ana tá estranha" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));

    soltarAResposta?.();

    await waitFor(() => expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy());
    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada");
  });
});

describe("Propriedade 3: o rollback não pisa no que a pessoa digitou", () => {
  it("o texto novo na caixa ganha da fala antiga", async () => {
    // A caixa de mensagem NÃO trava durante o turno, e é o que se faz enquanto
    // o assistente pensa: continuar escrevendo. Repor a fala por cima é a mesma
    // perda silenciosa que motivou o primeiro must-fix, na outra caixa.
    montar({ segurarAResposta: true, fimDoTurno: "rede" });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "a Ana tá estranha" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));

    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "na verdade é o Vínculo" } });
    soltarAResposta?.();

    await waitFor(() => expect(screen.queryByRole("alert")).toBeTruthy());
    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("na verdade é o Vínculo");
  });

  it("com a caixa vazia, a fala volta", async () => {
    // O par de presença: um rollback que nunca repusesse nada passaria no teste
    // acima, e a pessoa leria "mande de novo" sem ter o que mandar.
    montar({ fimDoTurno: "rede" });

    await falar("a Ana tá estranha");

    await waitFor(() =>
      expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("a Ana tá estranha"),
    );
  });

  it("só espaço em branco na caixa não conta como texto novo", async () => {
    montar({ segurarAResposta: true, fimDoTurno: "rede" });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "a Ana tá estranha" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(doChat().length).toBeGreaterThan(0));

    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "   " } });
    soltarAResposta?.();

    await waitFor(() =>
      expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("a Ana tá estranha"),
    );
  });
});

describe("O turno recusado", () => {
  it("volta atrás: a fala sai do fio e o texto volta para a caixa", async () => {
    // Sem isso, a tela diz "mande de novo" e não sobrou o que mandar: a fala
    // fica pendurada sem resposta, já gravada na sessão, e queimou um dos
    // quarenta lugares do teto que o servidor nunca viu.
    montar({ recusaDoChat: { status: 429, corpo: { error: "Rate limit exceeded: 10 per 1 minute" } } });

    await falar("a Ana tá estranha");

    await waitFor(() => expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("a Ana tá estranha"));
    expect(within(screen.getByRole("log")).queryByText("a Ana tá estranha")).toBeNull();
    expect((await screen.findByRole("alert")).textContent).toBe(MUITAS_MENSAGENS);
  });

  it("a falha de rede volta atrás do mesmo jeito", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        chamadas.push({ url, metodo: "POST", corpo: undefined });
        throw new Error("rede fora");
      }),
    );
    render(
      <AssistenteDeTecnologia token="tok" produtos={PRODUTOS} onCriada={(d, a) => criadas.push({ demanda: d, aviso: a })} />,
    );

    await falar("a Ana tá estranha");

    await waitFor(() => expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("a Ana tá estranha"));
    expect(within(screen.getByRole("log")).queryByText("a Ana tá estranha")).toBeNull();
  });

  it("o turno aceito NÃO volta atrás", async () => {
    // O par de presença dos dois acima: uma tela que nunca comitasse a fala
    // passaria nos dois.
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() => expect(within(screen.getByRole("log")).getByText("a Ana tá estranha")).toBeTruthy());
    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("");
  });
});

describe("Os tetos do corpo", () => {
  /** Uma conversa já no teto, guardada na sessão para a tela montar em cima dela. */
  function conversaNoTeto() {
    const messages: MensagemDoChat[] = Array.from({ length: LIMITE_DE_MENSAGENS }, (_, i) => ({
      role: i % 2 === 0 ? "assistant" : "user",
      content: `fala ${i}`,
    }));
    window.sessionStorage.setItem(CHAVE_DA_SESSAO, JSON.stringify({ messages, rascunho: RASCUNHO_VAZIO }));
  }

  it("a caixa de mensagem não deixa passar do teto de caracteres", () => {
    // O 422 do pydantic traz `detail` em LISTA, e o alerta mostraria JSON cru:
    // quem cola um texto longo tem que ser barrado antes da viagem.
    montar();

    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).maxLength).toBe(LIMITE_DA_MENSAGEM);
  });

  it("os campos do rascunho têm o par na tela dos tetos do servidor", () => {
    // O rascunho volta inteiro no corpo de cada turno: sem estes dois, o 422 do
    // servidor seria a primeira notícia de que o texto não cabia.
    montar();

    expect((screen.getByLabelText("Título") as HTMLInputElement).maxLength).toBe(LIMITE_DO_TITULO);
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).maxLength).toBe(LIMITE_DA_DESCRICAO);
  });

  it("no teto de mensagens, a tela para de mandar e diz o que fazer", async () => {
    conversaNoTeto();
    montar();

    await waitFor(() => expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).disabled).toBe(true));
    expect(screen.getByText(CONVERSA_NO_TETO)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("uma mensagem antes do teto, a conversa segue normalmente", async () => {
    // O par de presença: uma tela travada desde sempre passaria no teste acima.
    const messages: MensagemDoChat[] = Array.from({ length: LIMITE_DE_MENSAGENS - 1 }, (_, i) => ({
      role: i % 2 === 0 ? "assistant" : "user",
      content: `fala ${i}`,
    }));
    window.sessionStorage.setItem(CHAVE_DA_SESSAO, JSON.stringify({ messages, rascunho: RASCUNHO_VAZIO }));
    montar();

    await waitFor(() => expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).disabled).toBe(false));
    expect(screen.queryByText(CONVERSA_NO_TETO)).toBeNull();

    await falar("a última que cabe");

    // O corpo sai com 40 mensagens cravadas, que é o que o backend aceita.
    expect((doChat()[0].corpo?.messages as unknown[]).length).toBe(LIMITE_DE_MENSAGENS);
  });
});

describe("Criar Demanda", () => {
  it("só libera com título e Produto", async () => {
    montar();
    const botao = () => screen.getByRole("button", { name: "Criar Demanda" }) as HTMLButtonElement;
    expect(botao().disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Alguma coisa" } });
    expect(botao().disabled).toBe(true);

    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));
    fireEvent.click(within(screen.getByRole("listbox")).getByText("Ana"));
    expect(botao().disabled).toBe(false);
  });

  it("chama a rota de criação com o payload de hoje", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criacoes()).toHaveLength(1));
    expect(criacoes()[0].url).toBe("/api/admin/tecnologia/demandas");
    expect(criacoes()[0].metodo).toBe("POST");
    expect(criacoes()[0].corpo).toEqual({
      titulo: "Ana não responde de madrugada",
      tipo: "defeito",
      produto_id: "prod-1",
      prioridade: "normal",
      // Os quatro rótulos do roteiro de Defeito que ficaram em branco saem
      // como "não informado"; "Onde" não, porque foi respondido.
      descricao: [
        "Onde: no WhatsApp",
        `O que aconteceu: ${NAO_INFORMADO}`,
        `O que esperava: ${NAO_INFORMADO}`,
        `Quando: ${NAO_INFORMADO}`,
        `Como repetir: ${NAO_INFORMADO}`,
      ].join("\n"),
      prazo: null,
    });
  });

  it("entrega a Demanda criada a quem hospeda a tela", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(criadas[0].demanda.id).toBe("d-nova");
  });

  it("201 com corpo ilegível é sucesso sem confirmação, e fecha a porta da duplicata", async () => {
    // A Demanda NASCEU: o servidor respondeu 201 e o que falhou foi ler o
    // corpo. Dizer "mande de novo" empurraria para o pior desfecho, porque
    // `POST /demandas` não tem chave de idempotência e o segundo clique
    // nasceria a Demanda repetida, com dois donos notificados.
    montar({ criacaoIlegivel: true });
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain(CRIADA_SEM_CONFIRMACAO);
    // A frase do chat não serve aqui: lá o desfecho foi ruim, aqui foi bom.
    expect(alerta.textContent).not.toContain(RESPOSTA_ILEGIVEL);
    // A saída oferecida é o Quadro.
    expect(within(alerta).getByRole("link").getAttribute("href")).toBe("/admin/tecnologia");
    // E o botão FECHA, em vez de reabilitar.
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Criar Demanda" }) as HTMLButtonElement).disabled).toBe(true),
    );
    expect(criadas).toHaveLength(0);
  });

  it.each([
    ["null", null],
    ["sem id", { titulo: "Ana não responde" }],
    ["lista", []],
  ])("201 com corpo que lê e não serve (%s) também é sucesso sem confirmação", async (_nome, corpo) => {
    // O buraco que sobrou da rodada 4: fechei o corpo que LEVANTA no `json()` e
    // deixei aberto o corpo que faz parse e vem fora do contrato. Sem `id` não
    // há para onde ir, e o cast dizia que havia.
    montar({ corpoDaCriacaoForaDoContrato: corpo });
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain(CRIADA_SEM_CONFIRMACAO);
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Criar Demanda" }) as HTMLButtonElement).disabled).toBe(true),
    );
    expect(criadas).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));
    await waitFor(() => expect(criacoes()).toHaveLength(1));
  });

  it("depois do 201 sem confirmação, clicar de novo não cria uma segunda Demanda", async () => {
    montar({ criacaoIlegivel: true });
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));
    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));
    await screen.findByRole("alert");
    expect(criacoes()).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criacoes()).toHaveLength(1));
  });

  it("a criação que dá certo não mostra o aviso de sem confirmação", async () => {
    // O par de presença dos dois acima: um aviso cravado na tela passaria neles.
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(criadas).toHaveLength(1));
    expect(screen.queryByText(CRIADA_SEM_CONFIRMACAO)).toBeNull();
  });

  it("criar limpa o armazenamento de sessão", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Criar Demanda" }));

    await waitFor(() => expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull());
  });
});

describe("O armazenamento de sessão", () => {
  it("o rascunho volta ao remontar a tela", async () => {
    const { unmount } = montar();
    await falar("a Ana tá estranha");
    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );

    unmount();
    cleanup();
    montar();

    await waitFor(() =>
      expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("Ana não responde de madrugada"),
    );
    expect(screen.getByText("Entendi. Onde isso aconteceu?")).toBeTruthy();
  });

  it("sem nada guardado, a tela nasce com o rascunho vazio", () => {
    // O par de ausência do teste acima: uma tela que sempre mostra o mesmo
    // título passaria naquele sozinha.
    montar();

    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe(RASCUNHO_VAZIO.titulo);
  });
});

describe("Descartar", () => {
  it("limpa conversa, rascunho e o que estava guardado", async () => {
    montar();
    await falar("a Ana tá estranha");
    await waitFor(() => expect((screen.getByLabelText("Título") as HTMLInputElement).value).not.toBe(""));

    fireEvent.click(screen.getByRole("button", { name: /Descartar/ }));

    expect((screen.getByLabelText("Título") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Descrição") as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText("Entendi. Onde isso aconteceu?")).toBeNull();
    expect(window.sessionStorage.getItem(CHAVE_DA_SESSAO)).toBeNull();
  });
});

describe("O painel do rascunho", () => {
  it("é recolhível, e nasce aberto", () => {
    montar();
    const alavanca = screen.getByRole("button", { name: /Recolher/ });
    expect(alavanca.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(alavanca);

    expect(screen.getByRole("button", { name: /Abrir/ }).getAttribute("aria-expanded")).toBe("false");
  });

  it("só oferece Produto ativo", () => {
    montar();
    fireEvent.click(screen.getByRole("combobox", { name: "Produto" }));

    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(opcoes.map((o) => o.textContent)).toEqual(["Ana", "POPs"]);
  });

  it("sem Tipo escolhido, a tela diz com que Tipo a Demanda vai nascer", async () => {
    // O botão libera com título e Produto, e a rota de criação exige um Tipo:
    // quem cria sem conversar precisa LER qual vai, em vez de descobrir no
    // card depois.
    montar();

    expect(screen.getByText(/nasce como Informação/)).toBeTruthy();
  });

  it("com Tipo escolhido, a frase some", async () => {
    // O par do teste acima: uma frase cravada na tela passaria naquele.
    montar();

    await falar("a Ana tá estranha");

    await waitFor(() => expect(screen.queryByText(/nasce como Informação/)).toBeNull());
  });

  it("vem antes do chat no DOM, que é o que o põe no topo no celular", () => {
    // As duas colunas viram uma pilha abaixo de `lg`, e a pilha segue a ordem
    // do DOM: o rascunho primeiro, o chat embaixo (PRD #726, história 3).
    montar();

    const rascunho = screen.getByLabelText("Título");
    const chat = screen.getByLabelText("Mensagem");
    expect(rascunho.compareDocumentPosition(chat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
