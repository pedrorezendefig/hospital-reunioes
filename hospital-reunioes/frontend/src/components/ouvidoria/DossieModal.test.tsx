/**
 * @vitest-environment jsdom
 */

/**
 * A natureza informada pelo manifestante, na tela do Dossiê (issue #474).
 *
 * A régua de o que dizer já tem teste próprio em `lib/ouvidoria/
 * natureza-informada.ts`. O que só existe aqui dentro é a fiação: o bloco
 * aparecer quando o caso trouxe a sugestão, e não aparecer quando não trouxe.
 * Sem este arquivo, remover o bloco do JSX deixaria a suíte inteira verde.
 *
 * O `fetch` entra dublado por URL: o modal carrega anexos, notificações,
 * prorrogações, respostas e tentativas junto do Dossiê, e nenhum deles importa
 * para o que se quer provar.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SUGESTAO_NAO_E_CLASSIFICACAO } from "@/lib/ouvidoria/natureza-informada";
import { DossieModal } from "./DossieModal";

function dossie(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "em_classificacao",
    tipo_manifestacao: null,
    categoria: "A classificar",
    setor: "A definir",
    resumo: "Paciente elogia a equipe da recepção.",
    relato_integral: "A moça da recepção foi muito atenciosa comigo.",
    manifestante_nome: null,
    manifestante_contato: null,
    manifestante_vinculo: null,
    anonimo: true,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: null,
    desfecho_descricao: null,
    gravidade: null,
    prazo_area_em: null,
    validada_em: null,
    respondida_em: null,
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: null,
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "qr",
    canal_setor: "Recepção",
    canal_ponto: null,
    natureza_informada: null,
    ...overrides,
  };
}

function montarComDossie(caso: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      return respostaJson(caso);
    })
  );
  render(<DossieModal manifestacaoId="uuid-12" token="token-de-teste" onClose={() => {}} />);
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

describe("o Dossiê e a natureza informada pelo manifestante (issue #474)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra a sugestão do manifestante, com a origem escrita na linha", async () => {
    montarComDossie(dossie({ natureza_informada: "elogio" }));

    expect(await screen.findByText(/O manifestante informou: Elogio/)).toBeTruthy();
    expect(screen.getByText(SUGESTAO_NAO_E_CLASSIFICACAO)).toBeTruthy();
  });

  it("caso sem natureza informada não mostra o bloco", async () => {
    montarComDossie(dossie({ natureza_informada: null }));

    // Espera o Dossiê chegar antes de afirmar a ausência: sem isto o teste
    // passaria só porque a tela ainda estava carregando.
    expect(await screen.findByText("2026-0012", { exact: false })).toBeTruthy();
    expect(screen.queryByText(/O manifestante informou/)).toBeNull();
    expect(screen.queryByText(SUGESTAO_NAO_E_CLASSIFICACAO)).toBeNull();
  });

  it("a sugestão não vira a classificação do caso na tela", async () => {
    // O caso do canal aberto nasce sem tipo (ADR 0037): mesmo dizendo "elogio",
    // ele continua se apresentando como não classificado, e quem classifica é
    // o ouvidor no bloco de classificação (ADR 0040, decisão 3).
    montarComDossie(dossie({ natureza_informada: "elogio", tipo_manifestacao: null }));

    await screen.findByText(/O manifestante informou: Elogio/);
    await waitFor(() => {
      expect(screen.getByText("Não classificada")).toBeTruthy();
    });
  });
});
