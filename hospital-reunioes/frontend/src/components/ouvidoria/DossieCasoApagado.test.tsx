/**
 * @vitest-environment jsdom
 */

/**
 * O caso apagado, na tela do Dossiê (issue #593, ADR 0034).
 *
 * A régua de o que decide o apagamento e de onde sai o crédito tem teste
 * próprio em `lib/ouvidoria/apagamento.ts`. O que só existe aqui dentro é a
 * fiação: o aviso ocupar o lugar do relato, os blocos de texto do Dossiê
 * saírem da tela junto, e o botão de reabrir não ser oferecido num caso que o
 * servidor recusa.
 *
 * **As asserções procuram o MARCADOR do aviso, e não a ausência do relato.**
 * O caso que a Retenção limpou já chega com `relato_integral` nulo e
 * `resposta_da_area` nula: um teste que só perguntasse se o texto sumiu ficaria
 * verde com o bloco inteiro removido da tela, ou com o aviso nunca escrito.
 * Quem prova que a tela DIZ o que houve é o título do bloco.
 *
 * O `fetch` entra dublado por URL: a página carrega anexos, notificações,
 * prorrogações, respostas, tentativas e a trilha junto do Dossiê.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TITULO_DO_CASO_APAGADO } from "@/lib/ouvidoria/apagamento";
import { Dossie } from "./Dossie";

/** Meio-dia de Brasília: longe da virada do dia em qualquer fuso da máquina. */
const APAGADO_EM = "2031-09-01T15:00:00+00:00";
const AUTOR_DO_APAGAMENTO = "Sistema (retenção)";

const RESUMO = "Paciente relata espera acima de duas horas na recepção.";
const RELATO = "Cheguei as 8h com minha mãe e só fomos atendidos as 10h30.";
const RESPOSTA_DA_AREA = "Refizemos a escala do plantão noturno e abrimos mais um guichê.";
const ANEXO = "foto-da-fila.jpg";

/**
 * O texto que a Retenção deixa na justificativa da prorrogação. Ela não zera a
 * coluna (a migration 073 a fez NOT NULL): troca o conteúdo por este marcador
 * INTERNO, que não é frase para ninguém ler na tela.
 */
const MARCADOR_INTERNO = "[anonimizado pela retenção]";

function prorrogacao() {
  return {
    id: "prorrogacao-1",
    justificativa: MARCADOR_INTERNO,
    dias_uteis_pedidos: 3,
    prazo_anterior: "2026-08-31T20:00:00+00:00",
    prazo_novo: "2026-09-03T20:00:00+00:00",
    status: "aprovada",
    solicitada_em: "2026-08-28T17:00:00+00:00",
    solicitante_nome: "Carlos Titular",
    decidida_em: "2026-08-28T18:00:00+00:00",
    decidida_por_nome: "Marta Ouvidora",
    decisao_justificativa: null,
  };
}

/** Dois dias atrás: caso encerrado dentro da janela da reincidência. */
function encerradoAgoraHaPouco(): string {
  return new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
}

function movimentoDoApagamento() {
  return {
    ocorrido_em: APAGADO_EM,
    autor: AUTOR_DO_APAGAMENTO,
    sistema: true,
    apagamento: true,
    marco: null,
    marco_rotulo: null,
    descricao: "Caso alcançado pela política de retenção",
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
    resumo: RESUMO,
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
    resposta_da_area: RESPOSTA_DA_AREA,
    respondida_por_nome: "Carlos Titular",
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
    marcos: [],
    prazos: [],
    degradado: [],
    ...overrides,
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

/**
 * Deixa TODAS as leituras da página assentarem antes de afirmar ausência.
 *
 * A página dispara seis requisições, e o aviso de caso apagado vem da primeira
 * delas. Afirmar "o bloco X não está na tela" logo depois do aviso mediria a
 * requisição que ainda não voltou, não a porta que se quer provar: o teste
 * ficaria verde com a porta removida. Uma volta de macrotarefa esvazia as
 * promessas dos stubs, e o React processa as atualizações dentro do `act`.
 */
async function assentar() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function montar(
  caso: Record<string, unknown>,
  trilha: unknown = { movimentos: [], degradado: [] },
  prorrogacoes: unknown[] = []
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) {
        return respostaJson({
          anexos: [
            {
              id: "anexo-1",
              filename: ANEXO,
              content_type: "image/jpeg",
              tamanho_bytes: 120000,
              enviado_por_nome: "Joana da Silva",
            },
          ],
        });
      }
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      if (url.endsWith("/movimentos")) {
        if (trilha === null) return { ok: false, json: async () => ({}) } as Response;
        return respostaJson(trilha);
      }
      return respostaJson(caso);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

describe("o Dossiê do caso apagado (issue #593)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra o aviso com a data do carimbo e o autor da trilha", async () => {
    montar(dossie({ anonimizada_em: APAGADO_EM }), {
      movimentos: [movimentoDoApagamento()],
      degradado: [],
    });

    const aviso = await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });

    expect(aviso.textContent).toMatch(/01\/09\/2031/);
    // O crédito chega na segunda requisição, a da trilha: o aviso nasce com a
    // data que o caso já trazia e ganha o autor quando a trilha volta.
    await waitFor(() =>
      expect(
        screen.getByRole("note", { name: TITULO_DO_CASO_APAGADO }).textContent
      ).toContain(AUTOR_DO_APAGAMENTO)
    );
  });

  it("o caso vivo não mostra o aviso e continua mostrando o relato", async () => {
    montar(dossie());

    expect(await screen.findByText(RELATO)).toBeTruthy();
    expect(screen.queryByRole("note", { name: TITULO_DO_CASO_APAGADO })).toBeNull();
  });

  it("no caso apagado a tela não desenha resumo, relato, anexos nem resposta da área", async () => {
    // O servidor já devolve esses campos vazios no caso que a Retenção limpou,
    // mas a tela não pode depender disso: o resumo chega com o marcador interno
    // da anonimização, e o apagamento pela Diretoria (issue #595) grava o mesmo
    // carimbo por outra porta.
    montar(dossie({ anonimizada_em: APAGADO_EM }), {
      movimentos: [movimentoDoApagamento()],
      degradado: [],
    });
    await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    await assentar();

    expect(screen.queryByText("Resumo")).toBeNull();
    expect(screen.queryByText("Relato integral")).toBeNull();
    expect(screen.queryByText("Anexos")).toBeNull();
    expect(screen.queryByText(ANEXO)).toBeNull();
    expect(screen.queryByText(/Resposta da área/)).toBeNull();
    expect(screen.queryByText(RESPOSTA_DA_AREA)).toBeNull();
  });

  it("o botão de reabrir some no caso apagado e fica no caso vivo da mesma janela", async () => {
    montar(dossie());
    expect(await screen.findByRole("button", { name: /Reabrir por reincidência/ })).toBeTruthy();

    cleanup();
    vi.unstubAllGlobals();

    montar(dossie({ anonimizada_em: APAGADO_EM }), {
      movimentos: [movimentoDoApagamento()],
      degradado: [],
    });
    await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    await assentar();

    expect(screen.queryByRole("button", { name: /Reabrir por reincidência/ })).toBeNull();
  });

  it("no caso apagado a prorrogação não desenha o marcador interno da anonimização", async () => {
    // A Retenção não zera `justificativa` (a coluna é NOT NULL desde a
    // migration 073): ela troca o texto pelo marcador interno. Sem a porta, a
    // tela mostraria o aviso de caso apagado e, logo abaixo, esse marcador.
    montar(
      dossie({ anonimizada_em: APAGADO_EM }),
      { movimentos: [movimentoDoApagamento()], degradado: [] },
      [prorrogacao()]
    );
    await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    await assentar();

    expect(screen.queryByText("Prorrogação de prazo")).toBeNull();
    expect(screen.queryByText(MARCADOR_INTERNO)).toBeNull();
  });

  it("o caso vivo continua mostrando a prorrogação", async () => {
    // O contraste da porta nova: barrar o bloco para todo mundo passaria igual.
    montar(dossie(), { movimentos: [], degradado: [] }, [prorrogacao()]);

    expect(await screen.findByText("Prorrogação de prazo")).toBeTruthy();
  });

  it("no caso apagado a tela não oferece a classificação, que grava texto livre", async () => {
    // O campo "Rótulo do caso" grava em `categoria`, que a Retenção preserva de
    // propósito, e o caso carimbado já saiu da varredura dela: escrever ali
    // reintroduziria dado pessoal permanente pela tela que anuncia o
    // apagamento. Quem recusa de verdade é o servidor.
    montar(dossie({ anonimizada_em: APAGADO_EM }), {
      movimentos: [movimentoDoApagamento()],
      degradado: [],
    });
    await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });
    await assentar();

    expect(screen.queryByText("Classificação e sigilo")).toBeNull();
    expect(screen.queryByPlaceholderText(/Rótulo do caso/)).toBeNull();
  });

  it("o caso vivo continua oferecendo a classificação", async () => {
    montar(dossie());

    expect(await screen.findByText("Classificação e sigilo")).toBeTruthy();
    expect(screen.getByPlaceholderText(/Rótulo do caso/)).toBeTruthy();
  });

  it("trilha ilegível não apaga o aviso: só o crédito fica de fora", async () => {
    // A trilha é outra requisição, e ela pode não voltar. O aviso vive do
    // carimbo do próprio caso, então ele continua dito, com data e tudo.
    montar(dossie({ anonimizada_em: APAGADO_EM }), null);

    const aviso = await screen.findByRole("note", { name: TITULO_DO_CASO_APAGADO });

    await waitFor(() => expect(aviso.textContent).toMatch(/01\/09\/2031/));
    expect(aviso.textContent).not.toContain(AUTOR_DO_APAGAMENTO);
  });
});
