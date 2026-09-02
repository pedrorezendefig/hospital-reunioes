/**
 * @vitest-environment jsdom
 */

/**
 * A tela do responsável de setor, na ordem da RN-59 (issue #483, PRD #469).
 *
 * O que esta suíte prova é a hierarquia: quem abre este link é o usuário menos
 * treinado do módulo, responde do celular e não volta. A ordem dos elementos,
 * o relato aberto por padrão e o corte do caso protegido são o produto aqui,
 * não detalhe de estilo.
 *
 * A régua de quem lê o quê é do backend, e tem suíte própria
 * (`test_ouvidoria_blocos.py`, `test_ouvidoria_setor_portal.py`). Aqui se prova
 * que a tela respeita o que ele mandou: caso protegido chega com um bloco só, e
 * a tela não inventa os outros dois a partir do que ainda tem em mãos.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalDoSetorPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "token-de-teste" }),
}));

const RESUMO = "Paciente relata espera acima de duas horas na recepção.";
const RELATO = "Cheguei às 8h com minha mãe e só fomos atendidas às 10h30.";
const NOTA = "Confirmar a escala da recepção no turno da manhã e responder o que foi corrigido.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    protocolo: "2026-0007",
    setor: "Recepção",
    categoria: "Tempo de espera",
    gravidade: "alto",
    extrato: NOTA,
    blocos: [
      { chave: "resumo", rotulo: "RESUMO", texto: RESUMO },
      { chave: "relato_integral", rotulo: "RELATO INTEGRAL", texto: RELATO },
      { chave: "nota_da_ouvidoria", rotulo: "NOTA DA OUVIDORIA", texto: NOTA },
    ],
    aviso: null,
    identificacao: "Joana da Silva",
    sigiloso: false,
    destinatario_nome: "Carlos Titular",
    aceita_resposta: true,
    rotulo_prazo: "vence amanhã às 17h",
    prazo_estourado: false,
    minutos_uteis_restantes: 1080,
    degradado: [],
    prorrogacao: {
      regras: ["Uma vez por manifestação.", "Antes do vencimento.", "Com justificativa."],
      max_dias_uteis: 30,
      permitida: true,
      motivo: null,
      pedido: null,
    },
    ...overrides,
  };
}

const AVISO_SIGILO =
  "Caso sob sigilo reforçado: o relato original e o resumo do manifestante não são encaminhados, e o " +
  "caso segue sem identificação de quem manifestou. A nota da Ouvidoria abaixo é o extrato pertinente ao setor.";

/**
 * O caso protegido como o servidor o manda: um bloco só, mais o aviso.
 *
 * `resumo`, `relato_integral` e `manifestante_nome` vão no TOPO do objeto de
 * propósito, e é o ponto do teste. São as colunas que o servidor lê para montar
 * os blocos, e um payload futuro que as devolvesse cruas (por descuido ou por
 * outra tela precisar delas) não pode fazer o dado do cidadão reaparecer aqui.
 * A tela lê `blocos`, e só `blocos`: se ela buscar o dado fora dali, os testes
 * abaixo caem.
 */
function casoProtegido(overrides: Record<string, unknown> = {}) {
  return caso({
    sigiloso: true,
    identificacao: null,
    resumo: RESUMO,
    relato_integral: RELATO,
    manifestante_nome: "Joana da Silva",
    blocos: [{ chave: "nota_da_ouvidoria", rotulo: "NOTA DA OUVIDORIA", texto: NOTA }],
    aviso: AVISO_SIGILO,
    ...overrides,
  });
}

function responderComCaso(corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => corpo }) as unknown as Response)
  );
}

/** Está `a` antes de `b` na ordem de leitura da página? */
function vemAntes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

/**
 * Tudo que o olho lê dentro de `raiz` antes de chegar em `parada`.
 *
 * Serve para pegar intruso: qualquer texto novo enfiado no meio dos elementos
 * da RN-59 aparece aqui, tenha ele testid ou não.
 */
function textoAteChegarNo(raiz: Element, parada: Element): string {
  const passeio = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  let lido = "";
  while (passeio.nextNode()) {
    const no = passeio.currentNode;
    if (parada.contains(no)) break;
    lido += no.textContent ?? "";
  }
  return lido.replace(/\s+/g, " ").trim();
}

async function abrirTela() {
  render(<PortalDoSetorPage />);
  await screen.findByText(NOTA);
}

beforeEach(() => {
  responderComCaso(caso());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("a ordem da RN-59 (issue #483)", () => {
  it("apresenta os elementos de cima para baixo, na ordem que faz responder rápido", async () => {
    await abrirTela();

    const sequencia = [
      screen.getByTestId("faixa-de-gravidade"),
      screen.getByTestId("prazo-regressivo"),
      screen.getByTestId("linha-secundaria"),
      screen.getByTestId("bloco-resumo"),
      screen.getByTestId("bloco-relato_integral"),
      screen.getByTestId("bloco-nota_da_ouvidoria"),
      screen.getByLabelText(/o que foi feito/i),
      screen.getByRole("button", { name: /anexar/i }),
      screen.getByRole("button", { name: /^responder/i }),
      screen.getByRole("button", { name: /solicitar prorrogação/i }),
    ];

    for (let i = 0; i < sequencia.length - 1; i++) {
      expect(vemAntes(sequencia[i], sequencia[i + 1])).toBe(true);
    }
  });

  it("a faixa de gravidade diz o peso do caso antes de qualquer texto", async () => {
    await abrirTela();

    expect(screen.getByTestId("faixa-de-gravidade").textContent ?? "").toMatch(/alto/i);
  });

  it("nada além da identidade do hospital se mete entre a gravidade e o prazo", async () => {
    // O teste de ordem acima compara os nove elementos entre si e não enxerga
    // um intruso NO MEIO deles. Num celular, cada bloco inserido aqui empurra o
    // prazo para fora da primeira tela, que é o que a RN-59 existe para evitar.
    await abrirTela();

    const lido = textoAteChegarNo(
      screen.getByTestId("cabecalho-do-caso"),
      screen.getByTestId("prazo-regressivo")
    );

    expect(lido).toBe("Gravidade AltoDemanda da Ouvidoria");
  });

  it("o prazo aparece em linguagem natural, do motor de prazos", async () => {
    await abrirTela();

    expect(screen.getByTestId("prazo-regressivo").textContent ?? "").toContain("vence amanhã às 17h");
  });

  it("protocolo e setor ficam na linha secundária, para conferir que o caso é meu", async () => {
    await abrirTela();

    const linha = screen.getByTestId("linha-secundaria");
    expect(linha.textContent ?? "").toContain("2026-0007");
    expect(linha.textContent ?? "").toContain("Recepção");
  });
});

describe("os três blocos de leitura (ADR 0041, RN-60)", () => {
  it("o relato integral vem aberto por padrão, sem clique nenhum", async () => {
    await abrirTela();

    expect(screen.getByTestId("bloco-relato_integral").textContent ?? "").toContain(RELATO);
  });

  it("a nota da ouvidoria fica em bloco visualmente distinto do relato", async () => {
    await abrirTela();

    const relato = screen.getByTestId("bloco-relato_integral").className;
    const nota = screen.getByTestId("bloco-nota_da_ouvidoria").className;
    const resumo = screen.getByTestId("bloco-resumo").className;

    expect(new Set([relato, nota, resumo]).size).toBe(3);
  });

  it("cada bloco chega com o rótulo que o servidor mandou", async () => {
    await abrirTela();

    expect(screen.getByText("RESUMO")).toBeTruthy();
    expect(screen.getByText("RELATO INTEGRAL")).toBeTruthy();
    expect(screen.getByText("NOTA DA OUVIDORIA")).toBeTruthy();
  });

  it("caso comum não mostra aviso de corte: não houve corte", async () => {
    await abrirTela();

    expect(screen.queryByTestId("aviso-do-caso")).toBeNull();
  });
});

describe("a variante da RN-79: o caso protegido", () => {
  beforeEach(() => {
    responderComCaso(casoProtegido());
  });

  it("não mostra resumo nem relato, mesmo com o payload trazendo os dois crus", async () => {
    // O fixture protegido carrega `resumo` e `relato_integral` no topo do
    // objeto. Se a tela buscasse o dado fora de `blocos`, ela teria com que
    // desfazer o corte do servidor, e é isso que estas quatro linhas seguram.
    await abrirTela();

    expect(screen.queryByTestId("bloco-resumo")).toBeNull();
    expect(screen.queryByTestId("bloco-relato_integral")).toBeNull();
    expect(screen.queryByText(RESUMO)).toBeNull();
    expect(screen.queryByText(RELATO)).toBeNull();
  });

  it("mostra o aviso que explica por que o resto do caso não veio", async () => {
    await abrirTela();

    expect(screen.getByTestId("aviso-do-caso").textContent ?? "").toMatch(/sigilo reforçado/i);
  });

  it("a nota da ouvidoria é o que a área lê no lugar do relato", async () => {
    await abrirTela();

    expect(screen.getByTestId("bloco-nota_da_ouvidoria").textContent ?? "").toContain(NOTA);
  });

  it("não leva identificação de quem manifestou", async () => {
    await abrirTela();

    expect(screen.queryByText("Joana da Silva")).toBeNull();
  });

  it("mesmo protegido, o caso continua respondível", async () => {
    await abrirTela();

    expect(screen.getByRole("button", { name: /^responder/i })).toBeTruthy();
  });
});

describe("o campo único de resposta (RN-61)", () => {
  it("tem rótulo O QUE FOI FEITO, orientação fixa e exemplo no placeholder", async () => {
    await abrirTela();

    const campo = screen.getByLabelText(/o que foi feito/i) as HTMLTextAreaElement;
    expect(campo.placeholder.length).toBeGreaterThan(40);
    expect(screen.getByTestId("orientacao-da-resposta").textContent ?? "").toContain("20");
  });

  it("o botão responder fica desabilitado antes de 20 caracteres", async () => {
    await abrirTela();
    const campo = screen.getByLabelText(/o que foi feito/i);
    const botao = screen.getByRole("button", { name: /^responder/i }) as HTMLButtonElement;

    expect(botao.disabled).toBe(true);

    fireEvent.change(campo, { target: { value: "Trocamos a escala." } });
    expect(botao.disabled).toBe(true);

    fireEvent.change(campo, { target: { value: "Trocamos a escala do turno da manhã." } });
    await waitFor(() => expect(botao.disabled).toBe(false));
  });

  it("o botão responder fica desabilitado acima do teto de 10.000 caracteres", async () => {
    // O par simétrico do piso (issue #512). O teto vive no servidor desde a
    // v0.93.0, e sem este espelho o responsável escrevia 12.000 caracteres com
    // o botão habilitado e levava 422 com o campo cheio.
    await abrirTela();
    const campo = screen.getByLabelText(/o que foi feito/i);
    const botao = screen.getByRole("button", { name: /^responder/i }) as HTMLButtonElement;

    fireEvent.change(campo, { target: { value: "a".repeat(10_000) } });
    await waitFor(() => expect(botao.disabled).toBe(false));

    fireEvent.change(campo, { target: { value: "a".repeat(10_001) } });
    await waitFor(() => expect(botao.disabled).toBe(true));
  });

  it("o contador do teto só aparece perto do limite, e avisa quando passa", async () => {
    await abrirTela();
    const campo = screen.getByLabelText(/o que foi feito/i);

    // Resposta de tamanho normal não ganha contador: a tela já é longa.
    fireEvent.change(campo, { target: { value: "Trocamos a escala do turno da manhã." } });
    expect(screen.queryByTestId("aviso-do-teto")).toBeNull();

    fireEvent.change(campo, { target: { value: "a".repeat(9_500) } });
    await waitFor(() => expect(screen.getByTestId("aviso-do-teto").textContent).toContain("500"));

    fireEvent.change(campo, { target: { value: "a".repeat(10_001) } });
    await waitFor(() =>
      expect(screen.getByTestId("aviso-do-teto").textContent ?? "").toContain("passou")
    );
  });
});

describe("apenas os dois botões da RN-62", () => {
  it("a tela não oferece encerrar, reclassificar nem reatribuir", async () => {
    await abrirTela();

    const rotulos = screen
      .getAllByRole("button")
      .map((botao) => (botao.textContent ?? "").toLowerCase());

    expect(rotulos.some((r) => /encerrar/.test(r))).toBe(false);
    expect(rotulos.some((r) => /reclassificar/.test(r))).toBe(false);
    expect(rotulos.some((r) => /reatribuir/.test(r))).toBe(false);
  });

  it("nada do que a Ouvidoria preencheu é editável: só a resposta e o anexo entram", async () => {
    await abrirTela();

    const campos = [
      ...screen.getByTestId("cabecalho-do-caso").querySelectorAll("input, textarea, select"),
      ...screen.getByTestId("leitura-do-caso").querySelectorAll("input, textarea, select"),
    ];

    expect(campos).toHaveLength(0);
  });
});

describe("a prorrogação depois do vencimento (RN-62)", () => {
  beforeEach(() => {
    responderComCaso(
      caso({
        prazo_estourado: true,
        rotulo_prazo: "venceu há 2 dias úteis",
        prorrogacao: {
          regras: ["Uma vez por manifestação.", "Antes do vencimento.", "Com justificativa."],
          max_dias_uteis: 30,
          permitida: false,
          motivo: "O prazo desta manifestação já venceu. A prorrogação só vale se pedida antes do vencimento.",
          pedido: null,
        },
      })
    );
  });

  it("o botão continua na tela, desabilitado, com o motivo à vista", async () => {
    await abrirTela();

    const botao = screen.getByRole("button", { name: /solicitar prorrogação/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.getByText(/já venceu/i)).toBeTruthy();
  });

  it("o motivo está ligado ao botão e vem antes dele, que `disabled` tira do foco", async () => {
    // Quem navega por teclado nunca chega num botão desabilitado, então o
    // motivo tem que estar amarrado a ele e já ter sido lido quando o leitor
    // de tela passa pelo botão.
    await abrirTela();

    const botao = screen.getByRole("button", { name: /solicitar prorrogação/i });
    const idDoMotivo = botao.getAttribute("aria-describedby");
    expect(idDoMotivo).toBeTruthy();

    const motivo = document.getElementById(idDoMotivo!);
    expect(motivo?.textContent ?? "").toMatch(/já venceu/i);
    expect(vemAntes(motivo!, botao)).toBe(true);
  });

  it("o caso vencido continua aceitando resposta: responder nunca fica bloqueado pelo prazo", async () => {
    await abrirTela();
    const campo = screen.getByLabelText(/o que foi feito/i);

    fireEvent.change(campo, { target: { value: "Trocamos a escala do turno da manhã." } });

    const botao = screen.getByRole("button", { name: /^responder/i }) as HTMLButtonElement;
    await waitFor(() => expect(botao.disabled).toBe(false));
  });
});
