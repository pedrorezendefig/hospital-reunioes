/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319).
 *
 * A régua do que o painel mostra, testada fora da tela: quem entra em cada
 * bloco, o que o painel tem o direito de afirmar quando o módulo de métricas
 * avisa que uma leitura de apoio falhou, e o que ele faz quando a leitura nem
 * chega.
 */

import { describe, expect, it } from "vitest";
import {
  areasComVencidas,
  avisosDeDegradacao,
  calendarioUtilFoiLido,
  classificarFalha,
  classificarJanela,
  contarPorStatus,
  criticosAbertos,
  diaNoHospital,
  hojeNoHospital,
  intervaloDeAtualizacao,
  INTERVALO_BASE_MS,
  INTERVALO_MAXIMO_MS,
  podeVerPainel,
  precisaDaMarcaDeSigilo,
  proximosVencimentos,
  rotuloDoResponsavel,
  rotuloDoSetor,
  vencendoEm,
  type CasoDoPainel,
  type PendenciaDeArea,
} from "./painel";
import { agruparPorStatus, ORDEM_DA_FILA } from "./fila";
import type { StatusManifestacao } from "./prazo";

// Quarta-feira, 26/08/2026. Os vencimentos são carimbados às 17h de Brasília
// (20h UTC), que é o fim do expediente do motor de prazos (RN-22).
const HOJE = "2026-08-26";

/**
 * Sexta-feira, 28/08/2026. É o dia que o bloco "Vence amanhã" nunca conseguia
 * preencher: no sábado não vence nada, então a lista saía sempre vazia e o
 * ouvidor não via na sexta o que vence na segunda.
 */
const SEXTA = "2026-08-28";

function caso(overrides: Partial<CasoDoPainel> = {}): CasoDoPainel {
  return {
    status: "aguardando_area",
    gravidade: "medio",
    prazo_area_em: `${HOJE}T20:00:00+00:00`,
    // O prazo de referência da fundação, que a listagem sempre devolve. É o que
    // vale enquanto o caso ainda não foi validado e não tem prazo da área.
    prazo_resposta: "2026-09-02",
    prazo_estourado: false,
    sigilo_reforcado: false,
    ...overrides,
  };
}

/** Um caso ainda na fila de triagem: sem prazo da área, o da fundação valendo. */
function naTriagem(prazoResposta: string, overrides: Partial<CasoDoPainel> = {}): CasoDoPainel {
  return caso({
    status: "novo",
    gravidade: null,
    prazo_area_em: null,
    prazo_resposta: prazoResposta,
    ...overrides,
  });
}

function pendencia(overrides: Partial<PendenciaDeArea> = {}): PendenciaDeArea {
  return {
    setor: "Recepcao",
    responsavel: "Carlos Titular",
    pendentes: 3,
    vencidas: 1,
    dias_uteis_de_atraso: 1.7,
    ...overrides,
  };
}

describe("quem abre o painel", () => {
  it("aceita os dois perfis da Ouvidoria", () => {
    expect(podeVerPainel("ouvidor")).toBe(true);
    expect(podeVerPainel("diretoria_executiva")).toBe(true);
  });

  it("recusa quem não tem perfil na Ouvidoria, super admin de Reuniões incluído", () => {
    // O gate da Ouvidoria não tem bypass de super admin (ADR 0034, decisão 8).
    // Aqui só chega o eixo `perfil_ouvidoria`: quem é super admin de Reuniões e
    // não tem papel na Ouvidoria chega exatamente como null.
    expect(podeVerPainel(null)).toBe(false);
    expect(podeVerPainel(undefined)).toBe(false);
    expect(podeVerPainel("")).toBe(false);
    expect(podeVerPainel("facilitador")).toBe(false);
  });
});

describe("o dia civil, no fuso do hospital", () => {
  it("lê o vencimento no fuso do hospital, e não no do navegador", () => {
    // 26/08 às 23h de Brasília é 27/08 em UTC. Lido em UTC, um vencimento da
    // noite de hoje apareceria como "vence amanhã".
    expect(diaNoHospital("2026-08-27T02:00:00+00:00")).toBe("2026-08-26");
    expect(diaNoHospital("2026-08-26T20:00:00+00:00")).toBe("2026-08-26");
  });

  it("lê HOJE pela mesma régua, e não pelo relógio universal", () => {
    // Às 23h de Brasília o dia em UTC já virou. Sem esta régua, o painel aberto
    // no fim do plantão empurraria a janela inteira: o que vence hoje sumiria
    // de "Vence hoje" e o de amanhã subiria para o lugar dele.
    expect(hojeNoHospital(new Date("2026-08-27T02:00:00Z"))).toBe("2026-08-26");
    expect(hojeNoHospital(new Date("2026-08-26T15:00:00Z"))).toBe("2026-08-26");
  });
});

describe("a janela de vencimento de um caso", () => {
  it("separa vencido, hoje, amanhã e o resto", () => {
    expect(classificarJanela(caso({ prazo_area_em: `${HOJE}T20:00:00+00:00` }), HOJE)).toBe("hoje");
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-27T20:00:00+00:00" }), HOJE)).toBe("amanha");
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-31T20:00:00+00:00" }), HOJE)).toBe("depois");
  });

  it("o caso que JÁ estourou hoje sai de vence hoje e vira vencido", () => {
    // Vencimento hoje às 11h, ouvidor abre às 16h. Sem esta regra, o mesmo caso
    // aparecia como "Vence hoje" e como "Vencidas" da área em blocos vizinhos,
    // com leituras opostas: quem lê "vence hoje" planeja cobrar até o fim do
    // dia, e o caso já está contando contra o setor.
    const estourado = caso({ prazo_area_em: `${HOJE}T14:00:00+00:00`, prazo_estourado: true });

    expect(classificarJanela(estourado, HOJE)).toBe("vencido");
  });

  it("confia no veredito do motor, e não na data civil, para dizer que estourou", () => {
    // O motor mede em calendário útil e congela o caso pausado. Um vencimento de
    // ontem que o servidor ainda não deu por estourado não é a tela que vai
    // decidir, mas um vencimento de ontem sem veredito segue vencido.
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-25T20:00:00+00:00" }), HOJE)).toBe("vencido");
  });

  it("caso parado aguardando o manifestante fica fora da janela, com o relógio parado", () => {
    // O vencimento só é empurrado na retomada (issue #335). Anunciar "vence
    // hoje" num caso pausado cobraria o setor por uma espera que não é dele.
    expect(classificarJanela(caso({ status: "aguardando_manifestante" }), HOJE)).toBe("parado");
  });

  it("caso já respondido ou encerrado sai do radar de vencimento", () => {
    expect(classificarJanela(caso({ status: "respondido" }), HOJE)).toBe("parado");
    expect(classificarJanela(caso({ status: "encerrado" }), HOJE)).toBe("parado");
  });

  describe("o prazo da própria Ouvidoria, na fila de triagem", () => {
    it("usa o prazo de referência enquanto o caso não tem prazo da área", () => {
      // Cinco casos entram na segunda, ninguém tria, na sexta o prazo vence. Sem
      // este fallback o painel dizia "Vence hoje: 0" e "Nenhuma área com caso
      // vencido": a tela inteira jurava que não havia nada vencendo, e o atraso
      // era da Ouvidoria.
      expect(classificarJanela(naTriagem(HOJE), HOJE)).toBe("hoje");
      expect(classificarJanela(naTriagem("2026-08-27"), HOJE)).toBe("amanha");
      expect(classificarJanela(naTriagem("2026-08-24"), HOJE)).toBe("vencido");
    });

    it("vale também para o caso já em classificação, que ainda é fila do ouvidor", () => {
      expect(classificarJanela(naTriagem(HOJE, { status: "em_classificacao" }), HOJE)).toBe("hoje");
    });

    it("caso sem prazo nenhum não entra em janela nenhuma", () => {
      expect(classificarJanela(naTriagem(""), HOJE)).toBe("sem_prazo");
    });
  });
});

describe("os casos que vencem numa janela", () => {
  it("devolve só os da janela pedida", () => {
    const vencemHoje = [
      caso({ prazo_area_em: `${HOJE}T13:00:00+00:00` }),
      caso({ prazo_area_em: `${HOJE}T20:00:00+00:00` }),
    ];
    const outros = [
      caso({ prazo_area_em: "2026-08-27T20:00:00+00:00" }),
      caso({ prazo_area_em: "2026-08-25T20:00:00+00:00" }),
      naTriagem(""),
      caso({ status: "encerrado" }),
    ];

    expect(vencendoEm([...vencemHoje, ...outros], "hoje", HOJE)).toEqual(vencemHoje);
    expect(vencendoEm([...vencemHoje, ...outros], "amanha", HOJE)).toEqual([outros[0]]);
    expect(vencendoEm([...vencemHoje, ...outros], "vencido", HOJE)).toEqual([outros[1]]);
  });

  it("ordena do vencimento mais próximo para o mais distante", () => {
    const tarde = caso({ prazo_area_em: `${HOJE}T20:00:00+00:00` });
    const manha = caso({ prazo_area_em: `${HOJE}T11:00:00+00:00` });

    expect(vencendoEm([tarde, manha], "hoje", HOJE)).toEqual([manha, tarde]);
  });

  it("ordena o caso de triagem pelo prazo dele, junto dos da área", () => {
    // A área venceu ANTES da triagem de propósito: com uma chave que só olhasse
    // `prazo_area_em`, o caso de triagem (que tem esse campo nulo) iria parar
    // sempre na primeira posição, por acaso e não por urgência, e o painel
    // mandaria correr atrás do caso menos atrasado dos dois.
    const daArea = caso({ prazo_area_em: "2026-08-20T20:00:00+00:00" });
    const daTriagem = naTriagem("2026-08-25");

    expect(vencendoEm([daTriagem, daArea], "vencido", HOJE)).toEqual([daArea, daTriagem]);
  });
});

describe("os próximos vencimentos", () => {
  it("mostra na sexta o que vence na segunda, que a janela de amanhã não via", () => {
    // O bloco existe por causa deste dia. "Vence amanhã" é dia civil, e na
    // sexta-feira amanhã é sábado: a lista ficava vazia toda semana enquanto
    // havia caso vencendo na segunda.
    const naSegunda = caso({ prazo_area_em: "2026-08-31T20:00:00+00:00" });

    expect(vencendoEm([naSegunda], "amanha", SEXTA)).toEqual([]);
    expect(proximosVencimentos([naSegunda], SEXTA, 5)).toEqual([naSegunda]);
  });

  it("continua mostrando o que vence amanhã, que é o bloco que ele substituiu", () => {
    const amanha = caso({ prazo_area_em: "2026-08-27T20:00:00+00:00" });

    expect(proximosVencimentos([amanha], HOJE, 5)).toEqual([amanha]);
  });

  it("ordena do mais próximo para o mais distante e corta no limite", () => {
    const segunda = caso({ prazo_area_em: "2026-08-31T20:00:00+00:00" });
    const terca = caso({ prazo_area_em: "2026-09-01T20:00:00+00:00" });
    const quarta = caso({ prazo_area_em: "2026-09-02T20:00:00+00:00" });

    expect(proximosVencimentos([quarta, terca, segunda], SEXTA, 2)).toEqual([segunda, terca]);
  });

  it("não repete o que os blocos vizinhos mostram, nem ressuscita o parado", () => {
    // Vencido e "vence hoje" têm bloco próprio: repetir aqui faria o mesmo caso
    // ser cobrado duas vezes na mesma tela, e a soma dos três blocos deixaria
    // de fazer sentido para quem lê.
    const vencido = caso({ prazo_area_em: "2026-08-27T20:00:00+00:00", prazo_estourado: true });
    const venceHoje = caso({ prazo_area_em: `${SEXTA}T20:00:00+00:00` });
    const parado = caso({ prazo_area_em: "2026-08-31T20:00:00+00:00", status: "encerrado" });
    const semPrazo = naTriagem("");

    expect(proximosVencimentos([vencido, venceHoje, parado, semPrazo], SEXTA, 5)).toEqual([]);
  });

  it("inclui o caso ainda na triagem, pelo prazo de referência da fundação", () => {
    // O atraso da triagem é da Ouvidoria, e é ela que olha este painel.
    const daTriagem = naTriagem("2026-08-31");

    expect(proximosVencimentos([daTriagem], SEXTA, 5)).toEqual([daTriagem]);
  });
});

describe("os críticos abertos", () => {
  it("traz o caso crítico que ainda não fechou, inclusive o já respondido pela área", () => {
    // A área respondeu, mas o caso grave só sai do radar da Diretoria quando a
    // Ouvidoria encerra.
    const emAndamento = caso({ gravidade: "critico" });
    const respondido = caso({ gravidade: "critico", status: "respondido" });

    expect(criticosAbertos([emAndamento, respondido])).toEqual([emAndamento, respondido]);
  });

  it("deixa de fora o crítico encerrado e o que não é crítico", () => {
    const encerrado = caso({ gravidade: "critico", status: "encerrado" });
    const alto = caso({ gravidade: "alto" });
    const semGravidade = caso({ gravidade: null });

    expect(criticosAbertos([encerrado, alto, semGravidade])).toEqual([]);
  });

  it("carrega a marca de sigilo do caso adiante, sem descartá-la no caminho", () => {
    // A denúncia é sigilosa por natureza e é candidata natural a crítica: ela cai
    // neste bloco, em destaque, com protocolo, setor e resumo. Perder o campo
    // aqui deixaria a tela sem como distinguir denúncia protegida de reclamação
    // de fila (RN-40).
    const sigiloso = caso({ gravidade: "critico", sigilo_reforcado: true });

    expect(criticosAbertos([sigiloso])[0].sigilo_reforcado).toBe(true);
  });
});

describe("a marca de sigilo", () => {
  it("é exigida pelo caso sigiloso e só por ele", () => {
    expect(precisaDaMarcaDeSigilo(caso({ sigilo_reforcado: true }))).toBe(true);
    expect(precisaDaMarcaDeSigilo(caso({ sigilo_reforcado: false }))).toBe(false);
  });
});

describe("a fila por status", () => {
  it("conta na ordem do trabalho do ouvidor e não esconde estado vazio", () => {
    const contagem = contarPorStatus([
      caso({ status: "novo" }),
      caso({ status: "novo" }),
      caso({ status: "aguardando_area" }),
      caso({ status: "encerrado" }),
    ]);

    expect(contagem.map((linha) => [linha.status, linha.total])).toEqual([
      ["novo", 2],
      ["em_classificacao", 0],
      ["aguardando_area", 1],
      ["aguardando_manifestante", 0],
      ["respondido", 0],
      ["encerrado", 1],
    ]);
  });

  it("carrega o rótulo que a listagem já usa, para painel e fila falarem igual", () => {
    expect(contarPorStatus([]).map((linha) => linha.label)).toContain("Aguardando área");
  });

  it("é a mesma régua do agrupamento da fila, e não uma segunda contagem", () => {
    // Duas réguas divergem na primeira mudança: quem mexer na ordem ou no
    // tratamento de estado desconhecido de `agruparPorStatus` precisa ver o
    // painel mudar junto, e não descobrir a divergência em produção.
    const casos = [
      caso({ status: "novo" }),
      caso({ status: "aguardando_area" }),
      caso({ status: "em_recurso" as StatusManifestacao }),
    ];

    expect(contarPorStatus(casos).map((linha) => [linha.status, linha.total])).toEqual(
      agruparPorStatus(casos).map((grupo) => [grupo.status, grupo.itens.length])
    );
  });
});

describe("as áreas com caso vencido", () => {
  it("deixa de fora a área que tem pendência mas nenhuma vencida", () => {
    const emDia = pendencia({ setor: "Farmacia", vencidas: 0, dias_uteis_de_atraso: 0 });
    const atrasada = pendencia();

    expect(areasComVencidas([atrasada, emDia])).toEqual([atrasada]);
  });

  it("preserva a ordem que o módulo de métricas já devolve, sem impor uma sua", () => {
    // A fixture entra FORA da ordem do módulo de propósito: se este módulo
    // ordenasse por conta própria, o painel discordaria do relatório sobre onde
    // apertar, e um teste que entrasse já ordenado não pegaria isso.
    const pior = pendencia({ setor: "Recepcao", dias_uteis_de_atraso: 4.2 });
    const menos = pendencia({ setor: "Farmacia", dias_uteis_de_atraso: 1.1 });

    expect(areasComVencidas([menos, pior]).map((linha) => linha.setor)).toEqual(["Farmacia", "Recepcao"]);
  });
});

describe("o que o painel pode afirmar quando uma leitura falhou", () => {
  it("sem degradação nenhuma, não inventa aviso", () => {
    expect(avisosDeDegradacao([])).toEqual([]);
    expect(calendarioUtilFoiLido([])).toBe(true);
  });

  it("avisa que os prazos saíram com calendário errado quando os feriados não foram lidos", () => {
    // O pior caso do contrato: nada vem nulo e o número sai com cara de bom. E o
    // estrago não para na tabela de áreas: a listagem calcula o rótulo em dias
    // úteis com a MESMA tabela de feriados, e engole a falha sem avisar.
    const avisos = avisosDeDegradacao(["feriados"]);

    expect(avisos.map((a) => a.leitura)).toEqual(["feriados"]);
    expect(avisos[0].texto).toContain("feriado");
    expect(calendarioUtilFoiLido(["feriados"])).toBe(false);
  });

  it("avisa que o nome do responsável não pôde ser lido", () => {
    expect(avisosDeDegradacao(["responsaveis"]).map((a) => a.leitura)).toEqual(["responsaveis"]);
  });

  it("não presume calendário bom quando o módulo de métricas nem respondeu", () => {
    // Quem declara o `degradado` é o `/metricas`. Com ele fora, a lista vazia
    // era lida como "nada degradou", e a tela voltava a afirmar o rótulo em
    // dias úteis de cada caso sem ter como saber se os feriados foram lidos.
    expect(calendarioUtilFoiLido(null)).toBe(false);
  });

  it("cala sobre leitura que não mexe em número nenhum deste painel", () => {
    // `prorrogacoes` e `prazos` degradam a taxa de prorrogação e os trechos de
    // prazo, que são do relatório. Avisar aqui seria ruído sobre número que
    // esta tela nem mostra.
    expect(avisosDeDegradacao(["prorrogacoes", "prazos"])).toEqual([]);
  });
});

describe("o nome do setor na tabela de áreas", () => {
  it("troca o código do caso sem setor pelo rótulo de tela", () => {
    // O módulo de métricas agrupa o caso sem setor em `nao_informado`
    // (`ouvidoria_metricas.py`). O dado continua assim, porque é chave de
    // agrupamento; quem não pode falar em código é a tela.
    expect(rotuloDoSetor("nao_informado")).toBe("Não informado");
  });

  it("devolve o nome do setor exatamente como veio", () => {
    expect(rotuloDoSetor("Recepcao")).toBe("Recepcao");
  });
});

describe("o nome de quem responde pelo setor", () => {
  it("mostra o nome quando ele veio", () => {
    expect(rotuloDoResponsavel("Carlos Titular", [])).toBe("Carlos Titular");
  });

  it("diz que o setor está sem titular quando o cadastro FOI lido", () => {
    expect(rotuloDoResponsavel(null, [])).toBe("Sem titular vigente");
  });

  it("não acusa o setor de estar sem titular quando o cadastro não pôde ser lido", () => {
    // Nulo por falha de leitura é indistinguível de nulo por falta de titular
    // (contrato da #341). Sem esta separação, o painel acusaria de cadastro
    // vazio um setor que tem titular.
    const rotulo = rotuloDoResponsavel(null, ["responsaveis"]);

    expect(rotulo).not.toBe("Sem titular vigente");
    expect(rotulo).toBe("Cadastro não lido");
  });
});

describe("quando a leitura nem chega", () => {
  it("separa perda de acesso de instabilidade", () => {
    // Perder o perfil com o painel aberto não pode virar "está instável": a tela
    // precisa apagar o que já mostrou, e não manter a foto antiga com aviso.
    expect(classificarFalha(403)).toBe("sem_acesso");
    expect(classificarFalha(401)).toBe("sem_acesso");
    expect(classificarFalha(429)).toBe("instavel");
    expect(classificarFalha(500)).toBe("instavel");
    expect(classificarFalha(0)).toBe("instavel");
  });

  it("espaça a tentativa seguinte a cada falha, com teto", () => {
    // O limite do rate limiter é por IP e o hospital inteiro divide um balde só
    // (issue #399). Insistir de minuto em minuto num 429 mantém o balde
    // estourado, e o painel em branco junto.
    expect(intervaloDeAtualizacao(0)).toBe(INTERVALO_BASE_MS);
    expect(intervaloDeAtualizacao(1)).toBe(2 * INTERVALO_BASE_MS);
    expect(intervaloDeAtualizacao(2)).toBe(4 * INTERVALO_BASE_MS);
    expect(intervaloDeAtualizacao(50)).toBe(INTERVALO_MAXIMO_MS);
    expect(intervaloDeAtualizacao(3)).toBeLessThanOrEqual(INTERVALO_MAXIMO_MS);
  });
});

describe("estado que a tela ainda não conhece, no painel (issue #375, item 15)", () => {
  // Mesmo caso do `agruparPorStatus`: backend novo com tela velha, ou migration
  // antes do deploy. O item corrigiu a lista do ouvidor; o painel em tempo real
  // tem a sua própria contagem e a sua própria classificação de janela.
  const DESCONHECIDO = "em_recurso" as StatusManifestacao;

  it("a contagem por status mostra o estado desconhecido, em vez de perdê-lo", () => {
    const casos = [
      caso({ status: "aguardando_area" }),
      caso({ status: DESCONHECIDO }),
    ];

    const contagem = contarPorStatus(casos);
    const linha = contagem.find((c) => c.status === DESCONHECIDO);

    expect(linha?.total).toBe(1);
    // E o rótulo não sai vazio.
    expect(linha?.label).toBe("em_recurso");
  });

  it("os totais da contagem fecham com o total de casos", () => {
    // A prova de que nada some no caminho: era isso que quebrava quando o
    // estado desconhecido caía fora da ORDEM_DA_FILA.
    const casos = [
      caso({ status: "novo" }),
      caso({ status: DESCONHECIDO }),
      caso({ status: DESCONHECIDO }),
    ];

    const somados = contarPorStatus(casos).reduce((soma, linha) => soma + linha.total, 0);

    expect(somados).toBe(casos.length);
  });

  it("estado conhecido sem caso continua virando zero explícito", () => {
    const contagem = contarPorStatus([caso({ status: "novo" })]);

    expect(contagem.map((c) => c.status)).toEqual(ORDEM_DA_FILA);
    expect(contagem.find((c) => c.status === "encerrado")?.total).toBe(0);
  });
});

describe("janela de vencimento de um estado desconhecido (issue #375, item 15)", () => {
  const DESCONHECIDO = "em_recurso" as StatusManifestacao;

  it("caso com prazo estourado aparece como vencido, e não como parado", () => {
    // O caso do item: `EM_ANDAMENTO` é a lista que ESTA tela conhece, e um
    // status novo caía em "parado" antes de a pergunta chegar ao estouro. Um
    // caso já contando contra a área sumia da janela de vencidos, que é a
    // primeira coisa que o ouvidor olha.
    const janela = classificarJanela(
      caso({ status: DESCONHECIDO, prazo_estourado: true }),
      HOJE
    );

    expect(janela).toBe("vencido");
  });

  it("caso sem estouro entra na janela do dia do vencimento", () => {
    const janela = classificarJanela(caso({ status: DESCONHECIDO }), HOJE);

    expect(janela).toBe("hoje");
  });

  it("estado conhecido que não está em andamento continua parado", () => {
    // A porta certa fica fechada: caso encerrado não volta para as janelas de
    // cobrança só porque o desconhecido passou a entrar.
    expect(classificarJanela(caso({ status: "encerrado", prazo_estourado: true }), HOJE)).toBe(
      "parado"
    );
    expect(classificarJanela(caso({ status: "respondido" }), HOJE)).toBe("parado");
  });
});
