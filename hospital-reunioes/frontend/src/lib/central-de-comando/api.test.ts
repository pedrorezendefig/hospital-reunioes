/**
 * Como a recusa do backend da Central chega à tela (`lerRecusa`).
 *
 * O ramo novo da issue #846: só o 502 com a `CAUSA_TOKEN_VENCIDO` no corpo
 * chega com a `causa`. Causa desconhecida, ou a mesma causa noutro status,
 * segue a recusa de sempre, sem `causa`, e a tela mostra o erro honesto.
 */

import { describe, expect, it } from "vitest";

import { CAUSA_TOKEN_VENCIDO, lerRecusa } from "./api";

const FRASE = "O acesso ao Instagram expirou. Renove o token para voltar a atualizar os números.";

function resposta(status: number, corpo: unknown): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

describe("lerRecusa", () => {
  it("502 com a causa do token vencido chega com a causa e a frase do servidor", async () => {
    const recusa = await lerRecusa(resposta(502, { detail: FRASE, causa: CAUSA_TOKEN_VENCIDO }));

    expect(recusa).toEqual({ tipo: "falhou", mensagem: FRASE, causa: CAUSA_TOKEN_VENCIDO });
  });

  it("502 com uma causa que a tela não conhece segue sem causa", async () => {
    const recusa = await lerRecusa(resposta(502, { detail: "A fonte caiu.", causa: "outra-coisa" }));

    expect(recusa).toEqual({ tipo: "falhou", mensagem: "A fonte caiu." });
  });

  it.each([500, 503])("a causa do token vencido num status %i que não é 502 não vale", async (status) => {
    const recusa = await lerRecusa(resposta(status, { detail: FRASE, causa: CAUSA_TOKEN_VENCIDO }));

    expect(recusa.causa).toBeUndefined();
  });

  it("502 com a causa mas sem frase segue a recusa pelo status", async () => {
    const recusa = await lerRecusa(resposta(502, { causa: CAUSA_TOKEN_VENCIDO }));

    expect(recusa).toEqual({ tipo: "falhou", mensagem: "O servidor respondeu 502." });
  });
});
