/**
 * O envio e a fila de Contas médicas, a parte sem tela (issue #1123, PRD #1113).
 *
 * O teto do corpo do backend é de 100 MiB e não muda: por isso o envio sai em
 * lotes, todos com o mesmo `envio_id`, e os limites por arquivo e por envio são
 * conferidos aqui antes de subir o que o servidor recusaria de qualquer jeito.
 */
import { describe, expect, it, vi } from "vitest";

import {
  LIMITE_POR_ARQUIVO,
  TETO_DO_LOTE,
  detalheDaConta,
  enviarEmLotes,
  lotes,
  rotuloDaSituacao,
  separarArquivos,
  type ItemDaFila,
} from "./envio";

const MB = 1000 * 1000;

function pdf(nome: string, tamanho = 10): File {
  const arquivo = new File(["%PDF"], nome, { type: "application/pdf" });
  Object.defineProperty(arquivo, "size", { value: tamanho });
  return arquivo;
}

function item(campos: Partial<ItemDaFila>): ItemDaFila {
  return {
    id: "c-1",
    numero_atendimento: "31302",
    numero_conta: "48001",
    situacao: "NA_FILA",
    falta: null,
    periodo_inicio: "2026-10-01",
    periodo_fim: "2026-10-05",
    nota_entrada: null,
    valor_apontado: null,
    itens_feitos: 0,
    itens_total: 0,
    pendencias: 0,
    erro_motivo: null,
    ...campos,
  };
}

describe("os limites do envio, antes de subir", () => {
  it("o 31º arquivo fica de fora com a frase do limite", () => {
    const arquivos = Array.from({ length: 31 }, (_, i) => pdf(`conta-${i + 1}.pdf`));

    const { aceitos, recusas } = separarArquivos(arquivos);

    expect(aceitos).toHaveLength(30);
    expect(recusas).toEqual([
      {
        arquivo: "conta-31.pdf",
        numero_atendimento: null,
        motivo: "O envio já tem 30 arquivos, o limite. Mande este num próximo envio.",
      },
    ]);
  });

  it("arquivo de 101 MB fica de fora e não ocupa vaga", () => {
    const grande = pdf("prontuario-grande.pdf", 101 * MB);
    const arquivos = [grande, ...Array.from({ length: 30 }, (_, i) => pdf(`conta-${i + 1}.pdf`))];

    const { aceitos, recusas } = separarArquivos(arquivos);

    expect(aceitos).toHaveLength(30);
    expect(recusas).toEqual([
      {
        arquivo: "prontuario-grande.pdf",
        numero_atendimento: null,
        motivo: "O arquivo passa de 100 MB, o limite por arquivo.",
      },
    ]);
  });

  it("o arquivo de exatamente 100 MB entra", () => {
    expect(separarArquivos([pdf("limite.pdf", LIMITE_POR_ARQUIVO)]).aceitos).toHaveLength(1);
  });
});

describe("os lotes cabem no teto do corpo", () => {
  it("junta na ordem dos arquivos até o teto, e o arquivo grande vai sozinho", () => {
    const a = pdf("a.pdf", 60 * MB);
    const b = pdf("b.pdf", 25 * MB);
    const c = pdf("c.pdf", 10 * MB);
    const d = pdf("d.pdf", 95 * MB);
    const e = pdf("e.pdf", 1 * MB);

    expect(lotes([a, b, c, d, e]).map((lote) => lote.map((f) => f.name))).toEqual([
      ["a.pdf", "b.pdf"],
      ["c.pdf"],
      ["d.pdf"],
      ["e.pdf"],
    ]);
  });

  it("o teto do lote fica abaixo dos 100 MiB do corpo, com folga para o multipart", () => {
    expect(TETO_DO_LOTE).toBeLessThan(100 * 1024 * 1024);
    expect(LIMITE_POR_ARQUIVO).toBeLessThan(100 * 1024 * 1024);
  });
});

describe("enviar em lotes", () => {
  it("o primeiro lote abre o envio, os seguintes entram nele, e as recusas se somam", async () => {
    const respostas = [
      {
        envio_id: "envio-1",
        ultimo_envio: [{ numero_atendimento: "31302", frase: "falta o prontuário", texto: "31302, falta o prontuário", aviso: null }],
        recusas: [{ arquivo: "x.pdf", numero_atendimento: "31399", motivo: "Plano X ainda não configurado" }],
      },
      {
        envio_id: "envio-1",
        ultimo_envio: [{ numero_atendimento: "31302", frase: "conta e prontuário", texto: "31302, conta e prontuário", aviso: null }],
        recusas: [],
      },
    ];
    const chamadas: FormData[] = [];
    const buscar = vi.fn(async (_url: string, init?: RequestInit) => {
      chamadas.push(init?.body as FormData);
      return new Response(JSON.stringify(respostas[chamadas.length - 1]), { status: 200 });
    });
    const conta = pdf("conta.pdf", 60 * MB);
    const prontuario = pdf("prontuario.pdf", 60 * MB);

    const resultado = await enviarEmLotes([conta, prontuario], "tk", buscar);

    expect(buscar).toHaveBeenCalledTimes(2);
    expect(buscar.mock.calls[0][0]).toBe("/api/contas-medicas/envios");
    expect((buscar.mock.calls[0][1]?.headers as Record<string, string>).Authorization).toBe("Bearer tk");
    expect(chamadas[0].get("envio_id")).toBeNull();
    expect((chamadas[0].getAll("arquivos") as File[]).map((f) => f.name)).toEqual(["conta.pdf"]);
    expect(chamadas[1].get("envio_id")).toBe("envio-1");
    expect((chamadas[1].getAll("arquivos") as File[]).map((f) => f.name)).toEqual(["prontuario.pdf"]);
    expect(resultado.ultimo_envio.map((l) => l.texto)).toEqual(["31302, conta e prontuário"]);
    expect(resultado.recusas.map((r) => r.motivo)).toEqual(["Plano X ainda não configurado"]);
  });

  it("lote que o servidor recusa vira recusa de cada arquivo dele, e o envio segue", async () => {
    const buscar = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Corpo da requisição acima do limite de 100 MB." }), { status: 413 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ envio_id: "envio-2", ultimo_envio: [], recusas: [] }), { status: 200 }),
      );

    const resultado = await enviarEmLotes([pdf("a.pdf", 95 * MB), pdf("b.pdf", 95 * MB)], "tk", buscar);

    expect(resultado.recusas).toEqual([
      { arquivo: "a.pdf", numero_atendimento: null, motivo: "Corpo da requisição acima do limite de 100 MB." },
    ]);
    expect(resultado.envio_id).toBe("envio-2");
  });
});

describe("o que a fila mostra de cada conta", () => {
  it("cada situação tem a sua frase", () => {
    expect(rotuloDaSituacao(item({ situacao: "AGUARDANDO_ARQUIVO", falta: "prontuario" }))).toBe("Falta o prontuário");
    expect(rotuloDaSituacao(item({ situacao: "AGUARDANDO_ARQUIVO", falta: "conta" }))).toBe("Falta a conta");
    expect(rotuloDaSituacao(item({ situacao: "NA_FILA" }))).toBe("Na fila");
    expect(rotuloDaSituacao(item({ situacao: "PROCESSANDO" }))).toBe("Pronta em instantes");
    expect(rotuloDaSituacao(item({ situacao: "A_FAZER" }))).toBe("A fazer");
    expect(rotuloDaSituacao(item({ situacao: "EM_CORRECAO" }))).toBe("Em correção");
    expect(rotuloDaSituacao(item({ situacao: "ERRO" }))).toBe("Erro");
    expect(rotuloDaSituacao(item({ situacao: "CONCLUIDA_COM_PENDENCIA" }))).toBe("Concluída com pendência");
  });

  it("a conta a fazer traz a nota, o R$ e quantos itens foram feitos", () => {
    const conta = item({ situacao: "A_FAZER", nota_entrada: 74, valor_apontado: 584.6, itens_feitos: 0, itens_total: 9 });

    expect(detalheDaConta(conta)).toBe("Nota 74, R$ 584,60, 0 de 9");
  });

  it("a conta com erro traz o motivo, e a concluída com pendência, quantas", () => {
    expect(detalheDaConta(item({ situacao: "ERRO", erro_motivo: "Não consegui ler a conta inteira" }))).toBe(
      "Não consegui ler a conta inteira",
    );
    expect(detalheDaConta(item({ situacao: "CONCLUIDA_COM_PENDENCIA", nota_entrada: 80, pendencias: 2 }))).toBe(
      "Nota 80, 2 pendências",
    );
    expect(detalheDaConta(item({ situacao: "NA_FILA" }))).toBe("");
  });

  it("a conta concluída e reenviada mostra a nota de entrada e a de saída (issue #1136)", () => {
    expect(
      detalheDaConta(item({ situacao: "CONCLUIDA_COM_PENDENCIA", nota_entrada: 79, nota_saida: 86, pendencias: 1 })),
    ).toBe("Nota de entrada 79, nota de saída 86, 1 pendência");
    expect(detalheDaConta(item({ situacao: "CONCLUIDA", nota_entrada: 79, nota_saida: null }))).toBe("Nota 79");
  });
});
