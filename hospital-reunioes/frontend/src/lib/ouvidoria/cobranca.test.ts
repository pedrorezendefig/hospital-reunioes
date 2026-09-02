/**
 * A cobrança da fila (issue #495, PRD #471): reenviar o acionamento do setor
 * sem entrar no Dossiê.
 *
 * Cobrar não inventa email novo: é a regra vigente de reenvio (ADR 0034,
 * decisão 7), que nasce como registro próprio e preserva a data do primeiro
 * envio. Quem escolhe QUAL registro reenviar é esta função.
 */

import { describe, expect, it } from "vitest";

import {
  GATILHO_DO_ACIONAMENTO,
  acionamentoParaCobrar,
  decidirCobranca,
  textoDaCobranca,
  tomDaCobranca,
} from "./cobranca";

const CARLOS = { nome: "Carlos Titular", email: "carlos@hsm.br" };
const REGINA = { nome: "Regina Nova", email: "regina@hsm.br" };

function registro(id: string, gatilho: string, criada_em: string, destinatario = CARLOS) {
  return {
    id,
    gatilho,
    criada_em,
    destinatario_nome: destinatario.nome,
    destinatario_email: destinatario.email,
  };
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

/**
 * Para quem a cobrança pode sair (rodada de review do PR #534).
 *
 * O reenvio manda o relato integral do manifestante e um token novo do portal
 * do setor para o destinatário do acionamento ORIGINAL. A linha da fila mostra
 * o responsável de HOJE. Quando os dois são pessoas diferentes, um clique
 * despacharia o caso para quem não responde mais pela área.
 */
describe("decidirCobranca", () => {
  const ACIONAMENTO = registro("n-acionamento", GATILHO_DO_ACIONAMENTO, "2026-07-01T10:00:00Z");

  it("libera quando o destinatário do acionamento é o responsável de hoje", () => {
    const veredito = decidirCobranca([ACIONAMENTO], CARLOS, true);

    expect(veredito).toEqual({
      pode: true,
      notificacaoId: "n-acionamento",
      destinatario: "Carlos Titular",
    });
  });

  it("recusa quando o titular trocou: o acionamento antigo iria para quem saiu", () => {
    const veredito = decidirCobranca([ACIONAMENTO], REGINA, true);

    expect(veredito).toEqual({
      pode: false,
      motivo: "outro_destinatario",
      destinatario: "Carlos Titular",
    });
  });

  it("caixa e espaço do email não fazem de duas pessoas uma", () => {
    const gritado = { ...CARLOS, email: "  CARLOS@HSM.BR " };

    expect(decidirCobranca([ACIONAMENTO], gritado, true).pode).toBe(true);
  });

  it("email vazio dos dois lados não conta como a mesma pessoa", () => {
    // O cadastro aceita responsável sem email; o acionamento nunca sai sem um.
    // Sem esta guarda, dois vazios se igualariam e a cobrança sairia às cegas.
    const semEmail = { nome: "Sara", email: "" };
    const acionamentoSemEmail = { ...ACIONAMENTO, destinatario_email: "" };

    expect(decidirCobranca([acionamentoSemEmail], semEmail, true).pode).toBe(false);
  });

  it("setor que hoje não tem responsável nenhum não recebe cobrança de um clique", () => {
    expect(decidirCobranca([ACIONAMENTO], null, true)).toEqual({
      pode: false,
      motivo: "outro_destinatario",
      destinatario: "Carlos Titular",
    });
  });

  it("cadastro não lido recusa: não sei não pode virar pode mandar", () => {
    expect(decidirCobranca([ACIONAMENTO], CARLOS, false)).toEqual({
      pode: false,
      motivo: "cadastro_desconhecido",
    });
  });

  it("caso sem acionamento continua sem ter o que reenviar", () => {
    expect(decidirCobranca([], CARLOS, true)).toEqual({ pode: false, motivo: "sem_acionamento" });
  });
});

describe("o que a linha escreve depois de cobrar", () => {
  it("afirma a entrega só quando a resposta confirma", () => {
    const entregue = { fase: "reenviada", destinatario: "Carlos", entregue: true } as const;
    const naFila = { fase: "reenviada", destinatario: "Carlos", entregue: false } as const;

    expect(textoDaCobranca(entregue)).toBe("Acionamento reenviado a Carlos");
    expect(textoDaCobranca(naFila)).toContain("ficou na fila");
    expect(tomDaCobranca(entregue)).toBe("ok");
    expect(tomDaCobranca(naFila)).toBe("alerta");
  });

  it("a recusa por troca de responsável nomeia quem receberia", () => {
    const texto = textoDaCobranca({
      fase: "recusada",
      motivo: "outro_destinatario",
      destinatario: "Carlos Titular",
    });

    expect(texto).toContain("Carlos Titular");
    expect(texto).toContain("Dossiê");
  });

  it("toda fase tem frase, para o aviso nunca sair em branco", () => {
    const fases = [
      { fase: "enviando" },
      { fase: "reenviada", destinatario: "Carlos", entregue: true },
      { fase: "recusada", motivo: "sem_acionamento" },
      { fase: "recusada", motivo: "cadastro_desconhecido" },
      { fase: "recusada", motivo: "outro_destinatario", destinatario: "Carlos" },
      { fase: "falha" },
    ] as const;

    for (const fase of fases) {
      expect(textoDaCobranca(fase).length).toBeGreaterThan(0);
    }
  });
});
