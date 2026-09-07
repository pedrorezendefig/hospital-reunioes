/**
 * @vitest-environment jsdom
 */

/**
 * O Dossiê do caso devolvido à Ouvidoria (issue #601, PRD #598, ADR 0048).
 *
 * A régua de o que é uma devolução tem teste próprio em
 * `lib/ouvidoria/devolucao-a-ouvidoria.ts`. O que só existe aqui dentro é a
 * fiação: o bloco aparecer com o que a área escreveu, o caso comum não mostrar
 * nada, e o botão do despacho mudar de nome quando o que o ouvidor tem a fazer
 * é encaminhar de novo. Sem este arquivo, tirar o bloco do JSX deixaria a suíte
 * inteira verde.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA } from "@/lib/ouvidoria/devolucao-a-ouvidoria";
import { Dossie } from "./Dossie";

const MOTIVO = "Este caso é do Centro Médico: quem atendeu foi o plantonista.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "em_classificacao",
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
    prazo_area_em: null,
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

function movimentoDeDevolucao(setor: string, motivo: string, ocorrido_em: string, autor: string) {
  return {
    ocorrido_em,
    autor,
    sistema: true,
    marco: null,
    marco_rotulo: null,
    descricao: "Caso em classificação",
    texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} ${setor}: ${motivo}`,
    desde_marco: null,
    desde_marco_rotulo: null,
    minutos_uteis: null,
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montar(
  dossie: Record<string, unknown>,
  movimentos: unknown[] = [],
  { trilhaForaDoAr = false }: { trilhaForaDoAr?: boolean } = {}
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      if (url.endsWith("/movimentos")) {
        return trilhaForaDoAr
          ? ({ ok: false, status: 503, json: async () => ({}) } as Response)
          : respostaJson({ movimentos });
      }
      if (url.includes("/setores")) return respostaJson(["Recepcao", "Centro Medico"]);
      return respostaJson(dossie);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

describe("o Dossiê do caso devolvido à Ouvidoria (issue #601)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra a área que devolveu, o motivo, quem devolveu e quando", async () => {
    montar(caso(), [
      movimentoDeDevolucao("Recepcao", MOTIVO, "2026-08-26T17:00:00+00:00", "Carlos Titular"),
    ]);

    // Pelo cabeçalho do bloco, e tudo o mais DENTRO dele: a linha do tempo
    // mostra a mesma frase, o mesmo motivo, o mesmo nome e a mesma data,
    // porque é o mesmo movimento da trilha. Procurar solto pela página deixaria
    // este teste verde com o bloco arrancado do JSX.
    const titulo = await screen.findByRole("heading", { name: /Devolvido pela área Recepcao/ });
    const bloco = titulo.parentElement as HTMLElement;

    expect(bloco.textContent).toContain(MOTIVO);
    expect(bloco.textContent).toContain("Carlos Titular");
    expect(bloco.textContent).toContain("26/08/2026");
  });

  it("caso devolvido duas vezes diz quantas", async () => {
    montar(caso(), [
      movimentoDeDevolucao("Centro Medico", "Não é nosso.", "2026-09-02T14:00:00+00:00", "Dra. Bianca"),
      movimentoDeDevolucao("Recepcao", MOTIVO, "2026-08-26T17:00:00+00:00", "Carlos Titular"),
    ]);

    // A área do cabeçalho é a da devolução MAIS RECENTE: é dela que o caso
    // acabou de voltar, e é ela que o ouvidor não deve escolher de novo.
    const titulo = await screen.findByRole("heading", { name: /Devolvido pela área Centro Medico/ });

    expect(titulo.textContent).toContain("devolvido 2 vezes");
  });

  it("caso que nunca foi devolvido não mostra o bloco", async () => {
    montar(caso());

    // Espera o caso chegar antes de afirmar a ausência, senão o teste passaria
    // só porque a tela ainda estava carregando.
    expect(await screen.findByText(/Cheguei as 8h com minha mae/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Devolvido pela área/ })).toBeNull();
  });

  it("o botão do despacho vira Encaminhar para outra área no caso devolvido", async () => {
    montar(caso(), [
      movimentoDeDevolucao("Recepcao", MOTIVO, "2026-08-26T17:00:00+00:00", "Carlos Titular"),
    ]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Encaminhar para outra área/ })).toBeTruthy();
    });
    expect(screen.queryByRole("button", { name: /^Validar e acionar$/ })).toBeNull();
  });

  it("o caso em classificação que nunca foi despachado continua dizendo Validar e acionar", async () => {
    montar(caso());

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Validar e acionar/ })).toBeTruthy();
    });
    expect(screen.queryByRole("button", { name: /Encaminhar para outra área/ })).toBeNull();
  });

  it("motivo enorme fica dentro de uma área rolável, sem empurrar o resto do Dossiê", async () => {
    // O motivo é texto livre de quem tem o link do setor, com teto de 10.000
    // caracteres e quebras de linha à vontade. Sem limite de altura, o bloco
    // que abre o Dossiê empurra tudo o mais para muito abaixo da dobra.
    // A asserção é na classe porque o jsdom não calcula layout, mesmo molde do
    // teste do semáforo da fila.
    const enorme = Array.from({ length: 400 }, (_, i) => `linha ${i} do motivo`).join("\n");
    montar(caso(), [
      movimentoDeDevolucao("Recepcao", enorme, "2026-08-26T17:00:00+00:00", "Carlos Titular"),
    ]);

    const area = await screen.findByRole("region", { name: /Motivo da devolução/ });

    expect(area.textContent).toContain("linha 399 do motivo");
    expect(area.className).toContain("max-h-");
    expect(area.className).toContain("overflow-y-auto");
    // Área rolável tem que ser alcançável por teclado, senão quem não usa mouse
    // não chega ao resto do texto.
    expect(area.getAttribute("tabindex")).toBe("0");
  });

  it("motivo de uma palavra só e enorme não alarga o Dossiê na horizontal", async () => {
    // O irmão do teto vertical. `whitespace-pre-wrap` quebra em espaço, e a
    // peneira `sem_invisiveis` do servidor não insere nenhum: 10.000 caracteres
    // colados alargam o cartão e põem barra horizontal na página inteira. A
    // casa já usa `min-w-0` no filho do flex pelo mesmo motivo.
    const semEspaco = "a".repeat(4000);
    montar(caso(), [
      movimentoDeDevolucao("Recepcao", semEspaco, "2026-08-26T17:00:00+00:00", "Carlos Titular"),
    ]);

    const area = await screen.findByRole("region", { name: /Motivo da devolução/ });

    expect(area.className).toContain("break-words");
    // O `min-w-0` vai no filho do flex, que é quem se recusa a encolher abaixo
    // do conteúdo: sem ele, a quebra dentro do bloco não adianta.
    const colunaDoFlex = area.parentElement as HTMLElement;
    expect(colunaDoFlex.className).toContain("min-w-0");
  });

  it("trilha fora do ar avisa, em vez de fazer o caso devolvido parecer um caso comum", async () => {
    // Com o 503, a lista de movimentos volta vazia e o bloco some. O Dossiê do
    // caso devolvido fica IDÊNTICO ao de um caso nunca despachado, e o ouvidor
    // despacha às cegas, podendo reenviar para a mesma área que devolveu.
    montar(caso(), [], { trilhaForaDoAr: true });

    expect(await screen.findByText(/não foi possível ler a trilha deste caso/i)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Devolvido pela área/ })).toBeNull();
  });

  it("trilha lida sem devolução nenhuma não inventa aviso de falha", async () => {
    montar(caso());

    expect(await screen.findByText(/Cheguei as 8h com minha mae/)).toBeTruthy();
    expect(screen.queryByText(/não foi possível ler a trilha deste caso/i)).toBeNull();
  });
});
