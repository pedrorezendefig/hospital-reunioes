/**
 * A cobrança da fila (issue #495, PRD #471): reenviar o acionamento do setor
 * sem entrar no Dossiê.
 *
 * Cobrar não inventa email novo: é a regra vigente de reenvio (ADR 0034,
 * decisão 7), que nasce como registro próprio e preserva a data do primeiro
 * envio. Quem escolhe QUAL registro reenviar é esta função.
 */

import { describe, expect, it } from "vitest";

import { GATILHO_DO_ACIONAMENTO, acionamentoParaCobrar } from "./cobranca";

function registro(id: string, gatilho: string, criada_em: string) {
  return { id, gatilho, criada_em };
}

describe("qual notificação a cobrança reenvia (issue #495)", () => {
  it("é o acionamento do setor, e não uma notificação qualquer do caso", () => {
    const escolhido = acionamentoParaCobrar([
      registro("n1", "prazo_rompido", "2026-08-20T10:00:00Z"),
      registro("n2", GATILHO_DO_ACIONAMENTO, "2026-08-19T10:00:00Z"),
    ]);

    expect(escolhido?.id).toBe("n2");
  });

  it("é o acionamento mais recente, quando o caso já foi acionado mais de uma vez", () => {
    // A reabertura por reincidência aciona de novo: cobrar tem que falar do
    // acionamento que está valendo, não do de um mês atrás.
    const escolhido = acionamentoParaCobrar([
      registro("antigo", GATILHO_DO_ACIONAMENTO, "2026-07-01T10:00:00Z"),
      registro("novo", GATILHO_DO_ACIONAMENTO, "2026-08-19T10:00:00Z"),
    ]);

    expect(escolhido?.id).toBe("novo");
  });

  it("a ordem em que a lista chega não decide nada", () => {
    const escolhido = acionamentoParaCobrar([
      registro("novo", GATILHO_DO_ACIONAMENTO, "2026-08-19T10:00:00Z"),
      registro("antigo", GATILHO_DO_ACIONAMENTO, "2026-07-01T10:00:00Z"),
    ]);

    expect(escolhido?.id).toBe("novo");
  });

  it("caso sem acionamento registrado não tem o que reenviar", () => {
    // Setor sem responsável cadastrado é acionado sem email nenhum: a tela
    // precisa dizer isso em vez de mandar um POST que termina em 404.
    expect(acionamentoParaCobrar([registro("n1", "prazo_rompido", "2026-08-20T10:00:00Z")])).toBeNull();
    expect(acionamentoParaCobrar([])).toBeNull();
  });
});
