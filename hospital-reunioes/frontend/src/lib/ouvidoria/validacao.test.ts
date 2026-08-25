import { describe, expect, it } from "vitest";
import {
  contaNoIndicadorDeResolucao,
  descricaoDeDesfechoValida,
  DESFECHOS,
  estaVigente,
  LABEL_DESFECHO,
  podeEncerrar,
  podeGerirResponsaveis,
  podePausar,
  podeReabrir,
  podeRetomar,
  podeValidar,
  setorTemTitularVigente,
  type Responsavel,
} from "./validacao";

const TITULAR: Responsavel = {
  id: "r1",
  setor: "Recepção",
  papel: "titular",
  nome: "Carlos Titular",
  email: "carlos@hsm.br",
  vigencia_inicio: "2026-01-01",
  vigencia_fim: null,
};

describe("validação e acionamento (issue #325)", () => {
  it("só o caso em classificação oferece o botão de validar", () => {
    expect(podeValidar("em_classificacao")).toBe(true);
    expect(podeValidar("aguardando_area")).toBe(false);
    expect(podeValidar("encerrado")).toBe(false);
  });

  it("quem mantem o cadastro de responsaveis e a diretoria executiva", () => {
    expect(podeGerirResponsaveis("diretoria_executiva")).toBe(true);
    expect(podeGerirResponsaveis("ouvidor")).toBe(false);
    expect(podeGerirResponsaveis(null)).toBe(false);
  });
});

describe("encerramento com desfecho (issue #326)", () => {
  it("caso respondido ou aguardando area oferece o botao de encerrar", () => {
    expect(podeEncerrar("respondido")).toBe(true);
    expect(podeEncerrar("aguardando_area")).toBe(true);
    expect(podeEncerrar("em_classificacao")).toBe(true);
    expect(podeEncerrar("encerrado")).toBe(false);
    expect(podeEncerrar("novo")).toBe(false);
  });

  it("encerramento sem descricao e bloqueado ja na tela", () => {
    expect(descricaoDeDesfechoValida("A area corrigiu o protocolo.")).toBe(true);
    expect(descricaoDeDesfechoValida("   ")).toBe(false);
    expect(descricaoDeDesfechoValida("")).toBe(false);
  });
});

describe("vigencia do responsavel", () => {
  it("vigencia aberta responde hoje", () => {
    expect(estaVigente(TITULAR, "2026-08-25")).toBe(true);
  });

  it("quem sai no dia 31 ainda responde no dia 31", () => {
    const saindo = { ...TITULAR, vigencia_fim: "2026-08-25" };

    expect(estaVigente(saindo, "2026-08-25")).toBe(true);
    expect(estaVigente(saindo, "2026-08-26")).toBe(false);
  });

  it("quem ainda nao entrou no papel nao responde", () => {
    expect(estaVigente({ ...TITULAR, vigencia_inicio: "2026-09-01" }, "2026-08-25")).toBe(false);
  });

  it("setor sem titular vigente aparece como nao acionavel", () => {
    const gestor: Responsavel = { ...TITULAR, id: "r2", papel: "gestor", nome: "Regina" };
    const titularVencido = { ...TITULAR, vigencia_fim: "2026-07-31" };

    expect(setorTemTitularVigente([titularVencido, gestor], "2026-08-25")).toBe(false);
    expect(setorTemTitularVigente([TITULAR, gestor], "2026-08-25")).toBe(true);
  });
});

describe("pausa aguardando o manifestante (issue #335)", () => {
  it("só pausa o caso que está com a área", () => {
    expect(podePausar("aguardando_area")).toBe(true);
    expect(podePausar("em_classificacao")).toBe(false);
    expect(podePausar("respondido")).toBe(false);
    expect(podePausar("aguardando_manifestante")).toBe(false);
  });

  it("só retoma o caso que está parado", () => {
    expect(podeRetomar("aguardando_manifestante")).toBe(true);
    expect(podeRetomar("aguardando_area")).toBe(false);
    expect(podeRetomar("encerrado")).toBe(false);
  });

  it("encerra também o caso parado esperando o manifestante", () => {
    // É de lá que sai o encerramento por abandono, e a tela não pode esconder
    // o botão justo no estado em que ele é o desfecho esperado.
    expect(podeEncerrar("aguardando_manifestante")).toBe(true);
  });
});

describe("reabertura por reincidência (issue #335)", () => {
  it("reabre caso encerrado dentro de trinta dias corridos", () => {
    expect(podeReabrir("encerrado", "2026-09-02T17:00:00+00:00", "2026-09-21T17:00:00+00:00")).toBe(true);
  });

  it("não reabre depois de trinta dias corridos", () => {
    // Fora da janela o caminho é manifestação nova, não reabrir a antiga.
    expect(podeReabrir("encerrado", "2026-09-02T17:00:00+00:00", "2026-10-05T17:00:00+00:00")).toBe(false);
  });

  it("não reabre caso que ainda está aberto", () => {
    expect(podeReabrir("aguardando_area", "2026-09-02T17:00:00+00:00", "2026-09-21T17:00:00+00:00")).toBe(false);
  });

  it("não reabre caso encerrado sem data de encerramento", () => {
    // Sem o marco T3 não há janela para medir, e o servidor recusaria.
    expect(podeReabrir("encerrado", null, "2026-09-21T17:00:00+00:00")).toBe(false);
  });
});

describe("desfecho sem retorno do manifestante (issue #335)", () => {
  it("entra na lista de desfechos do encerramento", () => {
    expect(DESFECHOS).toContain("sem_retorno_do_manifestante");
    expect(LABEL_DESFECHO.sem_retorno_do_manifestante).toBe("Sem retorno do manifestante");
  });

  it("fica fora da conta de resolvido e não resolvido", () => {
    expect(contaNoIndicadorDeResolucao("sem_retorno_do_manifestante")).toBe(false);
    expect(contaNoIndicadorDeResolucao("procedente")).toBe(true);
    expect(contaNoIndicadorDeResolucao(null)).toBe(false);
  });
});
