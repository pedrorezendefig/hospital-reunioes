/**
 * @vitest-environment jsdom
 */

/**
 * O acuse de recebimento na página do caso (issue #493, RN-56, ADR 0042).
 *
 * A régua de o que dizer vem pronta do servidor (`acuse_do_caso`), com teste
 * próprio em `test_ouvidoria_acuse_recebimento.py`. O que só existe aqui é a
 * fiação: a linha aparecer com o que o servidor mandou, e as três situações
 * ficarem distintas na tela.
 *
 * A distinção importa mais do que parece. Juntar "não tinha para onde avisar"
 * com "ninguém avisou" faria a escolha de quem manifestou anônimo aparecer
 * como falha do hospital, e é justamente essa confusão que a marcação própria
 * da decisão 4 do ADR 0042 existe para desfazer.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dossie } from "./Dossie";

const ENTRADA = "2026-08-14T19:00:00+00:00";

function marcos() {
  return [
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
  ];
}

function dossie(acuse: Record<string, unknown> | undefined) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "em_classificacao",
    tipo_manifestacao: "reclamacao",
    categoria: "Reclamação",
    setor: "Recepção",
    resumo: "Paciente relata espera acima de duas horas.",
    relato_integral: "Cheguei as 8h e so fui atendido as 10h30.",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "joana@exemplo.com",
    manifestante_vinculo: "paciente",
    anonimo: false,
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
    canal: "site",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    marcos: marcos(),
    prazos: [],
    acuse,
    degradado: [],
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montar(caso: Record<string, unknown>) {
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

describe("o acuse de recebimento na página do caso (issue #493)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra quando o manifestante foi avisado", async () => {
    montar(
      dossie({
        rotulo: "Acuse de recebimento",
        em: "2026-08-14T19:01:00+00:00",
        situacao: "enviado",
        nota: null,
      })
    );

    expect(await screen.findByText("Acuse de recebimento")).toBeTruthy();
    // A situação e a data na mesma linha: a data sozinha aparece em outros
    // pontos da página, e casar com ela isolada provaria outra coisa.
    expect(screen.getByText(/Enviado ao manifestante, 14\/08\/2026/)).toBeTruthy();
  });

  it("não afirma envio quando o email falhou", async () => {
    // O carimbo do caso diz que o aviso foi GERADO, e ele é gravado antes de o
    // provedor responder. A situação vem do status da fila justamente para a
    // tela não garantir ao ouvidor um aviso que esgotou as tentativas.
    montar(
      dossie({
        rotulo: "Acuse de recebimento",
        em: "2026-08-14T19:01:00+00:00",
        situacao: "falha_no_envio",
        nota: "O provedor de email recusou a mensagem nas tentativas previstas. Reenvie pelo registro de notificações deste caso.",
      })
    );

    expect(await screen.findByText(/Não entregue/)).toBeTruthy();
    expect(screen.queryByText(/Enviado ao manifestante/)).toBeNull();
    expect(screen.getByText(/Reenvie pelo registro de notificações/)).toBeTruthy();
  });

  it("o que ainda está na fila não vira envio confirmado", async () => {
    montar(
      dossie({
        rotulo: "Acuse de recebimento",
        em: "2026-08-14T19:01:00+00:00",
        situacao: "em_envio",
        nota: null,
      })
    );

    expect(await screen.findByText(/Na fila de envio/)).toBeTruthy();
    expect(screen.queryByText(/Enviado ao manifestante/)).toBeNull();
  });

  it("diz por que ninguém foi avisado quando não havia canal", async () => {
    montar(
      dossie({
        rotulo: "Acuse de recebimento",
        em: "2026-08-14T19:01:00+00:00",
        situacao: "sem_contato",
        nota: "Sem canal para avisar: o caso é anônimo ou o contato informado não tem email.",
      })
    );

    expect(await screen.findByText(/Não enviado/)).toBeTruthy();
    expect(screen.getByText(/Sem canal para avisar/)).toBeTruthy();
  });

  it("caso de backend antigo não quebra a página do caso", async () => {
    // O frontend novo pode ser servido enquanto o backend ainda é o de antes:
    // ali o campo simplesmente não vem, e a linha some em vez de a página cair.
    montar(dossie(undefined));

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    expect(screen.queryByText("Acuse de recebimento")).toBeNull();
  });
});
