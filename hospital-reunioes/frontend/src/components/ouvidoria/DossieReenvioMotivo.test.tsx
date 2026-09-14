/**
 * @vitest-environment jsdom
 */

/**
 * O que o ouvidor lê quando clica em Reenviar e o email não sai (issue #707).
 *
 * A tela dizia sempre a mesma coisa: "o provedor de email recusou agora e o
 * sistema tenta de novo". Desde a revogação dos links da área antiga existe uma
 * recusa que nada tem a ver com o provedor (o destinatário já não responde pelo
 * setor do caso) e que NÃO será tentada de novo, porque a linha vira falha, que
 * é terminal. Com a frase velha, o ouvidor reclicava o botão achando que
 * insistia com um provedor que nunca foi chamado, e cada clique criava mais uma
 * linha em falha sem email nenhum.
 *
 * O servidor passou a devolver o `motivo` junto do `entregue`, e é ele que a
 * tela mostra. A frase do provedor continua existindo para quando não há motivo.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dossie } from "./Dossie";

const MOTIVO_DA_GUARDA = "O destinatário não responde mais pelo setor do caso; link não enviado";
const FRASE_DO_PROVEDOR = /o provedor de email recusou agora/;

const NOTIFICACAO = {
  id: "n-1",
  gatilho: "nova_demanda",
  destinatario_nome: "Carlos Titular",
  destinatario_email: "carlos@hsm.br",
  status: "falha",
  enviada_em: null,
  tentativas: 1,
  criada_em: "2026-08-25T17:00:00+00:00",
};

function caso() {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "aguardando_area",
    tipo_manifestacao: "reclamacao",
    categoria: "Demora no atendimento",
    setor: "Centro Medico",
    resumo: "Paciente relata espera acima de duas horas.",
    relato_integral: "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "(31) 99999-0000",
    manifestante_vinculo: "acompanhante",
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: null,
    desfecho_descricao: null,
    gravidade: "medio",
    prazo_area_em: "2026-08-31T20:00:00+00:00",
    validada_em: "2026-08-25T17:00:00+00:00",
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
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

/** Monta o Dossiê com uma notificação na lista e a resposta dada ao reenvio. */
function montarComReenvio(reenvio: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/reenviar")) return respostaJson(reenvio);
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [NOTIFICACAO] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      return respostaJson(caso());
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

async function clicarEmReenviar() {
  const botao = await screen.findByRole("button", { name: /Reenviar/ });
  fireEvent.click(botao);
}

describe("o motivo da recusa do reenvio na tela (issue #707)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra o motivo que o servidor devolveu, e não a frase do provedor", async () => {
    montarComReenvio({ id: "n-2", gatilho: "nova_demanda", entregue: false, motivo: MOTIVO_DA_GUARDA });

    await clicarEmReenviar();

    expect(await screen.findByText(MOTIVO_DA_GUARDA)).toBeTruthy();
    expect(screen.queryByText(FRASE_DO_PROVEDOR)).toBeNull();
  });

  it("sem motivo, a frase do provedor continua valendo", async () => {
    // É a recusa que a frase sempre descreveu: o provedor negou e a linha volta
    // para a fila. Sem esta contraprova, apagar a frase passaria despercebido.
    montarComReenvio({ id: "n-2", gatilho: "nova_demanda", entregue: false, motivo: null });

    await clicarEmReenviar();

    expect(await screen.findByText(FRASE_DO_PROVEDOR)).toBeTruthy();
  });

  it("reenvio que saiu diz para quem foi", async () => {
    montarComReenvio({ id: "n-2", gatilho: "nova_demanda", entregue: true, motivo: null });

    await clicarEmReenviar();

    await waitFor(() => {
      expect(screen.getByText("Reenviado para carlos@hsm.br.")).toBeTruthy();
    });
  });
});
