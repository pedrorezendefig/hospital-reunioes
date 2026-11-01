/**
 * @vitest-environment jsdom
 */

/**
 * Planejar com a IA (issue #1345, PRD #1344, ADR 0075).
 *
 * Duas costuras. O BOTÃO, pelo modal da Demanda (como o `VinculoDaDemanda`
 * e o `OQueMudaDaDemanda`): um teste que montasse só o botão provaria que ele
 * sabe se esconder, e não que o card o usa. E a TELA do planejamento, com o
 * `fetch` dublado: o que se cobra é o que vai no corpo do POST (a letra da
 * opção clicada, o texto do campo livre) e o que o diretor vê depois.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import { DemandaModal } from "./DemandaModal";
import { Demanda, EuNaAba } from "./demandas";
import {
  CONTINUAR_PLANEJAMENTO,
  MensagemDoPlanejamento,
  Planejamento,
  PLANEJAR_COM_A_IA,
} from "./planejamento";
import {
  FECHAR_E_RESUMIR,
  NADA_DECIDIDO,
  O_QUE_NAO_BATEU,
  PlanejamentoDaDemanda,
  SIM_MANDAR,
  TITULO_DAS_DECISOES,
  TITULO_DAS_DECISOES_DO_RESUMO,
  TITULO_DO_EM_ABERTO,
  TITULO_DO_ENVIADO,
  TITULO_DO_RESUMO,
  VOLTAR_PARA_A_TECNOLOGIA,
} from "./PlanejamentoDaDemanda";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ─── O botão no card ─────────────────────────────────────────────────────────

const DIRETOR: EuNaAba = {
  id: "P2",
  nome_completo: "Diretor do Hospital",
  tem_github_login: false,
  integracao_configurada: true,
};

function demanda(extra: Partial<Demanda> = {}): Demanda {
  return {
    id: "d-1",
    titulo: "Agenda de retorno na recepção",
    descricao: "O que precisa: marcar o retorno na saída",
    tipo: "novo",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova",
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P2",
    prioridade: "normal",
    prazo: null,
    criado_em: new Date().toISOString(),
    concluida_em: null,
    cancelada_em: null,
    tem_vinculo: false,
    ...extra,
  };
}

function montarModal(d: Demanda) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
  );
  return render(
    <DemandaModal
      demanda={d}
      produtos={[{ id: "prod-1", nome: "Ana", ativo: true }]}
      pessoas={[{ id: "P1", nome_completo: "Pedro Vitta" }]}
      token="token-de-teste"
      eu={DIRETOR}
      onFechar={() => {}}
      onMudou={() => {}}
    />,
  );
}

function botaoDePlanejar(): HTMLElement | null {
  return screen.queryByRole("link", { name: PLANEJAR_COM_A_IA });
}

describe("O botão Planejar com a IA no card aberto", () => {
  it.each(["novo", "ajuste"] as const)("aparece numa Demanda %s sem Vínculo e leva à tela do planejamento", (tipo) => {
    montarModal(demanda({ tipo }));

    expect(botaoDePlanejar()?.getAttribute("href")).toBe("/admin/tecnologia/planejamento/d-1");
  });

  it.each(["defeito", "decisao", "informacao", "terceiro", "consultoria"] as const)(
    "não aparece numa Demanda %s",
    (tipo) => {
      montarModal(demanda({ tipo }));

      expect(screen.getByLabelText("Título")).toBeTruthy(); // o card montou
      expect(botaoDePlanejar()).toBeNull();
    },
  );

  it("não aparece quando a Demanda já tem Vínculo, mesmo para o diretor, que não vê o número", () => {
    montarModal(demanda({ tem_vinculo: true, vinculo: null }));

    expect(screen.getByLabelText("Título")).toBeTruthy();
    expect(botaoDePlanejar()).toBeNull();
  });

  it.each(["concluida", "cancelada"] as const)("não aparece numa Demanda %s", (estado) => {
    montarModal(demanda({ estado }));

    expect(screen.getByLabelText("Título")).toBeTruthy();
    expect(botaoDePlanejar()).toBeNull();
  });
});

// Os três estados do botão (issue #1348, ADR 0075, decisão 8).
describe("O botão do card conforme o planejamento", () => {
  function botaoDeContinuar(): HTMLElement | null {
    return screen.queryByRole("link", { name: CONTINUAR_PLANEJAMENTO });
  }

  it("sem planejamento, mostra Planejar com a IA", () => {
    montarModal(demanda({ tem_planejamento: false }));

    expect(botaoDePlanejar()).not.toBeNull();
    expect(botaoDeContinuar()).toBeNull();
  });

  it("com planejamento em andamento, mostra Continuar planejamento e leva à mesma tela", () => {
    montarModal(demanda({ tem_planejamento: true }));

    expect(botaoDeContinuar()?.getAttribute("href")).toBe("/admin/tecnologia/planejamento/d-1");
    expect(botaoDePlanejar()).toBeNull();
  });

  it("com Vínculo, nenhum dos dois, mesmo com planejamento guardado", () => {
    montarModal(demanda({ tem_planejamento: true, tem_vinculo: true, vinculo: null }));

    expect(screen.getByLabelText("Título")).toBeTruthy();
    expect(botaoDePlanejar()).toBeNull();
    expect(botaoDeContinuar()).toBeNull();
  });
});

// ─── A tela do planejamento ──────────────────────────────────────────────────

const PERGUNTA: MensagemDoPlanejamento = {
  tipo: "pergunta",
  contexto: "Quem vai usar a agenda nova?",
  opcoes: [
    { letra: "A", texto: "Só a recepção." },
    { letra: "B", texto: "A recepção e a enfermagem." },
  ],
  recomendada: "B",
};

const SEGUNDA: MensagemDoPlanejamento = {
  tipo: "pergunta",
  contexto: "O retorno precisa de horário marcado?",
  opcoes: [
    { letra: "A", texto: "Sim, com hora." },
    { letra: "B", texto: "Só o dia." },
  ],
  recomendada: "A",
};

function planejamento(extra: Partial<Planejamento> = {}): Planejamento {
  return {
    demanda_id: "d-1",
    titulo: "Agenda de retorno na recepção",
    estado: "em_andamento",
    mensagens: [PERGUNTA],
    decisoes: [],
    ...extra,
  };
}

type Pedido = { url: string; metodo: string; corpo: unknown };

function resposta(corpo: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => corpo } as unknown as Response;
}

/** O que a rota de voz devolve como texto transcrito, no servidor de mentira. */
let transcricao = "só a recepção, de manhã";

/**
 * O servidor de mentira: o GET devolve `lido`, cada POST do planejamento
 * devolve o próximo de `respostas`, e a rota de voz devolve `transcricao`.
 */
function dublarServidor(lido: Planejamento, respostas: Response[] = []): Pedido[] {
  const pedidos: Pedido[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const audio = init?.body instanceof FormData;
      pedidos.push({ url, metodo, corpo: init?.body && !audio ? JSON.parse(String(init.body)) : undefined });
      if (url.endsWith("/transcricao/voz")) return resposta({ texto: transcricao });
      if (metodo === "GET") return resposta(lido);
      return respostas.shift() ?? resposta({ detail: "sem resposta preparada" }, 500);
    }),
  );
  return pedidos;
}

/** Os POSTs AO PLANEJAMENTO, isto é, o que foi para a IA. */
function posts(pedidos: Pedido[]): Pedido[] {
  return pedidos.filter((p) => p.metodo === "POST" && !p.url.endsWith("/transcricao/voz"));
}

function paraVoz(pedidos: Pedido[]): Pedido[] {
  return pedidos.filter((p) => p.url.endsWith("/transcricao/voz"));
}

// O ToastProvider é o de verdade: o hook de gravação de voz avisa por toast
// quando a transcrição falha, e ele exige provider para existir.
function montarTela() {
  return render(
    <ToastProvider>
      <PlanejamentoDaDemanda demandaId="d-1" token="token-de-teste" />
    </ToastProvider>,
  );
}

function painelDeDecisoes(): HTMLElement {
  return screen.getByRole("region", { name: TITULO_DAS_DECISOES });
}

const DEPOIS_DA_RESPOSTA = planejamento({
  mensagens: [PERGUNTA, { tipo: "resposta", opcao: "A", texto: "Só a recepção." }, SEGUNDA],
  decisoes: ["Só a recepção usa a agenda nova."],
});

describe("A tela do planejamento", () => {
  it("mostra a pergunta com o contexto e as duas opções", async () => {
    dublarServidor(planejamento());
    montarTela();

    expect(await screen.findByText("Quem vai usar a agenda nova?")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Só a recepção\./ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /A recepção e a enfermagem\./ })).toBeTruthy();
  });

  it("a opção recomendada vem destacada, e só ela", async () => {
    dublarServidor(planejamento());
    montarTela();

    const recomendada = await screen.findByRole("button", { name: /A recepção e a enfermagem\./ });
    const outra = screen.getByRole("button", { name: /Só a recepção\./ });
    expect(within(recomendada).getByText("Recomendada")).toBeTruthy();
    expect(within(outra).queryByText("Recomendada")).toBeNull();
  });

  it("clicar na opção manda a letra", async () => {
    const pedidos = dublarServidor(planejamento(), [resposta(DEPOIS_DA_RESPOSTA)]);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: /Só a recepção\./ }));

    await waitFor(() => expect(posts(pedidos)).toHaveLength(1));
    expect(posts(pedidos)[0]).toEqual({
      url: "/api/admin/tecnologia/demandas/d-1/planejamento",
      metodo: "POST",
      corpo: { opcao: "A" },
    });
  });

  it("o campo livre manda o texto", async () => {
    const pedidos = dublarServidor(planejamento(), [resposta(DEPOIS_DA_RESPOSTA)]);
    montarTela();

    fireEvent.change(await screen.findByLabelText("Sua resposta"), { target: { value: "Depende do plantão." } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar resposta" }));

    await waitFor(() => expect(posts(pedidos)).toHaveLength(1));
    expect(posts(pedidos)[0].corpo).toEqual({ texto: "Depende do plantão." });
  });

  it("O que já decidimos cresce a cada resposta", async () => {
    dublarServidor(planejamento(), [resposta(DEPOIS_DA_RESPOSTA)]);
    montarTela();

    await screen.findByText("Quem vai usar a agenda nova?");
    expect(within(painelDeDecisoes()).getByText(NADA_DECIDIDO)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Só a recepção\./ }));

    expect(await within(painelDeDecisoes()).findByText("Só a recepção usa a agenda nova.")).toBeTruthy();
    expect(await screen.findByText("O retorno precisa de horário marcado?")).toBeTruthy();
  });

  it("sem planejamento guardado, a tela começa a conversa sozinha", async () => {
    const pedidos = dublarServidor(planejamento({ estado: null, mensagens: [] }), [resposta(planejamento())]);
    montarTela();

    expect(await screen.findByText("Quem vai usar a agenda nova?")).toBeTruthy();
    expect(posts(pedidos).map((p) => p.corpo)).toEqual([{}]);
  });

  it("com conversa guardada, retoma de onde parou sem começar de novo", async () => {
    const pedidos = dublarServidor(DEPOIS_DA_RESPOSTA);
    montarTela();

    expect(await screen.findByText("O retorno precisa de horário marcado?")).toBeTruthy();
    expect(posts(pedidos)).toEqual([]);
  });

  it("retomar abre na última pergunta, sem as opções da anterior e com O que já decidimos completo", async () => {
    const TERCEIRA: MensagemDoPlanejamento = {
      tipo: "pergunta",
      contexto: "Quem confirma o retorno com o paciente?",
      opcoes: [
        { letra: "A", texto: "A recepção liga." },
        { letra: "B", texto: "O paciente recebe mensagem." },
      ],
      recomendada: "B",
    };
    const pedidos = dublarServidor(
      planejamento({
        mensagens: [...DEPOIS_DA_RESPOSTA.mensagens, { tipo: "resposta", opcao: "A", texto: "Sim, com hora." }, TERCEIRA],
        decisoes: ["Só a recepção usa a agenda nova.", "O retorno é marcado com hora."],
      }),
    );
    montarTela();

    // A pergunta que espera resposta é a última, com as duas opções clicáveis.
    expect(await screen.findByRole("button", { name: /A recepção liga\./ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /O paciente recebe mensagem\./ })).toBeTruthy();
    // As anteriores ficam na conversa como histórico, sem opção para clicar de novo.
    expect(screen.queryByRole("button", { name: /Só a recepção\./ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Só o dia\./ })).toBeNull();
    // O painel vem com tudo o que já foi decidido, na ordem.
    const decisoes = within(painelDeDecisoes()).getAllByRole("listitem").map((li) => li.textContent);
    expect(decisoes).toEqual(["Só a recepção usa a agenda nova.", "O retorno é marcado com hora."]);
    expect(posts(pedidos)).toEqual([]);
  });

  it("falha do servidor mostra a frase dele e deixa a conversa e o texto como estavam", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const frase = "A IA não conseguiu responder agora. Tente de novo em instantes.";
    dublarServidor(planejamento(), [resposta({ detail: frase }, 502)]);
    montarTela();

    fireEvent.change(await screen.findByLabelText("Sua resposta"), { target: { value: "Depende do plantão." } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar resposta" }));

    expect((await screen.findByRole("alert")).textContent).toContain(frase);
    expect(screen.getByText("Quem vai usar a agenda nova?")).toBeTruthy();
    expect((screen.getByLabelText("Sua resposta") as HTMLTextAreaElement).value).toBe("Depende do plantão.");
  });

  it("encerrado, não há mais opção nem campo para responder", async () => {
    dublarServidor(
      planejamento({
        estado: "encerrado",
        mensagens: [...DEPOIS_DA_RESPOSTA.mensagens, { tipo: "resposta", opcao: "B", texto: "Só o dia." }, {
          tipo: "encerrou",
          contexto: "Já tenho o que preciso para a Vitta planejar.",
        }],
      }),
    );
    montarTela();

    expect(await screen.findByText("Já tenho o que preciso para a Vitta planejar.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Sim, com hora\./ })).toBeNull();
    expect(screen.queryByLabelText("Sua resposta")).toBeNull();
  });
});

// ─── Fechar e resumir, o resumo e o "não" (issue #1347) ─────────────────────

const RESUMO = {
  decisoes: [
    { pergunta: "Quem vai usar a agenda nova?", escolha: "Só a recepção.", porque: "É a recepção que marca a saída." },
  ],
  em_aberto: ["Quem confirma o retorno com o paciente."],
};

const RESUMIDO = planejamento({
  estado: "resumido",
  mensagens: [PERGUNTA, { tipo: "resposta", opcao: "A", texto: "Só a recepção." }],
  decisoes: ["Só a recepção usa a agenda nova."],
  resumo: RESUMO,
});

function regiao(nome: string): HTMLElement {
  return screen.getByRole("region", { name: nome });
}

describe("Fechar e resumir", () => {
  it("já na primeira pergunta, chama a rota do resumo e abre o resumo", async () => {
    const pedidos = dublarServidor(planejamento(), [resposta(RESUMIDO)]);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: FECHAR_E_RESUMIR }));

    await waitFor(() => expect(posts(pedidos)).toHaveLength(1));
    expect(posts(pedidos)[0].url).toBe("/api/admin/tecnologia/demandas/d-1/planejamento/resumo");
    expect(await screen.findByRole("heading", { name: TITULO_DO_RESUMO })).toBeTruthy();
  });

  it("quando a IA encerra, a tela pede o resumo sozinha", async () => {
    const encerrado = planejamento({
      estado: "encerrado",
      mensagens: [
        PERGUNTA,
        { tipo: "resposta", opcao: "A", texto: "Só a recepção." },
        { tipo: "encerrou", contexto: "Já tenho o que preciso para a Vitta planejar." },
      ],
    });
    const pedidos = dublarServidor(planejamento(), [resposta(encerrado), resposta(RESUMIDO)]);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: /Só a recepção\./ }));

    expect(await screen.findByRole("heading", { name: TITULO_DO_RESUMO })).toBeTruthy();
    expect(posts(pedidos).map((p) => p.url)).toEqual([
      "/api/admin/tecnologia/demandas/d-1/planejamento",
      "/api/admin/tecnologia/demandas/d-1/planejamento/resumo",
    ]);
  });

  it("depois do encerrou, o botão continua lá", async () => {
    dublarServidor(
      planejamento({
        estado: "encerrado",
        mensagens: [PERGUNTA, { tipo: "encerrou", contexto: "Já tenho o que preciso para a Vitta planejar." }],
      }),
    );
    montarTela();

    expect(await screen.findByRole("button", { name: FECHAR_E_RESUMIR })).toBeTruthy();
  });
});

describe("O resumo", () => {
  it("lista as decisões, com pergunta, escolha e porquê, e o que ficou em aberto", async () => {
    dublarServidor(RESUMIDO);
    montarTela();

    await screen.findByRole("heading", { name: TITULO_DO_RESUMO });
    const decisoes = regiao(TITULO_DAS_DECISOES_DO_RESUMO);
    expect(within(decisoes).getByText("Quem vai usar a agenda nova?")).toBeTruthy();
    expect(within(decisoes).getByText("Só a recepção.")).toBeTruthy();
    expect(within(decisoes).getByText("É a recepção que marca a saída.")).toBeTruthy();
    expect(within(regiao(TITULO_DO_EM_ABERTO)).getByText("Quem confirma o retorno com o paciente.")).toBeTruthy();
    // O que ficou em aberto não aparece como decisão.
    expect(within(decisoes).queryByText("Quem confirma o retorno com o paciente.")).toBeNull();
  });

  it("o sim manda para os desenvolvedores e a tela diz que foi", async () => {
    const enviado = planejamento({ ...RESUMIDO, estado: "enviado" });
    const pedidos = dublarServidor(RESUMIDO, [resposta(enviado)]);
    montarTela();

    const sim = (await screen.findByRole("button", { name: SIM_MANDAR })) as HTMLButtonElement;
    expect(sim.disabled).toBe(false);
    fireEvent.click(sim);

    expect(await screen.findByRole("heading", { name: TITULO_DO_ENVIADO })).toBeTruthy();
    expect(posts(pedidos)).toEqual([
      { url: "/api/admin/tecnologia/demandas/d-1/planejamento/enviar", metodo: "POST", corpo: {} },
    ]);
    // O estado seguinte: sem resumo para responder, sem sim nem não.
    expect(screen.queryByRole("heading", { name: TITULO_DO_RESUMO })).toBeNull();
    expect(screen.queryByRole("button", { name: SIM_MANDAR })).toBeNull();
    expect(screen.queryByRole("button", { name: "Não" })).toBeNull();
    expect(screen.getByRole("link", { name: VOLTAR_PARA_A_TECNOLOGIA }).getAttribute("href")).toBe(
      "/admin/tecnologia",
    );
  });

  it("o sim que falha mostra a frase do servidor e o resumo continua", async () => {
    dublarServidor(RESUMIDO, [resposta({ detail: "O GitHub não respondeu. Tente de novo em alguns instantes." }, 502)]);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: SIM_MANDAR }));

    expect((await screen.findByRole("alert")).textContent).toContain("O GitHub não respondeu.");
    expect(screen.getByRole("heading", { name: TITULO_DO_RESUMO })).toBeTruthy();
    expect((screen.getByRole("button", { name: SIM_MANDAR }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("aberta depois do sim, a tela mostra que já foi, sem chamar a IA", async () => {
    const pedidos = dublarServidor(planejamento({ ...RESUMIDO, estado: "enviado" }));
    montarTela();

    expect(await screen.findByRole("heading", { name: TITULO_DO_ENVIADO })).toBeTruthy();
    expect(posts(pedidos)).toEqual([]);
  });

  it("o não sem texto é recusado na tela, sem ir ao servidor", async () => {
    const pedidos = dublarServidor(RESUMIDO);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: "Não" }));
    fireEvent.change(screen.getByLabelText(O_QUE_NAO_BATEU), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar o que não bateu" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Diga o que não bateu no resumo.");
    expect(posts(pedidos)).toEqual([]);
  });

  it("o não com texto vai à rota do não e a conversa retoma com a próxima pergunta", async () => {
    const depoisDoNao = planejamento({
      estado: "em_andamento",
      mensagens: [...RESUMIDO.mensagens, { tipo: "nao_bateu", texto: "A enfermagem também usa." }],
      resumo: RESUMO,
    });
    const retomou = planejamento({ ...depoisDoNao, mensagens: [...depoisDoNao.mensagens, SEGUNDA] });
    const pedidos = dublarServidor(RESUMIDO, [resposta(depoisDoNao), resposta(retomou)]);
    montarTela();

    fireEvent.click(await screen.findByRole("button", { name: "Não" }));
    fireEvent.change(screen.getByLabelText(O_QUE_NAO_BATEU), { target: { value: "A enfermagem também usa." } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar o que não bateu" }));

    expect(await screen.findByText("O retorno precisa de horário marcado?")).toBeTruthy();
    expect(posts(pedidos)).toEqual([
      {
        url: "/api/admin/tecnologia/demandas/d-1/planejamento/nao",
        metodo: "POST",
        corpo: { texto: "A enfermagem também usa." },
      },
      { url: "/api/admin/tecnologia/demandas/d-1/planejamento", metodo: "POST", corpo: {} },
    ]);
    expect(screen.queryByRole("heading", { name: TITULO_DO_RESUMO })).toBeNull();
  });

  it("aberta depois de um não cuja pergunta seguinte falhou, a tela pede a pergunta de novo", async () => {
    const depoisDoNao = planejamento({
      mensagens: [...RESUMIDO.mensagens, { tipo: "nao_bateu", texto: "A enfermagem também usa." }],
    });
    const seguinte = planejamento({ ...depoisDoNao, mensagens: [...depoisDoNao.mensagens, SEGUNDA] });
    const pedidos = dublarServidor(depoisDoNao, [resposta(seguinte)]);
    montarTela();

    expect(await screen.findByText("O retorno precisa de horário marcado?")).toBeTruthy();
    expect(posts(pedidos).map((p) => p.corpo)).toEqual([{}]);
  });
});

// ─── A voz no campo livre (issue #1348) ──────────────────────────────────────
//
// O gravador do navegador é falso, e o hook de gravação é o DE VERDADE, o
// mesmo do Assistente de Tecnologia: dublar o hook provaria que a tela sabe
// receber um texto, e não que o microfone chega à rota de voz que já existe.

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

async function falar() {
  fireEvent.click(await screen.findByRole("button", { name: "Gravar voz" }));
  await waitFor(() => expect(GravadorFalso.ultimo).not.toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "Parar de gravar" }));
}

function campoLivre(): HTMLTextAreaElement {
  return screen.getByLabelText("Sua resposta") as HTMLTextAreaElement;
}

describe("A voz no campo livre", () => {
  afterEach(() => {
    transcricao = "só a recepção, de manhã";
  });

  it("vai pela rota de transcrição que já existe e o texto cai no campo, sem ir para a IA", async () => {
    plugarOMicrofone();
    const pedidos = dublarServidor(planejamento());
    montarTela();

    await falar();

    await waitFor(() => expect(campoLivre().value).toBe("só a recepção, de manhã"));
    expect(paraVoz(pedidos)).toHaveLength(1);
    expect(paraVoz(pedidos)[0].metodo).toBe("POST");
    // Transcrever não é responder: nada foi para a IA ainda.
    expect(posts(pedidos)).toEqual([]);
  });

  it("o texto falado só vai para a IA quando o diretor envia, e vai como texto", async () => {
    plugarOMicrofone();
    const pedidos = dublarServidor(planejamento(), [resposta(DEPOIS_DA_RESPOSTA)]);
    montarTela();

    await falar();
    await waitFor(() => expect(campoLivre().value).toBe("só a recepção, de manhã"));
    fireEvent.click(screen.getByRole("button", { name: "Enviar resposta" }));

    await waitFor(() => expect(posts(pedidos)).toHaveLength(1));
    expect(posts(pedidos)[0].corpo).toEqual({ texto: "só a recepção, de manhã" });
  });

  it("o que já estava escrito fica, e a fala entra depois", async () => {
    plugarOMicrofone();
    dublarServidor(planejamento());
    montarTela();

    fireEvent.change(await screen.findByLabelText("Sua resposta"), { target: { value: "Depende do plantão." } });
    await falar();

    await waitFor(() => expect(campoLivre().value).toBe("Depende do plantão. só a recepção, de manhã"));
  });
});
