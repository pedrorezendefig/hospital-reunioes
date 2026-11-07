/**
 * @vitest-environment jsdom
 */

/**
 * A lista lateral das conversas da Tecnologia (issue #1384, PRD #1380, ADR 0077).
 *
 * A tela inteira da aba Assistente, com o `fetch` dublado: a lista das
 * Demandas de quem está logado, com o título e a Etapa; o clique que retoma
 * a conversa sem card; o que mostra O que muda na que já tem Vínculo; o
 * "Nova conversa"; e a lista como tela própria no celular.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

import { ABERTURA, SEM_CONVERSA_GUARDADA } from "./ChatDaTecnologia";
import { ConversasDaTecnologia, NOVA_CONVERSA, VOLTAR_PARA_A_LISTA } from "./ConversasDaTecnologia";
import { ConversaDoChat, FalaDoChat } from "./chat";
import { Demanda } from "./demandas";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const LISTA = "/api/admin/tecnologia/chat";

function demanda(id: string, titulo: string, extra: Partial<Demanda> = {}): Demanda {
  return {
    id,
    titulo,
    criado_em: "2026-11-01T10:00:00Z",
    etapa: "registrada",
    tem_vinculo: false,
    o_que_muda: null,
    partes: [],
    ...extra,
  };
}

const ABERTURA_GUARDADA: FalaDoChat = {
  autor: "ia",
  texto: ABERTURA,
  fonte: null,
  opcoes: ["Bug", "Melhoria"],
  nao_bateu: false,
};

function conversa(demandaId: string, extra: Partial<ConversaDoChat> = {}): ConversaDoChat {
  return {
    demanda_id: demandaId,
    estado: "em_andamento",
    mensagens: [
      ABERTURA_GUARDADA,
      { autor: "diretor", texto: "Bug", fonte: null, opcoes: [], nao_bateu: false },
      { autor: "ia", texto: "Onde isso aconteceu?", fonte: null, opcoes: [], nao_bateu: false },
    ],
    resumo: null,
    anexos: 0,
    planejamento: false,
    aviso_dos_anexos: null,
    ...extra,
  };
}

type Chamada = { url: string; metodo: string; corpo: unknown };
type Resposta = { status: number; corpo: unknown };
type Servidor = (url: string, metodo: string, corpo: unknown) => Resposta;

/** Monta a aba com um servidor falso que responde pela URL e pelo método. */
function montar(servidor: Servidor) {
  const chamadas: Chamada[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = init?.body ? JSON.parse(String(init.body)) : null;
      chamadas.push({ url, metodo, corpo });
      const resposta = servidor(url, metodo, corpo);
      return {
        ok: resposta.status < 400,
        status: resposta.status,
        json: async () => resposta.corpo,
      } as unknown as Response;
    }),
  );
  render(
    <ToastProvider>
      <ConversasDaTecnologia token="token-de-teste" />
    </ToastProvider>,
  );
  return chamadas;
}

function lista() {
  return screen.getByRole("navigation", { name: "Suas conversas" });
}

const SEM_CARD = demanda("d-1", "Botão de responder some na Ouvidoria");
const COM_VINCULO = demanda("d-2", "Aviso quando a ata sair", {
  etapa: "em_producao",
  versao: "v0.207.0",
  tem_vinculo: true,
  o_que_muda: "Agora o aviso da ata chega por e-mail.",
});

describe("A lista", () => {
  it("mostra o título e a Etapa de cada Demanda, na ordem que o servidor manda", async () => {
    montar((url) => (url === LISTA ? { status: 200, corpo: [COM_VINCULO, SEM_CARD] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("Aviso quando a ata sair");
    const itens = within(lista()).getAllByRole("listitem");
    expect(itens.map((item) => item.textContent)).toEqual([
      "Aviso quando a ata sairEm produção desde v0.207.0",
      "Botão de responder some na OuvidoriaRegistrada",
    ]);
  });

  it("mostra o selo Bug ou Melhoria ao lado da Etapa (issue #1438)", async () => {
    const bug = demanda("d-3", "O relatório some", { classificacao: "bug" });
    const melhoria = demanda("d-4", "Aviso quando a ata sair", { classificacao: "melhoria" });
    const antiga = demanda("d-5", "Pedido de antes do chat", { classificacao: null });
    montar((url) => (url === LISTA ? { status: 200, corpo: [bug, melhoria, antiga] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("O relatório some");
    const itens = within(lista()).getAllByRole("listitem");
    expect(itens.map((item) => item.textContent)).toEqual([
      "O relatório someRegistradaBug",
      "Aviso quando a ata sairRegistradaMelhoria",
      "Pedido de antes do chatRegistrada",
    ]);
  });

  it("sem conversa nenhuma, diz que ainda não há", async () => {
    montar(() => ({ status: 200, corpo: [] }));

    expect(await within(lista()).findByText("Nenhuma conversa ainda.")).toBeTruthy();
  });
});

describe("Retomar", () => {
  it("clicar numa conversa sem card retoma o chat de onde parou", async () => {
    const chamadas = montar((url, metodo) => {
      if (url === LISTA && metodo === "GET") return { status: 200, corpo: [SEM_CARD] };
      if (url === `${LISTA}/d-1` && metodo === "GET") return { status: 200, corpo: conversa("d-1") };
      if (url === `${LISTA}/d-1` && metodo === "POST") {
        const mais: FalaDoChat[] = [
          { autor: "diretor", texto: "Na Ouvidoria", fonte: null, opcoes: [], nao_bateu: false },
          { autor: "ia", texto: "O que aconteceu?", fonte: null, opcoes: [], nao_bateu: false },
        ];
        return { status: 200, corpo: conversa("d-1", { mensagens: [...conversa("d-1").mensagens, ...mais] }) };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder some/ }));

    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Sua mensagem"), { target: { value: "Na Ouvidoria" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));

    expect(await screen.findByText("O que aconteceu?")).toBeTruthy();
    expect(chamadas.find((c) => c.metodo === "POST")).toMatchObject({
      url: `${LISTA}/d-1`,
      corpo: { texto: "Na Ouvidoria", prints: [] },
    });
  });
});

describe("O custo da conversa (issue #1439)", () => {
  it("aparece no alto da conversa aberta, e nunca na lista", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      if (url === `${LISTA}/d-1`) {
        return { status: 200, corpo: conversa("d-1", { custo: { modelo: "Opus 5.5", custo_usd: 1.84 } }) };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder some/ }));

    expect(await screen.findByText("Opus 5.5 · US$ 1,84 até agora")).toBeTruthy();
    expect(within(lista()).queryByText(/US\$|Opus/)).toBeNull();
  });
});

describe("O pedido de antes do chat (issue #1386)", () => {
  it("sem conversa guardada, diz que ela não ficou aqui e não manda a tela nenhuma", async () => {
    montar((url, metodo) => {
      if (url === LISTA && metodo === "GET") return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: { detail: "Esta conversa não foi encontrada." } };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder some/ }));

    expect(await screen.findByText(SEM_CONVERSA_GUARDADA)).toBeTruthy();
    // A tela do Planejamento de antes saiu: nenhum link leva a ela.
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("Acompanhar", () => {
  it("clicar numa conversa com Vínculo mostra a conversa e O que muda", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [COM_VINCULO] };
      if (url === `${LISTA}/d-2`) {
        return { status: 200, corpo: conversa("d-2", { estado: "enviado" }) };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Aviso quando a ata sair/ }));

    const oQueMuda = await screen.findByRole("region", { name: "O que muda" });
    expect(within(oQueMuda).getByText("Agora o aviso da ata chega por e-mail.")).toBeTruthy();
    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    expect(screen.queryByLabelText("Sua mensagem")).toBeNull();
  });

  it("sem o texto da Vitta, diz Descrição em preparação", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [{ ...COM_VINCULO, o_que_muda: null }] };
      return { status: 404, corpo: { detail: "Esta conversa não foi encontrada." } };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Aviso quando a ata sair/ }));

    const oQueMuda = await screen.findByRole("region", { name: "O que muda" });
    expect(within(oQueMuda).getByText("Descrição em preparação")).toBeTruthy();
  });
});

describe("Nova conversa", () => {
  it("abre o chat do zero, e o primeiro turno faz a Demanda entrar na lista", async () => {
    let demandas: Demanda[] = [SEM_CARD];
    const chamadas = montar((url, metodo) => {
      if (url === LISTA && metodo === "GET") return { status: 200, corpo: demandas };
      if (url === `${LISTA}/d-1`) return { status: 200, corpo: conversa("d-1") };
      if (url === LISTA && metodo === "POST") {
        demandas = [demanda("d-9", "O relatório some"), SEM_CARD];
        return { status: 201, corpo: conversa("d-9") };
      }
      return { status: 404, corpo: {} };
    });
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");

    fireEvent.click(screen.getByRole("button", { name: NOVA_CONVERSA }));

    expect(screen.getByText(ABERTURA)).toBeTruthy();
    expect(screen.queryByText("Onde isso aconteceu?")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    expect(await within(lista()).findByText("O relatório some")).toBeTruthy();
    expect(chamadas.find((c) => c.metodo === "POST")).toMatchObject({ url: LISTA, corpo: { escolha: "bug" } });
  });
});

describe("Caixa alta (ADR 0080, issue #1455)", () => {
  it("o título da Demanda aparece como foi escrito, na lista e no alto da conversa", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [COM_VINCULO] };
      if (url === `${LISTA}/d-2`) return { status: 200, corpo: conversa("d-2", { estado: "enviado" }) };
      return { status: 404, corpo: {} };
    });

    const naLista = await within(lista()).findByText("Aviso quando a ata sair");
    expect(caixaDoDado(naLista)).toBe("normal-case");

    fireEvent.click(within(lista()).getByRole("button", { name: /Aviso quando a ata sair/ }));
    const titulo = await screen.findByRole("heading", { level: 2, name: "Aviso quando a ata sair" });
    expect(caixaDoDado(titulo)).toBe("normal-case");
  });
});

describe("No celular", () => {
  it("a lista é a tela de entrada, e a conversa aberta tem o caminho de volta", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      if (url === `${LISTA}/d-1`) return { status: 200, corpo: conversa("d-1") };
      return { status: 404, corpo: {} };
    });
    const painelDaLista = () => lista().parentElement as HTMLElement;
    const painelDoChat = () => screen.getByRole("region", { name: "Conversa aberta" });

    // Na largura do celular só um dos dois aparece: `hidden` esconde, e o
    // `md:` devolve os dois lado a lado na tela larga.
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    expect(painelDaLista().className).not.toMatch(/(^|\s)hidden(\s|$)/);
    expect(painelDoChat().className).toMatch(/(^|\s)hidden(\s|$)/);

    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");
    expect(painelDaLista().className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(painelDoChat().className).not.toMatch(/(^|\s)hidden(\s|$)/);

    fireEvent.click(screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA }));
    await waitFor(() => expect(painelDaLista().className).not.toMatch(/(^|\s)hidden(\s|$)/));
    expect(painelDoChat().className).toMatch(/(^|\s)hidden(\s|$)/);
  });
});
