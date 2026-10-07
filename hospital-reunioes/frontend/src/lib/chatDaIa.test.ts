// O par na tela dos tetos dos três chats de IA (issue #893): correção da Ata,
// Ata Guiada e elaboração de POP. O backend recusa mais de 40 mensagens, e
// vinte idas e voltas de conversa normal chegam lá; sem a janela, a conversa
// travaria para sempre (todo turno reenvia o histórico inteiro).
import { describe, expect, it } from "vitest";

import { ERRO_DO_TURNO, falaDaFalha, historicoParaEnvio } from "./chatDaIa";

function conversa(quantas: number) {
  return Array.from({ length: quantas }, (_, i) => ({
    role: (i % 2 === 0 ? "assistant" : "user") as "assistant" | "user",
    content: `fala ${i}`,
    timestamp: "2026-10-07T10:00:00Z",
  }));
}

describe("historicoParaEnvio", () => {
  it("uma conversa longa vai ao backend só com as últimas 40 falas", () => {
    const enviado = historicoParaEnvio(conversa(45));
    expect(enviado).toHaveLength(40);
    expect(enviado[0]).toEqual({ role: "user", content: "fala 5" });
    expect(enviado[39]).toEqual({ role: "assistant", content: "fala 44" });
  });

  it("uma conversa curta vai inteira, sem o timestamp", () => {
    expect(historicoParaEnvio(conversa(2))).toEqual([
      { role: "assistant", content: "fala 0" },
      { role: "user", content: "fala 1" },
    ]);
  });
});

describe("falaDaFalha", () => {
  it("a recusa do teto chega à conversa com a frase do backend", async () => {
    const frase = "A mensagem passou de 8.000 caracteres, o tamanho que o chat aceita. Encurte o texto e mande de novo.";
    const res = new Response(JSON.stringify({ detail: frase }), { status: 422 });
    expect(await falaDaFalha(res)).toBe(frase);
  });

  it("o 422 do pydantic, com detail em lista, não vira JSON cru na conversa", async () => {
    const res = new Response(JSON.stringify({ detail: [{ type: "missing" }] }), { status: 422 });
    expect(await falaDaFalha(res)).toBe(ERRO_DO_TURNO);
  });

  it("qualquer outra falha fica com a frase genérica de sempre", async () => {
    const res = new Response(JSON.stringify({ detail: "Internal" }), { status: 500 });
    expect(await falaDaFalha(res)).toBe("Desculpe, houve um erro. Tente novamente.");
  });
});
