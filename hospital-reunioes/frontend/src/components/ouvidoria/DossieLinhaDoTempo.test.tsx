/**
 * @vitest-environment jsdom
 */

/**
 * A linha do tempo do caso, na tela (issue #485, PRD #470, RN-63 a RN-65).
 *
 * A régua do que dizer tem teste próprio em `lib/ouvidoria/trilha.ts`, e a
 * tradução do movimento em evento tem o dela em `test_ouvidoria_linha_do_tempo.py`,
 * no servidor. O que só existe aqui dentro é a fiação: a seção aparecer com o
 * que o servidor mandou, o texto integral chegar inteiro à tela, e o caso que
 * a Retenção limpou continuar mostrando os fatos.
 *
 * O `fetch` entra dublado por URL: a página carrega anexos, notificações,
 * prorrogações, respostas e tentativas junto do Dossiê, e nenhum deles importa
 * para o que se quer provar.
 *
 * **Toda consulta passa por `linhaDoTempo()`, e não pelo `screen`.** O Dossiê
 * mostra a resposta corrente da área num bloco próprio, logo acima desta
 * seção, com exatamente o mesmo texto. Procurar a frase na página inteira
 * casaria com aquele bloco e o teste ficaria verde mesmo com a linha do tempo
 * apagada: verde pela porta errada é verde vazio. Perguntando DENTRO da lista,
 * o que passa é só o que esta seção renderizou.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SEM_CONFIRMACAO_DO_CALENDARIO, type EventoDaTrilha } from "@/lib/ouvidoria/trilha";
import { Dossie } from "./Dossie";

const ENTRADA_EM = "2026-08-24T13:00:00+00:00";
const ACIONAMENTO_EM = "2026-08-25T17:00:00+00:00";
const LEMBRETE_EM = "2026-08-26T12:00:00+00:00";
const RESPOSTA_EM = "2026-08-26T17:00:00+00:00";

const RESPOSTA_DA_AREA =
  "Revisamos a escala do plantao noturno e abrimos mais um guiche das 7h as 10h, com remanejamento de duas recepcionistas.";
const MOTIVO_DA_DEVOLUCAO =
  "A resposta nao diz o que foi apurado nem que providencia foi tomada no plantao noturno.";

function eventos(overrides: Record<string, unknown>[] = []) {
  const base = [
    {
      ocorrido_em: RESPOSTA_EM,
      autor: "Carlos Titular",
      sistema: false,
      marco: "T2",
      marco_rotulo: "Resposta da área",
      descricao: "Resposta da área recebida",
      texto: RESPOSTA_DA_AREA,
      desde_marco: "T1",
      desde_marco_rotulo: "Validação",
      minutos_uteis: 540,
    },
    {
      ocorrido_em: LEMBRETE_EM,
      autor: "Sistema (cobrança de prazos)",
      sistema: true,
      marco: null,
      marco_rotulo: null,
      descricao: "Lembrete de véspera enviado ao titular do setor",
      texto: null,
      desde_marco: null,
      desde_marco_rotulo: null,
      minutos_uteis: null,
    },
    {
      ocorrido_em: ACIONAMENTO_EM,
      autor: "Marta Ouvidora",
      sistema: false,
      marco: "T1",
      marco_rotulo: "Validação",
      descricao: "Caso validado e área acionada",
      texto: "Validada e acionada: setor Recepcao, gravidade medio",
      desde_marco: "T0",
      desde_marco_rotulo: "Entrada",
      minutos_uteis: 780,
    },
    {
      ocorrido_em: ENTRADA_EM,
      autor: "Canal aberto",
      sistema: true,
      marco: "T0",
      marco_rotulo: "Entrada",
      descricao: "Manifestação registrada",
      texto: "Registro pelo canal aberto (canal: qr)",
      desde_marco: null,
      desde_marco_rotulo: null,
      minutos_uteis: null,
    },
  ];
  return base.map((evento, i) => ({ ...evento, ...(overrides[i] ?? {}) }));
}

function dossie(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-24",
    prazo_resposta: "2026-08-31",
    status: "respondido",
    tipo_manifestacao: "reclamacao",
    categoria: "Demora no atendimento",
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
    prazo_area_em: "2026-08-31T20:00:00+00:00",
    validada_em: ACIONAMENTO_EM,
    respondida_em: RESPOSTA_EM,
    resposta_da_area: RESPOSTA_DA_AREA,
    respondida_por_nome: "Carlos Titular",
    encerrada_em: null,
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "qr",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    marcos: [],
    prazos: [],
    degradado: [],
    ...overrides,
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montar(trilha: unknown, caso: Record<string, unknown> = dossie()) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
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

/** A lista da linha do tempo, e só ela: a fronteira do que estes testes olham. */
async function linhaDoTempo() {
  return within(await screen.findByRole("list", { name: "Linha do tempo do caso" }));
}

describe("a linha do tempo do caso (issue #485)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra cada evento com data e hora, autor e descrição", async () => {
    montar({ movimentos: eventos(), degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.getByText("Manifestação registrada")).toBeTruthy();
    expect(trilha.getByText("Caso validado e área acionada")).toBeTruthy();
    expect(trilha.getByText("Lembrete de véspera enviado ao titular do setor")).toBeTruthy();
    expect(trilha.getByText(/26\/08\/2026.*Carlos Titular/)).toBeTruthy();
  });

  it("o evento automático se assina como Sistema", async () => {
    montar({ movimentos: eventos(), degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.getByText(/Sistema \(cobrança de prazos\)/)).toBeTruthy();
  });

  it("a resposta da área aparece inteira, sem cortar (RN-64)", async () => {
    // O caso está `respondido` e a coluna da resposta corrente está cheia, ou
    // seja: a frase TAMBÉM existe no bloco do Dossiê logo acima. É por isso
    // que a busca é dentro da lista, e o número exato de ocorrências ali é 1.
    montar({ movimentos: eventos(), degradado: [] });
    const trilha = await linhaDoTempo();

    // A frase inteira, e não um começo dela com reticências: o ponto da linha
    // do tempo é não obrigar o ouvidor a pular de tela para ler o que foi dito.
    expect(trilha.getAllByText(RESPOSTA_DA_AREA)).toHaveLength(1);
  });

  it("a devolução mostra o motivo inteiro, sem repetir o rótulo do ato", async () => {
    // A devolução é o segundo dos três textos da RN-64, e o único que não tem
    // bloco próprio no Dossiê: se ele não vier daqui, não vem de lugar nenhum.
    const devolucao: EventoDaTrilha = {
      ocorrido_em: "2026-08-27T13:00:00+00:00",
      autor: "Marta Ouvidora",
      sistema: false,
      marco: null,
      marco_rotulo: null,
      descricao: "Resposta devolvida à área por insuficiência",
      texto: MOTIVO_DA_DEVOLUCAO,
      desde_marco: null,
      desde_marco_rotulo: null,
      minutos_uteis: null,
    };
    const comDevolucao = [...eventos(), devolucao];
    montar({ movimentos: comDevolucao, degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.getByText(MOTIVO_DA_DEVOLUCAO)).toBeTruthy();
  });

  it("a transição de marco diz quanto tempo passou desde o marco anterior", async () => {
    montar({ movimentos: eventos(), degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.getByText("1 dia útil desde a etapa Validação")).toBeTruthy();
    // 780 minutos de expediente são 1 dia útil (9 horas) e 4 horas.
    expect(trilha.getByText("1 dia útil e 4 horas úteis desde a etapa Entrada")).toBeTruthy();
  });

  it("o evento que não fecha marco não ganha tempo decorrido", async () => {
    montar({ movimentos: eventos(), degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.queryByText(/desde a etapa Resposta da área/)).toBeNull();
  });

  it("sem calendário confirmado o número sai da tela em vez de sair errado", async () => {
    montar({ movimentos: eventos(), degradado: ["feriados"] });
    const trilha = await linhaDoTempo();

    expect(trilha.getAllByText(SEM_CONFIRMACAO_DO_CALENDARIO).length).toBeGreaterThan(0);
    expect(trilha.queryByText(/1 dia útil desde a etapa/)).toBeNull();
  });

  it("caso anonimizado pela Retenção mostra os fatos sem os textos", async () => {
    // A retenção zera a observação dos movimentos: o que aconteceu, quando e
    // por quem continua na trilha; o que foi dito, não.
    const semTextos = eventos([{ texto: null }, {}, { texto: null }, { texto: null }]);
    montar({ movimentos: semTextos, degradado: [] });
    const trilha = await linhaDoTempo();

    expect(trilha.getByText("Resposta da área recebida")).toBeTruthy();
    expect(trilha.queryByText(RESPOSTA_DA_AREA)).toBeNull();
  });

  it("trilha que não pôde ser lida não vira caso sem história na tela", async () => {
    // O servidor responde 503 quando a leitura falha. Mostrar a seção vazia
    // afirmaria que o caso não tem trilha, que é outra coisa.
    montar(null);

    expect(await screen.findByText("Paciente relata espera acima de duas horas.")).toBeTruthy();
    expect(screen.queryByText("Linha do tempo")).toBeNull();
  });
});
