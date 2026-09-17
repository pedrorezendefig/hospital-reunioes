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

import { ToastProvider } from "@/components/ui/Toast";

import { AssistenteDeTecnologia } from "./AssistenteDeTecnologia";
import {
  ANEXO_ILEGIVEL,
  AUDIO_FORA_DA_LISTA,
  AUDIO_SEM_FALA,
  AVISO_DE_IA,
  CHAVE_DA_SESSAO,
  CONVERSA_NO_TETO,
  DOCUMENTO_FORA_DA_LISTA,
  IMAGEM_FORA_DA_LISTA,
  LIMITE_DA_DESCRICAO,
  LIMITE_DA_MENSAGEM,
  LIMITE_DE_MENSAGENS,
  LIMITE_DO_TITULO,
  MensagemDoChat,
  MUITAS_MENSAGENS,
  NAO_INFORMADO,
  PRINT_SEM_LEITURA,
  RASCUNHO_VAZIO,
  RascunhoDaDemanda,
  RESPOSTA_ILEGIVEL,
  respostaDoChatValida,
  CRIADA_SEM_CONFIRMACAO,
} from "./assistente";
import { Demanda, ProdutoDaEscolha } from "./demandas";

type Chamada = {
  url: string;
  metodo: string;
  corpo: Record<string, unknown> | undefined;
  arquivo?: string;
  /**
   * O campo do `FormData` em que o arquivo foi. Ele é guardado porque é
   * contrato: cada rota do backend declara o nome do seu (`audio`, `arquivo`,
   * `imagem`), e mandar no campo errado é 422 com `detail` em lista.
   */
  campo?: string;
};

/** Os campos de arquivo que as três rotas de anexo declaram. */
const CAMPOS_DE_ARQUIVO = ["audio", "arquivo", "imagem"];

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
  /** O que a rota de voz devolve como texto transcrito. */
  transcricao?: string;
  /** O que a rota de extração devolve como texto do documento. */
  textoDoDocumento?: string;
  /** O que a rota do print devolve como descrição da imagem. */
  descricaoDoPrint?: string;
  /** A recusa da rota de voz ou da de extração, com o corpo cru daquela camada. */
  recusaDoAnexo?: { status: number; corpo: unknown };
  /** Um 200 da extração cujo corpo o `JSON.parse` aceita e que não serve. */
  corpoDoAnexoForaDoContrato?: unknown;
  /** Segura a resposta do anexo: entre o clique e a soltura a leitura está EM VOO. */
  segurarOAnexo?: boolean;
};

let soltarOAnexo: (() => void) | null = null;

let soltarAResposta: (() => void) | null = null;

function servidor(opcoes: Opcoes) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    // O anexo vai em `FormData`, e o turno em JSON: o dublê guarda o nome do
    // arquivo num caso e o corpo no outro. `JSON.parse` de um FormData
    // explodiria aqui dentro e a falha apareceria como "a tela não chamou".
    const enviado = init?.body;
    const forma = enviado instanceof FormData ? enviado : null;
    const corpo = forma || !enviado ? undefined : JSON.parse(String(enviado));
    const campo = CAMPOS_DE_ARQUIVO.find((c) => forma?.get(c) instanceof File);
    const anexo = campo ? forma?.get(campo) : null;
    chamadas.push({
      url,
      metodo: init?.method ?? "GET",
      corpo,
      arquivo: anexo instanceof File ? anexo.name : undefined,
      campo,
    });

    if (url.endsWith("/transcricao/voz")) {
      if (opcoes.segurarOAnexo) await new Promise<void>((resolve) => (soltarOAnexo = resolve));
      if (opcoes.recusaDoAnexo) {
        return {
          ok: false,
          status: opcoes.recusaDoAnexo.status,
          json: async () => opcoes.recusaDoAnexo!.corpo,
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ texto: opcoes.transcricao ?? "a Ana travou de madrugada" }),
      } as unknown as Response;
    }

    if (url.endsWith("/assistente/extrair-documento")) {
      if (opcoes.segurarOAnexo) await new Promise<void>((resolve) => (soltarOAnexo = resolve));
      if (opcoes.recusaDoAnexo) {
        return {
          ok: false,
          status: opcoes.recusaDoAnexo.status,
          json: async () => opcoes.recusaDoAnexo!.corpo,
        } as unknown as Response;
      }
      if ("corpoDoAnexoForaDoContrato" in opcoes) {
        return { ok: true, status: 200, json: async () => opcoes.corpoDoAnexoForaDoContrato } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ texto: opcoes.textoDoDocumento ?? "a Ana travou de madrugada", filename: "nota.pdf" }),
      } as unknown as Response;
    }
    if (url.endsWith("/assistente/descrever-imagem")) {
      if (opcoes.segurarOAnexo) await new Promise<void>((resolve) => (soltarOAnexo = resolve));
      if (opcoes.recusaDoAnexo) {
        return {
          ok: false,
          status: opcoes.recusaDoAnexo.status,
          json: async () => opcoes.recusaDoAnexo!.corpo,
        } as unknown as Response;
      }
      if ("corpoDoAnexoForaDoContrato" in opcoes) {
        return { ok: true, status: 200, json: async () => opcoes.corpoDoAnexoForaDoContrato } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ texto: opcoes.descricaoDoPrint ?? "A tela de login da Ana, com erro" }),
      } as unknown as Response;
    }
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
  // O ToastProvider é o de verdade: o hook de gravação de voz avisa por toast
  // quando a transcrição falha, e ele exige provider para existir.
  return render(
    <ToastProvider>
      <AssistenteDeTecnologia
        token="tok"
        produtos={PRODUTOS}
        onCriada={(demanda, aviso) => criadas.push({ demanda, aviso })}
      />
    </ToastProvider>,
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
  soltarOAnexo = null;
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
      <ToastProvider>
        <AssistenteDeTecnologia
          token="tok"
          produtos={PRODUTOS}
          onCriada={(d, a) => criadas.push({ demanda: d, aviso: a })}
        />
      </ToastProvider>,
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


// ═══════════════════════════════════════════════════════════════════════════
// Falar e anexar (issue #729)
// ═══════════════════════════════════════════════════════════════════════════
//
// Três entradas novas e uma regra só: toda entrada vira TEXTO antes de chegar
// ao chat. O chat nunca recebe arquivo, e o que aparece na conversa é sempre
// uma mensagem da pessoa, com a origem à mostra.

/**
 * O gravador do navegador, falso.
 *
 * Ele existe para o teste exercitar o hook de gravação DE VERDADE (o mesmo da
 * Ata Guiada), e não um dublê do hook: dublar o hook provaria que a tela sabe
 * receber um texto, e não que o botão de microfone chega à rota de voz.
 */
class GravadorFalso {
  static ultimo: GravadorFalso | null = null;
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: unknown, opcoes?: { mimeType?: string }) {
    this.mimeType = opcoes?.mimeType ?? "audio/webm";
    GravadorFalso.ultimo = this;
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["bytes-de-audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function plugarOMicrofone() {
  GravadorFalso.ultimo = null;
  vi.stubGlobal("MediaRecorder", GravadorFalso);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [{ stop: vi.fn() }] }) },
  });
}

function arquivo(nome: string, tamanho: number, tipo = "application/octet-stream"): File {
  const falso = new File(["x"], nome, { type: tipo });
  // `File` de verdade calcula o `size` do conteúdo, e o teto que se quer provar
  // é de megabytes: escrever 25 MB de string no jsdom seria pagar caro por um
  // número. Só o `size` é forjado.
  Object.defineProperty(falso, "size", { value: tamanho });
  return falso;
}

function escolher(rotulo: string, arquivos: File[]) {
  const entrada = screen.getByLabelText(rotulo) as HTMLInputElement;
  fireEvent.change(entrada, { target: { files: arquivos } });
}

function paraVoz(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/transcricao/voz"));
}

function paraExtracao(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/assistente/extrair-documento"));
}

function paraODescritor(): Chamada[] {
  return chamadas.filter((c) => c.url.endsWith("/assistente/descrever-imagem"));
}

/** A última fala mandada ao assistente, como ela foi no corpo do turno. */
function ultimaFala(): string {
  const mensagens = doChat().at(-1)?.corpo?.messages as MensagemDoChat[];
  return mensagens.at(-1)!.content;
}

describe("A voz gravada", () => {
  it("vira mensagem com o prefixo de áudio e dispara o turno", async () => {
    plugarOMicrofone();
    montar({ transcricao: "a Ana tá travando de madrugada" });

    fireEvent.click(screen.getByLabelText("Gravar voz"));
    await waitFor(() => expect(GravadorFalso.ultimo).not.toBeNull());
    fireEvent.click(screen.getByLabelText("Parar de gravar"));

    // Foi pela rota de voz QUE JÁ EXISTE, e não por uma rota nova.
    await waitFor(() => expect(paraVoz()).toHaveLength(1));
    expect(paraVoz()[0].metodo).toBe("POST");
    expect(paraVoz()[0].arquivo).toMatch(/^voz\./);

    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(ultimaFala()).toBe("[áudio] a Ana tá travando de madrugada");
    // E a pessoa VÊ o que o assistente recebeu, na conversa.
    expect(within(screen.getByRole("log")).getByText("[áudio] a Ana tá travando de madrugada")).toBeTruthy();
  });

  it("o chat nunca recebe arquivo: o corpo do turno é JSON com a fala dentro", async () => {
    plugarOMicrofone();
    montar({ transcricao: "a Ana tá travando" });

    fireEvent.click(screen.getByLabelText("Gravar voz"));
    await waitFor(() => expect(GravadorFalso.ultimo).not.toBeNull());
    fireEvent.click(screen.getByLabelText("Parar de gravar"));

    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(doChat()[0].arquivo).toBeUndefined();
    expect(doChat()[0].corpo?.rascunho).toBeDefined();
  });
});

describe("O arquivo de áudio", () => {
  it("vai à MESMA rota de voz e vira mensagem com o prefixo de áudio", async () => {
    montar({ transcricao: "encaminhei o áudio do WhatsApp" });

    escolher("Arquivo de áudio", [arquivo("recado.m4a", 2 * 1024 * 1024, "audio/mp4")]);

    await waitFor(() => expect(paraVoz()).toHaveLength(1));
    expect(paraVoz()[0].arquivo).toBe("recado.m4a");
    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(ultimaFala()).toBe("[áudio] encaminhei o áudio do WhatsApp");
  });

  it("áudio acima de 25 MB vira aviso na conversa, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de áudio", [arquivo("longo.mp3", 26 * 1024 * 1024, "audio/mpeg")]);

    await waitFor(() => expect(within(screen.getByRole("log")).getByText(/25 MB/)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("áudio de formato fora da lista vira aviso, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de áudio", [arquivo("recado.aac", 1000, "audio/aac")]);

    await waitFor(() => expect(screen.getByText(AUDIO_FORA_DA_LISTA)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("áudio sem fala vira aviso, e não uma mensagem só com o prefixo", async () => {
    montar({ transcricao: "   " });

    escolher("Arquivo de áudio", [arquivo("mudo.wav", 1000, "audio/wav")]);

    await waitFor(() => expect(screen.getByText(AUDIO_SEM_FALA)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });
});

describe("O documento", () => {
  it("vira mensagem com o nome do arquivo e dispara o turno", async () => {
    montar({ textoDoDocumento: "Relatório: a Ana caiu três vezes em setembro." });

    escolher("Arquivo de documento", [arquivo("relatorio.pdf", 3 * 1024 * 1024, "application/pdf")]);

    await waitFor(() => expect(paraExtracao()).toHaveLength(1));
    expect(paraExtracao()[0].arquivo).toBe("relatorio.pdf");
    await waitFor(() => expect(doChat()).toHaveLength(1));
    // O nome é o que o SERVIDOR devolveu ("nota.pdf"), e não o do arquivo
    // local: é lá que ele foi limpo do que quebraria o prefixo de origem.
    expect(ultimaFala()).toBe("[documento nota.pdf] Relatório: a Ana caiu três vezes em setembro.");
  });

  it("documento acima do teto do formato vira aviso, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de documento", [arquivo("longo.txt", 6 * 1024 * 1024, "text/plain")]);

    await waitFor(() => expect(within(screen.getByRole("log")).getByText(/5 MB/)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("documento de formato fora da lista vira aviso, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de documento", [arquivo("planilha.xlsx", 1000)]);

    await waitFor(() => expect(screen.getByText(DOCUMENTO_FORA_DA_LISTA)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("recusa do servidor vira aviso com a frase DELE, e nenhum turno é mandado", async () => {
    montar({ recusaDoAnexo: { status: 422, corpo: { detail: "PDF parece ser escaneado (sem texto extraivel)." } } });

    escolher("Arquivo de documento", [arquivo("escaneado.pdf", 1000, "application/pdf")]);

    await waitFor(() => expect(screen.getByText(/PDF parece ser escaneado/)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("corpo que o `json()` lê e que não serve vira aviso, e nenhum turno é mandado", async () => {
    // A fronteira valendo para o CORPO, e não só para a rede: sem ela, um 200
    // sem `texto` viraria a mensagem "[documento undefined] undefined".
    montar({ corpoDoAnexoForaDoContrato: { arquivo: "nota.pdf" } });

    escolher("Arquivo de documento", [arquivo("nota.pdf", 1000, "application/pdf")]);

    await waitFor(() => expect(screen.getByText(ANEXO_ILEGIVEL)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("corpo sem o `filename` também não vira mensagem", async () => {
    // O detector do teste de cima: uma peneira que cobrasse só o `texto`
    // passaria lá e deixaria o prefixo de origem sair como "[documento
    // undefined]", que é o prefixo que o backend NÃO reconhece para cercar.
    montar({ corpoDoAnexoForaDoContrato: { texto: "a Ana travou" } });

    escolher("Arquivo de documento", [arquivo("nota.pdf", 1000, "application/pdf")]);

    await waitFor(() => expect(screen.getByText(ANEXO_ILEGIVEL)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });
});

describe("O aviso do anexo", () => {
  it("não entra no fio que vai ao assistente", async () => {
    // Um aviso da TELA no meio das mensagens iria ao prompt no turno seguinte
    // como se o assistente o tivesse dito.
    montar();
    escolher("Arquivo de documento", [arquivo("planilha.xlsx", 1000)]);
    await waitFor(() => expect(screen.getByText(DOCUMENTO_FORA_DA_LISTA)).toBeTruthy());

    await falar("deixa, eu escrevo");

    const mandadas = doChat()[0].corpo?.messages as MensagemDoChat[];
    expect(mandadas.some((m) => m.content.includes("Só dá para ler"))).toBe(false);
    expect(mandadas.at(-1)!.content).toBe("deixa, eu escrevo");
  });

  it("o aviso que veio do SERVIDOR também não entra no fio", async () => {
    // O par do teste acima, e a razão de ele existir: a recusa local e a
    // recusa do servidor são o mesmo desfecho, e por um tempo eram dois
    // lugares escrevendo o aviso. O de cima cobria só o primeiro.
    montar({ recusaDoAnexo: { status: 422, corpo: { detail: "PDF parece ser escaneado." } } });
    escolher("Arquivo de documento", [arquivo("escaneado.pdf", 1000, "application/pdf")]);
    await waitFor(() => expect(screen.getByText(/PDF parece ser escaneado/)).toBeTruthy());

    await falar("deixa, eu escrevo");

    const mandadas = doChat()[0].corpo?.messages as MensagemDoChat[];
    expect(mandadas.some((m) => m.content.includes("escaneado"))).toBe(false);
  });

  it("some quando o turno seguinte começa", async () => {
    montar();
    escolher("Arquivo de documento", [arquivo("planilha.xlsx", 1000)]);
    await waitFor(() => expect(screen.getByText(DOCUMENTO_FORA_DA_LISTA)).toBeTruthy());

    await falar("deixa, eu escrevo");

    await waitFor(() => expect(screen.queryByText(DOCUMENTO_FORA_DA_LISTA)).toBeNull());
  });
});

describe("O microfone aberto", () => {
  it("trava o envio, e o botão de parar continua vivo", async () => {
    // A classe é a mesma do Enter no meio da leitura do anexo: todo controle
    // que só faz sentido fora de um turno respeita o mesmo `ocupado`. Sem
    // `gravando` lá dentro, mandar pelo teclado durante a gravação começava o
    // turno e o botão de PARAR ficava cinza enquanto a tela mandava clicar
    // nele; com aquele turno chegando ao teto de mensagens, ele não reabilitava
    // nunca mais e o microfone ficava aberto até alguém descartar a conversa.
    plugarOMicrofone();
    montar();

    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "deixa, eu escrevo" } });
    // O par de presença: com texto e sem gravação, o Enviar está vivo.
    expect((screen.getByLabelText("Enviar") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByLabelText("Gravar voz"));
    await waitFor(() => expect(screen.getByLabelText("Parar de gravar")).toBeTruthy());

    expect((screen.getByLabelText("Enviar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByLabelText("Mensagem"), { key: "Enter" });
    expect(doChat()).toHaveLength(0);
    // E o caminho de volta fica aberto: é ele que desliga o microfone.
    expect((screen.getByLabelText("Parar de gravar") as HTMLButtonElement).disabled).toBe(false);
  });

  it("os botões de anexo também ficam travados enquanto grava", async () => {
    plugarOMicrofone();
    montar();
    expect((screen.getByLabelText("Anexar documento") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByLabelText("Gravar voz"));
    await waitFor(() => expect(screen.getByLabelText("Parar de gravar")).toBeTruthy());

    expect((screen.getByLabelText("Anexar documento") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Anexar áudio") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Anexar print") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("O teto de taxa no anexo", () => {
  it("o 429 diz para esperar, e não para trocar de arquivo", async () => {
    // O `slowapi` responde `{"error": ...}` SEM `detail`, então a frase
    // genérica sairia mandando "tente outro arquivo" quando a saída é esperar
    // um minuto. É a mesma frase do turno, e não uma terceira.
    montar({ recusaDoAnexo: { status: 429, corpo: { error: "Rate limit exceeded: 10 per 1 minute" } } });

    escolher("Arquivo de documento", [arquivo("nota.pdf", 1000, "application/pdf")]);

    await waitFor(() => expect(screen.getByText(MUITAS_MENSAGENS)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("o 429 da rota de voz fala a mesma língua", async () => {
    // A outra porta de anexo passa pela mesma função, e um teste só provaria
    // uma delas.
    montar({ recusaDoAnexo: { status: 429, corpo: { error: "Rate limit exceeded" } } });

    escolher("Arquivo de áudio", [arquivo("recado.mp3", 1000, "audio/mpeg")]);

    await waitFor(() => expect(screen.getByText(MUITAS_MENSAGENS)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });
});

describe("Mandar pelo teclado no meio de uma leitura", () => {
  it("o Enter não começa um turno enquanto o anexo está sendo lido, e o anexo chega", async () => {
    // O botão de mandar já está desabilitado aqui, mas o Enter da caixa não
    // passa por ele. Sem guarda, o turno do teclado saía primeiro e a fala do
    // documento voltava para uma tela que já estava conversando: sumia calada.
    montar({ segurarOAnexo: true, textoDoDocumento: "o que estava no PDF" });
    escolher("Arquivo de documento", [arquivo("nota.pdf", 1000, "application/pdf")]);
    await waitFor(() => expect(paraExtracao()).toHaveLength(1));

    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "ah, e mais uma coisa" } });
    fireEvent.keyDown(screen.getByLabelText("Mensagem"), { key: "Enter" });
    expect(doChat()).toHaveLength(0);

    soltarOAnexo!();

    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(ultimaFala()).toBe("[documento nota.pdf] o que estava no PDF");
    // E o que a pessoa digitou continua na caixa, para ela mandar em seguida.
    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("ah, e mais uma coisa");
  });
});

describe("Descartar no meio de um anexo", () => {
  it("o documento que voltar depois não ressuscita a conversa", async () => {
    montar({ segurarOAnexo: true, textoDoDocumento: "texto de um pedido que foi jogado fora" });
    escolher("Arquivo de documento", [arquivo("nota.pdf", 1000, "application/pdf")]);
    await waitFor(() => expect(paraExtracao()).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: /Descartar/ }));
    soltarOAnexo!();

    // Nada de turno, e a conversa segue com a fala de boas-vindas e nada mais.
    await waitFor(() => expect(screen.getByLabelText("Mensagem")).toBeTruthy());
    expect(doChat()).toHaveLength(0);
    expect(within(screen.getByRole("log")).queryByText(/documento nota\.pdf/)).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// O print de tela (issue #730)
// ═══════════════════════════════════════════════════════════════════════════
//
// A quarta entrada, e a mesma regra das outras três: a imagem vira TEXTO antes
// de chegar ao chat. O que aparece na conversa é uma mensagem da pessoa com
// `[print] ` na frente, que é o que a deixa conferir o que o assistente
// enxergou e o que faz o backend cercar a descrição como material de fora.

describe("O print", () => {
  it("vira mensagem com o prefixo de print e dispara o turno", async () => {
    montar({ descricaoDoPrint: "A tela de login da Ana, com o aviso 'senha inválida'." });

    escolher("Arquivo de print", [arquivo("tela.png", 800 * 1024, "image/png")]);

    await waitFor(() => expect(paraODescritor()).toHaveLength(1));
    expect(paraODescritor()[0].metodo).toBe("POST");
    expect(paraODescritor()[0].arquivo).toBe("tela.png");
    // No campo que a rota declara: no campo errado o backend responde 422 com
    // `detail` em lista, que é o que chega como JSON cru ao aviso.
    expect(paraODescritor()[0].campo).toBe("imagem");

    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(ultimaFala()).toBe("[print] A tela de login da Ana, com o aviso 'senha inválida'.");
    // E a pessoa VÊ na conversa o que o assistente recebeu (PRD #726, história 37).
    expect(
      within(screen.getByRole("log")).getByText("[print] A tela de login da Ana, com o aviso 'senha inválida'."),
    ).toBeTruthy();
  });

  it("o chat nunca recebe a imagem: o corpo do turno é JSON com a descrição dentro", async () => {
    montar({ descricaoDoPrint: "A tela de login" });

    escolher("Arquivo de print", [arquivo("tela.png", 1000, "image/png")]);

    await waitFor(() => expect(doChat()).toHaveLength(1));
    expect(doChat()[0].arquivo).toBeUndefined();
    expect(doChat()[0].corpo?.rascunho).toBeDefined();
  });

  it("print acima de 5 MB vira aviso na conversa, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de print", [arquivo("tela.png", 6 * 1024 * 1024, "image/png")]);

    await waitFor(() => expect(within(screen.getByRole("log")).getByText(/5 MB/)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("imagem de formato fora da lista vira aviso, sem ir à rede e sem turno", async () => {
    montar();

    escolher("Arquivo de print", [arquivo("animada.gif", 1000, "image/gif")]);

    await waitFor(() => expect(screen.getByText(IMAGEM_FORA_DA_LISTA)).toBeTruthy());
    expect(chamadas).toHaveLength(0);
  });

  it("recusa do servidor vira aviso com a frase DELE, e nenhum turno é mandado", async () => {
    montar({
      recusaDoAnexo: { status: 502, corpo: { detail: "Não deu para ler esse print agora. Tente de novo." } },
    });

    escolher("Arquivo de print", [arquivo("tela.png", 1000, "image/png")]);

    await waitFor(() => expect(screen.getByText(/Não deu para ler esse print agora/)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("corpo que o `json()` lê e que não serve vira aviso, e nenhum turno é mandado", async () => {
    // Sem a fronteira, um 200 sem `texto` viraria a mensagem "[print] undefined".
    montar({ corpoDoAnexoForaDoContrato: { descricao: "a tela de login" } });

    escolher("Arquivo de print", [arquivo("tela.png", 1000, "image/png")]);

    await waitFor(() => expect(screen.getByText(ANEXO_ILEGIVEL)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("descrição em branco vira aviso, e não uma mensagem só com o prefixo", async () => {
    // Mesmo caso do áudio sem fala: `[print] ` seco mandaria o assistente
    // adivinhar o que a pessoa nunca mostrou.
    montar({ descricaoDoPrint: "   " });

    escolher("Arquivo de print", [arquivo("tela.png", 1000, "image/png")]);

    await waitFor(() => expect(screen.getByText(PRINT_SEM_LEITURA)).toBeTruthy());
    expect(doChat()).toHaveLength(0);
  });

  it("o botão de anexar print trava enquanto a leitura de um anexo está em voo", async () => {
    // A mesma regra dos outros dois: a caixa fica travada até o anexo virar
    // mensagem ou aviso, senão dois turnos saem por cima um do outro.
    montar({ segurarOAnexo: true });

    escolher("Arquivo de print", [arquivo("tela.png", 1000, "image/png")]);

    await waitFor(() => expect((screen.getByLabelText("Anexar print") as HTMLButtonElement).disabled).toBe(true));
    soltarOAnexo!();
    await waitFor(() => expect((screen.getByLabelText("Anexar print") as HTMLButtonElement).disabled).toBe(false));
  });
});
