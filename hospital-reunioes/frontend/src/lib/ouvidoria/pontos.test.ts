import { describe, expect, it } from "vitest";
import {
  agruparPorSetor,
  nomeDoArquivo,
  podeGerirPontos,
  pontoEstaCompleto,
  type PontoDeEscuta,
} from "./pontos";

function ponto(overrides: Partial<PontoDeEscuta> = {}): PontoDeEscuta {
  return {
    id: "ponto-1",
    codigo: "AB2CD3",
    setor: "Recepção",
    ponto: "Poltrona 12",
    ativo: true,
    criado_em: "2026-08-27T12:00:00+00:00",
    qr_data_uri: "data:image/png;base64,AAA",
    ...overrides,
  };
}

describe("quem gere os cartazes (ADR 0036, decisão 7)", () => {
  it("os dois perfis da Ouvidoria gerem", () => {
    // Cartaz é operação do canal, não governança: não carrega dado de paciente
    // e não muda prazo nem responsabilidade. O ouvidor é quem sabe qual cartaz
    // caiu da parede.
    expect(podeGerirPontos("ouvidor")).toBe(true);
    expect(podeGerirPontos("diretoria_executiva")).toBe(true);
  });

  it("quem está fora da Ouvidoria não gere", () => {
    expect(podeGerirPontos(null)).toBe(false);
    expect(podeGerirPontos(undefined)).toBe(false);
    expect(podeGerirPontos("secretaria")).toBe(false);
  });
});

describe("a lista de cartazes", () => {
  it("agrupa por setor, na ordem do alfabeto", () => {
    const grupos = agruparPorSetor([
      ponto({ id: "b", setor: "Recepção" }),
      ponto({ id: "a", setor: "Enfermagem" }),
      ponto({ id: "c", setor: "Recepção", ponto: "Balcão" }),
    ]);

    expect(grupos.map((g) => g.setor)).toEqual(["Enfermagem", "Recepção"]);
    // Os dois cartazes da Recepção ficam juntos, e dentro do setor vale a
    // ordem do rótulo (o teste seguinte).
    expect(grupos[1].pontos.map((p) => p.id).sort()).toEqual(["b", "c"]);
  });

  it("dentro do setor, ordena pelo rótulo do ponto", () => {
    // A tela é uma lista de lugares: procurar "Poltrona 12" numa ordem
    // aleatória é o que faz o ouvidor desistir de usar a tela.
    const grupos = agruparPorSetor([
      ponto({ id: "b", ponto: "Poltrona 12" }),
      ponto({ id: "a", ponto: "Balcão" }),
    ]);

    expect(grupos[0].pontos.map((p) => p.ponto)).toEqual(["Balcão", "Poltrona 12"]);
  });

  it("o cartaz aposentado continua na lista, junto do setor dele", () => {
    // Desativar não é apagar: o ouvidor precisa ver o que já foi usado.
    const grupos = agruparPorSetor([ponto({ ativo: false })]);

    expect(grupos[0].pontos).toHaveLength(1);
  });

  it("lista vazia não vira grupo nenhum", () => {
    expect(agruparPorSetor([])).toEqual([]);
  });
});

describe("o formulário de cartaz novo", () => {
  it("exige setor e rótulo", () => {
    // O rótulo é o que faz alguém achar o cartaz na parede depois.
    expect(pontoEstaCompleto({ setor: "Recepção", ponto: "Poltrona 12" })).toBe(true);
    expect(pontoEstaCompleto({ setor: "", ponto: "Poltrona 12" })).toBe(false);
    expect(pontoEstaCompleto({ setor: "Recepção", ponto: "" })).toBe(false);
  });

  it("espaço em branco não conta como preenchido", () => {
    expect(pontoEstaCompleto({ setor: "  ", ponto: "  " })).toBe(false);
  });
});

describe("o nome do arquivo que a pessoa baixa", () => {
  it("leva o código, para não virar uma pasta de arquivos iguais", () => {
    expect(nomeDoArquivo(ponto(), "pdf")).toBe("cartaz-ouvidoria-AB2CD3.pdf");
    expect(nomeDoArquivo(ponto(), "png")).toBe("qr-ouvidoria-AB2CD3.png");
  });
});
