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
 * O `fetch` entra dublado por URL: a página carrega anexos, notificações,
 * prorrogações, respostas e tentativas junto do Dossiê, e nenhum deles importa
 * para o que se quer provar.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SUGESTAO_NAO_E_CLASSIFICACAO } from "@/lib/ouvidoria/natureza-informada";
import { Dossie } from "./Dossie";

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
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
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
    // passaria só porque a tela ainda estava carregando. O marco é o relato, e
    // não o protocolo: o cabeçalho mostra o protocolo PEDIDO na URL enquanto o
    // caso não chega, então ele apareceria sem o caso ter chegado.
    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
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

/**
 * O Paciente do caso na tela do ouvidor (issue #666, PRD #659, ADR 0052).
 *
 * As duas linhas ficam ao lado de "Quem manifestou", "Contato" e "Vínculo": é
 * o bloco onde o ouvidor lê o caso inteiro antes de acionar. O teste asserta o
 * VALOR na linha certa, e não a presença do texto na página: "Maria Souza"
 * solto passaria com o nome caindo em qualquer outro lugar, e "Não informado"
 * solto casaria com a linha do contato.
 */
describe("o Dossiê e o Paciente do caso (issue #666)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function valorDaLinha(rotulo: string): string {
    return screen.getByText(rotulo).nextElementSibling?.textContent ?? "";
  }

  it("mostra o nome do paciente e a referência do atendimento", async () => {
    montarComDossie(
      dossie({
        manifestante_vinculo: "acompanhante",
        paciente_nome: "Maria Souza",
        paciente_referencia: "Leito 12, dia 9",
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Maria Souza");
    expect(valorDaLinha("Referência do atendimento")).toBe("Leito 12, dia 9");
  });

  it("caso sem paciente informado desenha as duas linhas com Não informado", async () => {
    // A linha existe sempre: o ouvidor precisa saber que o campo está vazio,
    // e não que ele não existe.
    montarComDossie(dossie({ paciente_nome: null, paciente_referencia: null }));

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Não informado");
    expect(valorDaLinha("Referência do atendimento")).toBe("Não informado");
  });

  it("o caso anônimo mostra o paciente e segue sem identificar quem manifestou", async () => {
    // A decisão 3 do ADR 0052 desenhada: são duas pessoas, e o anonimato é de
    // uma só.
    montarComDossie(
      dossie({
        anonimo: true,
        manifestante_nome: null,
        manifestante_vinculo: "acompanhante",
        paciente_nome: "Maria Souza",
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Maria Souza");
    expect(valorDaLinha("Quem manifestou")).toBe("Manifestação anônima");
  });
});
