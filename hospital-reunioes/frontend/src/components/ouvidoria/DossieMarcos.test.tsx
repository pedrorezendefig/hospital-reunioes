/**
 * @vitest-environment jsdom
 */

/**
 * Os quatro marcos com tempo decorrido, na tela do caso (issue #480).
 *
 * A régua de o que dizer já tem teste próprio em `lib/ouvidoria/marcos.ts`, e
 * a conta do tempo em `test_ouvidoria_marcos.py`, no servidor. O que só existe
 * aqui dentro é a fiação: o bloco aparecer com o que o servidor mandou, o
 * marco pendente não virar data e o prazo que a gravidade não tem não ganhar
 * linha na tela.
 *
 * O `fetch` entra dublado por URL: a página carrega anexos, notificações,
 * prorrogações, respostas e tentativas junto do Dossiê, e nenhum deles importa
 * para o que se quer provar.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MARCO_PENDENTE, SEM_CONFIRMACAO_DO_CALENDARIO } from "@/lib/ouvidoria/marcos";
import { Dossie } from "./Dossie";

const ENTRADA = "2026-08-14T19:00:00+00:00";
const VALIDACAO = "2026-08-17T12:00:00+00:00";

function marcos(overrides: Record<string, unknown>[] = []) {
  const base = [
    {
      chave: "T0",
      rotulo: "Entrada",
      em: ENTRADA,
      pendente: false,
      trecho: null,
      minutos_uteis: null,
      em_curso: false,
      tramitacao_anterior_em: null,
    },
    {
      chave: "T1",
      rotulo: "Validação",
      em: VALIDACAO,
      pendente: false,
      trecho: "Triagem da Ouvidoria",
      minutos_uteis: 120,
      em_curso: false,
      tramitacao_anterior_em: null,
    },
    {
      chave: "T2",
      rotulo: "Resposta da área",
      em: null,
      pendente: true,
      trecho: "Resposta da área",
      minutos_uteis: 540,
      em_curso: true,
      tramitacao_anterior_em: null,
    },
    {
      chave: "T3",
      rotulo: "Conclusão",
      em: null,
      pendente: true,
      trecho: "Desfecho pela Ouvidoria",
      minutos_uteis: null,
      em_curso: false,
      tramitacao_anterior_em: null,
    },
  ];
  return base.map((marco, i) => ({ ...marco, ...(overrides[i] ?? {}) }));
}

function prazos(overrides: Record<string, unknown> = {}) {
  return [
    {
      chave: "area",
      rotulo: "Prazo da área",
      em: "2026-08-19T20:00:00+00:00",
      situacao: "definido",
      rotulo_prazo: "vence em 2 dias úteis",
      estourado: false,
      nota: null,
    },
    {
      chave: "conclusivo",
      rotulo: "Prazo conclusivo",
      em: "2026-08-25T20:00:00+00:00",
      situacao: "definido",
      rotulo_prazo: "vence em 6 dias úteis",
      estourado: false,
      nota: null,
      ...overrides,
    },
  ];
}

function dossie(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "aguardando_area",
    tipo_manifestacao: "reclamacao",
    categoria: "Reclamação",
    setor: "Recepção",
    resumo: "Paciente relata espera acima de duas horas.",
    relato_integral: "Cheguei as 8h e so fui atendido as 10h30.",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "(31) 99999-0000",
    manifestante_vinculo: "paciente",
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: null,
    desfecho_descricao: null,
    gravidade: "medio",
    prazo_area_em: "2026-08-19T20:00:00+00:00",
    validada_em: VALIDACAO,
    respondida_em: null,
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: null,
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "telefone",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    marcos: marcos(),
    prazos: prazos(),
    degradado: [],
    ...overrides,
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montarComDossie(caso: Record<string, unknown>, depoisDaAcao?: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      // As ações do ouvidor devolvem o Dossiê, e a tela adota o corpo inteiro.
      if (url.endsWith("/classificacao")) return respostaJson(depoisDaAcao ?? caso);
      return respostaJson(caso);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

describe("os quatro marcos na página do caso (issue #480)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra os quatro marcos e o tempo decorrido de cada trecho", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    expect(screen.getByText("Entrada")).toBeTruthy();
    expect(screen.getByText("Validação")).toBeTruthy();
    expect(screen.getByText("Resposta da área")).toBeTruthy();
    expect(screen.getByText("Conclusão")).toBeTruthy();
    // A data de entrada é o T0, o que a tela nunca mostrou (D-05).
    expect(screen.getByText(/14\/08\/2026/)).toBeTruthy();
    expect(screen.getByText("Triagem da Ouvidoria: 2 horas úteis")).toBeTruthy();
  });

  it("marco que não aconteceu aparece pendente, sem data inventada", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    // A resposta da área e a conclusão ainda não aconteceram neste caso.
    expect(screen.getAllByText(MARCO_PENDENTE)).toHaveLength(2);
  });

  it("o trecho ainda aberto diz que o número é o de agora", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Resposta da área: 1 dia útil até agora")).toBeTruthy();
  });

  it("o trecho que nem começou não mostra tempo nenhum", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    expect(screen.queryByText(/Desfecho pela Ouvidoria/)).toBeNull();
  });

  it("caso reaberto diz quando a tramitação anterior foi concluída", async () => {
    // A reabertura por reincidência preserva `encerrada_em`, que é o marco da
    // tramitação anterior. Ele não passa por conclusão do ciclo aberto (vem
    // pendente), e também não some da tela: fica dito pelo que é.
    montarComDossie(
      dossie({
        reincidencia: true,
        marcos: marcos([{}, {}, {}, { tramitacao_anterior_em: "2026-08-20T14:00:00+00:00" }]),
      })
    );

    expect(await screen.findByText(/A tramitação anterior foi concluída em/)).toBeTruthy();
  });

  it("caso que não foi reaberto não fala de tramitação anterior", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    expect(screen.queryByText(/tramitação anterior/)).toBeNull();
  });

  it("mostra os dois prazos junto dos marcos", async () => {
    montarComDossie(dossie());

    expect(await screen.findByText("Prazo da área")).toBeTruthy();
    expect(screen.getByText("Prazo conclusivo")).toBeTruthy();
    expect(screen.getByText(/vence em 6 dias úteis/)).toBeTruthy();
  });

  it("gravidade sem prazo conclusivo não mostra esse prazo", async () => {
    // O crítico não tem célula conclusiva na tabela (PRD #468, história 12): a
    // tela não inventa a data nem deixa a linha vazia.
    montarComDossie(
      dossie({
        gravidade: "critico",
        prazos: prazos({ em: null, situacao: "sem_prazo", rotulo_prazo: null }),
      })
    );

    expect(await screen.findByText("Prazo da área")).toBeTruthy();
    expect(screen.queryByText("Prazo conclusivo")).toBeNull();
  });

  it("a nota do prazo conclusivo explica por que ele não andou", async () => {
    const nota = "A prorrogação e a espera pelo manifestante movem o prazo da área, nunca o conclusivo.";
    montarComDossie(dossie({ prazos: prazos({ nota }) }));

    expect(await screen.findByText(nota)).toBeTruthy();
  });

  it("o calendário que não pôde ser lido tira os números da tela, não só avisa", async () => {
    // Fail-open com a marca junto (issue #449): a página abre, mas não pode
    // afirmar dias úteis que saíram de uma leitura que falhou. Avisar e
    // afirmar o número logo abaixo seria avisar por educação, e é o contrário
    // do que a superfície irmã (o painel) faz.
    montarComDossie(dossie({ degradado: ["feriados"] }));

    expect(await screen.findByText(/calendário de feriados não pôde ser lido/)).toBeTruthy();
    expect(screen.queryByText(/2 horas úteis/)).toBeNull();
    expect(screen.queryByText(/vence em 6 dias úteis/)).toBeNull();
    // A data do vencimento é dado persistido, e continua na tela.
    expect(screen.getAllByText(new RegExp(SEM_CONFIRMACAO_DO_CALENDARIO)).length).toBeGreaterThan(0);
  });

  it("o bloco continua na tela depois de uma ação do ouvidor, com o número novo", async () => {
    // As ações do caso (pausar, retomar, devolver, reabrir, classificar)
    // devolvem o Dossiê e a tela ADOTA o corpo inteiro. Resposta sem os marcos
    // faz o bloco sumir na hora, sem erro nenhum, e leva junto o prazo da área
    // e a data de validação, que só vivem aqui desde a issue #480.
    const depois = dossie({
      marcos: marcos([{}, { minutos_uteis: 180 }]),
    });
    montarComDossie(dossie(), depois);

    expect(await screen.findByText("Triagem da Ouvidoria: 2 horas úteis")).toBeTruthy();
    // O botão nasce desabilitado e só libera quando o tipo do caso chega ao
    // formulário. Clicar antes disso é clicar em nada, e o teste passaria a
    // depender de quem ganha a corrida.
    const salvar = screen.getByText("Salvar classificação") as HTMLButtonElement;
    await waitFor(() => expect(salvar.disabled).toBe(false));
    fireEvent.click(salvar);

    expect(await screen.findByText("Triagem da Ouvidoria: 3 horas úteis")).toBeTruthy();
    expect(screen.getByText("Marcos do caso")).toBeTruthy();
  });

  it("caso vindo de um backend sem os marcos não quebra a página", async () => {
    montarComDossie(dossie({ marcos: undefined, prazos: undefined, degradado: undefined }));

    expect(await screen.findByText(/Cheguei as 8h/)).toBeTruthy();
    expect(screen.queryByText("Marcos do caso")).toBeNull();
  });
});
