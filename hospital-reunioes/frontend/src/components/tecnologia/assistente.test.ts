import { describe, expect, it } from "vitest";

import {
  avisoDaImagem,
  IMAGEM_FORA_DA_LISTA,
  LIMITE_DA_IMAGEM,
  LIMITE_DA_MENSAGEM,
  PREFIXO_DE_PRINT,
  mensagemComOrigem,
  TEXTO_CORTADO,
} from "./assistente";

// ─── Falar e anexar (issue #729) ────────────────────────────────────────────

describe("A peneira do print (issue #730)", () => {
  it("aceita os quatro formatos de imagem, em qualquer caixa de letra", () => {
    for (const ext of [".png", ".jpg", ".jpeg", ".webp"]) {
      expect(avisoDaImagem({ name: `tela${ext}`, size: 1000 })).toBeNull();
      expect(avisoDaImagem({ name: `TELA${ext.toUpperCase()}`, size: 1000 })).toBeNull();
    }
  });

  it("recusa formato de imagem fora da lista", () => {
    // `.gif` e `.heic` são os dois que chegam de verdade e que o modelo não lê
    // por esta rota; sem ponto nenhum no nome também não é print.
    expect(avisoDaImagem({ name: "tela.gif", size: 1000 })).toBe(IMAGEM_FORA_DA_LISTA);
    expect(avisoDaImagem({ name: "foto.heic", size: 1000 })).toBe(IMAGEM_FORA_DA_LISTA);
    expect(avisoDaImagem({ name: "semponto", size: 1000 })).toBe(IMAGEM_FORA_DA_LISTA);
  });

  it("recusa print acima de 3,75 MB, o teto do backend, dizendo o limite", () => {
    // Desde a issue #1520 o teto vem do espelho da tabela do backend: antes a
    // tela deixava subir até 5 MB e o servidor recusava acima de 3,75 MB.
    expect(LIMITE_DA_IMAGEM).toBe(3932160);
    const aviso = avisoDaImagem({ name: "tela.png", size: LIMITE_DA_IMAGEM + 1 });
    expect(aviso).toContain("limite de 3,75 MB");
    // E o de 3,75 MB cravados passa: o par que impede um `>=` disfarçado, e que
    // mantém a tela concordando com o 413 do backend em vez de recusar antes.
    expect(avisoDaImagem({ name: "tela.png", size: LIMITE_DA_IMAGEM })).toBeNull();
  });

  it("arquivo que viola as DUAS regras ouve a do formato, como no backend", () => {
    // A ordem das duas guardas é contrato, e não gosto: a rota peneira a
    // extensão ANTES de olhar o tamanho, então um `.gif` de 6 MB leva 422 de
    // formato lá. Com a ordem invertida aqui, a tela diria "passou do limite de
    // 5 MB" e o servidor diria "só dá para ler .png, .jpg, .jpeg ou .webp"
    // sobre o mesmo arquivo: é a classe de bug que a #729 combateu.
    expect(avisoDaImagem({ name: "animada.gif", size: LIMITE_DA_IMAGEM + 1 })).toBe(IMAGEM_FORA_DA_LISTA);
  });

  it("o prefixo do print não leva nome de arquivo", () => {
    // O nome de um print é "Captura de tela 2026-09-17 às 14.02.11.png", que não
    // diz nada a quem lê a conversa. `[print] ` seco é origem que o backend
    // reconhece e cerca (`PREFIXO_DE_ORIGEM` aceita rótulo sem nome).
    expect(mensagemComOrigem(PREFIXO_DE_PRINT, "A tela de login com erro")).toBe("[print] A tela de login com erro");
  });
});

describe("A fala que vem de fora, dentro do teto (issue #729)", () => {
  it("a descrição longa é cortada no teto da fala e diz que foi cortada", () => {
    const fala = mensagemComOrigem(PREFIXO_DE_PRINT, "x".repeat(LIMITE_DA_MENSAGEM * 2));

    expect(fala.length).toBe(LIMITE_DA_MENSAGEM);
    expect(fala.startsWith(PREFIXO_DE_PRINT)).toBe(true);
    expect(fala.endsWith(TEXTO_CORTADO)).toBe(true);
  });
});
