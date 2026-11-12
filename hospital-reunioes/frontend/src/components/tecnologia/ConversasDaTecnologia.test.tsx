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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

import { ABERTURA, SEM_CONVERSA_GUARDADA } from "./ChatDaTecnologia";
import {
  AMPLIAR,
  ConversasDaTecnologia,
  NOVA_CONVERSA,
  SEM_ACESSO,
  VOLTAR_PARA_A_LISTA,
} from "./ConversasDaTecnologia";
import { ConversaDoChat, FalaDoChat } from "./chat";
import { Demanda } from "./demandas";

beforeEach(() => {
  // O jsdom não implementa `scrollIntoView`, que o `Select` da casa chama ao
  // abrir a lista de opções dos filtros (issue #1578).
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
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
function montar(servidor: Servidor, demandaInicial: string | null = null) {
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
  const arvore = (demanda: string | null) => (
    <ToastProvider>
      <ConversasDaTecnologia token="token-de-teste" demandaInicial={demanda} />
    </ToastProvider>
  );
  const { rerender } = render(arvore(demandaInicial));
  trocarDemandaInicial = (demanda) => rerender(arvore(demanda));
  return chamadas;
}

/** Remonta a aba montada com outra `demandaInicial`, como a página faz quando o endereço muda. */
let trocarDemandaInicial: (demanda: string | null) => void = () => {};

const demandaDaUrl = () => new URLSearchParams(window.location.search).get("demanda");

/** A página lê o `?demanda=` do endereço: depois de a tela escrever nele, a prop muda também. */
function aPaginaLeOEndereco() {
  trocarDemandaInicial(demandaDaUrl());
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
    expect(itens).toHaveLength(2);
    expect(within(itens[0]).getByText("Aviso quando a ata sair")).toBeTruthy();
    expect(within(itens[0]).getByText("Em produção desde v0.207.0")).toBeTruthy();
    expect(within(itens[1]).getByText("Botão de responder some na Ouvidoria")).toBeTruthy();
    expect(within(itens[1]).getByText("Registrada")).toBeTruthy();
  });

  it("mostra o selo Bug ou Melhoria ao lado da Etapa (issue #1438)", async () => {
    const bug = demanda("d-3", "O relatório some", { classificacao: "bug" });
    const melhoria = demanda("d-4", "Aviso quando a ata sair", { classificacao: "melhoria" });
    const antiga = demanda("d-5", "Pedido de antes do chat", { classificacao: null });
    montar((url) => (url === LISTA ? { status: 200, corpo: [bug, melhoria, antiga] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("O relatório some");
    const itens = within(lista()).getAllByRole("listitem");
    expect(within(itens[0]).getByText("Bug")).toBeTruthy();
    expect(within(itens[1]).getByText("Melhoria")).toBeTruthy();
    expect(within(itens[2]).queryByText(/^(Bug|Melhoria)$/)).toBeNull();
    expect(within(itens[2]).getByText("Registrada")).toBeTruthy();
  });

  it("mostra o selo Tem demonstração só no pedido com o link do vídeo (issue #1559)", async () => {
    const comVideo = demanda("d-6", "Selo na lista", { demonstracao_url: "https://youtu.be/demo" });
    const semVideo = demanda("d-7", "Sem vídeo", { demonstracao_url: null });
    montar((url) => (url === LISTA ? { status: 200, corpo: [comVideo, semVideo] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("Selo na lista");
    const itens = within(lista()).getAllByRole("listitem");
    expect(within(itens[0]).getByText("Tem demonstração")).toBeTruthy();
    expect(within(itens[1]).queryByText("Tem demonstração")).toBeNull();
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
  it("clicar numa conversa com Vínculo mostra a conversa e o Documento do card", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [COM_VINCULO] };
      if (url === `${LISTA}/d-2`) {
        return { status: 200, corpo: conversa("d-2", { estado: "enviado" }) };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Aviso quando a ata sair/ }));

    const oQueMuda = await screen.findByRole("region", { name: "Documento do card" });
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

    const oQueMuda = await screen.findByRole("region", { name: "Documento do card" });
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
    const chat = screen.getByRole("region", { name: "Conversa aberta" });
    fireEvent.click(within(chat).getByRole("button", { name: "Bug" }));
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

describe("O Desenvolvedor (issue #1531, ADR 0083)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const TODAS = `${LISTA}?filtro=todas`;
  const PARA_MIM = `${LISTA}?filtro=para_mim`;
  const DO_DIRETOR = demanda("d-7", "O relatório some", { minha: false, autor: "Diretor do Hospital" });
  const COM_CARD_DE_OUTRO = demanda("d-8", "O botão sumiu", {
    minha: false,
    autor: "Outro Diretor",
    etapa: "em_desenvolvimento",
    tem_vinculo: true,
    issue_numero: 912,
    issue_url: "https://github.com/pedrorezendefig/hospital-reunioes/issues/912",
  });

  it("vê o filtro Todas, que traz as Demandas de todos com o autor em cada linha", async () => {
    const chamadas = montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [SEM_CARD] };
      if (url === TODAS) return { status: 200, corpo: [DO_DIRETOR, { ...SEM_CARD, autor: "Pedro Vitta" }] };
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await screen.findByRole("button", { name: "Todas" }));

    await within(lista()).findByText("O relatório some");
    const itens = within(lista()).getAllByRole("listitem");
    expect(within(itens[0]).getByText("O relatório some")).toBeTruthy();
    expect(within(itens[0]).getByText("Diretor do Hospital")).toBeTruthy();
    expect(within(itens[1]).getByText("Botão de responder some na Ouvidoria")).toBeTruthy();
    expect(within(itens[1]).getByText("Pedro Vitta")).toBeTruthy();
    expect(chamadas.some((c) => c.url === TODAS)).toBe(true);
  });

  it("quem não é Desenvolvedor não vê o filtro", async () => {
    montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: false } };
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });

    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    expect(screen.queryByRole("button", { name: "Todas" })).toBeNull();
  });

  it("abre a Demanda de outro autor só para ler: a entrevista inteira e os Anexos", async () => {
    montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [DO_DIRETOR] };
      if (url === `${LISTA}/d-7`) {
        return {
          status: 200,
          corpo: conversa("d-7", {
            anexos: 1,
            anexos_da_demanda: [{ nome: "tela.png", tipo: "image/png", url: "https://storage.local/tela.png?t=1" }],
          }),
        };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /O relatório some/ }));

    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    expect(screen.getByText(ABERTURA)).toBeTruthy();
    const anexo = await screen.findByRole("link", { name: /tela\.png/ });
    expect(anexo.getAttribute("href")).toBe("https://storage.local/tela.png?t=1");
    expect(screen.queryByLabelText("Sua mensagem")).toBeNull();
  });

  it("vê o número e o link da issue na Demanda que já tem card", async () => {
    montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [COM_CARD_DE_OUTRO] };
      if (url === `${LISTA}/d-8`) return { status: 200, corpo: conversa("d-8", { estado: "enviado" }) };
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /O botão sumiu/ }));

    const link = await screen.findByRole("link", { name: "#912" });
    expect(link.getAttribute("href")).toBe("https://github.com/pedrorezendefig/hospital-reunioes/issues/912");
  });

  // ─── O Responsável e o Para mim (issue #1533, ADR 0083, decisão 5) ────────

  it("a lista abre em Para mim e mostra só as Demandas de que ele é Responsável", async () => {
    const minha = demanda("d-9", "Agenda de retorno", {
      tem_vinculo: true,
      etapa: "em_analise",
      responsavel: "Pedro Vitta",
    });
    const chamadas = montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [minha] };
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });

    await within(lista()).findByText("Agenda de retorno");
    expect(screen.getByRole("button", { name: "Para mim" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(lista()).getAllByRole("listitem")).toHaveLength(1);
    const listas = chamadas.filter((c) => c.url.startsWith(LISTA));
    expect(listas.map((c) => c.url)).toEqual([PARA_MIM]);
  });

  it("o recorte do Desenvolvedor é Para mim, Minhas e Todas", async () => {
    montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      return { status: 200, corpo: [] };
    });

    const filtros = await screen.findByRole("group", { name: "Recorte" });
    expect(within(filtros).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Para mim",
      "Minhas",
      "Todas",
    ]);
  });
});

describe("O Responsável na lista (issue #1533, ADR 0083)", () => {
  it("o diretor vê quem cuida de cada pedido que já virou card", async () => {
    const comResponsavel = demanda("d-10", "Agenda de retorno", {
      tem_vinculo: true,
      etapa: "em_analise",
      responsavel: "Lucas Sampaio",
    });
    montar((url) => (url === LISTA ? { status: 200, corpo: [comResponsavel, SEM_CARD] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("Agenda de retorno");
    const itens = within(lista()).getAllByRole("listitem");
    expect(within(itens[0]).getByText("Responsável")).toBeTruthy();
    expect(within(itens[0]).getByText("Lucas Sampaio")).toBeTruthy();
    expect(within(itens[0]).getByText("Em análise")).toBeTruthy();
    expect(within(itens[1]).queryByText("Responsável")).toBeNull();
  });

  it("o Desenvolvedor vê o autor e o Responsável em cada linha", async () => {
    const deOutro = demanda("d-11", "O botão sumiu", {
      minha: false,
      autor: "Diretor do Hospital",
      tem_vinculo: true,
      etapa: "em_analise",
      responsavel: "Pedro Rib",
    });
    montar((url) => {
      if (url === "/api/admin/tecnologia/eu") return { status: 200, corpo: { desenvolvedor: true } };
      if (url === `${LISTA}?filtro=todas`) return { status: 200, corpo: [deOutro] };
      return { status: 200, corpo: [] };
    });

    fireEvent.click(await screen.findByRole("button", { name: "Todas" }));

    await within(lista()).findByText("O botão sumiu");
    const [item] = within(lista()).getAllByRole("listitem");
    expect(within(item).getByText("Pediu")).toBeTruthy();
    expect(within(item).getByText("Diretor do Hospital")).toBeTruthy();
    expect(within(item).getByText("Responsável")).toBeTruthy();
    expect(within(item).getByText("Pedro Rib")).toBeTruthy();
  });
});

describe("A Conversa da Demanda e o aviso do sino (issue #1537, ADR 0083)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const TODAS = `${LISTA}?filtro=todas`;
  const PARA_MIM = `${LISTA}?filtro=para_mim`;
  const DO_DIRETOR = demanda("d-7", "O relatório some", { minha: false, autor: "Diretor do Hospital" });
  const CONVERSA_DA_DEMANDA = { mensagens: [], mencionaveis: [] };

  it("a Demanda aberta mostra a Conversa da Demanda numa área própria, e a conversa nova não", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [COM_VINCULO] };
      if (url === `${LISTA}/d-2`) return { status: 200, corpo: conversa("d-2", { estado: "enviado" }) };
      if (url === `${LISTA}/d-2/conversa`) return { status: 200, corpo: CONVERSA_DA_DEMANDA };
      return { status: 404, corpo: {} };
    });

    await within(lista()).findByText("Aviso quando a ata sair");
    expect(screen.queryByRole("region", { name: "Conversa da Demanda" })).toBeNull();

    fireEvent.click(within(lista()).getByRole("button", { name: /Aviso quando a ata sair/ }));

    expect(await screen.findByRole("region", { name: "Conversa da Demanda" })).toBeTruthy();
  });

  it("o aviso do sino abre a Demanda do diretor", async () => {
    const chamadas = montar(
      (url) => {
        if (url === EU) return { status: 200, corpo: { desenvolvedor: false } };
        if (url === LISTA) return { status: 200, corpo: [SEM_CARD, COM_VINCULO] };
        if (url === `${LISTA}/d-2`) return { status: 200, corpo: conversa("d-2", { estado: "enviado" }) };
        if (url === `${LISTA}/d-2/conversa`) return { status: 200, corpo: CONVERSA_DA_DEMANDA };
        return { status: 404, corpo: {} };
      },
      "d-2",
    );

    expect(await screen.findByText("Agora o aviso da ata chega por e-mail.")).toBeTruthy();
    await waitFor(() => expect(chamadas.some((c) => c.url === `${LISTA}/d-2/conversa`)).toBe(true));
    expect(within(lista()).getByRole("button", { name: /Aviso quando a ata sair/ }).getAttribute("aria-current")).toBe(
      "true",
    );
  });

  it("com a Demanda escondida pelo Para mim, o filtro muda para Todas e o card abre (issue #1586)", async () => {
    const chamadas = montar(
      (url) => {
        if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
        if (url === PARA_MIM) return { status: 200, corpo: [] };
        if (url === TODAS) return { status: 200, corpo: [SEM_CARD, DO_DIRETOR] };
        if (url === `${LISTA}/d-7`) return { status: 200, corpo: conversa("d-7") };
        if (url === `${LISTA}/d-7/conversa`) return { status: 200, corpo: CONVERSA_DA_DEMANDA };
        return { status: 404, corpo: {} };
      },
      "d-7",
    );

    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    expect(await screen.findByRole("region", { name: "Conversa da Demanda" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Todas" }).getAttribute("aria-pressed")).toBe("true");
    expect(chamadas.filter((c) => c.url.startsWith(`${LISTA}?`)).map((c) => c.url)).toEqual([PARA_MIM, TODAS]);
  });
});

describe("Envio falhou (issue #1535, ADR 0083, decisão 7)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const REENVIAR = `${LISTA}/d-1/reenviar`;
  const FALHOU = demanda("d-1", "Botão de responder some na Ouvidoria", {
    classificacao: "bug",
    envio_falhou: true,
    envio_motivo: null,
  });
  const CRIADA = demanda("d-1", "Botão de responder some na Ouvidoria", {
    classificacao: "bug",
    tem_vinculo: true,
    etapa: "em_analise",
    envio_falhou: false,
  });
  const RESUMO = {
    titulo: "Botão de responder some na Ouvidoria",
    onde: "Ouvidoria",
    o_que_aconteceu: "O botão sumiu",
    o_que_esperava: "Ver o botão",
    como_repetir: "não informado",
    criterios: ["O botão aparece"],
  };
  const RESUMIDA = conversa("d-1", { estado: "resumido", resumo: RESUMO });

  function linha(titulo: RegExp) {
    return within(lista()).getByRole("button", { name: titulo });
  }

  it("o diretor vê o selo Envio falhou na linha do pedido", async () => {
    montar((url) => (url === LISTA ? { status: 200, corpo: [FALHOU, COM_VINCULO] } : { status: 404, corpo: {} }));

    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    expect(within(linha(/Botão de responder/)).getByText("Envio falhou")).toBeTruthy();
    expect(within(linha(/Aviso quando a ata/)).queryByText("Envio falhou")).toBeNull();
  });

  it("o diretor clica em Reenviar, o card nasce e o selo sai, sem ver motivo técnico", async () => {
    let enviado = false;
    const chamadas = montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: [enviado ? CRIADA : FALHOU] };
      if (url === `${LISTA}/d-1` && metodo === "GET") return { status: 200, corpo: RESUMIDA };
      if (url === REENVIAR && metodo === "POST") {
        enviado = true;
        return { status: 200, corpo: { ...RESUMIDA, estado: "enviado" } };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    const aviso = await screen.findByRole("region", { name: "Envio falhou" });
    expect(aviso.textContent).not.toContain("GitHub");
    fireEvent.click(within(aviso).getByRole("button", { name: "Reenviar" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: "Envio falhou" })).toBeNull());
    expect(chamadas.filter((c) => c.url === REENVIAR && c.metodo === "POST")).toHaveLength(1);
    await waitFor(() => expect(within(linha(/Botão de responder/)).queryByText("Envio falhou")).toBeNull());
  });

  it("o Desenvolvedor filtra Envio falhou, vê o motivo e reenvia o pedido de outro autor", async () => {
    const deOutro = { ...FALHOU, minha: false, autor: "Diretor do Hospital", envio_motivo: "GitHub respondeu 502" };
    const chamadas = montar((url, metodo) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      // A lista abre em Para mim, e a rota de verdade devolve aqui as falhas de
      // todos os autores, sem card e sem Responsavel: e o que prova
      // `test_envio_falhou_partindo_de_para_mim_mostra_as_falhas_de_todos`.
      if (url === `${LISTA}?filtro=para_mim&envio_falhou=true`) return { status: 200, corpo: [deOutro] };
      if (url === `${LISTA}/d-1` && metodo === "GET") return { status: 200, corpo: RESUMIDA };
      if (url === REENVIAR) return { status: 200, corpo: { ...RESUMIDA, estado: "enviado" } };
      return { status: 200, corpo: [] };
    });

    fireEvent.click(await screen.findByRole("switch", { name: "Só envio falhou" }));
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));

    const aviso = await screen.findByRole("region", { name: "Envio falhou" });
    expect(within(aviso).getByText("GitHub respondeu 502")).toBeTruthy();
    fireEvent.click(within(aviso).getByRole("button", { name: "Reenviar" }));
    await waitFor(() => expect(chamadas.some((c) => c.url === REENVIAR && c.metodo === "POST")).toBe(true));
  });

  it("o Reenviar que falha de novo mostra a frase do servidor e o aviso fica", async () => {
    montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: [FALHOU] };
      if (url === `${LISTA}/d-1` && metodo === "GET") return { status: 200, corpo: RESUMIDA };
      if (url === REENVIAR) return { status: 502, corpo: { detail: "O GitHub não respondeu. Tente de novo." } };
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    const aviso = await screen.findByRole("region", { name: "Envio falhou" });
    fireEvent.click(within(aviso).getByRole("button", { name: "Reenviar" }));

    expect(await within(aviso).findByText("O GitHub não respondeu. Tente de novo.")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Envio falhou" })).toBeTruthy();
  });

  it("o Criar o card que falha faz a lista reler e mostrar o selo", async () => {
    let falhou = false;
    montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: [falhou ? FALHOU : { ...FALHOU, envio_falhou: false }] };
      if (url === `${LISTA}/d-1` && metodo === "GET") return { status: 200, corpo: RESUMIDA };
      if (url === `${LISTA}/d-1/criar-card` && metodo === "POST") {
        falhou = true;
        return { status: 502, corpo: { detail: "O GitHub não respondeu. Tente de novo." } };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Criar o card" }));

    await waitFor(() => expect(within(linha(/Botão de responder/)).getByText("Envio falhou")).toBeTruthy());
  });
});

describe("Designação falhou (issue #1536, ADR 0083, decisão 7)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const PARA_MIM = `${LISTA}?filtro=para_mim`;
  const DESIGNAR = `${LISTA}/d-1/designar-de-novo`;
  const SEM_DONO = demanda("d-1", "Botão de responder some na Ouvidoria", {
    classificacao: "bug",
    tem_vinculo: true,
    etapa: "em_analise",
    issue_numero: 900,
    designacao_falhou: true,
    envio_motivo: "A issue #900 nasceu sem o Responsável (lucas-vitta)",
  });
  const DESIGNADA = { ...SEM_DONO, designacao_falhou: false, envio_motivo: null };

  it("o Desenvolvedor vê o estado com o motivo e Designar de novo o resolve", async () => {
    let designada = false;
    const chamadas = montar((url, metodo) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [designada ? DESIGNADA : SEM_DONO] };
      if (url === DESIGNAR && metodo === "POST") {
        designada = true;
        return { status: 200, corpo: DESIGNADA };
      }
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    const aviso = await screen.findByRole("region", { name: "Designação falhou" });
    expect(within(aviso).getByText("A issue #900 nasceu sem o Responsável (lucas-vitta)")).toBeTruthy();
    fireEvent.click(within(aviso).getByRole("button", { name: "Designar de novo" }));

    await waitFor(() => expect(screen.queryByRole("region", { name: "Designação falhou" })).toBeNull());
    expect(chamadas.filter((c) => c.url === DESIGNAR && c.metodo === "POST")).toHaveLength(1);
  });

  it("o Designar de novo que falha mostra a frase do servidor e o aviso fica", async () => {
    montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === PARA_MIM) return { status: 200, corpo: [SEM_DONO] };
      if (url === DESIGNAR) return { status: 502, corpo: { detail: "O GitHub não respondeu. Tente de novo." } };
      return { status: 404, corpo: {} };
    });

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    const aviso = await screen.findByRole("region", { name: "Designação falhou" });
    fireEvent.click(within(aviso).getByRole("button", { name: "Designar de novo" }));

    expect(await within(aviso).findByText("O GitHub não respondeu. Tente de novo.")).toBeTruthy();
  });

  it("o diretor não vê o estado nem o botão", async () => {
    montar((url) => (url === LISTA ? { status: 200, corpo: [SEM_DONO] } : { status: 404, corpo: {} }));

    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));

    await screen.findByRole("heading", { name: "Botão de responder some na Ouvidoria" });
    expect(screen.queryByRole("region", { name: "Designação falhou" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Designar de novo" })).toBeNull();
  });
});

describe("Apagar a Demanda (issue #1549, ADR 0084, decisão 2)", () => {
  const APAGAR_URL = `${LISTA}/d-1`;
  const PODE = demanda("d-1", "Botão de responder some na Ouvidoria", { pode_apagar: true });
  const NAO_PODE = demanda("d-1", "Botão de responder some na Ouvidoria", { pode_apagar: false });

  function dialogo() {
    return screen.queryByRole("dialog");
  }

  it("quem pode apagar vê o botão Apagar na conversa aberta, e quem não pode não vê", async () => {
    montar((url) => (url === LISTA ? { status: 200, corpo: [PODE] } : { status: 200, corpo: conversa("d-1") }));
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    expect(await screen.findByRole("button", { name: "Apagar" })).toBeTruthy();
    cleanup();

    montar((url) => (url === LISTA ? { status: 200, corpo: [NAO_PODE] } : { status: 200, corpo: conversa("d-1") }));
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    await screen.findByText("Onde isso aconteceu?");
    expect(screen.queryByRole("button", { name: "Apagar" })).toBeNull();
  });

  it("o clique pede confirmação antes de apagar, e Cancelar não apaga nada", async () => {
    const chamadas = montar((url) =>
      url === LISTA ? { status: 200, corpo: [PODE] } : { status: 200, corpo: conversa("d-1") },
    );
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));

    const confirmacao = await screen.findByRole("dialog");
    expect(within(confirmacao).getByRole("heading", { name: "Apagar este pedido?" })).toBeTruthy();
    expect(chamadas.some((c) => c.metodo === "DELETE")).toBe(false);
    fireEvent.click(within(confirmacao).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(dialogo()).toBeNull());
    expect(chamadas.some((c) => c.metodo === "DELETE")).toBe(false);
  });

  it("confirmar apaga, e o pedido some da lista", async () => {
    let apagada = false;
    const chamadas = montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: apagada ? [COM_VINCULO] : [PODE, COM_VINCULO] };
      if (url === APAGAR_URL && metodo === "DELETE") {
        apagada = true;
        return { status: 204, corpo: null };
      }
      return { status: 200, corpo: conversa("d-1") };
    });
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));

    const confirmacao = await screen.findByRole("dialog");
    fireEvent.click(within(confirmacao).getByRole("button", { name: "Apagar" }));

    await waitFor(() => expect(within(lista()).queryByText("Botão de responder some na Ouvidoria")).toBeNull());
    expect(chamadas.filter((c) => c.url === APAGAR_URL && c.metodo === "DELETE")).toHaveLength(1);
    expect(within(lista()).getByText("Aviso quando a ata sair")).toBeTruthy();
  });

  it("a recusa do servidor aparece na tela e o pedido fica", async () => {
    montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: [PODE] };
      if (url === APAGAR_URL && metodo === "DELETE") {
        return { status: 502, corpo: { detail: "O GitHub não respondeu, e o card não foi fechado lá." } };
      }
      return { status: 200, corpo: conversa("d-1") };
    });
    fireEvent.click(await within(lista()).findByRole("button", { name: /Botão de responder/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Apagar" }));

    expect(await screen.findByText("O GitHub não respondeu, e o card não foi fechado lá.")).toBeTruthy();
    expect(within(lista()).getByText("Botão de responder some na Ouvidoria")).toBeTruthy();
  });
});

/** Escolhe uma opção num campo de filtro: abre o campo pelo rótulo e clica na opção. */
function escolher(campo: string, opcao: string) {
  const filtros = screen.getByRole("region", { name: "Filtros da lista" });
  fireEvent.click(within(filtros).getByRole("combobox", { name: campo }));
  fireEvent.click(screen.getByRole("option", { name: opcao }));
}

describe("A barra de filtros por categoria (issue #1578, emenda da ADR 0084)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const DESENVOLVEDORES = "/api/admin/tecnologia/desenvolvedores";
  const QUEM_CUIDA = [
    { id: "P1", nome: "Pedro Vitta", padrao: true },
    { id: "P4", nome: "Pedro Rib", padrao: false },
  ];

  function filtros() {
    return screen.getByRole("region", { name: "Filtros da lista" });
  }

  /** O rótulo visível de cada campo, na ordem da barra. */
  function campos() {
    return within(filtros())
      .getAllByRole("combobox")
      .map((c) => document.querySelector(`label[for="${c.id}"]`)?.textContent);
  }

  function comoDiretor() {
    return montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: false } };
      if (url.startsWith(LISTA)) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });
  }

  it("a busca pelo título vai ao servidor", async () => {
    const chamadas = comoDiretor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar pelo título" }), {
      target: { value: "relatorio" },
    });

    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain(`${LISTA}?busca=relatorio`));
  });

  it("o diretor combina Tipo e Etapa, e Todos desfaz o Tipo", async () => {
    const chamadas = comoDiretor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    escolher("Tipo", "Bug");
    escolher("Etapa", "Em produção");
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain(`${LISTA}?tipo=bug&etapa=em_producao`));
    expect(within(filtros()).getByRole("combobox", { name: "Tipo" }).textContent).toBe("Bug");

    escolher("Tipo", "Todos");
    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(`${LISTA}?etapa=em_producao`));
  });

  it("o diretor vê Tipo, Etapa e Origem, sem o recorte, o Responsável e o Envio falhou", async () => {
    comoDiretor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    expect(campos()).toEqual(["Tipo", "Etapa", "Origem"]);
    expect(within(filtros()).queryByRole("group", { name: "Recorte" })).toBeNull();
    expect(within(filtros()).queryByRole("switch")).toBeNull();
  });

  it("o Desenvolvedor combina Responsável e Envio falhou com o Para mim", async () => {
    // O que a rota de verdade responde a essa combinacao: a falha de outro autor,
    // porque Envio falhou nao e cortado por Responsavel (a Demanda sem card nao
    // tem um), como prova o teste de rota de mesmo nome no backend.
    const COMBINADA = `${LISTA}?filtro=para_mim&tipo=melhoria&responsavel=P4&envio_falhou=true`;
    const falhaDeOutro = demanda("d-9", "Relatorio de custo por setor", {
      classificacao: "melhoria",
      envio_falhou: true,
      minha: false,
      autor: "Diretor do Hospital",
    });
    const chamadas = montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === DESENVOLVEDORES) return { status: 200, corpo: QUEM_CUIDA };
      if (url === COMBINADA) return { status: 200, corpo: [falhaDeOutro] };
      if (url.startsWith(LISTA)) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    await waitFor(() => expect(campos()).toEqual(["Tipo", "Etapa", "Origem", "Responsável"]));

    const recorte = within(filtros()).getByRole("group", { name: "Recorte" });
    expect(within(recorte).getAllByRole("button").map((b) => b.textContent)).toEqual(["Para mim", "Minhas", "Todas"]);
    expect(within(recorte).getByRole("button", { name: "Para mim" }).getAttribute("aria-pressed")).toBe("true");

    escolher("Responsável", "Pedro Rib");
    const soFalhas = within(filtros()).getByRole("switch", { name: "Só envio falhou" });
    expect(soFalhas.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(soFalhas);
    expect(soFalhas.getAttribute("aria-checked")).toBe("true");
    escolher("Tipo", "Melhoria");

    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(COMBINADA));
    expect(await within(lista()).findByText("Relatorio de custo por setor")).toBeTruthy();
    expect(within(lista()).queryByText("Botão de responder some na Ouvidoria")).toBeNull();
  });

  it("Limpar filtros aparece só com filtro ativo e volta tudo ao padrão, menos o recorte", async () => {
    const chamadas = montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === DESENVOLVEDORES) return { status: 200, corpo: QUEM_CUIDA };
      if (url.startsWith(LISTA)) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    await within(filtros()).findByRole("switch", { name: "Só envio falhou" });
    expect(within(filtros()).queryByRole("button", { name: "Limpar filtros" })).toBeNull();

    escolher("Etapa", "Planejada");
    fireEvent.click(within(filtros()).getByRole("switch", { name: "Só envio falhou" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar pelo título" }), { target: { value: "ata" } });
    await waitFor(() =>
      expect(chamadas.at(-1)?.url).toBe(`${LISTA}?filtro=para_mim&busca=ata&etapa=planejada&envio_falhou=true`),
    );

    fireEvent.click(within(filtros()).getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(`${LISTA}?filtro=para_mim`));
    expect((screen.getByRole("searchbox", { name: "Buscar pelo título" }) as HTMLInputElement).value).toBe("");
    expect(within(filtros()).getByRole("combobox", { name: "Etapa" }).textContent).toBe("Todas");
    expect(within(filtros()).getByRole("switch", { name: "Só envio falhou" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    expect(within(filtros()).queryByRole("button", { name: "Limpar filtros" })).toBeNull();
  });

  it("a barra fica em cima, fora da coluna da lista", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });
    const painelDaLista = () => lista().parentElement as HTMLElement;

    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    expect(painelDaLista().contains(filtros())).toBe(false);
    expect(filtros().compareDocumentPosition(lista()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("O pedido ao lado da lista e o Ampliar (issue #1593)", () => {
  const OUTRO = demanda("d-3", "Relatório de leitos atrasa");
  const recolhida = /(^|\s)md:hidden(\s|$)/;

  function comDuas() {
    return montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD, OUTRO] };
      if (url === `${LISTA}/d-1`) return { status: 200, corpo: conversa("d-1") };
      if (url === `${LISTA}/d-3`) return { status: 200, corpo: conversa("d-3") };
      return { status: 404, corpo: {} };
    });
  }

  const painelDaLista = () => lista().parentElement as HTMLElement;
  const filtros = () => screen.getByRole("region", { name: "Filtros da lista" });
  const aberto = () => screen.getByRole("region", { name: "Conversa aberta" });
  const voltar = () => screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA });
  const cardDe = (titulo: RegExp) =>
    within(lista())
      .getAllByRole("listitem")
      .find((item) => within(item).queryByRole("button", { name: titulo })) as HTMLElement;

  /** A lista e a barra à vista na tela larga, e o Voltar só no celular. */
  function listaAoLado() {
    expect(painelDaLista().className).not.toMatch(recolhida);
    expect(filtros().className).not.toMatch(recolhida);
    expect(voltar().className).toMatch(recolhida);
  }

  /** A lista e a barra recolhidas na tela larga, e o Voltar à vista. */
  function listaRecolhida() {
    expect(painelDaLista().className).toMatch(recolhida);
    expect(filtros().className).toMatch(recolhida);
    expect(voltar().className).not.toMatch(recolhida);
  }

  it("em tela larga, o clique no cartão abre o pedido com a lista visível", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");

    listaAoLado();
  });

  it("o Ampliar do cartão abre o pedido com a lista recolhida, e o Voltar devolve a lista", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(within(cardDe(/Botão de responder some/)).getByRole("button", { name: AMPLIAR }));
    await screen.findByText("Onde isso aconteceu?");
    listaRecolhida();

    fireEvent.click(voltar());
    await waitFor(() => expect(painelDaLista().className).not.toMatch(recolhida));
    expect(filtros().className).not.toMatch(recolhida);
  });

  it("o Ampliar também fica no topo do pedido aberto ao lado, e faz o mesmo", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");
    listaAoLado();

    fireEvent.click(within(aberto()).getByRole("button", { name: AMPLIAR }));
    listaRecolhida();
    // Ampliado, o pedido não oferece Ampliar de novo: o caminho é o Voltar.
    expect(within(aberto()).queryByRole("button", { name: AMPLIAR })).toBeNull();

    fireEvent.click(voltar());
    await waitFor(() => expect(painelDaLista().className).not.toMatch(recolhida));

    // De volta ao lado da lista, o Ampliar do topo amplia de novo.
    fireEvent.click(within(aberto()).getByRole("button", { name: AMPLIAR }));
    listaRecolhida();
  });

  it("depois de ampliar um pedido, o clique em outro cartão abre ao lado", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(within(cardDe(/Botão de responder some/)).getByRole("button", { name: AMPLIAR }));
    await screen.findByText("Onde isso aconteceu?");
    listaRecolhida();
    fireEvent.click(voltar());

    fireEvent.click(within(lista()).getByRole("button", { name: /Relatório de leitos atrasa/ }));
    await waitFor(() => expect(cardDe(/Relatório de leitos/).querySelector("[aria-current]")).toBeTruthy());
    listaAoLado();
  });

  it("o Ampliar do cartão fica visível sem passar o mouse, e o Conversar segue no hover", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    const card = cardDe(/Botão de responder some/);

    const ampliar = within(card).getByRole("button", { name: AMPLIAR }).className.split(/\s+/);
    expect(ampliar.filter((c) => /opacity-0/.test(c))).toEqual([]);
    expect(ampliar).toContain("md:inline-flex");
    const conversar = within(card).getByRole("button", { name: "Conversar" }).className.split(/\s+/);
    expect(conversar).toContain("md:opacity-0");
  });
});

describe("O card da conversa (issue #1578)", () => {
  const COMPLETO = demanda("d-c", "Ata de reunião longa para com erro", {
    criado_em: "2026-11-01T13:00:00Z",
    etapa: "em_desenvolvimento",
    tem_vinculo: true,
    classificacao: "bug",
    origem: "diretor",
    autor: "Felipe Malafaia",
    responsavel: "Pedro Rezende",
    partes_entregues: 2,
    partes_total: 5,
  });

  function comCard() {
    return montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [COMPLETO] };
      if (url === `${LISTA}/d-c/conversa`) return { status: 200, corpo: { mensagens: [], mencionaveis: [] } };
      return { status: 404, corpo: {} };
    });
  }

  async function card() {
    await within(lista()).findByText("Ata de reunião longa para com erro");
    return within(lista()).getAllByRole("listitem")[0];
  }

  it("mostra a data de abertura, quem pediu e quem cuida com as iniciais, e a Etapa", async () => {
    comCard();
    const item = await card();

    expect(within(item).getByText(/^Aberto em 01\/11/)).toBeTruthy();
    expect(within(item).getByText("Felipe Malafaia")).toBeTruthy();
    expect(within(item).getByText("FM")).toBeTruthy();
    expect(within(item).getByText("Pedro Rezende")).toBeTruthy();
    expect(within(item).getByText("PR")).toBeTruthy();
    expect(within(item).getByText("Em desenvolvimento")).toBeTruthy();
    expect(within(item).getByText("Bug")).toBeTruthy();
    expect(within(item).getByText("Pedido do diretor")).toBeTruthy();
  });

  it("o PRD com partes mostra X de Y partes e a barra de progresso", async () => {
    comCard();
    const item = await card();

    expect(within(item).getByText("2 de 5 partes")).toBeTruthy();
    const barra = within(item).getByRole("progressbar", { name: "Partes entregues" });
    expect(barra.getAttribute("aria-valuenow")).toBe("2");
    expect(barra.getAttribute("aria-valuemax")).toBe("5");
  });

  it("tem borda fora do hover, transição no hover e no foco, e não se move com motion-reduce", async () => {
    comCard();
    const item = await card();
    const contorno = item.firstElementChild as HTMLElement;

    expect(contorno.className).toMatch(/(^|\s)border(\s|$)/);
    expect(contorno.className).not.toMatch(/border-transparent/);
    expect(contorno.className).toMatch(/hover:shadow/);
    expect(contorno.className).toMatch(/focus-within:/);
    expect(contorno.className).toMatch(/(^|\s)transition/);
    // O translate do hover só existe sob motion-safe: com prefers-reduced-motion o card não pula.
    const classes = contorno.className.split(/\s+/);
    expect(classes).toContain("motion-safe:hover:-translate-y-0.5");
    const comTranslate = classes.filter((c) => /translate/.test(c));
    expect(comTranslate.length).toBeGreaterThan(0);
    for (const c of comTranslate) expect(c.startsWith("motion-safe:")).toBe(true);
  });

  it("Conversar abre a Demanda com a caixa da Conversa da Demanda em foco", async () => {
    comCard();
    const item = await card();

    fireEvent.click(within(item).getByRole("button", { name: "Conversar" }));

    const caixa = await screen.findByRole("textbox", { name: "Mensagem para a Conversa" });
    await waitFor(() => expect(document.activeElement).toBe(caixa));
  });

  it("clicar no card abre a Demanda sem roubar o foco para a Conversa", async () => {
    comCard();
    const item = await card();

    fireEvent.click(within(item).getByRole("button", { name: /Ata de reunião longa/ }));

    const caixa = await screen.findByRole("textbox", { name: "Mensagem para a Conversa" });
    expect(document.activeElement).not.toBe(caixa);
  });

  it("na vista ao lado a Conversa da Demanda fica embaixo do documento, sem terceira coluna (issue #1593)", async () => {
    comCard();
    const item = await card();

    fireEvent.click(within(item).getByRole("button", { name: /Ata de reunião longa/ }));

    const conversaDaDemanda = await screen.findByRole("region", { name: "Conversa da Demanda" });
    const coluna = conversaDaDemanda.parentElement as HTMLElement;
    expect(coluna.className).not.toMatch(/xl:sticky/);
    expect((coluna.parentElement as HTMLElement).className).not.toMatch(/xl:grid-cols-/);
    const documento = screen.getByRole("heading", { name: "Ata de reunião longa para com erro" });
    expect(documento.compareDocumentPosition(conversaDaDemanda) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("ampliado, a Conversa da Demanda fica numa coluna à direita, fixa na rolagem", async () => {
    comCard();
    const item = await card();

    fireEvent.click(within(item).getByRole("button", { name: AMPLIAR }));

    const conversaDaDemanda = await screen.findByRole("region", { name: "Conversa da Demanda" });
    const coluna = conversaDaDemanda.parentElement as HTMLElement;
    expect(coluna.className).toMatch(/xl:sticky/);
    expect((coluna.parentElement as HTMLElement).className).toMatch(/xl:grid-cols-/);
  });
});

describe("Os cards que a Vitta abre pelo terminal (issue #1554, ADR 0084, decisão 4)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const DO_TERMINAL = demanda("d-v", "Ouvidoria: prazo por setor", {
    etapa: "em_analise",
    tem_vinculo: true,
    minha: false,
    origem: "vitta",
    o_que_muda: "**O que muda:** o prazo aparece por setor.",
  });
  const DO_DIRETOR = demanda("d-d", "Botão de imprimir", {
    etapa: "em_analise",
    tem_vinculo: true,
    origem: "diretor",
  });

  function comoDiretor(extra: (url: string) => Resposta | null = () => null) {
    return montar((url) => {
      const especial = extra(url);
      if (especial) return especial;
      if (url === EU) return { status: 200, corpo: { desenvolvedor: false } };
      if (url.startsWith(LISTA + "?") || url === LISTA) return { status: 200, corpo: [DO_TERMINAL, DO_DIRETOR] };
      if (url === `${LISTA}/d-v/conversa`) return { status: 200, corpo: { mensagens: [], mencionaveis: [] } };
      return { status: 404, corpo: {} };
    });
  }

  it("cada linha leva o selo Vitta ou Pedido do diretor", async () => {
    comoDiretor();

    await within(lista()).findByText("Ouvidoria: prazo por setor");
    const itens = within(lista()).getAllByRole("listitem");
    expect(within(itens[0]).getByText("Ouvidoria: prazo por setor")).toBeTruthy();
    expect(within(itens[0]).getByText("Vitta")).toBeTruthy();
    expect(within(itens[1]).getByText("Botão de imprimir")).toBeTruthy();
    expect(within(itens[1]).getByText("Pedido do diretor")).toBeTruthy();
  });

  it("o filtro Origem pede ao servidor só os cards daquela origem", async () => {
    const chamadas = comoDiretor();
    await within(lista()).findByText("Ouvidoria: prazo por setor");

    escolher("Origem", "Vitta");
    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(`${LISTA}?origem=vitta`));

    escolher("Origem", "Pedido do diretor");
    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(`${LISTA}?origem=diretor`));
  });

  it("o card Vitta abre o documento e a Conversa da Demanda, sem o chat do agente", async () => {
    const chamadas = comoDiretor();
    await within(lista()).findByText("Ouvidoria: prazo por setor");

    fireEvent.click(within(lista()).getByRole("button", { name: /Ouvidoria: prazo por setor/ }));

    expect(await screen.findByRole("region", { name: "Conversa da Demanda" })).toBeTruthy();
    const aberta = screen.getByRole("region", { name: "Conversa aberta" });
    expect(within(aberta).getByText("o prazo aparece por setor.")).toBeTruthy();
    expect(within(aberta).queryByText(ABERTURA)).toBeNull();
    expect(chamadas.map((c) => c.url)).not.toContain(`${LISTA}/d-v`);
  });
});

describe("Revisar com o código de hoje (issue #1557, ADR 0084, decisão 3)", () => {
  const REVISAO = `${LISTA}/d-2/revisao`;
  const CARD = demanda("d-2", "Retorno marcado na saída", {
    etapa: "em_analise",
    tem_vinculo: true,
    classificacao: "melhoria",
    pode_revisar: true,
  });
  const EM_REVISAO = { ...CARD, pode_revisar: false, em_revisao: true };
  const ESTIMATIVA = { modelo: "Opus 5.5", minimo_usd: 0.42, maximo_usd: 3.1 };
  const ITEM = "A recepção já marca o retorno na saída do paciente.";
  const NA_REVISAO = conversa("d-2", {
    planejamento: true,
    mensagens: [
      {
        autor: "diretor",
        texto: "Só a recepção.",
        fonte: null,
        opcoes: [],
        nao_bateu: false,
        respondido_por: "Diretor do Hospital",
      },
      {
        autor: "ia",
        texto: "Retrato de hoje: o que o sistema já faz, o que mudou desde o card e o que continua em aberto.",
        fonte: null,
        opcoes: [],
        nao_bateu: false,
        retrato: {
          ja_existe: [{ item: ITEM, versao: "v0.245.0" }],
          mudou: ["A enfermagem também vê o retorno."],
          em_aberto: ["Quem confirma o retorno com o paciente."],
        },
      },
      {
        autor: "ia",
        texto: `Isso atende? Já existe desde a v0.245.0: ${ITEM}`,
        fonte: null,
        opcoes: ["Atende, pode sair do pedido.", "Não atende, continua no pedido."],
        recomendada: "B",
        nao_bateu: false,
      },
    ],
  });

  function abrirOCard() {
    return within(lista()).findByRole("button", { name: /Retorno marcado na saída/ });
  }

  it("o botão aparece só no card que o servidor diz que se revisa", async () => {
    montar((url) => (url === LISTA ? { status: 200, corpo: [CARD] } : { status: 200, corpo: conversa("d-2") }));
    fireEvent.click(await abrirOCard());
    expect(await screen.findByRole("button", { name: "Revisar com o código de hoje" })).toBeTruthy();
    cleanup();

    montar((url) =>
      url === LISTA
        ? { status: 200, corpo: [{ ...CARD, pode_revisar: false }] }
        : { status: 200, corpo: conversa("d-2") },
    );
    fireEvent.click(await abrirOCard());
    await screen.findByRole("heading", { name: "Retorno marcado na saída" });
    expect(screen.queryByRole("button", { name: "Revisar com o código de hoje" })).toBeNull();
  });

  it("o clique mostra a estimativa em dólar, e Cancelar não começa a revisão", async () => {
    const chamadas = montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [CARD] };
      if (url === REVISAO) return { status: 200, corpo: ESTIMATIVA };
      return { status: 200, corpo: conversa("d-2") };
    });
    fireEvent.click(await abrirOCard());

    fireEvent.click(await screen.findByRole("button", { name: "Revisar com o código de hoje" }));

    const confirmacao = await screen.findByRole("dialog");
    expect(
      await within(confirmacao).findByText(/O Retrato de hoje deve custar entre US\$ 0,42 e US\$ 3,10 no Opus 5\.5\./),
    ).toBeTruthy();
    fireEvent.click(within(confirmacao).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(chamadas.some((c) => c.url === REVISAO && c.metodo === "POST")).toBe(false);
  });

  it("confirmar começa a revisão e abre a conversa com o Retrato de hoje e o nome de quem respondeu", async () => {
    let revisando = false;
    const chamadas = montar((url, metodo) => {
      if (url === LISTA) return { status: 200, corpo: [revisando ? EM_REVISAO : CARD] };
      if (url === REVISAO && metodo === "GET") return { status: 200, corpo: ESTIMATIVA };
      if (url === REVISAO && metodo === "POST") {
        revisando = true;
        return { status: 200, corpo: NA_REVISAO };
      }
      return { status: 200, corpo: revisando ? NA_REVISAO : conversa("d-2") };
    });
    fireEvent.click(await abrirOCard());
    fireEvent.click(await screen.findByRole("button", { name: "Revisar com o código de hoje" }));
    const confirmacao = await screen.findByRole("dialog");
    await within(confirmacao).findByText(/US\$ 0,42/);

    fireEvent.click(within(confirmacao).getByRole("button", { name: "Revisar" }));

    const retrato = await screen.findByRole("region", { name: "Retrato de hoje" });
    expect(within(retrato).getByText(ITEM)).toBeTruthy();
    expect(within(retrato).getByText("desde a v0.245.0")).toBeTruthy();
    expect(within(retrato).getByText("A enfermagem também vê o retorno.")).toBeTruthy();
    expect(within(retrato).getByText("Quem confirma o retorno com o paciente.")).toBeTruthy();
    expect(screen.getByText("Diretor do Hospital")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Não atende, continua no pedido\./ })).toBeTruthy();
    expect(chamadas.filter((c) => c.url === REVISAO && c.metodo === "POST").map((c) => c.corpo)).toEqual([
      { confirmado: true },
    ]);
  });
});

describe("O endereço acompanha o card aberto (issue #1586)", () => {
  const OUTRO = demanda("d-3", "Relatório de leitos atrasa");

  function comDuas(demandaInicial: string | null = null) {
    return montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD, OUTRO] };
      if (url === `${LISTA}/d-1`) return { status: 200, corpo: conversa("d-1") };
      if (url === `${LISTA}/d-3`) return { status: 200, corpo: conversa("d-3", { mensagens: [ABERTURA_GUARDADA] }) };
      return { status: 404, corpo: {} };
    }, demandaInicial);
  }

  it("abrir um card põe a Demanda no endereço sem nova entrada no histórico, e voltar no celular tira", async () => {
    window.history.replaceState(null, "", "/admin/tecnologia");
    const entradas = window.history.length;
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");

    expect(window.location.pathname).toBe("/admin/tecnologia");
    expect(demandaDaUrl()).toBe("d-1");
    expect(window.history.length).toBe(entradas);

    fireEvent.click(screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA }));

    await waitFor(() => expect(demandaDaUrl()).toBeNull());
    expect(window.location.pathname).toBe("/admin/tecnologia");
    expect(window.history.length).toBe(entradas);
  });

  it("abrir um card, clicar noutro e recarregar abre o segundo", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");
    aPaginaLeOEndereco();
    fireEvent.click(within(lista()).getByRole("button", { name: /Relatório de leitos atrasa/ }));
    aPaginaLeOEndereco();
    await waitFor(() => expect(screen.queryByText("Onde isso aconteceu?")).toBeNull());

    // Recarregar: a tela nasce de novo, só com o que está no endereço.
    cleanup();
    comDuas(demandaDaUrl());

    await waitFor(() =>
      expect(
        within(lista()).getByRole("button", { name: /Relatório de leitos atrasa/ }).getAttribute("aria-current"),
      ).toBe("true"),
    );
    expect(within(lista()).getByRole("button", { name: /Botão de responder some/ }).getAttribute("aria-current")).not.toBe(
      "true",
    );
  });

  it("o endereço que a própria tela escreveu não reabre o card nem desfaz o Ampliar", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    const card = within(lista())
      .getAllByRole("listitem")
      .find((item) => within(item).queryByRole("button", { name: /Botão de responder some/ })) as HTMLElement;

    fireEvent.click(within(card).getByRole("button", { name: AMPLIAR }));
    await screen.findByText("Onde isso aconteceu?");
    aPaginaLeOEndereco();

    expect((lista().parentElement as HTMLElement).className).toMatch(/(^|\s)md:hidden(\s|$)/);
  });

  it("com uma Demanda fora da lista, avisa que não há acesso, sem título nem número, e volta à lista", async () => {
    const DE_OUTRO_DIRETOR = "Escala da enfermagem some";
    const chamadas = comDuas("d-99");
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    const aberto = screen.getByRole("region", { name: "Conversa aberta" });
    expect(await within(aberto).findByText(SEM_ACESSO)).toBeTruthy();
    expect(aberto.className).not.toMatch(/(^|\s)hidden(\s|$)/);
    expect(within(aberto).queryByText(DE_OUTRO_DIRETOR)).toBeNull();
    expect(within(aberto).queryByText(/#\d+/)).toBeNull();
    expect(within(aberto).queryByText(ABERTURA)).toBeNull();
    expect(chamadas.some((c) => c.url.startsWith(`${LISTA}/d-99`))).toBe(false);

    const voltar = screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA });
    expect(voltar.className).not.toMatch(/(^|\s)md:hidden(\s|$)/);
    fireEvent.click(voltar);

    await waitFor(() => expect(screen.queryByText(SEM_ACESSO)).toBeNull());
    expect((lista().parentElement as HTMLElement).className).not.toMatch(/(^|\s)hidden(\s|$)/);
    expect(demandaDaUrl()).toBeNull();
  });

  it("o sino com a tela já aberta abre o card que ele aponta, e no celular mostra o card", async () => {
    comDuas();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");
    aPaginaLeOEndereco();
    fireEvent.click(screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA }));
    aPaginaLeOEndereco();

    // O sino leva ao mesmo endereço com outra Demanda, e a página repassa.
    window.history.pushState(null, "", "/admin/tecnologia?demanda=d-3");
    aPaginaLeOEndereco();

    await waitFor(() =>
      expect(
        within(lista()).getByRole("button", { name: /Relatório de leitos atrasa/ }).getAttribute("aria-current"),
      ).toBe("true"),
    );
    expect(screen.getByRole("region", { name: "Conversa aberta" }).className).not.toMatch(/(^|\s)hidden(\s|$)/);
  });
});
