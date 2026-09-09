/**
 * @vitest-environment jsdom
 */

/**
 * Apagar pela Diretoria, na tela do Dossiê (issue #595, PRD #591, ADR 0047).
 *
 * A régua de quem pode apagar tem teste próprio em `lib/ouvidoria/apagamento.ts`.
 * O que só existe aqui dentro é a fiação: o botão aparecer para a Diretoria e
 * só para ela, a confirmação exigir o motivo escrito, o motivo viajar no corpo
 * do POST, e a tela adotar o Dossiê que a rota devolve.
 *
 * **Todo teste do que NÃO aparece vem em par com o caso em que aparece.** Um
 * "o ouvidor não vê o botão" sozinho ficaria verde com o botão removido da tela
 * para todo mundo, ou com a página quebrada antes de desenhar qualquer coisa.
 *
 * O perfil chega pelo `useCurrentParticipante`, que é dublado aqui: é ele que a
 * página usa para saber quem está logado.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TITULO_DO_CASO_APAGADO } from "@/lib/ouvidoria/apagamento";
import { Dossie } from "./Dossie";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: null as string | null }));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: { id: "P11", nome_completo: "Dr. Diretor", perfil_ouvidoria: sessao.perfilOuvidoria },
    loading: false,
    error: null,
  }),
  invalidateCurrentParticipante: () => {},
}));

const APAGADO_EM = "2026-09-08T15:00:00+00:00";
const MOTIVO = "Pedido da paciente, com decisão da Diretoria em 08/09/2026.";
const RELATO = "Cheguei as 8h com minha mãe e só fomos atendidos as 10h30.";

/** Dois dias atrás: caso encerrado, e ainda dentro da janela da reincidência. */
function encerradoAgoraHaPouco(): string {
  return new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
}

function movimentoDoApagamento(autor: string) {
  return {
    ocorrido_em: APAGADO_EM,
    autor,
    sistema: false,
    apagamento: true,
    marco: null,
    marco_rotulo: null,
    descricao: "Apagamento do Dossiê",
    texto: null,
    desde_marco: null,
    desde_marco_rotulo: null,
    minutos_uteis: null,
  };
}

function dossie(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "encerrado",
    tipo_manifestacao: "reclamacao",
    categoria: "Demora no atendimento",
    setor: "Recepção",
    resumo: "Paciente relata espera acima de duas horas na recepção.",
    relato_integral: RELATO,
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "(31) 99999-0000",
    manifestante_vinculo: "acompanhante",
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: "procedente",
    desfecho_descricao: null,
    gravidade: "medio",
    prazo_area_em: null,
    validada_em: "2026-08-25T17:00:00+00:00",
    respondida_em: "2026-08-27T17:00:00+00:00",
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: encerradoAgoraHaPouco(),
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "ana",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    anonimizada_em: null,
    apagamento_pedido_em: null,
    apagamento_pedido_por: null,
    apagamento_motivo: null,
    marcos: [],
    prazos: [],
    degradado: [],
    ...overrides,
  };
}

/** O caso como a rota o devolve depois de apagar. */
function apagado() {
  return dossie({
    anonimizada_em: APAGADO_EM,
    apagamento_pedido_em: APAGADO_EM,
    apagamento_pedido_por: "P11",
    apagamento_motivo: MOTIVO,
    relato_integral: null,
    resumo: "[anonimizado pela retenção]",
    manifestante_nome: null,
    manifestante_contato: null,
  });
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

async function assentar() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

/**
 * `depoisDeApagar` é o corpo que a rota do apagamento devolve, e `trilha` o que
 * a leitura dos movimentos traz. Os dois entram separados porque provam coisas
 * diferentes: o primeiro que a tela ADOTA a resposta, o segundo de onde vem o
 * crédito de quem apagou.
 */
function montar(
  caso: Record<string, unknown>,
  { depoisDeApagar, trilha }: { depoisDeApagar?: Record<string, unknown>; trilha?: unknown } = {}
) {
  const chamadas: { url: string; body: unknown }[] = [];
  let atual = caso;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/apagamento")) {
        chamadas.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
        atual = depoisDeApagar ?? apagado();
        return respostaJson(atual);
      }
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      if (url.endsWith("/movimentos")) return respostaJson(trilha ?? { movimentos: [], degradado: [] });
      return respostaJson(atual);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
  return chamadas;
}

const BOTAO_APAGAR = { name: /^Apagar$/ };

describe("o botão de apagar, e quem o vê (issue #595)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("a Diretoria vê o botão no caso encerrado", async () => {
    montar(dossie());

    expect(await screen.findByRole("button", BOTAO_APAGAR)).toBeTruthy();
  });

  it("o ouvidor não vê o botão no MESMO caso", async () => {
    sessao.perfilOuvidoria = "ouvidor";
    montar(dossie());

    // Espera a página assentar antes de afirmar ausência: o Dossiê chega na
    // primeira das seis requisições, e afirmar cedo mediria a tela vazia.
    expect(await screen.findByText(RELATO)).toBeTruthy();
    await assentar();

    expect(screen.queryByRole("button", BOTAO_APAGAR)).toBeNull();
  });

  it("o caso em andamento não oferece o botão, nem para a Diretoria", async () => {
    montar(dossie({ status: "aguardando_area" }));

    expect(await screen.findByText(RELATO)).toBeTruthy();
    await assentar();

    expect(screen.queryByRole("button", BOTAO_APAGAR)).toBeNull();
  });

  it("o caso já apagado não oferece o botão", async () => {
    montar(apagado(), { trilha: { movimentos: [movimentoDoApagamento("Dr. Diretor")], degradado: [] } });

    await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    await assentar();

    expect(screen.queryByRole("button", BOTAO_APAGAR)).toBeNull();
  });
});

describe("a confirmação com motivo obrigatório (issue #595)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function abrirAConfirmacao() {
    const botao = await screen.findByRole("button", BOTAO_APAGAR);
    await act(async () => {
      fireEvent.click(botao);
    });
  }

  it("sem motivo escrito o ato não sai da tela", async () => {
    const chamadas = montar(dossie());
    await abrirAConfirmacao();

    const confirmar = screen.getByRole("button", { name: /Apagar agora/ });

    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      fireEvent.click(confirmar);
    });
    expect(chamadas).toEqual([]);
  });

  it("com o motivo escrito o ato vai ao servidor com ele no corpo", async () => {
    const chamadas = montar(dossie(), {
      trilha: { movimentos: [movimentoDoApagamento("Dr. Diretor")], degradado: [] },
    });
    await abrirAConfirmacao();

    fireEvent.change(screen.getByRole("textbox", { name: /Motivo/ }), { target: { value: MOTIVO } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Apagar agora/ }));
    });

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toContain("/manifestacoes/uuid-12/apagamento");
    expect(chamadas[0].body).toEqual({ motivo: MOTIVO });
  });

  it("o aviso do ato continua legível depois de o botão sair da tela", async () => {
    // O carimbo do servidor precisa de par na tela. Como a tela adota o caso
    // já apagado no mesmo render, o bloco do botão sai junto: um aviso escrito
    // DENTRO dele nunca chegaria a ser lido, e o ato ficaria sem confirmação
    // nenhuma para quem clicou.
    montar(dossie(), { trilha: { movimentos: [movimentoDoApagamento("Dr. Diretor")], degradado: [] } });
    await abrirAConfirmacao();

    fireEvent.change(screen.getByRole("textbox", { name: /Motivo/ }), { target: { value: MOTIVO } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Apagar agora/ }));
    });

    expect(await screen.findByText(/Caso apagado\./)).toBeTruthy();
    // E o botão realmente saiu: sem isto, o aviso poderia estar aparecendo
    // por o bloco inteiro ter continuado na tela.
    expect(screen.queryByRole("button", BOTAO_APAGAR)).toBeNull();
  });

  it("a recusa do servidor chega à tela com a frase que ele mandou", async () => {
    const recusa = "Só um caso encerrado pode ser apagado.";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/apagamento")) {
          return { ok: false, status: 409, json: async () => ({ detail: recusa }) } as Response;
        }
        if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
        if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
        if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
        if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
        if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
        if (url.endsWith("/movimentos")) return respostaJson({ movimentos: [], degradado: [] });
        return respostaJson(dossie());
      })
    );
    render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
    await abrirAConfirmacao();

    fireEvent.change(screen.getByRole("textbox", { name: /Motivo/ }), { target: { value: MOTIVO } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Apagar agora/ }));
    });

    expect(await screen.findByText(recusa)).toBeTruthy();
  });

  it("a tela adota o caso que a rota devolve, sem recarregar nada", async () => {
    // Sem isso, a Diretoria continuaria lendo o relato de um caso que o banco
    // já apagou, até alguém apertar F5.
    montar(dossie(), { trilha: { movimentos: [movimentoDoApagamento("Dr. Diretor")], degradado: [] } });
    await abrirAConfirmacao();

    fireEvent.change(screen.getByRole("textbox", { name: /Motivo/ }), { target: { value: MOTIVO } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Apagar agora/ }));
    });

    const aviso = await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    expect(aviso.textContent).toContain(MOTIVO);
    await waitFor(() => expect(screen.queryByText(RELATO)).toBeNull());
  });
});

describe("o aviso do caso apagado diz por quem e por quê (issue #595)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "diretoria_executiva";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("o caso apagado pela Diretoria mostra o autor e o motivo", async () => {
    montar(apagado(), { trilha: { movimentos: [movimentoDoApagamento("Dr. Diretor")], degradado: [] } });

    const aviso = await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });

    await waitFor(() => expect(aviso.textContent).toContain("Dr. Diretor"));
    expect(aviso.textContent).toContain(MOTIVO);
  });

  it("o caso apagado pelos cinco anos mostra o autor de sistema e nenhum motivo", async () => {
    // O contraste que impede a tela de inventar um motivo onde não houve
    // pedido nenhum: ali o prazo venceu, e não há o que citar.
    const cincoAnos = dossie({
      anonimizada_em: APAGADO_EM,
      relato_integral: null,
      apagamento_pedido_em: null,
      apagamento_pedido_por: null,
      apagamento_motivo: null,
    });
    montar(cincoAnos, { trilha: { movimentos: [movimentoDoApagamento("Sistema (retenção)")], degradado: [] } });

    const aviso = await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });

    await waitFor(() => expect(aviso.textContent).toContain("Sistema (retenção)"));
    expect(aviso.textContent).not.toContain("Motivo");
  });
});
