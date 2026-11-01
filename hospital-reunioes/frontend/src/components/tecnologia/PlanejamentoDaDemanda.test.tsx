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

import { DemandaModal } from "./DemandaModal";
import { Demanda, EuNaAba } from "./demandas";
import { MensagemDoPlanejamento, Planejamento, PLANEJAR_COM_A_IA } from "./planejamento";
import { NADA_DECIDIDO, PlanejamentoDaDemanda, TITULO_DAS_DECISOES } from "./PlanejamentoDaDemanda";

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

/** O servidor de mentira: o GET devolve `lido`, cada POST devolve o próximo de `respostas`. */
function dublarServidor(lido: Planejamento, respostas: Response[] = []): Pedido[] {
  const pedidos: Pedido[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      pedidos.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (metodo === "GET") return resposta(lido);
      return respostas.shift() ?? resposta({ detail: "sem resposta preparada" }, 500);
    }),
  );
  return pedidos;
}

function posts(pedidos: Pedido[]): Pedido[] {
  return pedidos.filter((p) => p.metodo === "POST");
}

function montarTela() {
  return render(<PlanejamentoDaDemanda demandaId="d-1" token="token-de-teste" />);
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
