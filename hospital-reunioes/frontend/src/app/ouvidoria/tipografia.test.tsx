/**
 * @vitest-environment jsdom
 */

/**
 * A varredura tipográfica da Ouvidoria (issue #489, PRD #471, RN-76, D-19).
 *
 * A regra da caixa alta mora em `lib/ouvidoria/tipografia` e tem teste próprio.
 * Aqui ela é APLICADA: as telas são renderizadas, tudo o que sai em maiúscula
 * é recolhido do DOM e passa pela régua. É o que impede a volta do que abriu a
 * issue, um crédito de resposta com nome e data grudado dentro do título da
 * seção, saindo inteiro em caixa alta.
 *
 * A caixa alta é sempre do CSS. Por isso a varredura procura a classe
 * `uppercase` e lê o `textContent` como ele foi escrito: se alguém trocar o
 * mecanismo e escrever "ENCERRAR" no JSX, o texto some do DOM em caixa mista e
 * nenhum teste daqui tem como reencontrá-lo. É o segundo motivo, além do leitor
 * de tela, para a maiúscula nunca nascer no código.
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dossie } from "@/components/ouvidoria/Dossie";
import { ehRotuloCurto } from "@/lib/ouvidoria/tipografia";

import OuvidoriaPage from "./page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: "ouvidor" as string | null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      perfil_ouvidoria: sessao.perfilOuvidoria,
    },
    loading: false,
  }),
}));

const RESUMO =
  "Paciente relata espera de mais de três horas na recepção do ambulatório, sem nenhuma " +
  "informação sobre a fila e sem lugar para sentar durante todo o período de espera.";

const RELATO =
  "Cheguei às oito da manhã com a guia em mãos e só fui chamado às onze e meia, sem que " +
  "ninguém explicasse o motivo da demora nem oferecesse água.";

/* ------------------------------------------------------------------ */
/* A varredura                                                         */
/* ------------------------------------------------------------------ */

function classesDe(no: Element): string[] {
  // `getAttribute` e não `className`: em elemento SVG o `className` é um
  // `SVGAnimatedString`, e `split` nele estoura no meio da varredura.
  return (no.getAttribute("class") ?? "").split(/\s+/);
}

/** O elemento pinta a si e aos filhos de maiúscula? */
function carregaCaixaAlta(no: Element): boolean {
  return classesDe(no).includes("uppercase");
}

/** O elemento SAI em maiúscula, por classe própria ou herdada de um pai? */
function saiEmCaixaAlta(no: Element | null): boolean {
  for (let atual: Element | null = no; atual; atual = atual.parentElement) {
    const classes = classesDe(atual);
    if (classes.includes("normal-case")) return false;
    if (classes.includes("uppercase")) return true;
  }
  return false;
}

/**
 * O texto que este elemento realmente grita.
 *
 * Não é o `textContent`: o rótulo pode carregar um aparte que se declarou fora
 * da maiúscula, como a marca de obrigatoriedade do campo. Somar o que ele diz
 * ao que o rótulo grita acusaria um grito que a tela não dá.
 */
function textoGritado(no: Element): string {
  let texto = "";
  for (const filho of Array.from(no.childNodes)) {
    if (filho.nodeType === Node.TEXT_NODE) texto += filho.textContent ?? "";
    else if (filho.nodeType === Node.ELEMENT_NODE) {
      const elemento = filho as Element;
      if (classesDe(elemento).includes("normal-case")) continue;
      texto += textoGritado(elemento);
    }
  }
  return texto;
}

/** Tudo o que a tela está gritando, no momento em que a varredura passa. */
function textosEmCaixaAlta(): string[] {
  return Array.from(document.body.querySelectorAll("*")).filter(carregaCaixaAlta).map(textoGritado);
}

function frasesEmCaixaAlta(): string[] {
  return textosEmCaixaAlta()
    .filter((texto) => !ehRotuloCurto(texto))
    .map((texto) => texto.replace(/\s+/g, " ").trim());
}

/* ------------------------------------------------------------------ */
/* A fila                                                              */
/* ------------------------------------------------------------------ */

const BASE = {
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-12-31",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: RESUMO,
  conversa_id: "",
  gravidade: "alto",
  prazo_area_em: null,
  prazo_estourado: false,
  rotulo_prazo: "",
  minutos_uteis_restantes: null,
  tem_novidade: false,
};

function caso(numero: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    ...BASE,
    id: `uuid-${numero}`,
    numero,
    protocolo: `2026-${String(numero).padStart(4, "0")}`,
    status,
    ...extra,
  };
}

/** Um caso de cada estado: os três botões primários da fila numa tela só. */
const FILA = [
  caso(1, "em_classificacao", { gravidade: null }),
  caso(2, "aguardando_area"),
  caso(3, "respondido"),
];

async function montarFila() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const endereco = String(url);
      const json = endereco.includes("/participantes/setores")
        ? ["Recepção", "Enfermagem"]
        : endereco.includes("/responsaveis")
          ? { responsaveis: [] }
          : { protocolos: FILA };
      return { ok: true, status: 200, json: async () => json } as Response;
    })
  );
  render(<OuvidoriaPage />);
  await screen.findByText("2026-0002");
}

function linhaDe(protocolo: string): HTMLElement {
  const linha = document.querySelector<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (!linha) throw new Error(`sem linha para o protocolo ${protocolo}`);
  return linha;
}

/* ------------------------------------------------------------------ */
/* O Dossiê                                                            */
/* ------------------------------------------------------------------ */

const DOSSIE = {
  id: "uuid-9",
  protocolo: "2026-0009",
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-08-21",
  status: "encerrado",
  tipo_manifestacao: "reclamacao",
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: RESUMO,
  relato_integral: RELATO,
  manifestante_nome: "Joana Aparecida da Silva",
  manifestante_contato: "joana@exemplo.com",
  manifestante_vinculo: "paciente",
  anonimo: false,
  sigilo_reforcado: false,
  dados_incompletos: false,
  desfecho: "procedente",
  desfecho_descricao:
    "A escala da recepção foi reforçada a partir desta semana, com mais um atendente no turno da manhã.",
  gravidade: "medio",
  prazo_area_em: null,
  validada_em: "2026-08-14T20:00:00+00:00",
  respondida_em: "2026-08-18T16:00:00+00:00",
  resposta_da_area:
    "A escala foi revista e o setor passou a contar com um atendente extra no turno da manhã.",
  respondida_por_nome: "Carlos Eduardo de Almeida",
  encerrada_em: "2026-08-20T19:00:00+00:00",
  pausada_em: null,
  minutos_pausados: 0,
  reincidencia: false,
  reaberta_em: null,
  canal: "site",
  canal_setor: null,
  canal_ponto: null,
  natureza_informada: null,
  marcos: [
    {
      chave: "T0",
      rotulo: "Entrada",
      em: "2026-08-14T19:00:00+00:00",
      pendente: false,
      trecho: null,
      minutos_uteis: null,
      em_curso: false,
      tramitacao_anterior_em: null,
    },
  ],
  prazos: [],
  acuse: {
    rotulo: "Acuse de recebimento",
    em: "2026-08-14T19:01:00+00:00",
    situacao: "enviado",
    nota: null,
  },
  aviso_encerramento: {
    rotulo: "Aviso de encerramento",
    em: "2026-08-20T19:00:00+00:00",
    situacao: "enviado",
    nota: null,
  },
  degradado: [],
};

async function montarDossie() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const endereco = String(url);
      const json = endereco.endsWith("/anexos")
        ? { anexos: [] }
        : endereco.endsWith("/notificacoes")
          ? { notificacoes: [] }
          : endereco.endsWith("/prorrogacoes")
            ? { prorrogacoes: [] }
            : endereco.endsWith("/respostas")
              ? { respostas: [] }
              : endereco.endsWith("/tentativas-contato")
                ? { tentativas: [] }
                : DOSSIE;
      return { ok: true, json: async () => json } as Response;
    })
  );
  render(<Dossie protocolo="2026-0009" token="token-de-teste" />);
  await screen.findByText("Marcos do caso");
}

/* ------------------------------------------------------------------ */

beforeEach(() => {
  sessao.perfilOuvidoria = "ouvidor";
  vi.unstubAllGlobals();
});

afterEach(async () => {
  // A leitura do cadastro de responsáveis continua em voo depois que a linha
  // aparece. Sem deixá-la pousar, o `setState` dela chega com a árvore já fora
  // do ar e o erro vaza para o arquivo de teste seguinte.
  await act(async () => {});
  cleanup();
  vi.unstubAllGlobals();
});

describe("nenhum texto corrido sai em caixa alta (RN-76, D-19)", () => {
  it("na fila, com os três estados e o menu de ações aberto", async () => {
    await montarFila();
    fireEvent.click(
      within(linhaDe("2026-0002")).getByRole("button", { name: /mais ações/i })
    );

    // A varredura precisa ter achado o que varrer: sem esta linha, um seletor
    // que parasse de casar deixaria a lista vazia e o teste passaria à toa.
    expect(textosEmCaixaAlta().length).toBeGreaterThanOrEqual(8);
    expect(frasesEmCaixaAlta()).toEqual([]);
  });

  it("no Dossiê, com resposta da área e desfecho preenchidos", async () => {
    await montarDossie();

    expect(textosEmCaixaAlta().length).toBeGreaterThanOrEqual(8);
    expect(frasesEmCaixaAlta()).toEqual([]);
  });

  it("nos modais de validar, encerrar e registrar", async () => {
    await montarFila();
    fireEvent.click(within(linhaDe("2026-0001")).getByRole("button", { name: /validar/i }));
    await act(async () => {});
    expect(frasesEmCaixaAlta()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(within(linhaDe("2026-0003")).getByRole("button", { name: /encerrar/i }));
    expect(frasesEmCaixaAlta()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(screen.getByRole("button", { name: /nova manifestação/i }));
    expect(frasesEmCaixaAlta()).toEqual([]);
  });

  it("o resumo, o relato e o desfecho ficam em caixa mista", async () => {
    // O contrapeso da varredura: ela só reprova o que está marcado, e um dia
    // em que ninguém marcasse nada ela passaria calada. Estes três são o texto
    // que a issue existe para proteger.
    await montarDossie();

    for (const texto of [RESUMO, RELATO, DOSSIE.desfecho_descricao, DOSSIE.resposta_da_area]) {
      expect(saiEmCaixaAlta(screen.getByText(texto))).toBe(false);
    }
  });

  it("o crédito de quem respondeu não entra no título da seção", async () => {
    // O caso que abriu a issue: o nome e a data moravam dentro do `h3` em
    // maiúscula, e o Dossiê gritava "RESPOSTA DA ÁREA (CARLOS EDUARDO DE
    // ALMEIDA, 18/08/2026 13:00)".
    await montarDossie();

    const titulo = screen.getByText("Resposta da área");
    expect(carregaCaixaAlta(titulo)).toBe(true);
    // O crédito continua na mesma linha, ao lado do rótulo: o que mudou foi só
    // a caixa dele. Por isso a conferência é do que o título grita, e não do
    // `textContent`, que segue trazendo os dois.
    expect(textoGritado(titulo).trim()).toBe("Resposta da área");
    expect(titulo.textContent).toContain("Carlos Eduardo de Almeida");
    expect(saiEmCaixaAlta(screen.getByText(/Carlos Eduardo de Almeida/))).toBe(false);
  });
});

describe("os rótulos curtos vão para caixa alta (RN-76)", () => {
  it("a ação primária de cada estado da fila", async () => {
    await montarFila();

    for (const [protocolo, nome] of [
      ["2026-0001", /validar e acionar/i],
      ["2026-0002", /cobrar/i],
      ["2026-0003", /encerrar/i],
    ] as const) {
      const botao = within(linhaDe(protocolo)).getByRole("button", { name: nome });
      expect(saiEmCaixaAlta(botao)).toBe(true);
    }
  });

  it("as ações secundárias do menu da linha", async () => {
    await montarFila();
    const linha = linhaDe("2026-0002");
    fireEvent.click(within(linha).getByRole("button", { name: /mais ações/i }));

    const abrir = within(linha).getByRole("link", { name: /abrir manifestação/i });
    expect(saiEmCaixaAlta(abrir)).toBe(true);
  });

  it("a pílula de gravidade, que é rótulo de escala e não texto", async () => {
    await montarFila();

    expect(saiEmCaixaAlta(within(linhaDe("2026-0002")).getByText("Alto"))).toBe(true);
  });

  it("o botão de registrar manifestação do topo", async () => {
    await montarFila();

    expect(saiEmCaixaAlta(screen.getByRole("button", { name: /nova manifestação/i }))).toBe(true);
  });

  it("os botões do Dossiê", async () => {
    sessao.perfilOuvidoria = "ouvidor";
    await montarDossie();

    expect(saiEmCaixaAlta(screen.getByRole("button", { name: /salvar classificação/i }))).toBe(
      true
    );
  });
});

describe("a barra de atalhos continua em caixa mista (RN-77, D-16)", () => {
  it("nenhuma pílula de navegação vai para caixa alta", async () => {
    // Porta para outra tela não é dado nem ação: no resto da casa nenhuma
    // navegação é caixa alta, e esta barra ainda é a única linha do módulo sem
    // folga de largura, onde os 10% que a maiúscula alarga custam caro.
    sessao.perfilOuvidoria = "diretoria_executiva";
    await montarFila();

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    for (const pilula of within(nav).getAllByRole("link")) {
      expect(saiEmCaixaAlta(pilula)).toBe(false);
    }
  });
});
