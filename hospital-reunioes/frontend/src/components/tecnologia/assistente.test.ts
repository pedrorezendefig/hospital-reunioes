import { describe, expect, it } from "vitest";

import {
  AUDIO_FORA_DA_LISTA,
  avisoDaImagem,
  avisoDoAudio,
  avisoDoDocumento,
  conversaTevePrint,
  descricaoAoCriar,
  DOCUMENTO_FORA_DA_LISTA,
  IMAGEM_FORA_DA_LISTA,
  LIMITE_DA_IMAGEM,
  PREFIXO_DE_PRINT,
  documentoExtraidoValido,
  LIMITE_DA_MENSAGEM,
  LIMITE_DO_AUDIO,
  LIMITE_DO_DOCUMENTO_BINARIO,
  LIMITE_DO_DOCUMENTO_TEXTO,
  mensagemComOrigem,
  motivoDoAnexo,
  NAO_INFORMADO,
  podeCriar,
  PREFIXO_DE_AUDIO,
  prefixoDeDocumento,
  RASCUNHO_VAZIO,
  corpoValidado,
  demandaCriadaValida,
  listaDeProdutosValida,
  respostaDoChatValida,
  ROTEIRO_POR_TIPO,
  TEXTO_CORTADO,
  tetoDoDocumento,
  transcricaoValida,
} from "./assistente";
import { TIPOS } from "./demandas";

describe("Roteiro por Tipo", () => {
  it("todos os sete Tipos têm entrada no roteiro", () => {
    // Um Tipo novo sem roteiro faria `descricaoAoCriar` estourar na hora de
    // criar, com o rascunho pronto na tela.
    expect(TIPOS.every((t) => Array.isArray(ROTEIRO_POR_TIPO[t]))).toBe(true);
  });

  it("Defeito, Novo/Ajuste, Informação/Consultoria e Terceiro têm rótulos diferentes entre si", () => {
    // O par de presença: um roteiro só, repetido nos sete, passaria no teste
    // acima sem que rótulo nenhum estivesse certo.
    expect(ROTEIRO_POR_TIPO.defeito).toEqual(["Onde", "O que aconteceu", "O que esperava", "Quando", "Como repetir"]);
    expect(ROTEIRO_POR_TIPO.novo).toEqual(["O que precisa", "Por quê", "Quem usa", "Hoje é assim"]);
    expect(ROTEIRO_POR_TIPO.ajuste).toEqual(ROTEIRO_POR_TIPO.novo);
    expect(ROTEIRO_POR_TIPO.informacao).toEqual(["Pergunta", "Contexto", "O que já sei"]);
    expect(ROTEIRO_POR_TIPO.consultoria).toEqual(ROTEIRO_POR_TIPO.informacao);
    expect(ROTEIRO_POR_TIPO.terceiro).toEqual(["Quem de fora", "O que falta dele"]);
    expect(ROTEIRO_POR_TIPO.decisao).toEqual([]);
  });
});

describe("descricaoAoCriar", () => {
  it("rótulo sem resposta sai como não informado, na ordem do roteiro", () => {
    const saida = descricaoAoCriar("terceiro", "O que falta dele: o acesso ao relatório");

    expect(saida).toBe(["Quem de fora: " + NAO_INFORMADO, "O que falta dele: o acesso ao relatório"].join("\n"));
  });

  it("o rótulo respondido não vira não informado", () => {
    // O par do teste acima: uma função que escrevesse "não informado" em tudo
    // passaria naquele sozinha.
    const saida = descricaoAoCriar("terceiro", "Quem de fora: a Global Health\nO que falta dele: o acesso");

    expect(saida).not.toContain(NAO_INFORMADO);
  });

  it("resposta de várias linhas fica com o rótulo dela", () => {
    const saida = descricaoAoCriar("terceiro", "Quem de fora: a MV\nfalei com o analista ontem");

    expect(saida).toBe(["Quem de fora: a MV", "falei com o analista ontem", "O que falta dele: " + NAO_INFORMADO].join("\n"));
  });

  it("descrição vazia vira o roteiro inteiro em branco", () => {
    expect(descricaoAoCriar("informacao", "")).toBe(
      ["Pergunta: " + NAO_INFORMADO, "Contexto: " + NAO_INFORMADO, "O que já sei: " + NAO_INFORMADO].join("\n"),
    );
  });

  it("Decisão não ganha rótulo nenhum", () => {
    expect(descricaoAoCriar("decisao", "escolher entre mensal e trimestral")).toBe(
      "escolher entre mensal e trimestral",
    );
  });

  it("o que a pessoa escreveu fora dos rótulos é preservado", () => {
    const saida = descricaoAoCriar("terceiro", "contexto solto\nQuem de fora: a MV\nO que falta dele: o acesso");

    expect(saida.split("\n")[0]).toBe("contexto solto");
  });
});

describe("podeCriar", () => {
  it("o rascunho vazio não cria", () => {
    expect(podeCriar(RASCUNHO_VAZIO)).toBe(false);
  });

  it("título sem Produto não cria", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "Alguma coisa" })).toBe(false);
  });

  it("Produto sem título não cria", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, produto_id: "prod-1" })).toBe(false);
  });

  it("título e Produto criam, mesmo sem Tipo, descrição nem prazo", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "Alguma coisa", produto_id: "prod-1" })).toBe(true);
  });

  it("título só de espaço não conta como título", () => {
    expect(podeCriar({ ...RASCUNHO_VAZIO, titulo: "   ", produto_id: "prod-1" })).toBe(false);
  });
});

describe("O rascunho vazio", () => {
  it("nasce sem Tipo e sem Produto", () => {
    // Um Tipo de partida seria preservado pelo prompt e a Demanda nasceria com
    // o Tipo errado, calada.
    expect(RASCUNHO_VAZIO.tipo).toBeNull();
    expect(RASCUNHO_VAZIO.produto_id).toBeNull();
  });

  it("nasce com prioridade Normal", () => {
    expect(RASCUNHO_VAZIO.prioridade).toBe("normal");
  });
});

describe("respostaDoChatValida", () => {
  const BOA = {
    reply: "Entendi.",
    rascunho: {
      titulo: "Ana não responde",
      tipo: "defeito",
      produto_id: "prod-1",
      prioridade: "normal",
      prazo: null,
      descricao: "Onde: no WhatsApp",
    },
  };

  it("aceita o contrato inteiro", () => {
    expect(respostaDoChatValida(BOA)).toBe(true);
  });

  it("aceita os campos que podem ser nulos", () => {
    expect(respostaDoChatValida({ ...BOA, rascunho: { ...BOA.rascunho, tipo: null, produto_id: null } })).toBe(true);
  });

  // Os quatro primeiros são os corpos que quebravam a tela: `null` levantava no
  // meio do encerramento e congelava o painel, e os outros chegavam ao render.
  it.each([
    ["null", null],
    ["lista", []],
    ["objeto vazio", {}],
    ["sem rascunho", { reply: "oi" }],
    ["rascunho pela metade", { reply: "oi", rascunho: {} }],
    ["rascunho nulo", { reply: "oi", rascunho: null }],
    ["reply que não é texto", { ...BOA, reply: 42 }],
    ["titulo que não é texto", { ...BOA, rascunho: { ...BOA.rascunho, titulo: 42 } }],
    ["descricao ausente", { ...BOA, rascunho: { ...BOA.rascunho, descricao: undefined } }],
    ["prioridade ausente", { ...BOA, rascunho: { ...BOA.rascunho, prioridade: undefined } }],
    ["prazo que não é texto nem nulo", { ...BOA, rascunho: { ...BOA.rascunho, prazo: 7 } }],
  ])("recusa %s", (_nome, corpo) => {
    expect(respostaDoChatValida(corpo)).toBe(false);
  });
});

describe("demandaCriadaValida", () => {
  it("aceita a Demanda com id", () => {
    expect(demandaCriadaValida({ id: "d-1", titulo: "Ana" })).toBe(true);
  });

  it.each([
    ["null", null],
    ["lista", []],
    ["sem id", { titulo: "Ana" }],
    ["id que não é texto", { id: 7 }],
  ])("recusa %s", (_nome, corpo) => {
    expect(demandaCriadaValida(corpo)).toBe(false);
  });
});

describe("listaDeProdutosValida", () => {
  it("aceita a lista de Produtos", () => {
    expect(listaDeProdutosValida([{ id: "p1", nome: "Ana", ativo: true }])).toBe(true);
  });

  it("aceita a lista vazia", () => {
    // Nenhum Produto ativo é um estado possível, não um corpo quebrado.
    expect(listaDeProdutosValida([])).toBe(true);
  });

  it.each([
    ["null", null],
    ["objeto", { produtos: [] }],
    ["item nulo", [null]],
    ["item sem id", [{ nome: "Ana" }]],
    ["item sem nome", [{ id: "p1" }]],
    ["item que é texto", ["Ana"]],
  ])("recusa %s", (_nome, corpo) => {
    expect(listaDeProdutosValida(corpo)).toBe(false);
  });
});

describe("corpoValidado", () => {
  /** Uma `Response` de mentira: só o `json()` importa aqui. */
  function resposta(json: () => Promise<unknown>): Response {
    return { ok: true, status: 200, json } as unknown as Response;
  }

  it("devolve o corpo quando ele passa pelo validador", async () => {
    const corpo = await corpoValidado(resposta(async () => ({ id: "d-1" })), demandaCriadaValida);
    expect(corpo).toEqual({ id: "d-1" });
  });

  it("devolve null quando o corpo não dá para ler", async () => {
    const corpo = await corpoValidado(
      resposta(async () => {
        throw new SyntaxError("Unexpected token <");
      }),
      demandaCriadaValida,
    );
    expect(corpo).toBeNull();
  });

  it("devolve null quando o corpo lê e não serve", async () => {
    // As duas causas saem pela MESMA porta de propósito: para quem está
    // olhando, a resposta chegou e não dá para usar.
    expect(await corpoValidado(resposta(async () => ({ titulo: "Ana" })), demandaCriadaValida)).toBeNull();
  });

  it("nunca levanta, nem com o `json()` explodindo", async () => {
    await expect(
      corpoValidado(
        resposta(async () => {
          throw new TypeError("network error");
        }),
        respostaDoChatValida,
      ),
    ).resolves.toBeNull();
  });
});

// ─── Falar e anexar (issue #729) ────────────────────────────────────────────

describe("O prefixo de origem", () => {
  it("põe a origem na frente do que foi transcrito ou extraído", () => {
    expect(mensagemComOrigem(PREFIXO_DE_AUDIO, "a Ana travou")).toBe("[áudio] a Ana travou");
    expect(mensagemComOrigem(prefixoDeDocumento("nota.pdf"), "a Ana travou")).toBe("[documento nota.pdf] a Ana travou");
  });

  it("o texto que cabe vai inteiro, sem aviso de corte", () => {
    // O par do teste de baixo: um corte que valesse sempre passaria lá e
    // mutilaria toda transcrição de dez segundos.
    const mensagem = mensagemComOrigem(PREFIXO_DE_AUDIO, "x".repeat(LIMITE_DA_MENSAGEM - 200));
    expect(mensagem.length).toBeLessThanOrEqual(LIMITE_DA_MENSAGEM);
    expect(mensagem).not.toContain(TEXTO_CORTADO);
  });

  it("o texto grande demais entra cortado, e o corte é DITO", () => {
    // O teto da mensagem é do backend (422 do pydantic, `detail` em lista, que
    // chegaria como JSON cru ao alerta). Um documento de duas páginas passa
    // dele. Cortar calado mandaria meia verdade ao assistente sem ninguém
    // saber: a mensagem é o que a pessoa lê na conversa, e ela diz o corte.
    const mensagem = mensagemComOrigem(prefixoDeDocumento("longo.pdf"), "x".repeat(LIMITE_DA_MENSAGEM * 2));
    expect(mensagem.length).toBeLessThanOrEqual(LIMITE_DA_MENSAGEM);
    expect(mensagem).toContain(TEXTO_CORTADO);
    expect(mensagem.startsWith("[documento longo.pdf] ")).toBe(true);
  });
});

describe("A peneira do arquivo", () => {
  it("aceita os cinco formatos de áudio, em qualquer caixa de letra", () => {
    for (const ext of [".mp3", ".m4a", ".ogg", ".wav", ".webm"]) {
      expect(avisoDoAudio({ name: `voz${ext}`, size: 1000 })).toBeNull();
      expect(avisoDoAudio({ name: `VOZ${ext.toUpperCase()}`, size: 1000 })).toBeNull();
    }
  });

  it("recusa formato de áudio fora da lista", () => {
    expect(avisoDoAudio({ name: "voz.aac", size: 1000 })).toBe(AUDIO_FORA_DA_LISTA);
    expect(avisoDoAudio({ name: "semponto", size: 1000 })).toBe(AUDIO_FORA_DA_LISTA);
  });

  it("recusa áudio acima de 25 MB, dizendo o limite", () => {
    const aviso = avisoDoAudio({ name: "voz.mp3", size: LIMITE_DO_AUDIO + 1 });
    expect(aviso).toContain("25 MB");
    // E o de 25 MB cravados passa: o par que impede um `>=` disfarçado.
    expect(avisoDoAudio({ name: "voz.mp3", size: LIMITE_DO_AUDIO })).toBeNull();
  });

  it("aceita os quatro formatos de documento", () => {
    for (const ext of [".pdf", ".docx", ".txt", ".md"]) {
      expect(avisoDoDocumento({ name: `nota${ext}`, size: 1000 })).toBeNull();
    }
  });

  it("recusa formato de documento fora da lista", () => {
    expect(avisoDoDocumento({ name: "planilha.xlsx", size: 1000 })).toBe(DOCUMENTO_FORA_DA_LISTA);
  });

  it("o teto do documento depende do formato, como no extrator do backend", () => {
    // Um teto único discordaria do 413 de lá: a tela recusaria o PDF de seis
    // megabytes que o servidor aceita, ou deixaria subir o .txt de dez.
    expect(tetoDoDocumento("nota.txt")).toBe(LIMITE_DO_DOCUMENTO_TEXTO);
    expect(tetoDoDocumento("nota.md")).toBe(LIMITE_DO_DOCUMENTO_TEXTO);
    expect(tetoDoDocumento("nota.pdf")).toBe(LIMITE_DO_DOCUMENTO_BINARIO);
    expect(tetoDoDocumento("nota.docx")).toBe(LIMITE_DO_DOCUMENTO_BINARIO);

    expect(avisoDoDocumento({ name: "nota.txt", size: 6 * 1024 * 1024 })).toContain("5 MB");
    expect(avisoDoDocumento({ name: "nota.pdf", size: 6 * 1024 * 1024 })).toBeNull();
    expect(avisoDoDocumento({ name: "nota.pdf", size: 16 * 1024 * 1024 })).toContain("15 MB");
  });
});

describe("A fronteira do corpo do anexo", () => {
  it("a transcrição só passa com `texto` em texto", () => {
    expect(transcricaoValida({ texto: "a Ana travou" })).toBe(true);
    expect(transcricaoValida({ texto: 42 })).toBe(false);
    expect(transcricaoValida({})).toBe(false);
    expect(transcricaoValida(null)).toBe(false);
  });

  it("o documento extraído cobra também o `filename`", () => {
    // O `filename` é o que vira o prefixo de origem na conversa, e é o backend
    // que o entrega limpo: sem ele não há prefixo, e sem prefixo não há cerca.
    expect(documentoExtraidoValido({ texto: "a Ana travou", filename: "nota.pdf" })).toBe(true);
    expect(documentoExtraidoValido({ texto: "a Ana travou" })).toBe(false);
    expect(documentoExtraidoValido({ filename: "nota.pdf" })).toBe(false);
  });

  it("o motivo da recusa é o do servidor quando ele diz um", async () => {
    const resposta = { status: 413, json: async () => ({ detail: "O arquivo passou do limite de 5 MB." }) };
    expect(await motivoDoAnexo(resposta as Response)).toBe("O arquivo passou do limite de 5 MB.");
  });

  it("recusa sem corpo JSON (um 413 do proxy) vira frase de gente, não JSON cru", async () => {
    const resposta = {
      status: 413,
      json: async () => {
        throw new SyntaxError("Unexpected token <");
      },
    };
    const motivo = await motivoDoAnexo(resposta as unknown as Response);
    expect(motivo).toContain("413");
    expect(motivo).toContain("arquivo");
  });

  it("`detail` em LISTA não chega cru à tela", async () => {
    // É o formato do 422 do pydantic, e foi ele que já chegou como JSON cru ao
    // alerta vermelho uma vez.
    const resposta = { status: 422, json: async () => ({ detail: [{ loc: ["body"], msg: "x" }] }) };
    const motivo = await motivoDoAnexo(resposta as unknown as Response);
    expect(motivo).not.toContain("loc");
    expect(motivo).toContain("422");
  });
});

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

  it("recusa print acima de 5 MB, dizendo o limite", () => {
    const aviso = avisoDaImagem({ name: "tela.png", size: LIMITE_DA_IMAGEM + 1 });
    expect(aviso).toContain("5 MB");
    // E o de 5 MB cravados passa: o par que impede um `>=` disfarçado, e que
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

describe("A conversa teve print? (rodada 2 do PR #771)", () => {
  it("fala da pessoa com o prefixo de print conta", () => {
    expect(conversaTevePrint([{ role: "user", content: "[print] a tela de login" }])).toBe(true);
  });

  it("conversa sem print não conta, nem com as outras duas origens", () => {
    // O detector: um `true` fixo passaria no teste de cima e poria o aviso de
    // dado de paciente em toda conversa, inclusive nas que nunca viram imagem.
    expect(conversaTevePrint([{ role: "user", content: "a Ana travou ontem" }])).toBe(false);
    expect(conversaTevePrint([{ role: "user", content: "[áudio] a Ana travou" }])).toBe(false);
    expect(conversaTevePrint([{ role: "user", content: "[documento nota.pdf] a Ana travou" }])).toBe(false);
    expect(conversaTevePrint([])).toBe(false);
  });

  it("fala do assistente não conta, nem repetindo o prefixo", () => {
    // O que interessa é o que entrou de FORA. Se contasse, o modelo repetindo
    // "[print] ..." na resposta acenderia o aviso sem print nenhum.
    expect(conversaTevePrint([{ role: "assistant", content: "[print] a tela de login" }])).toBe(false);
  });

  it("o prefixo tem que estar no COMEÇO da fala", () => {
    // É o mesmo critério do `PREFIXO_DE_ORIGEM` do backend (`^\[...`), que é
    // quem cerca o material: alguém citando "[print]" no meio de uma frase
    // digitada não trouxe imagem nenhuma.
    expect(conversaTevePrint([{ role: "user", content: "eu ia mandar um [print] mas desisti" }])).toBe(false);
  });
});
