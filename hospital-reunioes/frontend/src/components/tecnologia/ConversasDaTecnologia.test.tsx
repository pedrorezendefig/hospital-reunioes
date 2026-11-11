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
  render(
    <ToastProvider>
      <ConversasDaTecnologia token="token-de-teste" demandaInicial={demandaInicial} />
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
    expect(itens.map((item) => item.textContent)).toEqual([
      "O relatório someDiretor do HospitalRegistrada",
      "Botão de responder some na OuvidoriaPedro VittaRegistrada",
    ]);
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

    const filtros = await screen.findByRole("group", { name: "Filtro das conversas" });
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
    expect(itens.map((item) => item.textContent)).toEqual([
      "Agenda de retornoResponsável: Lucas SampaioEm análise",
      "Botão de responder some na OuvidoriaRegistrada",
    ]);
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
    expect(within(lista()).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "O botão sumiuDiretor do HospitalResponsável: Pedro RibEm análise",
    ]);
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

  it("o aviso do sino abre a Demanda de outro autor para o Desenvolvedor, pela lista de Todas", async () => {
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
    expect(chamadas.filter((c) => c.url.startsWith(`${LISTA}?`)).map((c) => c.url)).toEqual([TODAS]);
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

    fireEvent.click(await screen.findByRole("button", { name: "Envio falhou" }));
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

describe("A lista larga com busca e filtros em chips (issue #1551, PRD #1548)", () => {
  const EU = "/api/admin/tecnologia/eu";
  const DESENVOLVEDORES = "/api/admin/tecnologia/desenvolvedores";
  const QUEM_CUIDA = [
    { id: "P1", nome: "Pedro Vitta", padrao: true },
    { id: "P4", nome: "Pedro Rib", padrao: false },
  ];

  function filtros() {
    return screen.getByRole("region", { name: "Filtros da lista" });
  }

  function chips() {
    return within(filtros())
      .getAllByRole("button")
      .map((b) => b.textContent);
  }

  function chip(grupo: string, rotulo: string) {
    return within(within(filtros()).getByRole("group", { name: grupo })).getByRole("button", { name: rotulo });
  }

  function comoDiretor() {
    return montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: false } };
      if (url.startsWith(LISTA)) return { status: 200, corpo: [SEM_CARD] };
      return { status: 404, corpo: {} };
    });
  }

  function comoDesenvolvedor() {
    return montar((url) => {
      if (url === EU) return { status: 200, corpo: { desenvolvedor: true } };
      if (url === DESENVOLVEDORES) return { status: 200, corpo: QUEM_CUIDA };
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

  it("o diretor combina Bug e Etapa, e clicar de novo desliga o chip", async () => {
    const chamadas = comoDiretor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    fireEvent.click(chip("Tipo", "Bug"));
    fireEvent.click(chip("Etapa", "Em produção"));
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain(`${LISTA}?tipo=bug&etapa=em_producao`));
    expect(chip("Tipo", "Bug").getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(chip("Tipo", "Bug"));
    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(`${LISTA}?etapa=em_producao`));
    expect(chip("Tipo", "Bug").getAttribute("aria-pressed")).toBe("false");
  });

  it("o diretor não vê os chips do Desenvolvedor", async () => {
    comoDiretor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");

    expect(chips()).toEqual([
      "Bug",
      "Melhoria",
      "Registrada",
      "Em análise",
      "Planejada",
      "Em desenvolvimento",
      "Entregue",
      "Em produção",
      "Não será feita",
    ]);
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

    fireEvent.click(await within(filtros()).findByRole("button", { name: "Pedro Rib" }));
    fireEvent.click(chip("Situação", "Envio falhou"));
    fireEvent.click(chip("Tipo", "Melhoria"));

    await waitFor(() => expect(chamadas.at(-1)?.url).toBe(COMBINADA));
    expect(await within(lista()).findByText("Relatorio de custo por setor")).toBeTruthy();
    expect(within(lista()).queryByText("Botão de responder some na Ouvidoria")).toBeNull();
    expect(chips()).toEqual([
      "Para mim",
      "Minhas",
      "Todas",
      "Bug",
      "Melhoria",
      "Registrada",
      "Em análise",
      "Planejada",
      "Em desenvolvimento",
      "Entregue",
      "Em produção",
      "Não será feita",
      "Pedro Vitta",
      "Pedro Rib",
      "Envio falhou",
    ]);
  });

  it("os chips quebram linha dentro da coluna, sem rolagem horizontal", async () => {
    comoDesenvolvedor();
    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    await within(filtros()).findByRole("button", { name: "Pedro Rib" });

    const grupos = within(filtros()).getAllByRole("group");
    expect(grupos).toHaveLength(5);
    for (const grupo of grupos) {
      expect(grupo.className).toMatch(/(^|\s)flex-wrap(\s|$)/);
      expect(grupo.className).not.toMatch(/overflow-x|flex-nowrap|whitespace-nowrap/);
    }
    for (const botao of within(filtros()).getAllByRole("button")) {
      expect(botao.className).not.toMatch(/(^|\s)flex-1(\s|$)/);
    }
  });

  it("a lista recolhe com uma Demanda aberta e volta pelo botão", async () => {
    montar((url) => {
      if (url === LISTA) return { status: 200, corpo: [SEM_CARD] };
      if (url === `${LISTA}/d-1`) return { status: 200, corpo: conversa("d-1") };
      return { status: 404, corpo: {} };
    });
    const painelDaLista = () => lista().parentElement as HTMLElement;
    const recolhida = /(^|\s)md:hidden(\s|$)/;
    const voltar = () => screen.getByRole("button", { name: VOLTAR_PARA_A_LISTA });

    await within(lista()).findByText("Botão de responder some na Ouvidoria");
    expect(painelDaLista().className).not.toMatch(recolhida);
    expect(voltar().className).toMatch(recolhida);

    fireEvent.click(within(lista()).getByRole("button", { name: /Botão de responder some/ }));
    await screen.findByText("Onde isso aconteceu?");
    expect(painelDaLista().className).toMatch(recolhida);
    expect(voltar().className).not.toMatch(recolhida);

    fireEvent.click(voltar());
    await waitFor(() => expect(painelDaLista().className).not.toMatch(recolhida));
  });
});
