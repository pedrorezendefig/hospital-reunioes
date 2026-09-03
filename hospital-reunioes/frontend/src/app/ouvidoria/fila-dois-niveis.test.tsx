/**
 * @vitest-environment jsdom
 */

/**
 * A fila em linha de dois níveis (issue #495, PRD #471, RN-70 a RN-74).
 *
 * A tela era uma tabela de sete colunas com rolagem horizontal: o resumo
 * quebrava linha num corredor estreito e a ação principal ficava fora da área
 * visível. Esta suíte trava o que substituiu a tabela, e o que ela trava é
 * comportamento, não pixel: qual botão cada estado oferece, o que a cobrança
 * dispara, e que o resumo é cortado em vez de empurrar a linha para fora da
 * tela.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

const RESUMO_LONGO =
  "Paciente relata espera de mais de três horas na recepção do ambulatório, sem nenhuma " +
  "informação sobre a fila e sem lugar para sentar durante todo o período de espera.";

const BASE = {
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-12-31",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: RESUMO_LONGO,
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

const TITULAR = {
  id: "r1",
  setor: "Recepção",
  papel: "titular",
  nome: "Carlos Titular",
  email: "carlos@hsm.br",
  vigencia_inicio: "2020-01-01",
  vigencia_fim: null,
};

/** O cadastro completo, com as armadilhas da cadeia de acionamento dentro. */
const CADASTRO = [
  // Substituto do mesmo setor: entra na cobrança de prazo rompido, nunca no
  // acionamento, e por isso não pode ser o nome da linha.
  { ...TITULAR, id: "r2", papel: "substituto", nome: "Sara Substituta" },
  // Titular que saiu: a vigência acabou, e ele não responde mais.
  { ...TITULAR, id: "r3", nome: "Bruno Vencido", vigencia_fim: "2020-12-31" },
  // Titular de OUTRO setor.
  { ...TITULAR, id: "r4", setor: "Farmácia", nome: "Fabio da Farmácia" },
  TITULAR,
];

/** As chamadas que a tela fez, para as asserções de cobrança. */
let chamadas: { url: string; metodo: string }[] = [];

function montar(
  protocolos: ReturnType<typeof caso>[],
  opcoes: {
    responsaveis?: unknown[];
    cadastroFora?: boolean;
    entregue?: boolean;
    // A cobrança que o SERVIDOR recusou (issue #536): o status e a frase que
    // ele manda, porque é ela que o ouvidor lê na linha.
    cobrancaRecusada?: { status: number; detail?: string };
    // Quem o servidor escolheu. Nunca o nome que a tela desenhou: a promessa é
    // sobre o email que saiu.
    destinatario?: string;
  } = {}
) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const endereco = String(url);
      chamadas.push({ url: endereco, metodo: init?.method ?? "GET" });
      if (endereco.includes("/cobrar-setor")) {
        if (opcoes.cobrancaRecusada) {
          return {
            ok: false,
            status: opcoes.cobrancaRecusada.status,
            json: async () => ({ detail: opcoes.cobrancaRecusada!.detail }),
          } as Response;
        }
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: "cobranca-1",
            destinatario: opcoes.destinatario ?? TITULAR.nome,
            entregue: opcoes.entregue ?? true,
          }),
        } as Response;
      }
      if (endereco.includes("/responsaveis")) {
        if (opcoes.cadastroFora) {
          return { ok: false, status: 503, json: async () => ({}) } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ responsaveis: opcoes.responsaveis ?? CADASTRO }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ protocolos }) } as Response;
    })
  );
  render(<OuvidoriaPage />);
}

async function linhaDe(protocolo: string): Promise<HTMLElement> {
  await screen.findByText(protocolo);
  // Um caso respondido com novidade aparece DUAS vezes na tela, por desenho da
  // issue #486 (bloco de destaque e grupo de estado). Pegar o primeiro nó em
  // silêncio faria o teste olhar sempre a cópia do bloco: melhor falhar e pedir
  // desambiguação.
  const linhas = document.querySelectorAll<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (linhas.length === 0) throw new Error(`sem linha para o protocolo ${protocolo}`);
  if (linhas.length > 1) {
    throw new Error(`${linhas.length} linhas para o protocolo ${protocolo}: escolha qual`);
  }
  return linhas[0];
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  sessao.perfilOuvidoria = "ouvidor";
  vi.unstubAllGlobals();
});

describe("a linha de dois níveis substitui a tabela (RN-72, RN-73)", () => {
  it("a fila não é mais uma tabela", async () => {
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    expect(screen.queryByRole("table")).toBeNull();
  });

  it("nada rola para o lado: nenhum contêiner da fila esconde conteúdo no eixo x", async () => {
    // A tabela antiga vivia dentro de um `overflow-x-auto`, e era ele que
    // levava a ação principal para fora da área visível (D-06). Em jsdom não
    // há layout para medir, então o que se trava é a causa: nenhum ancestral
    // da linha pode voltar a oferecer o corredor lateral.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    for (let no = linha.parentElement; no && no !== document.body; no = no.parentElement) {
      expect(no.className).not.toContain("overflow-x-auto");
      expect(no.className).not.toContain("overflow-x-scroll");
    }
  });

  it("o resumo é cortado em uma linha, com o texto inteiro no tooltip", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    const resumo = within(linha).getByText(RESUMO_LONGO);
    expect(resumo.className).toContain("truncate");
    expect(resumo.getAttribute("title")).toBe(RESUMO_LONGO);
  });

  it("o nível 2 diz o setor, quem responde por ele e o prazo", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByText("Recepção")).toBeTruthy();
    await waitFor(() => expect(within(linha).getByText("Carlos Titular")).toBeTruthy());
  });

  it("setor sem responsável vigente é dito na linha, e não deixado em branco", async () => {
    montar([caso(7, "aguardando_area")], { responsaveis: [] });
    const linha = await linhaDe("2026-0007");

    expect(await within(linha).findByText("Sem responsável")).toBeTruthy();
  });

  it("o nome que sai é o do titular vigente do setor, e não outro do cadastro", async () => {
    // A cadeia é a mesma do acionamento no servidor: titular vigente, senão o
    // gestor. Substituto, titular vencido e gente de outro setor ficam de fora.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(await within(linha).findByText("Carlos Titular")).toBeTruthy();
    expect(within(linha).queryByText("Sara Substituta")).toBeNull();
    expect(within(linha).queryByText("Bruno Vencido")).toBeNull();
    expect(within(linha).queryByText("Fabio da Farmácia")).toBeNull();
  });

  it("sem titular vigente, quem aparece é o gestor: é para ele que a demanda sobe", async () => {
    montar([caso(7, "aguardando_area")], {
      responsaveis: [
        { ...TITULAR, id: "r9", papel: "gestor", nome: "Regina Gestora" },
        { ...TITULAR, id: "r3", nome: "Bruno Vencido", vigencia_fim: "2020-12-31" },
      ],
    });
    const linha = await linhaDe("2026-0007");

    expect(await within(linha).findByText("Regina Gestora")).toBeTruthy();
  });

  it("quem não lê o cadastro não vê afirmação nenhuma sobre o responsável", async () => {
    // O índice é da equipe de Reuniões inteira, e só a Ouvidoria lê o cadastro
    // de responsáveis. Sem esta guarda, TODA linha da fila diria "Sem
    // responsável" para a secretária, e o aviso de setor órfão, que existe para
    // a Diretoria enxergar, deixaria de significar qualquer coisa.
    sessao.perfilOuvidoria = null;
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByText("Recepção")).toBeTruthy();
    expect(within(linha).queryByText("Sem responsável")).toBeNull();
    expect(within(linha).queryByText("Carlos Titular")).toBeNull();
  });

  it("cadastro que não pôde ser lido vira aviso na tela, e não silêncio", async () => {
    // Mesma régua da issue #449: leitura que falhou é dita, nunca virada em
    // afirmação sobre o dado.
    montar([caso(7, "aguardando_area")], { cadastroFora: true });
    const linha = await linhaDe("2026-0007");

    expect(await screen.findByText(/cadastro de responsáveis por setor não pôde ser lido/i)).toBeTruthy();
    expect(within(linha).queryByText("Sem responsável")).toBeNull();
  });

  it("a gravidade aparece na pílula, e é a única cor de urgência da linha", async () => {
    montar([caso(7, "aguardando_area", { gravidade: "critico" })]);
    const linha = await linhaDe("2026-0007");

    const pilula = within(linha).getByText("Crítico");
    expect(pilula.className).toContain("red");
    // O nome do estado é da faixa do grupo (RN-71), nunca da linha.
    expect(within(linha).queryByText("Aguardando área")).toBeNull();
  });
});

describe("a ação primária de cada estado, sempre visível (RN-74, D-06)", () => {
  it("caso em classificação oferece validar e acionar", async () => {
    montar([caso(7, "em_classificacao")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Validar e acionar" })).toBeTruthy();
  });

  it("caso com a área oferece cobrar", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Cobrar" })).toBeTruthy();
  });

  it("caso respondido oferece encerrar", async () => {
    montar([caso(7, "respondido")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();
  });

  it("caso encerrado oferece só o caminho do Dossiê, sem menu nenhum", async () => {
    montar([caso(7, "encerrado")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).getByRole("link", { name: "Abrir manifestação" })).toBeTruthy();
    expect(within(linha).queryByRole("button", { name: /Mais ações/ })).toBeNull();
  });

  it("o que sobra fica no menu, e não na linha", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).queryByRole("button", { name: "Encerrar" })).toBeNull();
    expect(within(linha).queryByRole("link", { name: "Abrir manifestação" })).toBeNull();

    fireEvent.click(within(linha).getByRole("button", { name: /Mais ações/ }));

    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();
    expect(within(linha).getByRole("link", { name: "Abrir manifestação" })).toBeTruthy();
  });

  it("o menu fecha no Escape", async () => {
    // O fecha-ao-sair é do hook `useFecharFlutuante`, compartilhado com o menu
    // de atalhos do topo desde a issue #496. Sem esta asserção aqui, quem
    // mexer no hook amanhã só teria aviso do OUTRO consumidor, e esta linha
    // ficaria com um menu preso aberto sobre a fila inteira.
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");
    fireEvent.click(within(linha).getByRole("button", { name: /Mais ações/ }));
    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(within(linha).queryByRole("button", { name: "Encerrar" })).toBeNull();
  });

  it("o menu fecha ao clicar fora dele", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");
    fireEvent.click(within(linha).getByRole("button", { name: /Mais ações/ }));
    expect(within(linha).getByRole("button", { name: "Encerrar" })).toBeTruthy();

    fireEvent.mouseDown(document.body);

    expect(within(linha).queryByRole("button", { name: "Encerrar" })).toBeNull();
  });

  it("quem está fora da Ouvidoria vê a linha e nenhuma ação", async () => {
    sessao.perfilOuvidoria = null;
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    expect(within(linha).queryByRole("button")).toBeNull();
    expect(within(linha).queryByRole("link")).toBeNull();
  });
});

describe("cobrar é acordar o setor de novo (RN-74, issue #536)", () => {
  it("chama a rota que decide o destinatário no servidor, e só ela", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    await waitFor(() => expect(chamadas.some((c) => c.metodo === "POST")).toBe(true));
    // Uma chamada, e sem passar pela lista de notificações do caso: a tela não
    // precisa mais ler os destinatários de todos os emails do caso para achar
    // o do acionamento, e não é ela que escolhe quem recebe.
    expect(chamadas.filter((c) => c.metodo === "POST").map((c) => c.url)).toEqual([
      "/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor",
    ]);
    expect(chamadas.some((c) => c.url.includes("/notificacoes"))).toBe(false);
    expect(await within(linha).findByText("Acionamento reenviado a Carlos Titular")).toBeTruthy();
  });

  it("o setor que trocou de titular continua cobrável, pelo mesmo botão", async () => {
    // O caso foi acionado quando Carlos era titular. Ele saiu, Regina entrou.
    // Até a #536 a tela travava a cobrança aqui, e o ouvidor tinha de cobrar
    // caso por caso pelo Dossiê. Agora o servidor manda para quem responde
    // hoje, e a linha promete pelo nome que ELE devolveu.
    montar([caso(7, "aguardando_area")], {
      responsaveis: [
        { ...TITULAR, id: "r3", nome: "Carlos Titular", vigencia_fim: "2020-12-31" },
        { ...TITULAR, id: "r5", nome: "Regina Nova", email: "regina@hsm.br" },
      ],
      destinatario: "Regina Nova",
    });
    const linha = await linhaDe("2026-0007");
    await within(linha).findByText("Regina Nova");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(await within(linha).findByText("Acionamento reenviado a Regina Nova")).toBeTruthy();
    expect(within(linha).queryByText(/Carlos Titular/)).toBeNull();
  });

  it("a recusa do servidor chega ao ouvidor com a frase do servidor", async () => {
    // As duas faltas que o servidor distingue mandam a lugares diferentes:
    // setor sem ninguém vigente pede cadastro novo, responsável sem email pede
    // o cadastro completo de quem já está lá. A tela não reescreve nenhuma.
    montar([caso(7, "aguardando_area")], {
      cobrancaRecusada: {
        status: 409,
        detail: "Carlos Titular está sem email no cadastro de responsáveis. Complete o cadastro.",
      },
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(await within(linha).findByText(/sem email no cadastro de responsáveis/i)).toBeTruthy();
  });

  it("erro sem frase curada não vira aviso ao ouvidor", async () => {
    // Um 500 do servidor traz "Internal Server Error" no `detail`, e isso não
    // pode aterrar na linha da fila como explicação de nada.
    montar([caso(7, "aguardando_area")], {
      cobrancaRecusada: { status: 500, detail: "Internal Server Error" },
    });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(await within(linha).findByText(/Não foi possível cobrar agora/i)).toBeTruthy();
    expect(within(linha).queryByText(/Internal Server Error/)).toBeNull();
  });

  it("provedor que recusou o email não vira cobrança entregue na tela", async () => {
    montar([caso(7, "aguardando_area")], { entregue: false });
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(await within(linha).findByText(/ficou na fila/)).toBeTruthy();
    expect(within(linha).queryByText(/^Acionamento reenviado a Carlos Titular$/)).toBeNull();
  });

  it("cobrança feita trava o botão, para o segundo clique não emitir outro token", async () => {
    montar([caso(7, "aguardando_area")]);
    const linha = await linhaDe("2026-0007");

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));
    await within(linha).findByText("Acionamento reenviado a Carlos Titular");

    expect(within(linha).getByRole("button", { name: "Cobrar" })).toHaveProperty("disabled", true);
  });

  it("cadastro que a tela não leu não impede mais a cobrança", async () => {
    // A leitura do cadastro serve para a linha escrever o nome do responsável,
    // e não para decidir a cobrança. Com ela fora do ar a linha cala o nome, e
    // o botão continua funcionando: quem confere é o servidor.
    montar([caso(7, "aguardando_area")], { cadastroFora: true });
    const linha = await linhaDe("2026-0007");
    await screen.findByText(/cadastro de responsáveis por setor não pôde ser lido/i);

    fireEvent.click(within(linha).getByRole("button", { name: "Cobrar" }));

    expect(await within(linha).findByText("Acionamento reenviado a Carlos Titular")).toBeTruthy();
  });
});

describe("a faixa de cada grupo (RN-70, RN-71)", () => {
  it("o cabeçalho do grupo é uma faixa na cor do estado, com o contador", async () => {
    montar([caso(7, "aguardando_area"), caso(8, "aguardando_area")]);
    await linhaDe("2026-0007");

    const faixa = screen.getByText("Aguardando área").closest("header");
    expect(faixa).not.toBeNull();
    expect(faixa!.className).toContain("bg-amber-100");
    expect(within(faixa!).getByText("2 manifestações")).toBeTruthy();
  });

  it("o rótulo do estado sobe em caixa alta pelo estilo, e não pelo texto", async () => {
    // Caixa alta escrita no texto é o que o leitor de tela soletra letra a
    // letra, e o que a issue #489 teria de desfazer depois.
    montar([caso(7, "aguardando_area")]);
    await linhaDe("2026-0007");

    const rotulo = screen.getByText("Aguardando área");
    expect(rotulo.className).toContain("uppercase");
  });
});
