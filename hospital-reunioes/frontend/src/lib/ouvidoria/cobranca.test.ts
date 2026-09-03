/**
 * O que a linha da fila escreve depois de cobrar (issues #495 e #536).
 *
 * Escolher o destinatário saiu daqui na #536: quem responde pelo setor hoje é
 * decisão do servidor, e a tela só exibe o que a resposta afirmou. O que sobra
 * para testar é justamente isso, que a frase nunca prometa mais do que a
 * resposta disse.
 */

import { describe, expect, it } from "vitest";

import { RECUSA_SEM_EXPLICACAO, textoDaCobranca, tomDaCobranca } from "./cobranca";

describe("o que a linha escreve depois de cobrar", () => {
  it("afirma a entrega só quando a resposta confirma", () => {
    const entregue = { fase: "reenviada", destinatario: "Carlos", entregue: true } as const;
    const naFila = { fase: "reenviada", destinatario: "Carlos", entregue: false } as const;

    expect(textoDaCobranca(entregue)).toBe("Acionamento reenviado a Carlos");
    expect(textoDaCobranca(naFila)).toContain("ficou na fila");
    expect(tomDaCobranca(entregue)).toBe("ok");
    expect(tomDaCobranca(naFila)).toBe("alerta");
  });

  it("nomeia quem recebeu, e não o responsável em abstrato", () => {
    // O nome vem do servidor, que é quem escolheu. A linha mostra o
    // responsável de hoje ao lado do botão, mas a promessa tem de ser sobre o
    // email que de fato saiu.
    expect(textoDaCobranca({ fase: "reenviada", destinatario: "Regina Nova", entregue: true })).toContain(
      "Regina Nova"
    );
  });

  it("a recusa mostra a explicação do servidor, palavra por palavra", () => {
    // As duas faltas que o servidor distingue (setor sem responsável vigente e
    // responsável vigente sem email) mandam o ouvidor a lugares diferentes.
    // Reescrever a frase aqui apagaria a diferença.
    const explicacao = "Carlos Titular está sem email no cadastro de responsáveis.";

    expect(textoDaCobranca({ fase: "recusada", explicacao })).toBe(explicacao);
  });

  it("recusa que chegou sem frase não sai em branco na linha", () => {
    expect(textoDaCobranca({ fase: "recusada", explicacao: "" })).toBe(RECUSA_SEM_EXPLICACAO);
    expect(tomDaCobranca({ fase: "recusada", explicacao: "" })).toBe("alerta");
  });

  it("toda fase tem frase, para o aviso nunca sair em branco", () => {
    const fases = [
      { fase: "enviando" },
      { fase: "reenviada", destinatario: "Carlos", entregue: true },
      { fase: "reenviada", destinatario: "Carlos", entregue: false },
      { fase: "recusada", explicacao: "Setor sem responsável vigente." },
      { fase: "falha" },
    ] as const;

    for (const fase of fases) {
      expect(textoDaCobranca(fase).length).toBeGreaterThan(0);
    }
  });
});
