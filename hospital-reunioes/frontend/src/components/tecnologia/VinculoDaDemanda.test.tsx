/**
 * @vitest-environment jsdom
 */

/**
 * O Vínculo na tela (issue #674, PRD #673, ADR 0054).
 *
 * Duas perguntas, e cada uma no lugar onde ela é decidida de verdade:
 *
 * 1. **O selo**, pelo CARD do Quadro, e não pelo `SeloDeEtapa` isolado. O
 *    critério é "o card não tem selo quando não há Vínculo": um teste que
 *    montasse só o componente provaria que ele sabe se calar, e não que o card
 *    o usa.
 * 2. **Os controles**, pelo MODAL. Eles aparecem, somem e desabilitam a partir
 *    do "eu" que o backend responde, e é no modal que essa decisão vira tela.
 *
 * Nenhum destes testes fala com rede: o `fetch` é dublado, e o que se cobra é
 * o que o componente MANDA, não o que o servidor faria com isso (quem prova o
 * servidor é o `test_tecnologia_vinculo.py`).
 */

import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DemandaModal } from "./DemandaModal";
import { QuadroDemandas } from "./QuadroDemandas";
import { AJUDA_DE_LEVAR, AJUDA_DO_CAMPO, AVISO_SEM_INTEGRACAO, LEVAR_PARA_DESENVOLVIMENTO } from "./VinculoDaDemanda";
import {
  Demanda,
  ETAPA_ROTULO,
  ETAPAS,
  EU_DESCONHECIDO,
  EtapaDemanda,
  EuNaAba,
  FiltrosDoQuadro,
  SEM_FILTRO,
  temSelo,
  textoDoSelo,
} from "./demandas";

const PRODUTOS = [{ id: "prod-1", nome: "Ana", ativo: true }];
const PESSOAS = [{ id: "P1", nome_completo: "Pedro Vitta" }];

const DA_VITTA: EuNaAba = {
  id: "P1",
  nome_completo: "Pedro Vitta",
  tem_github_login: true,
  integracao_configurada: true,
};

const DA_VITTA_SEM_INTEGRACAO: EuNaAba = { ...DA_VITTA, integracao_configurada: false };

const DIRETOR: EuNaAba = {
  id: "P2",
  nome_completo: "Diretor do Hospital",
  tem_github_login: false,
  integracao_configurada: true,
};

function demanda(extra: Partial<Demanda> = {}): Demanda {
  return {
    id: "d-1",
    titulo: "Levar o selo ao card",
    descricao: null,
    tipo: "novo",
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "nova",
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P1",
    prioridade: "normal",
    prazo: null,
    criado_em: new Date().toISOString(),
    concluida_em: null,
    cancelada_em: null,
    ...extra,
  };
}

/** Uma Demanda vinculada, como o backend a devolve a quem é da Vitta. */
const VINCULADA = demanda({
  etapa: "em_desenvolvimento",
  partes_entregues: 3,
  partes_total: 7,
  github_sincronizado_em: "2026-09-10T12:00:00Z",
  vinculo: { numero: 673, url: "https://github.com/pedrorezendefig/hospital-reunioes/issues/673" },
});

type Chamada = { url: string; metodo: string; corpo: unknown };
let chamadas: Chamada[] = [];

function dublarFetch(opcoes: { recusa?: { status: number; detail: string }; demandas?: Demanda[] } = {}) {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (metodo !== "GET" && opcoes.recusa) {
        return {
          ok: false,
          status: opcoes.recusa.status,
          json: async () => ({ detail: opcoes.recusa!.detail }),
        } as unknown as Response;
      }
      if (url.includes("/conversa")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }
      if (metodo !== "GET") {
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => opcoes.demandas ?? [] } as unknown as Response;
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function montarModal(d: Demanda, eu: EuNaAba, opcoes: Parameters<typeof dublarFetch>[0] = {}) {
  dublarFetch(opcoes);
  return render(
    <DemandaModal
      demanda={d}
      produtos={PRODUTOS}
      pessoas={PESSOAS}
      token="token-de-teste"
      eu={eu}
      onFechar={() => {}}
      onMudou={() => {}}
    />,
  );
}

function montarQuadro(demandas: Demanda[]) {
  dublarFetch({ demandas });

  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <QuadroDemandas
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
        eu={EU_DESCONHECIDO}
      />
    );
  }

  return render(<Anfitriao />);
}

// ─── 1. Os rótulos ───────────────────────────────────────────────────────────

describe("Os seis textos da Etapa", () => {
  it("cada Etapa tem o seu rótulo em pt-BR", () => {
    expect(ETAPAS).toHaveLength(6);
    expect(ETAPAS.map((e) => ETAPA_ROTULO[e])).toEqual([
      "Registrada",
      "Em análise",
      "Planejada",
      "Em desenvolvimento",
      "Entregue",
      "Não será feita",
    ]);
  });

  it("o aviso não expõe o nome das variáveis de ambiente", () => {
    // O gate `if (!eu.tem_github_login) return null` é de RUNTIME: esta string
    // vive no bundle JS, servido a qualquer um que abra a página, com sessão ou
    // sem. O backend já acertou nisso (o motivo dele fala de configuração sem
    // citar variável), e a tela segue o mesmo critério.
    expect(AVISO_SEM_INTEGRACAO).not.toContain("GITHUB_INTEGRACAO");
    // E o par de presença: o aviso continua dizendo a CAUSA, e não um
    // "indisponível" seco que mandaria a pessoa tentar de novo para sempre.
    expect(AVISO_SEM_INTEGRACAO).toContain("não está configurada");
  });

  it("nenhum texto do Vínculo tem travessão", () => {
    // Regra da casa: travessão e meia-risca são marca de texto gerado por IA e
    // não entram em nada que o usuário vê. Estes são lidos pelo diretor.
    const textos = [
      ...Object.values(ETAPA_ROTULO),
      AVISO_SEM_INTEGRACAO,
      AJUDA_DO_CAMPO,
      AJUDA_DE_LEVAR,
      LEVAR_PARA_DESENVOLVIMENTO,
    ];
    for (const texto of textos) {
      // Os dois vem por `fromCharCode` porque o proprio lint da casa proibe o
      // caractere literal em qualquer arquivo, inclusive no teste que o caca.
      expect(texto).not.toContain(String.fromCharCode(0x2014));
      expect(texto).not.toContain(String.fromCharCode(0x2013));
    }
  });
});

describe("O que o selo diz", () => {
  it("sem Vínculo não há selo", () => {
    expect(temSelo(demanda())).toBe(false);
    expect(temSelo(demanda({ etapa: "registrada" }))).toBe(false);
  });

  it("Etapa que o backend não mandou também não vira selo", () => {
    // Backend uma versão atrás: inventar um selo seria pior do que não mostrar
    // nada.
    expect(temSelo(demanda({ etapa: undefined }))).toBe(false);
    expect(temSelo(demanda({ etapa: "inventada" as EtapaDemanda }))).toBe(false);
  });

  it("com Vínculo há selo", () => {
    expect(temSelo(VINCULADA)).toBe(true);
  });

  it("o selo mostra a fração quando há partes", () => {
    expect(textoDoSelo(VINCULADA)).toBe("Em desenvolvimento · 3 de 7 partes");
  });

  it("sem partes o selo é só a Etapa", () => {
    expect(textoDoSelo(demanda({ etapa: "entregue" }))).toBe("Entregue");
  });

  it("total zero não vira fração", () => {
    // "0 de 0 partes" é uma barra vazia onde não existe barra.
    expect(textoDoSelo(demanda({ etapa: "entregue", partes_entregues: 0, partes_total: 0 }))).toBe("Entregue");
  });
});

// ─── 2. O selo no card ───────────────────────────────────────────────────────

describe("O selo no card do Quadro", () => {
  it("Demanda sem Vínculo não tem selo", async () => {
    montarQuadro([demanda()]);

    expect(await screen.findByText("Levar o selo ao card")).toBeTruthy();
    for (const rotulo of Object.values(ETAPA_ROTULO)) {
      expect(screen.queryByText(rotulo)).toBeNull();
    }
  });

  it("Demanda vinculada mostra a Etapa e as partes", async () => {
    montarQuadro([VINCULADA]);

    expect(await screen.findByText("Em desenvolvimento · 3 de 7 partes")).toBeTruthy();
  });

  it("o selo continua no card de quem não tem login no GitHub", async () => {
    // O diretor não recebe `vinculo` (o backend omite o objeto), e mesmo assim
    // vê o selo: é a Etapa que fala com ele, e ela vem para todo mundo.
    montarQuadro([{ ...VINCULADA, vinculo: null }]);

    expect(await screen.findByText("Em desenvolvimento · 3 de 7 partes")).toBeTruthy();
  });
});

// ─── 3. Os controles no modal ────────────────────────────────────────────────

describe("Quem vê os controles do Vínculo", () => {
  it("quem tem login vê o campo de vincular", async () => {
    montarModal(demanda(), DA_VITTA);

    expect(await screen.findByLabelText("Vincular issue")).toBeTruthy();
  });

  it("quem não tem login não vê nada disso", async () => {
    montarModal(demanda(), DIRETOR);

    // O modal abriu (o par de presença: sem ele, um modal que não renderizasse
    // nada passaria por este teste).
    expect(await screen.findByLabelText("Título")).toBeTruthy();
    expect(screen.queryByLabelText("Vincular issue")).toBeNull();
    expect(screen.queryByText(/Vínculo com o desenvolvimento/i)).toBeNull();
  });

  it("quem não tem login não vê o botão nem o link da Demanda vinculada", async () => {
    montarModal({ ...VINCULADA, vinculo: null }, DIRETOR);

    expect(await screen.findByLabelText("Título")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Desvincular" })).toBeNull();
    expect(screen.queryByText(/Abrir no GitHub/i)).toBeNull();
  });

  it("quem tem login vê o link e o botão da Demanda vinculada", async () => {
    montarModal(VINCULADA, DA_VITTA);

    const link = await screen.findByText("Abrir no GitHub (#673)");
    expect(link.closest("a")?.getAttribute("href")).toBe(
      "https://github.com/pedrorezendefig/hospital-reunioes/issues/673",
    );
    expect(screen.getByRole("button", { name: "Desvincular" })).toBeTruthy();
    // E o campo de vincular some: a Demanda já tem Vínculo.
    expect(screen.queryByLabelText("Vincular issue")).toBeNull();
  });
});

describe("Quando a foto guardada não tem o endereço da issue", () => {
  const SEM_URL = { ...VINCULADA, vinculo: { numero: 673, url: null } };

  it("o número vira texto e o link some", async () => {
    // `href="#"` seria um clique morto: o cursor vira mãozinha, a pessoa clica
    // e nada acontece, e ela conclui que a página quebrou. O número continua à
    // vista, que é o que ela precisa para achar a issue à mão.
    montarModal(SEM_URL, DA_VITTA);

    expect(await screen.findByText("Issue #673")).toBeTruthy();
    expect(screen.queryByText(/Abrir no GitHub/)).toBeNull();
  });

  it("com endereço o link continua lá", async () => {
    // O par de presença: um link escondido sempre passaria pelo teste acima.
    montarModal(VINCULADA, DA_VITTA);

    const link = await screen.findByText("Abrir no GitHub (#673)");
    expect(link.closest("a")?.getAttribute("href")).toContain("/issues/673");
    expect(screen.queryByText("Issue #673")).toBeNull();
  });

  it("o Desvincular continua disponível sem o endereço", async () => {
    montarModal(SEM_URL, DA_VITTA);

    expect((await screen.findByRole("button", { name: "Desvincular" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("Quando a integração não está configurada", () => {
  it("o campo e o botão ficam desabilitados, com o aviso", async () => {
    montarModal(demanda(), DA_VITTA_SEM_INTEGRACAO);

    expect(await screen.findByText(AVISO_SEM_INTEGRACAO)).toBeTruthy();
    expect((screen.getByLabelText("Vincular issue") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Vincular" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("o Desvincular da Demanda vinculada também fica desabilitado", async () => {
    montarModal(VINCULADA, DA_VITTA_SEM_INTEGRACAO);

    expect(await screen.findByText(AVISO_SEM_INTEGRACAO)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Desvincular" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("com a integração de pé não há aviso nem campo desabilitado", async () => {
    // O par de presença dos dois testes acima: um aviso cravado na tela, ou um
    // `disabled` fixo, passaria por eles sem provar nada.
    montarModal(demanda(), DA_VITTA);

    expect(await screen.findByLabelText("Vincular issue")).toBeTruthy();
    expect(screen.queryByText(AVISO_SEM_INTEGRACAO)).toBeNull();
    expect((screen.getByLabelText("Vincular issue") as HTMLInputElement).disabled).toBe(false);
  });
});

describe("O que o modal manda ao servidor", () => {
  it("vincular manda o número na porta de vincular", async () => {
    montarModal(demanda(), DA_VITTA);

    const campo = await screen.findByLabelText("Vincular issue");
    await act(async () => {
      fireEvent.change(campo, { target: { value: "673" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Vincular" }));
    });

    await waitFor(() => {
      const enviada = chamadas.find((c) => c.url.endsWith("/demandas/d-1/vincular"));
      expect(enviada?.metodo).toBe("POST");
      // Número, e não texto: mandar "673" faria a recusa vir do pydantic, em
      // lista, e a tela mostraria o JSON cru no alerta vermelho.
      expect(enviada?.corpo).toEqual({ numero: 673 });
    });
  });

  it("desvincular chama a porta de desvincular", async () => {
    montarModal(VINCULADA, DA_VITTA);

    const botao = await screen.findByRole("button", { name: "Desvincular" });
    await act(async () => {
      fireEvent.click(botao);
    });

    await waitFor(() => {
      expect(chamadas.some((c) => c.url.endsWith("/demandas/d-1/desvincular") && c.metodo === "POST")).toBe(true);
    });
  });

  it("a recusa do servidor aparece na tela com a frase DELE", async () => {
    // A tela não inventa causa: quem sabe por que recusou (número inexistente,
    // pull request, issue já usada) é a API.
    const detail = "A issue #999 não existe no repositório da integração. Confira o número e tente de novo.";
    montarModal(demanda(), DA_VITTA, { recusa: { status: 422, detail } });

    const campo = await screen.findByLabelText("Vincular issue");
    await act(async () => {
      fireEvent.change(campo, { target: { value: "999" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Vincular" }));
    });

    expect(await screen.findByText(detail)).toBeTruthy();
  });

  it("campo vazio não chama o servidor", async () => {
    montarModal(demanda(), DA_VITTA);

    await screen.findByLabelText("Vincular issue");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Vincular" }));
    });

    expect(chamadas.some((c) => c.url.includes("/vincular"))).toBe(false);
  });
});

// ─── 5. Levar para desenvolvimento (issue #677) ──────────────────────────────

/**
 * O Quadro com um "eu" escolhido e um banco que MUDA depois do POST.
 *
 * É o que permite provar o critério inteiro: a lista volta com a Etapa nova na
 * releitura que o próprio modal dispara, e o selo aparece sem ninguém recarregar
 * a página.
 */
function montarQuadroComEu(demandas: Demanda[], eu: EuNaAba, depoisDoPost?: Demanda[]) {
  chamadas = [];
  let levada = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.includes("/conversa")) {
        return { ok: true, status: 200, json: async () => [] } as unknown as Response;
      }
      if (metodo !== "GET") {
        if (url.includes("/levar-para-desenvolvimento")) levada = true;
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => (levada && depoisDoPost ? depoisDoPost : demandas),
      } as unknown as Response;
    }),
  );

  function Anfitriao() {
    const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
    return (
      <QuadroDemandas
        token="token-de-teste"
        carregandoAuth={false}
        produtos={PRODUTOS}
        pessoas={PESSOAS}
        filtros={filtros}
        onFiltrosChange={setFiltros}
        eu={eu}
      />
    );
  }

  return render(<Anfitriao />);
}

describe("Quem vê o botão de levar para desenvolvimento", () => {
  it("quem tem login vê o botão na Demanda sem Vínculo", async () => {
    montarModal(demanda(), DA_VITTA);

    expect(await screen.findByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO })).toBeTruthy();
  });

  it("o diretor não vê o botão", async () => {
    // O botão é da Vitta (ADR 0054, decisão 9), e o backend recusa com 403 quem
    // não tem login: esconder aqui é o par na tela, não a proteção.
    montarModal(demanda(), DIRETOR);

    expect(await screen.findByLabelText("Título")).toBeTruthy();
    expect(screen.queryByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO })).toBeNull();
  });

  it("a Demanda que já tem Vínculo não mostra o botão", async () => {
    // Uma segunda issue para o mesmo pedido divide o trabalho em dois lugares.
    montarModal(VINCULADA, DA_VITTA);

    expect(await screen.findByRole("button", { name: "Desvincular" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO })).toBeNull();
  });

  it("sem integração o botão fica desabilitado, com o aviso", async () => {
    montarModal(demanda(), DA_VITTA_SEM_INTEGRACAO);

    expect(await screen.findByText(AVISO_SEM_INTEGRACAO)).toBeTruthy();
    const botao = screen.getByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });

  it("com a integração de pé o botão está clicável", async () => {
    // O par de presença do teste acima: um `disabled` fixo passaria por ele.
    montarModal(demanda(), DA_VITTA);

    const botao = (await screen.findByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO })) as HTMLButtonElement;
    expect(botao.disabled).toBe(false);
  });

  it("a ajuda diz que o clique cria a issue de verdade", async () => {
    // Ele ESCREVE num repositório público: isso não pode ser surpresa.
    montarModal(demanda(), DA_VITTA);

    expect(await screen.findByText(AJUDA_DE_LEVAR)).toBeTruthy();
  });
});

describe("O que o clique de levar manda ao servidor", () => {
  it("chama a porta de levar para desenvolvimento, sem corpo", async () => {
    montarModal(demanda(), DA_VITTA);

    const botao = await screen.findByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO });
    await act(async () => {
      fireEvent.click(botao);
    });

    await waitFor(() => {
      const enviada = chamadas.find((c) => c.url.endsWith("/demandas/d-1/levar-para-desenvolvimento"));
      expect(enviada?.metodo).toBe("POST");
      // Corpo vazio: o que a issue precisa (título, texto, tipo, Produto,
      // autor) o servidor já tem, e mandar daqui abriria uma porta para a tela
      // escrever no GitHub o que quisesse.
      expect(enviada?.corpo).toEqual({});
    });
  });

  it("a recusa do servidor aparece na tela com a frase DELE", async () => {
    const detail = "A Demanda já está vinculada à issue #673. Desfaça o Vínculo antes de levá-la para o desenvolvimento de novo.";
    montarModal(demanda(), DA_VITTA, { recusa: { status: 422, detail } });

    const botao = await screen.findByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO });
    await act(async () => {
      fireEvent.click(botao);
    });

    expect(await screen.findByText(detail)).toBeTruthy();
  });
});

describe("O selo depois de levar para desenvolvimento", () => {
  it("o card ganha o selo Em análise sem ninguém recarregar a página", async () => {
    const antes = demanda();
    const depois = demanda({ etapa: "em_analise", vinculo: { numero: 901, url: null } });
    montarQuadroComEu([antes], DA_VITTA, [depois]);

    const card = await screen.findByText("Levar o selo ao card");
    await act(async () => {
      fireEvent.click(card);
    });
    const botao = await screen.findByRole("button", { name: LEVAR_PARA_DESENVOLVIMENTO });
    await act(async () => {
      fireEvent.click(botao);
    });

    expect(await screen.findByText(ETAPA_ROTULO.em_analise)).toBeTruthy();
  });

  it("o par de presença: sem o clique não há selo nenhum", async () => {
    const antes = demanda();
    const depois = demanda({ etapa: "em_analise", vinculo: { numero: 901, url: null } });
    montarQuadroComEu([antes], DA_VITTA, [depois]);

    expect(await screen.findByText("Levar o selo ao card")).toBeTruthy();
    expect(screen.queryByText(ETAPA_ROTULO.em_analise)).toBeNull();
  });
});
