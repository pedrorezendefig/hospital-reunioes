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
import { AJUDA_DO_CAMPO, AVISO_SEM_INTEGRACAO } from "./VinculoDaDemanda";
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

  it("nenhum texto do Vínculo tem travessão", () => {
    // Regra da casa: travessão e meia-risca são marca de texto gerado por IA e
    // não entram em nada que o usuário vê. Estes são lidos pelo diretor.
    const textos = [...Object.values(ETAPA_ROTULO), AVISO_SEM_INTEGRACAO, AJUDA_DO_CAMPO];
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
