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
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

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

/** Os Desenvolvedores do "Quem cuida disto?" (issue #1533). */
const DESENVOLVEDORES = [
  { id: "P5", nome: "Lucas Sampaio", padrao: false },
  { id: "P4", nome: "Pedro Rib", padrao: false },
  { id: "P1", nome: "Pedro Rezende", padrao: true },
];

/**
 * Monta o chat com um servidor falso que responde, em ordem, o que lhe derem.
 * A lista do "Quem cuida disto?" responde à parte, sem entrar na fila nem nas
 * chamadas: os testes de antes dela continuam contando os POSTs do mesmo jeito.
 */
function montar(respostas: Resposta[], desenvolvedores: Resposta = { status: 200, corpo: DESENVOLVEDORES }) {
  const chamadas: Chamada[] = [];
  const fila = [...respostas];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/admin/tecnologia/desenvolvedores") {
        return {
          ok: desenvolvedores.status < 400,
          status: desenvolvedores.status,
          json: async () => desenvolvedores.corpo,
        } as unknown as Response;
      }
      // O upload do anexo vai em multipart: guarda o FormData como veio.
      const corpo =
        init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : null;
      chamadas.push({ url, metodo: init?.method ?? "GET", corpo });
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

// ─── Quem cuida disto? (issue #1533, ADR 0083, decisão 5) ────────────────────

describe("Quem cuida disto?", () => {
  it("o resumo lista os Desenvolvedores e diz para quem vai sem escolha", async () => {
    montar([{ status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) }]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    const seletor = (await screen.findByLabelText("Quem cuida disto?")) as HTMLSelectElement;

    await waitFor(() => expect(seletor.options.length).toBe(4));
    expect(Array.from(seletor.options).map((o) => o.textContent)).toEqual([
      "Sem escolha",
      "Lucas Sampaio",
      "Pedro Rib",
      "Pedro Rezende",
    ]);
    expect(seletor.value).toBe("");
    expect(screen.getByText("Escolher é opcional. Sem escolha, o card vai para Pedro Rezende.")).toBeTruthy();
  });

  it("Criar o card leva quem foi escolhido", async () => {
    const chamadas = montar([
      { status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) },
      { status: 200, corpo: conversa({ estado: "enviado", resumo: RESUMO }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    const seletor = (await screen.findByLabelText("Quem cuida disto?")) as HTMLSelectElement;
    await waitFor(() => expect(seletor.options.length).toBe(4));

    fireEvent.change(seletor, { target: { value: "P4" } });
    fireEvent.click(screen.getByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu relato/)).toBeTruthy();
    expect(chamadas[1]).toMatchObject({
      url: "/api/admin/tecnologia/chat/d-1/criar-card",
      corpo: { responsavel_id: "P4" },
    });
  });

  it("sem escolha, Criar o card vai sem Responsável e não trava", async () => {
    const chamadas = montar([
      { status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) },
      { status: 200, corpo: conversa({ estado: "enviado", resumo: RESUMO }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    await screen.findByLabelText("Quem cuida disto?");

    fireEvent.click(screen.getByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu relato/)).toBeTruthy();
    expect(chamadas[1].corpo).toEqual({});
  });

  it("sem a lista, o resumo segue com Criar o card e sem a pergunta", async () => {
    const chamadas = montar(
      [
        { status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) },
        { status: 200, corpo: conversa({ estado: "enviado", resumo: RESUMO }) },
      ],
      { status: 500, corpo: { detail: "fora do ar" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));

    fireEvent.click(await screen.findByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu relato/)).toBeTruthy();
    expect(screen.queryByLabelText("Quem cuida disto?")).toBeNull();
    expect(chamadas[1].corpo).toEqual({});
  });

  it("a melhoria também pergunta quem cuida e leva a escolha", async () => {
    const chamadas = montar([
      { status: 201, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
      { status: 200, corpo: melhoria({ estado: "enviado", resumo_da_melhoria: RESUMO_DA_MELHORIA }) },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    const seletor = (await screen.findByLabelText("Quem cuida disto?")) as HTMLSelectElement;
    await waitFor(() => expect(seletor.options.length).toBe(4));

    fireEvent.change(seletor, { target: { value: "P5" } });
    fireEvent.click(screen.getByRole("button", { name: CRIAR_O_CARD }));

    expect(await screen.findByText(/A Vitta recebeu o seu pedido/)).toBeTruthy();
    expect(chamadas[1].corpo).toEqual({ responsavel_id: "P5" });
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

// ─── Caixa alta (ADR 0080, issue #1455) ──────────────────────────────────────

describe("Caixa alta na conversa e no resumo", () => {
  it("as opções da conversa ficam corridas, mesmo dentro do botão", async () => {
    montar([{ status: 201, corpo: melhoria() }]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));

    const opcao = await screen.findByRole("button", { name: /Não, na enfermagem/ });
    expect(caixaDoDado(within(opcao).getByText(/Não, na enfermagem/))).toBe("normal-case");
  });

  it("a confirmação de bug ou melhoria fica corrida no botão", async () => {
    const confirmacao = conversa({
      mensagens: [
        ABERTURA_GUARDADA,
        { autor: "diretor", texto: "O botão sumiu", fonte: null, opcoes: [], nao_bateu: false },
        { autor: "ia", texto: "É um bug?", fonte: null, opcoes: ["Sim, é um bug"], nao_bateu: false },
      ],
    });
    montar([{ status: 201, corpo: confirmacao }]);

    escrever("O botão sumiu");

    expect(caixaDoDado(await screen.findByRole("button", { name: "Sim, é um bug" }))).toBe("normal-case");
  });

  it("no resumo do bug, os subtítulos ficam em caixa alta e o texto fica corrido", async () => {
    montar([{ status: 201, corpo: conversa({ estado: "resumido", resumo: RESUMO }) }]);
    fireEvent.click(screen.getByRole("button", { name: "Bug" }));
    const resumo = await screen.findByRole("region", { name: "Resumo do bug" });

    for (const subtitulo of ["Onde", "O que aconteceu", "O que esperava", "Como repetir", "Prints"]) {
      expect(caixaDoDado(within(resumo).getByText(subtitulo))).toBe("uppercase");
    }
    expect(within(resumo).getByRole("heading", { level: 3, name: "Como saber que foi resolvido" })).toBeTruthy();
    expect(caixaDoDado(within(resumo).getByText(RESUMO.titulo))).toBeNull();
    expect(caixaDoDado(within(resumo).getByText(RESUMO.onde))).toBeNull();
    expect(caixaDoDado(within(resumo).getByText(RESUMO.criterios[0]))).toBeNull();
  });

  it("no resumo da melhoria, os subtítulos são títulos e as decisões ficam corridas", async () => {
    montar([{ status: 201, corpo: melhoria({ estado: "resumido", resumo_da_melhoria: RESUMO_DA_MELHORIA }) }]);
    fireEvent.click(screen.getByRole("button", { name: "Melhoria" }));
    const resumo = await screen.findByRole("region", { name: "Resumo da melhoria" });

    expect(within(resumo).getByRole("heading", { level: 3, name: "Decisões" })).toBeTruthy();
    expect(within(resumo).getByRole("heading", { level: 3, name: "Ficou em aberto" })).toBeTruthy();
    expect(caixaDoDado(within(resumo).getByText("Só a recepção."))).toBeNull();
    expect(caixaDoDado(within(resumo).getByText("Quem confirma o retorno com o paciente."))).toBeNull();
  });
});

// ─── O documento no chat (issue #1520) ──────────────────────────────────────

function seletorDeAnexo(): HTMLInputElement {
  const entrada = document.querySelector('input[type="file"]');
  if (!(entrada instanceof HTMLInputElement)) throw new Error("o chat não tem o seletor de anexo");
  return entrada;
}

/** Um arquivo do tamanho dado sem alocar os bytes: o `size` é o que a recusa lê. */
function arquivo(nome: string, tamanho = 1000): File {
  const falso = new File(["x"], nome);
  Object.defineProperty(falso, "size", { value: tamanho });
  return falso;
}

function escolher(anexo: File) {
  fireEvent.change(seletorDeAnexo(), { target: { files: [anexo] } });
}

const MB = 1024 * 1024;

describe("O documento no chat (issue #1520)", () => {
  it("o botão de anexo aceita print e documento, pelos tipos da tabela do backend", () => {
    montar([]);

    expect(seletorDeAnexo().accept).toBe(".png,.jpg,.jpeg,.webp,.md,.txt,.pdf,.docx,.csv,.xlsx");
    expect(screen.getByRole("button", { name: "Anexar print ou documento" })).toBeTruthy();
  });

  it("tipo fora da lista é recusado na tela, antes do upload, com a frase que diz o que entra", async () => {
    const chamadas = montar([]);

    escolher(arquivo("dados.ods"));

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toBe(
      "Esse tipo de arquivo não entra na conversa. Entram print (.png, .jpg, .jpeg ou .webp) e documento (.md, .txt, .pdf, .docx, .csv ou .xlsx).",
    );
    expect(chamadas).toEqual([]);
  });

  it.each([
    ["relatorio.pdf", 15 * MB + 1, "15 MB"],
    ["plano.docx", 15 * MB + 1, "15 MB"],
    ["notas.md", 5 * MB + 1, "5 MB"],
    ["notas.txt", 5 * MB + 1, "5 MB"],
    ["glosas.csv", 5 * MB + 1, "5 MB"],
    ["glosas.xlsx", 15 * MB + 1, "15 MB"],
    ["tela.png", 3932161, "3,75 MB"],
  ])("%s acima do teto é recusado na tela antes do upload, com o número do backend", async (nome, tamanho, teto) => {
    const chamadas = montar([]);

    escolher(arquivo(nome, tamanho));

    expect((await screen.findByRole("alert")).textContent).toContain(`limite de ${teto}`);
    expect(chamadas).toEqual([]);
  });

  it("no teto cravado o documento sobe", async () => {
    const chamadas = montar([{ status: 422, corpo: { detail: "recusa do servidor" } }]);

    escolher(arquivo("relatorio.pdf", 15 * MB));

    await screen.findByText("recusa do servidor");
    expect(chamadas[0].url).toBe("/api/admin/tecnologia/assistente/ler-documento");
  });

  it("o documento sobe, a fala leva o identificador e mostra o nome e o tamanho, sem o texto", async () => {
    const lido = { documento_id: "doc-1", nome: "melhorias.md", tamanho_bytes: 12 * 1024, caracteres: 900 };
    const comODocumento = conversa({
      mensagens: [
        ABERTURA_GUARDADA,
        {
          autor: "diretor",
          texto: "",
          fonte: null,
          opcoes: [],
          nao_bateu: false,
          documentos: [{ nome: "melhorias.md", tamanho_bytes: 12 * 1024 }],
        },
        { autor: "ia", texto: "Li o documento. É uma melhoria?", fonte: null, opcoes: [], nao_bateu: false },
      ],
    });
    const chamadas = montar([
      { status: 200, corpo: lido },
      { status: 201, corpo: comODocumento },
    ]);

    escolher(arquivo("melhorias.md", 12 * 1024));

    expect(await screen.findByText("Li o documento. É uma melhoria?")).toBeTruthy();
    expect((chamadas[0].corpo as FormData).get("documento")).toBeInstanceOf(File);
    expect(chamadas[1]).toMatchObject({
      url: "/api/admin/tecnologia/chat",
      metodo: "POST",
      corpo: { texto: "", prints: [], documentos: ["doc-1"] },
    });
    const anexado = screen.getByRole("group", { name: "Documento anexado: melhorias.md" });
    expect(anexado.textContent).toContain("melhorias.md");
    expect(anexado.textContent).toContain("12 KB");
  });

  it("planilha .xls antiga é recusada na tela, antes do upload, com a frase que pede .xlsx (issue #1521)", async () => {
    const chamadas = montar([]);

    escolher(arquivo("glosas.XLS"));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Planilha no formato antigo (.xls) não entra. Abra no Excel, salve como .xlsx e anexe de novo.",
    );
    expect(chamadas).toEqual([]);
  });

  it.each(["glosas.xlsx", "glosas.csv"])("a planilha %s sobe pela rota do documento (issue #1521)", async (nome) => {
    const chamadas = montar([{ status: 422, corpo: { detail: "recusa do servidor" } }]);

    escolher(arquivo(nome, 2 * MB));

    await screen.findByText("recusa do servidor");
    expect(chamadas[0].url).toBe("/api/admin/tecnologia/assistente/ler-documento");
    expect((chamadas[0].corpo as FormData).get("documento")).toBeInstanceOf(File);
  });

  it("a recusa do servidor ao documento aparece na tela, e a conversa não anda", async () => {
    const frase = "Esse PDF é uma imagem de papel, sem texto para ler. Mande as páginas como print, pelo mesmo botão.";
    const chamadas = montar([{ status: 422, corpo: { detail: frase } }]);

    escolher(arquivo("escaneado.pdf", 2 * MB));

    expect((await screen.findByRole("alert")).textContent).toBe(frase);
    expect(chamadas).toHaveLength(1);
  });
});
