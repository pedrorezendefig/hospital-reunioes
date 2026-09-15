/**
 * @vitest-environment jsdom
 */

/**
 * O Redirecionamento no Dossiê (issue #710, PRD #706, ADR 0055).
 *
 * A régua de quais estados aceitam o ato tem teste próprio em
 * `lib/ouvidoria/acoes.ts`, e a de como o movimento é lido da trilha, em
 * `lib/ouvidoria/redirecionamento.ts`. O que só existe aqui dentro é a fiação:
 * o botão aparecer onde o ato cabe, abrir a tela em modo redirecionamento, e a
 * linha do tempo mostrar o ato do ouvidor com nome próprio em vez da descrição
 * genérica da transição. Sem este arquivo, tirar o botão do JSX deixaria a
 * suíte inteira verde.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA } from "@/lib/ouvidoria/devolucao-a-ouvidoria";
import { PREFIXO_DO_REDIRECIONAMENTO } from "@/lib/ouvidoria/redirecionamento";
import { Dossie } from "./Dossie";

const MOTIVO = "O caso é de conduta médica: a Recepção não tem como apurar.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "aguardando_area",
    tipo_manifestacao: "reclamacao",
    categoria: "Demora no atendimento",
    setor: "Recepcao",
    resumo: "Paciente relata espera acima de duas horas.",
    relato_integral: "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: null,
    manifestante_vinculo: null,
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: null,
    desfecho_descricao: null,
    gravidade: "medio",
    prazo_area_em: "2026-08-20T18:00:00+00:00",
    validada_em: "2026-08-18T13:00:00+00:00",
    respondida_em: null,
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: null,
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "ana",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    extrato_para_o_setor: "Apurar a espera do plantao e responder a Ouvidoria.",
    ...overrides,
  };
}

/** O movimento de saída que o servidor grava no redirecionamento. */
function movimentoDeRedirecionamento(setor = "Recepcao", motivo = MOTIVO) {
  return {
    ocorrido_em: "2026-09-15T13:00:00+00:00",
    autor: "Ana Ouvidora",
    // O ouvidor está logado: `autor_id` não nulo.
    sistema: false,
    apagamento: false,
    marco: null,
    marco_rotulo: null,
    descricao: "Caso em classificação",
    texto: `${PREFIXO_DO_REDIRECIONAMENTO} (de ${setor}): ${motivo}`,
    desde_marco: null,
    desde_marco_rotulo: null,
    minutos_uteis: null,
  };
}

/** O movimento da Devolução à Ouvidoria, que chega ao MESMO estado. */
function movimentoDeDevolucao(setor = "Recepcao") {
  return {
    ...movimentoDeRedirecionamento(),
    autor: "Carlos Titular",
    sistema: true,
    texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} ${setor}: Este caso é do Centro Médico.`,
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montar(dossie: Record<string, unknown>, movimentos: unknown[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      if (url.endsWith("/movimentos")) return respostaJson({ movimentos });
      if (url.includes("/setores")) return respostaJson(["Recepcao", "Centro Medico"]);
      if (url.includes("/responsaveis")) return respostaJson({ responsaveis: [] });
      return respostaJson(dossie);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

function botaoDeRedirecionar() {
  return screen.queryByRole("button", { name: /^Redirecionar$/ });
}

describe("o botão Redirecionar no Dossiê (issue #710)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("aparece no caso que está com a área", async () => {
    montar(caso());

    await waitFor(() => expect(botaoDeRedirecionar()).toBeTruthy());
  });

  it("aparece no caso que a área já respondeu", async () => {
    // A área errada que responde "isso é do Centro Médico" em vez de devolver.
    montar(
      caso({
        status: "respondido",
        respondida_em: "2026-08-19T15:00:00+00:00",
        respondida_por_nome: "Carlos Titular",
        resposta_da_area: "Esse caso é do Centro Médico.",
      })
    );

    await waitFor(() => expect(botaoDeRedirecionar()).toBeTruthy());
  });

  it("não aparece nos estados em que o servidor recusaria", async () => {
    // Um por vez, porque o Dossiê é uma tela só: o caso em classificação já
    // oferece Validar e acionar, e é ele quem escolhe a área ali.
    for (const status of ["em_classificacao", "aguardando_manifestante", "encerrado"]) {
      montar(caso({ status }));
      await waitFor(() => expect(screen.getByText(/Manifestação 2026-0012/)).toBeTruthy());
      expect(botaoDeRedirecionar()).toBeNull();
      cleanup();
      vi.unstubAllGlobals();
    }
  });

  it("CONTRAPROVA: o clique abre a tela em modo redirecionamento, pronta para enviar", async () => {
    // Sem esta, o mutante que nunca abre a modal passaria: o botão existiria na
    // tela e o ato inteiro estaria indisponível.
    montar(caso());
    await waitFor(() => expect(botaoDeRedirecionar()).toBeTruthy());

    fireEvent.click(botaoDeRedirecionar()!);

    await waitFor(() =>
      expect(screen.getByText(/Redirecionar 2026-0012 para outra área/)).toBeTruthy()
    );
    // A área em branco e o motivo obrigatório são o que distingue este ato da
    // validação (ADR 0055, decisão 1).
    expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("");
    expect(screen.getByLabelText(/Motivo do redirecionamento/)).toBeTruthy();
    // E a tela continua trazendo o que já foi decidido, para o ouvidor só
    // trocar a área e explicar.
    expect((screen.getByLabelText(/Extrato para o setor/) as HTMLTextAreaElement).value).toBe(
      "Apurar a espera do plantao e responder a Ouvidoria."
    );
  });
});

describe("o que o Dossiê diz depois de redirecionar (issue #710)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra a frase de confirmação com a área nova e o aviso à anterior", async () => {
    // Carimbo do servidor sem par na tela some em silêncio: sem esta frase, o
    // Dossiê recarregaria com a área nova no lugar da antiga e nada diria que
    // o caso mudou de mãos nem que a área anterior foi avisada.
    montar(caso());
    await waitFor(() => expect(botaoDeRedirecionar()).toBeTruthy());
    fireEvent.click(botaoDeRedirecionar()!);

    await screen.findByRole("option", { name: "Centro Medico" });
    fireEvent.change(screen.getByLabelText(/Área responsável/), {
      target: { value: "Centro Medico" },
    });
    fireEvent.change(screen.getByLabelText(/Motivo do redirecionamento/), {
      target: { value: MOTIVO },
    });
    fireEvent.click(screen.getByRole("button", { name: /Redirecionar para a área nova/ }));

    await waitFor(() =>
      expect(
        screen.getByText("Caso redirecionado para Centro Medico. A área anterior foi avisada.")
      ).toBeTruthy()
    );
  });
});

describe("a linha do tempo distingue o redirecionamento da devolução (ADR 0055)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra o ato do ouvidor com rótulo próprio e o motivo ao lado", async () => {
    montar(caso(), [movimentoDeRedirecionamento()]);

    const trilha = await screen.findByRole("list", { name: "Linha do tempo do caso" });
    // O marcador positivo, e não a ausência da descrição genérica: procurar o
    // que NÃO está na tela é cego a maiúscula, corte e aspas.
    expect(within(trilha).getByText("Redirecionado pelo ouvidor (de Recepcao)")).toBeTruthy();
    expect(within(trilha).getByText(MOTIVO)).toBeTruthy();
    // O rótulo SUBSTITUI a descrição da transição: com as duas, a linha diria
    // "Caso em classificação" sobre um caso que já está com a área nova.
    expect(within(trilha).queryByText("Caso em classificação")).toBeNull();
  });

  it("não vira bloco de devolução no caso que ficou em classificação", async () => {
    // O cenário da falha DEPOIS da saída: o caso saiu da área e o acionamento
    // da nova não terminou. É exatamente o estado em que o bloco da devolução
    // aparece, e contar este ato ali inflaria a contagem de devoluções com os
    // redirecionamentos da própria Ouvidoria.
    montar(caso({ status: "em_classificacao", prazo_area_em: null }), [
      movimentoDeRedirecionamento(),
    ]);

    await screen.findByRole("list", { name: "Linha do tempo do caso" });
    expect(screen.queryByText(/Devolvido pela área/)).toBeNull();
  });

  it("CONTRAPROVA: a devolução da área continua aparecendo e contando", async () => {
    // A régua nova não pode ter cegado a antiga.
    montar(caso({ status: "em_classificacao", prazo_area_em: null }), [
      movimentoDeDevolucao(),
      movimentoDeRedirecionamento(),
    ]);

    await waitFor(() => expect(screen.getByText("Devolvido pela área Recepcao")).toBeTruthy());
    const trilha = await screen.findByRole("list", { name: "Linha do tempo do caso" });
    expect(within(trilha).getByText("Redirecionado pelo ouvidor (de Recepcao)")).toBeTruthy();
  });
});
