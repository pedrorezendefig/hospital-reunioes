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
import { BREAKPOINT_DA_BARRA, CSS_DO_ORCAMENTO } from "@/lib/ouvidoria/atalhos";
import { ehRotuloCurto } from "@/lib/ouvidoria/tipografia";

import PortalDoSetorPage from "../ouvidoria-setor/[token]/page";
import NotaExternaPage from "./nota-externa/page";
import OuvidoriaPage from "./page";
import PainelEmTempoRealPage from "./painel/page";
import PontosDeEscutaPage from "./pontos/page";
import PrazosDaOuvidoriaPage from "./prazos/page";
import ResponsaveisDaOuvidoriaPage from "./responsaveis/page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: "ouvidor" as string | null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

// O portal do setor lê o token da rota. Nenhuma outra tela varrida aqui usa
// `next/navigation`, então o dublê não muda o comportamento das demais.
vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "token-de-teste" }),
}));

// O painel se recarrega por relógio. O dublê guarda a função de carga para o
// teste dispará-la uma vez: o que se varre é a tela desenhada, não o intervalo.
const painel = vi.hoisted(() => ({ carga: null as null | (() => Promise<void> | void) }));

vi.mock("@/hooks/usePolling", () => ({
  usePolling: (callback: () => Promise<void> | void) => {
    painel.carga = callback;
  },
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
    // Cada modal traz o piso de contagem junto, e não só a lista vazia de
    // frases: lista vazia é o que se vê tanto quando está tudo certo quanto
    // quando o modal não renderizou nada. O piso é do modal ABERTO, medido
    // acima do que a fila atrás dele já grita.
    await montarFila();
    const naFila = textosEmCaixaAlta().length;

    fireEvent.click(within(linhaDe("2026-0001")).getByRole("button", { name: /validar/i }));
    await act(async () => {});
    expect(textosEmCaixaAlta().length).toBeGreaterThan(naFila + 5);
    expect(frasesEmCaixaAlta()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(within(linhaDe("2026-0003")).getByRole("button", { name: /encerrar/i }));
    expect(textosEmCaixaAlta().length).toBeGreaterThan(naFila + 2);
    expect(frasesEmCaixaAlta()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(screen.getByRole("button", { name: /nova manifestação/i }));
    expect(textosEmCaixaAlta().length).toBeGreaterThan(naFila + 5);
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
  it("o CSS da barra mostra a barra no mesmo ponto que o orçamento supõe", async () => {
    // A conta de `larguraDaBarra` vale para UMA largura de tela, e ela só
    // significa alguma coisa se for a mesma em que o CSS revela a barra. Foi
    // essa divergência que deixou o orçamento afirmar que cabia, medindo uma
    // tela onde a barra nem aparecia.
    sessao.perfilOuvidoria = "diretoria_executiva";
    await montarFila();

    const nav = screen.getByRole("navigation", { name: /atalhos da ouvidoria/i });
    const gatilho = screen.getByRole("button", { name: "Atalhos" });
    expect(nav.className).toContain(`${BREAKPOINT_DA_BARRA}:flex`);
    expect(gatilho.parentElement!.className).toContain(`${BREAKPOINT_DA_BARRA}:hidden`);
  });

  it("o contêiner da fila tem o padding que o orçamento desconta", async () => {
    // A terceira parcela da conta, junto com o sidebar e o padding do `main`
    // (esses dois travados em `Sidebar.test` e `AppShell.test`). As três eram
    // números copiados à mão, e foi por um deles estar faltando que o
    // orçamento afirmou que a barra cabia.
    await montarFila();

    const raiz = screen.getByRole("heading", { name: "Ouvidoria" }).closest(".max-w-6xl");
    expect(raiz).not.toBeNull();
    expect(raiz!.className.split(/\s+/)).toContain(CSS_DO_ORCAMENTO.paddingDaFila);
  });

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

/* ------------------------------------------------------------------ */
/* As outras seis telas do módulo                                      */
/*                                                                     */
/* A varredura nasceu cobrindo a fila, o Dossiê e os modais, e essas    */
/* seis ficaram de fora enquanto este mesmo diff mexia nas seis. Tela   */
/* fora da varredura é tela sem rede: uma frase inteira dentro de uma   */
/* pílula em maiúscula do painel passava com a suíte toda verde.        */
/* ------------------------------------------------------------------ */

function json(corpo: unknown) {
  return { ok: true, status: 200, json: async () => corpo } as Response;
}

/** Responde cada porta pelo endereço, e estoura no endereço que ninguém previu. */
function porPorta(rotas: [string, unknown][]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const endereco = String(url);
      const rota = rotas.find(([pedaco]) => endereco.includes(pedaco));
      if (!rota) throw new Error(`porta não prevista no teste: ${endereco}`);
      return json(rota[1]);
    })
  );
}

const CASO_DO_PAINEL = {
  id: "id-1",
  protocolo: "2026-0031",
  status: "aguardando_area",
  setor: "Enfermagem",
  resumo: RESUMO,
  gravidade: "medio",
  prazo_area_em: "2026-01-05T20:00:00+00:00",
  prazo_resposta: "2026-01-05",
  prazo_estourado: true,
  rotulo_prazo: "vencido há 2 dias úteis",
  sigilo_reforcado: true,
};

const CASO_DO_SETOR = {
  protocolo: "2026-0007",
  setor: "Recepção",
  categoria: "Tempo de espera",
  gravidade: "alto",
  extrato: "Confirmar a escala da recepção no turno da manhã.",
  blocos: [
    { chave: "resumo", rotulo: "RESUMO", texto: RESUMO },
    { chave: "relato_integral", rotulo: "RELATO INTEGRAL", texto: RELATO },
  ],
  aviso: null,
  identificacao: "Joana Aparecida da Silva",
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
};

const RESPONSAVEL = {
  id: "r1",
  setor: "Recepção",
  papel: "titular",
  nome: "Carlos Eduardo de Almeida",
  email: "carlos@hsm",
  vigencia_inicio: "2020-01-01",
  vigencia_fim: null,
};

const PONTO = {
  id: "pt1",
  codigo: "AB12",
  setor: "Recepção",
  ponto: "Balcão da recepção",
  ativo: true,
  criado_em: "2026-08-01T12:00:00+00:00",
  qr_data_uri: "data:image/png;base64,iVBORw0KGgo=",
};

/**
 * Cada tela com a porta que ela abre e a âncora que ela grita. Todas montadas
 * como Diretoria Executiva, que é o perfil que enxerga a maior superfície do
 * módulo e portanto o que dá mais texto para a varredura passar.
 */
const TELAS: {
  nome: string;
  montar: () => Promise<void>;
  /** Um rótulo que a tela obrigatoriamente grita, para a varredura não passar no vazio. */
  ancora: () => HTMLElement;
}[] = [
  {
    nome: "o painel em tempo real",
    montar: async () => {
      porPorta([
        ["/metricas", { degradado: [], pendencias_por_area: [] }],
        ["/protocolos", { protocolos: [CASO_DO_PAINEL] }],
      ]);
      render(<PainelEmTempoRealPage />);
      await act(async () => {
        await painel.carga?.();
      });
      await screen.findByText("2026-0031");
    },
    ancora: () => screen.getByText("Sigiloso"),
  },
  {
    nome: "o portal do setor",
    montar: async () => {
      porPorta([["/api/ouvidoria-setor/", CASO_DO_SETOR]]);
      render(<PortalDoSetorPage />);
      await screen.findByText("O que foi feito");
    },
    ancora: () => screen.getByRole("button", { name: /responder à ouvidoria/i }),
  },
  {
    nome: "a nota externa",
    montar: async () => {
      porPorta([
        [
          "/api/ouvidoria/nota-externa",
          {
            notas: [
              {
                fonte: "google",
                nota: 4.2,
                escala: 5,
                registrada_em: "2026-08-01",
                registrada_por_nome: "Marta Ouvidora",
              },
            ],
          },
        ],
      ]);
      render(<NotaExternaPage />);
      await screen.findByText("Google");
    },
    ancora: () => screen.getAllByRole("button", { name: /registrar/i })[0],
  },
  {
    nome: "os pontos de escuta",
    montar: async () => {
      porPorta([
        ["/api/ouvidoria/pontos", { pontos: [PONTO] }],
        ["/api/participantes/setores", ["Recepção", "Enfermagem"]],
      ]);
      render(<PontosDeEscutaPage />);
      await screen.findByText("Balcão da recepção");
    },
    ancora: () => screen.getByRole("button", { name: /cartaz a5/i }),
  },
  {
    nome: "a tabela de prazos",
    montar: async () => {
      porPorta([
        [
          "/api/ouvidoria/prazos",
          {
            prazos: [
              { gravidade: "alto", marco: "area_resposta", valor: 2, unidade: "dias_uteis" },
              {
                gravidade: "alto",
                marco: "acusar_recebimento",
                valor: 24,
                unidade: "horas_corridas",
              },
            ],
          },
        ],
        [
          "/api/ouvidoria/feriados",
          { feriados: [{ data: "2026-09-07", nome: "Independência", abrangencia: "nacional" }] },
        ],
      ]);
      render(<PrazosDaOuvidoriaPage />);
      await screen.findByText("Independência");
    },
    ancora: () => screen.getByRole("button", { name: /remover feriado/i }),
  },
  {
    nome: "os responsáveis por setor",
    montar: async () => {
      porPorta([
        ["/api/ouvidoria/responsaveis", { responsaveis: [RESPONSAVEL] }],
        ["/api/participantes/setores", ["Recepção", "Enfermagem"]],
      ]);
      render(<ResponsaveisDaOuvidoriaPage />);
      await screen.findByText("Carlos Eduardo de Almeida");
    },
    ancora: () => screen.getByRole("button", { name: /^cadastrar$/i }),
  },
];

describe("nenhum texto corrido sai em caixa alta nas outras seis telas (RN-76, D-19)", () => {
  for (const tela of TELAS) {
    it(`em ${tela.nome}`, async () => {
      sessao.perfilOuvidoria = "diretoria_executiva";
      await tela.montar();

      // A âncora é o piso: um rótulo que a tela obrigatoriamente grita. Sem
      // ela, uma tela que não renderizasse nada devolveria lista vazia de
      // frases e a varredura passaria calada, que é o modo de falhar de toda
      // asserção negativa.
      expect(saiEmCaixaAlta(tela.ancora())).toBe(true);
      expect(frasesEmCaixaAlta()).toEqual([]);
    });
  }
});
