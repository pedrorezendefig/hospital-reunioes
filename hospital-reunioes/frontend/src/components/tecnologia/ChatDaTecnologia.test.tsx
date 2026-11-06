/**
 * @vitest-environment jsdom
 */

/**
 * O chat da aba Tecnologia com o Roteiro do bug (issue #1381, PRD #1380, ADR 0077).
 *
 * A tela, com o `fetch` dublado: o que se cobra é o que vai no corpo de cada
 * POST (o botão da abertura, o texto livre, o que não bateu) e o que o diretor
 * vê depois (a pergunta, a fonte da resposta, o resumo, o card criado, o erro).
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import {
  ABERTURA,
  ChatDaTecnologia,
  CONTINUAR_RESPONDENDO,
  CRIAR_O_CARD,
  FECHAR_E_RESUMIR,
  NAO_BATEU,
} from "./ChatDaTecnologia";
import { ConversaDoChat, FalaDoChat } from "./chat";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

type Chamada = { url: string; metodo: string; corpo: unknown };

const ABERTURA_GUARDADA: FalaDoChat = {
  autor: "ia",
  texto: ABERTURA,
  fonte: null,
  opcoes: ["Bug", "Melhoria"],
  nao_bateu: false,
};

function conversa(extra: Partial<ConversaDoChat> = {}): ConversaDoChat {
  return {
    demanda_id: "d-1",
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
  } as ConversaDoChat;
}

const RESUMO = {
  titulo: "Botão de responder some na Ouvidoria",
  onde: "Ouvidoria, no caso aberto",
  o_que_aconteceu: "O botão Responder sumiu",
  o_que_esperava: "Ver o botão Responder no caso",
  como_repetir: "não informado",
  criterios: ["O botão Responder aparece no caso aberto da Ouvidoria"],
};

type Resposta = { status: number; corpo: unknown };

/** Monta o chat com um servidor falso que responde, em ordem, o que lhe derem. */
function montar(respostas: Resposta[]) {
  const chamadas: Chamada[] = [];
  const fila = [...respostas];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, metodo: init?.method ?? "GET", corpo: init?.body ? JSON.parse(String(init.body)) : null });
      const proxima = fila.shift() ?? { status: 500, corpo: { detail: "sem resposta no teste" } };
      return {
        ok: proxima.status < 400,
        status: proxima.status,
        json: async () => proxima.corpo,
      } as unknown as Response;
    }),
  );
  render(
    <ToastProvider>
      <ChatDaTecnologia token="token-de-teste" />
    </ToastProvider>,
  );
  return chamadas;
}

function escrever(texto: string) {
  fireEvent.change(screen.getByLabelText("Sua mensagem"), { target: { value: texto } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
}

describe("A abertura", () => {
  it("abre no chat com a pergunta bug ou melhoria, dois botões e o campo livre", () => {
    montar([]);

    expect(screen.getByText(ABERTURA)).toBeTruthy();
    const opcoes = within(screen.getByRole("group", { name: "Opções" })).getAllByRole("button");
    expect(opcoes.map((b) => b.textContent)).toEqual(["Bug", "Melhoria"]);
    expect(screen.getByLabelText("Sua mensagem")).toBeTruthy();
  });

  it("o botão Bug começa a conversa e a primeira pergunta aparece", async () => {
    const chamadas = montar([{ status: 201, corpo: conversa() }]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    expect(chamadas[0]).toMatchObject({ url: "/api/admin/tecnologia/chat", metodo: "POST", corpo: { escolha: "bug" } });
  });

  it("o texto livre começa a conversa, e a confirmação vem com os botões", async () => {
    const confirmacao = conversa({
      mensagens: [
        ABERTURA_GUARDADA,
        { autor: "diretor", texto: "O botão sumiu", fonte: null, opcoes: [], nao_bateu: false },
        {
          autor: "ia",
          texto: "Pelo que você contou, é um bug. É isso?",
          fonte: null,
          opcoes: ["Sim, é um bug", "Não, é uma melhoria"],
          nao_bateu: false,
        },
      ],
    });
    const chamadas = montar([{ status: 201, corpo: confirmacao }, { status: 200, corpo: conversa() }]);

    escrever("O botão sumiu");
    fireEvent.click(await screen.findByRole("button", { name: "Sim, é um bug" }));

    await waitFor(() => expect(chamadas).toHaveLength(2));
    expect(chamadas[0].corpo).toEqual({ texto: "O botão sumiu", prints: [] });
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1", corpo: { texto: "Sim, é um bug" } });
  });
});

describe("O modelo e o custo no cabeçalho (issue #1439)", () => {
  it("mostra o modelo e o custo em dólar no formato brasileiro, e atualiza a cada resposta", async () => {
    montar([
      { status: 201, corpo: conversa({ custo: { modelo: "Opus 5.5", custo_usd: 1.8371 } }) },
      { status: 200, corpo: conversa({ custo: { modelo: "Opus 5.5", custo_usd: 12.5 } }) },
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    expect(await screen.findByText("Opus 5.5 · US$ 1,84 até agora")).toBeTruthy();
    escrever("Na Ouvidoria");
    expect(await screen.findByText("Opus 5.5 · US$ 12,50 até agora")).toBeTruthy();
  });

  it("com o custo nulo, diz custo não medido, nunca zero", async () => {
    montar([{ status: 201, corpo: conversa({ custo: { modelo: "Opus 5.5", custo_usd: null } }) }]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    expect(await screen.findByText("Opus 5.5 · custo não medido")).toBeTruthy();
    expect(screen.queryByText(/US\$/)).toBeNull();
  });

  it("sem chamada nenhuma, o cabeçalho não mostra custo", async () => {
    montar([{ status: 201, corpo: conversa({ custo: null }) }]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    expect(await screen.findByText("Onde isso aconteceu?")).toBeTruthy();
    expect(screen.queryByText(/US\$|custo não medido/)).toBeNull();
  });
});

describe("A dúvida que o material responde", () => {
  it("a resposta diz de onde veio", async () => {
    const respondida = conversa({
      mensagens: [
        ABERTURA_GUARDADA,
        { autor: "diretor", texto: "Como baixo a ata?", fonte: null, opcoes: [], nao_bateu: false },
        { autor: "ia", texto: "A ata sai em PDF depois da assinatura.", fonte: "Reuniões", opcoes: [], nao_bateu: false },
      ],
    });
    montar([{ status: 201, corpo: respondida }]);

    escrever("Como baixo a ata?");

    expect(await screen.findByText("De onde veio: material da Vitta sobre Reuniões")).toBeTruthy();
    expect(screen.queryByRole("button", { name: CRIAR_O_CARD })).toBeNull();
  });
});

describe("O resumo do bug", () => {
  it("mostra os rótulos e os critérios, com Criar o card e Não bateu", async () => {
    montar([{ status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO, anexos: 2 }) }]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    const resumo = await screen.findByRole("region", { name: "Resumo do bug" });
    expect(within(resumo).getByText("Ouvidoria, no caso aberto")).toBeTruthy();
    expect(within(resumo).getByText("não informado")).toBeTruthy();
    expect(within(resumo).getByText("O botão Responder aparece no caso aberto da Ouvidoria")).toBeTruthy();
    expect(within(resumo).getByText("2 imagens guardadas no aplicativo")).toBeTruthy();
    expect(within(resumo).getByRole("button", { name: CRIAR_O_CARD })).toBeTruthy();
    expect(within(resumo).getByRole("button", { name: NAO_BATEU })).toBeTruthy();
  });

  it("Não bateu manda o que não bateu e volta à conversa, que refaz o resumo", async () => {
    const voltou = conversa({
      mensagens: [
        ...conversa().mensagens,
        { autor: "diretor", texto: "Foi nas Reuniões", fonte: null, opcoes: [], nao_bateu: true },
      ],
    });
    const refeito = conversa({ estado: "resumido", resumo: { ...RESUMO, onde: "Reuniões, na ata" } });
    const chamadas = montar([
      { status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) },
      { status: 200, corpo: voltou },
      { status: 200, corpo: refeito },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    fireEvent.click(await screen.findByRole("button", { name: NAO_BATEU }));

    fireEvent.change(screen.getByLabelText("O que não bateu"), { target: { value: "Foi nas Reuniões" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar o que não bateu" }));

    expect(await screen.findByText("Reuniões, na ata")).toBeTruthy();
    expect(chamadas[1]).toMatchObject({
      url: "/api/admin/tecnologia/chat/d-1/nao-bateu",
      corpo: { texto: "Foi nas Reuniões" },
    });
    expect(chamadas[2]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1", metodo: "POST", corpo: {} });
  });

  it("Criar o card manda para o desenvolvimento e a tela diz que foi", async () => {
    const chamadas = montar([
      { status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) },
      { status: 200, corpo: conversa({ estado: "enviado", resumo: RESUMO }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    fireEvent.click(await screen.findByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu relato/)).toBeTruthy();
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1/criar-card", metodo: "POST" });
  });
});

describe("A falha do provedor", () => {
  it("mostra o erro claro e não perde a conversa nem o texto escrito", async () => {
    const frase = "A IA não conseguiu responder agora, e a conversa ficou como estava. Tente de novo em instantes.";
    montar([
      { status: 201, corpo: conversa() },
      { status: 502, corpo: { detail: frase } },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    await screen.findByText("Onde isso aconteceu?");

    escrever("Na Ouvidoria");

    expect((await screen.findByRole("alert")).textContent).toContain(frase);
    expect(screen.getByText("Onde isso aconteceu?")).toBeTruthy();
    expect((screen.getByLabelText("Sua mensagem") as HTMLTextAreaElement).value).toBe("Na Ouvidoria");
  });
});

// ─── A melhoria dentro do chat (issue #1383) ─────────────────────────────────

const PERGUNTA: FalaDoChat = {
  autor: "ia",
  texto: "Preciso entender o problema. Ele acontece na recepção?",
  fonte: null,
  opcoes: ["Sim, na recepção.", "Não, na enfermagem."],
  recomendada: "B",
  nao_bateu: false,
};

function melhoria(extra: Partial<ConversaDoChat> = {}): ConversaDoChat {
  return conversa({
    planejamento: true,
    mensagens: [ABERTURA_GUARDADA, { autor: "diretor", texto: "Melhoria", fonte: null, opcoes: [], nao_bateu: false }, PERGUNTA],
    ...extra,
  });
}

const RESUMO_DA_MELHORIA = {
  decisoes: [{ pergunta: "Quem usa?", escolha: "Só a recepção.", porque: "É ela quem marca o retorno." }],
  em_aberto: ["Quem confirma o retorno com o paciente."],
  termos: [],
  candidatas_a_adr: [],
};

describe("A melhoria", () => {
  it("o botão Melhoria abre a pergunta com contexto, duas opções, a recomendada destacada e o campo livre", async () => {
    const chamadas = montar([{ status: 201, corpo: melhoria() }]);

    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    expect(await screen.findByText(PERGUNTA.texto)).toBeTruthy();
    const opcoes = within(screen.getByRole("group", { name: "Opções" })).getAllByRole("button");
    expect(opcoes).toHaveLength(2);
    expect(opcoes[0].textContent).toContain("Sim, na recepção.");
    expect(opcoes[0].textContent).not.toContain("Recomendada");
    expect(opcoes[1].textContent).toContain("Não, na enfermagem.");
    expect(opcoes[1].textContent).toContain("Recomendada");
    expect(screen.getByLabelText("Sua mensagem")).toBeTruthy();
    expect(chamadas[0].corpo).toEqual({ escolha: "melhoria" });
  });

  it("clicar numa opção manda a letra dela", async () => {
    const chamadas = montar([{ status: 201, corpo: melhoria() }, { status: 200, corpo: melhoria() }]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    fireEvent.click(await screen.findByRole("button", { name: /Sim, na recepção/ }));

    await waitFor(() => expect(chamadas).toHaveLength(2));
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1", corpo: { opcao: "A" } });
  });

  it("Fechar e resumir fica à mão e pede o resumo, que traz o que ficou em aberto", async () => {
    const chamadas = montar([
      { status: 201, corpo: melhoria() },
      { status: 200, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    fireEvent.click(await screen.findByRole("button", { name: FECHAR_E_RESUMIR }));

    const resumo = await screen.findByRole("region", { name: "Resumo da melhoria" });
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1/resumo", metodo: "POST" });
    expect(within(resumo).getByText("Ficou em aberto")).toBeTruthy();
    expect(within(resumo).getByText("Quem confirma o retorno com o paciente.")).toBeTruthy();
    expect(within(resumo).getByText("Só a recepção.")).toBeTruthy();
    expect(within(resumo).getByRole("button", { name: CRIAR_O_CARD })).toBeTruthy();
    expect(within(resumo).getByRole("button", { name: NAO_BATEU })).toBeTruthy();
  });

  it("o bug não tem Fechar e resumir", async () => {
    montar([{ status: 201, corpo: conversa() }]);

    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    await screen.findByText("Onde isso aconteceu?");
    expect(screen.queryByRole("button", { name: FECHAR_E_RESUMIR })).toBeNull();
  });

  it("a melhoria contada em texto pede a primeira pergunta sozinha, sem o diretor clicar", async () => {
    const passou = conversa({
      planejamento: true,
      mensagens: [
        ...conversa().mensagens.slice(0, 2),
        { autor: "ia", texto: "Agora umas perguntas sobre o pedido.", fonte: null, opcoes: [], nao_bateu: false },
      ],
    });
    const chamadas = montar([{ status: 201, corpo: passou }, { status: 200, corpo: melhoria() }]);

    escrever("Queria um aviso quando a ata sair");

    expect(await screen.findByText(PERGUNTA.texto)).toBeTruthy();
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1", metodo: "POST", corpo: {} });
  });

  it("com as perguntas encerradas, o resumo vem sozinho", async () => {
    const encerrado = melhoria({
      estado: "encerrado",
      mensagens: [...melhoria().mensagens, { autor: "ia", texto: "Já tenho o que preciso.", fonte: null, opcoes: [], nao_bateu: false }],
    });
    const chamadas = montar([
      { status: 201, corpo: melhoria() },
      { status: 200, corpo: encerrado },
      { status: 200, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    fireEvent.click(await screen.findByRole("button", { name: /Sim, na recepção/ }));

    expect(await screen.findByRole("region", { name: "Resumo da melhoria" })).toBeTruthy();
    expect(chamadas[2]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1/resumo", metodo: "POST" });
  });

  it("Criar o card manda a melhoria e a tela diz que foi", async () => {
    const chamadas = montar([
      { status: 201, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
      { status: 200, corpo: melhoria({ estado: "enviado", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    fireEvent.click(await screen.findByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu pedido/)).toBeTruthy();
    expect(chamadas[1]).toMatchObject({ url: "/api/admin/tecnologia/chat/d-1/criar-card", metodo: "POST" });
  });
});

// ─── A conversa aberta até o card (issue #1437, ADR 0079, decisão 3) ─────────

describe("A melhoria segue aberta até o Criar o card", () => {
  it("depois do resumo, o campo livre está habilitado e a fala traz nova pergunta", async () => {
    const nova: FalaDoChat = { ...PERGUNTA, texto: "Quem confirma o retorno com o paciente?" };
    const chamadas = montar([
      { status: 201, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
      { status: 200, corpo: melhoria({ mensagens: [...melhoria().mensagens, nova] }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    await screen.findByRole("region", { name: "Resumo da melhoria" });

    escrever("Falta dizer quem confirma.");

    expect(await screen.findByText(nova.texto)).toBeTruthy();
    expect(chamadas[1]).toMatchObject({
      url: "/api/admin/tecnologia/chat/d-1",
      metodo: "POST",
      corpo: { texto: "Falta dizer quem confirma." },
    });
  });

  it("encerrado, o campo livre está habilitado e a fala volta às perguntas", async () => {
    const encerrado = melhoria({
      estado: "encerrado",
      mensagens: [
        ...melhoria().mensagens,
        { autor: "ia", texto: "Já tenho o que preciso.", fonte: null, opcoes: [], nao_bateu: false },
      ],
    });
    const nova: FalaDoChat = { ...PERGUNTA, texto: "O médico também vê o aviso?" };
    const chamadas = montar([
      { status: 201, corpo: melhoria() },
      { status: 200, corpo: encerrado },
      // O resumo automático falha, e a conversa fica encerrada na tela.
      { status: 502, corpo: { detail: "A IA não conseguiu responder agora." } },
      { status: 200, corpo: melhoria({ mensagens: [...encerrado.mensagens, nova] }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    fireEvent.click(await screen.findByRole("button", { name: /Sim, na recepção/ }));
    await screen.findByText("Já tenho o que preciso.");
    await waitFor(() => expect(chamadas).toHaveLength(3));

    escrever("Esqueci: o médico também precisa ver.");

    expect(await screen.findByText(nova.texto)).toBeTruthy();
    expect(chamadas[3]).toMatchObject({
      url: "/api/admin/tecnologia/chat/d-1",
      corpo: { texto: "Esqueci: o médico também precisa ver." },
    });
  });
});

// ─── Continuar respondendo (issue #1440, ADR 0079, decisão 4) ────────────────

describe("O resumo com lacuna traz o Continuar respondendo", () => {
  it("com algo em aberto, o botão aparece e o clique volta às perguntas", async () => {
    const nova: FalaDoChat = { ...PERGUNTA, texto: "Quem confirma o retorno com o paciente?" };
    const chamadas = montar([
      { status: 201, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
      { status: 200, corpo: melhoria({ mensagens: [...melhoria().mensagens, nova] }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    const resumo = await screen.findByRole("region", { name: "Resumo da melhoria" });

    fireEvent.click(within(resumo).getByRole("button", { name: CONTINUAR_RESPONDENDO }));

    expect(await screen.findByText(nova.texto)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Resumo da melhoria" })).toBeNull();
    expect(chamadas[1]).toMatchObject({
      url: "/api/admin/tecnologia/chat/d-1",
      metodo: "POST",
      corpo: { continuar: true },
    });
  });

  it("com Nada ficou em aberto, o botão não aparece", async () => {
    montar([
      {
        status: 201,
        corpo: melhoria({ estado: "resumido", resumo_da_melhoria: { ...RESUMO_DA_MELHORIA, em_aberto: [] } }),
      },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    const resumo = await screen.findByRole("region", { name: "Resumo da melhoria" });

    expect(within(resumo).getByText("Nada ficou em aberto.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: CONTINUAR_RESPONDENDO })).toBeNull();
    expect(within(resumo).getByRole("button", { name: CRIAR_O_CARD })).toBeTruthy();
  });
});
