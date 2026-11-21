/**
 * @vitest-environment jsdom
 */

/**
 * As telas do Comitê de Conduta (issue #1824): MINHA VEZ, Casos e a tela do
 * caso, com a caixa "O QUE FAZER AGORA".
 *
 * Quem decide o que cada pessoa pode fazer é o servidor (a caixa vem pronta,
 * com o motivo do botão bloqueado). O que se trava aqui é o que a tela mostra
 * e o que ela pede ao servidor.
 *
 * jsdom não mede largura. O que segura a tela a 375 px é não ter largura fixa
 * nenhuma e empilhar botões e filtros no celular (`w-full sm:w-auto`,
 * `grid-cols-1 sm:grid-cols-2`).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CasosDoComite } from "./CasosDoComite";
import { MinhaVez } from "./MinhaVez";
import { OQueFazerAgora } from "./OQueFazerAgora";
import { TelaDoCaso } from "./TelaDoCaso";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }) },
  }),
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/comite-de-conduta" }));

let respostas: Record<string, unknown>;
let chamadas: { url: string; method: string; body: unknown }[];

beforeEach(() => {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      const chave = Object.keys(respostas).find((k) => url.endsWith(k)) ?? "";
      return { ok: true, status: 200, json: async () => respostas[chave] ?? {} } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ITEM = {
  id: "c1",
  protocolo: "CC-AB12-CD34",
  etapa: "triagem",
  rito: null,
  acao: "Confirmar a triagem",
  prazo_em: null,
  prazo_vencido: false,
  faltam_dias: null,
};

describe("MINHA VEZ", () => {
  it("vazia, diz que nada depende da pessoa", async () => {
    respostas = { "/minha-vez": { itens: [] } };
    render(<MinhaVez />);

    expect(await screen.findByText("Nada depende de você agora.")).toBeTruthy();
  });

  it("sem o Termo assinado, diz que falta assinar e não oferece caso (issue #1823)", async () => {
    respostas = { "/minha-vez": { itens: [], termo_pendente: true } };
    render(<MinhaVez />);

    expect(await screen.findByText("Falta assinar o Termo de Confidencialidade e Posse.")).toBeTruthy();
    expect(screen.getByText(/chegou no seu e-mail profissional pela ClickSign/)).toBeTruthy();
    expect(screen.queryByText("Nada depende de você agora.")).toBeNull();
    expect(screen.queryByRole("link", { name: "ABRIR O MAIS URGENTE" })).toBeNull();
  });

  it("mostra protocolo, etapa, ação e prazo, na ordem do servidor", async () => {
    respostas = {
      "/minha-vez": {
        itens: [
          { ...ITEM, id: "c2", protocolo: "CC-ZZZZ-0001", etapa: "encaminhamento", acao: "Enviar a orientação", faltam_dias: 2 },
          { ...ITEM, faltam_dias: 12, etapa: "apuracao", acao: "Conferir a triagem" },
        ],
      },
    };
    render(<MinhaVez />);

    const lista = await screen.findByRole("list", { name: "O que depende de você" });
    const linhas = within(lista).getAllByRole("listitem");
    expect(linhas.map((l) => l.textContent)).toEqual([
      "CC-ZZZZ-0001Faltam 2 diasEncaminhamentoEnviar a orientação",
      "CC-AB12-CD34Faltam 12 diasApuraçãoConferir a triagem",
    ]);
    expect(screen.getByRole("link", { name: "ABRIR O MAIS URGENTE" }).getAttribute("href")).toBe(
      "/comite-de-conduta/casos/c2"
    );
  });
});

describe("Casos", () => {
  it("filtra por situação e por rito no servidor", async () => {
    respostas = { "/casos": { casos: [] }, "?situacao=encerrado": { casos: [] }, "&rito=completo": { casos: [] } };
    render(<CasosDoComite />);
    await screen.findByText("Nenhum caso com esse filtro.");

    fireEvent.change(screen.getByLabelText("Situação"), { target: { value: "encerrado" } });
    fireEvent.change(screen.getByLabelText("Rito"), { target: { value: "completo" } });

    await waitFor(() =>
      expect(chamadas.at(-1)?.url).toBe("/api/comite-de-conduta/casos?situacao=encerrado&rito=completo")
    );
  });

  it("cada caso mostra protocolo, rito, etapa e prazo, e marca o vencido", async () => {
    respostas = {
      "/casos": {
        casos: [
          { id: "c1", protocolo: "CC-AB12-CD34", etapa: "apuracao", rito: "rapido", categoria: "A", situacao: "em_andamento", prazo_em: "2026-11-01", prazo_vencido: true, faltam_dias: -3 },
        ],
      },
    };
    render(<CasosDoComite />);

    const caso = await screen.findByRole("link", { name: /CC-AB12-CD34/ });
    expect(caso.textContent).toBe("CC-AB12-CD34Venceu há 3 diasRápido, apuraçãoPrazo vencido registrado");
  });
});

describe("a caixa O QUE FAZER AGORA", () => {
  const CAIXA = {
    frase: "Leia o resumo. Confirme se o caso é do canal e qual o rito.",
    botao: "CONFIRMAR TRIAGEM",
    como_fazer: ["Leia o relato original", "Confira cada sugestão", "Se faltar informação, pergunte ao denunciante"],
    acao: "confirmar_triagem",
    bloqueio: null,
  };

  it("mostra a frase, o botão e o Como fazer em três linhas ao toque", () => {
    const aoAgir = vi.fn();
    render(<OQueFazerAgora caixa={CAIXA} aoAgir={aoAgir} />);

    expect(screen.getByText(CAIXA.frase)).toBeTruthy();
    expect(screen.queryByText("Confira cada sugestão")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Como fazer" }));
    expect(screen.getAllByRole("listitem").map((l) => l.textContent)).toEqual(CAIXA.como_fazer);

    fireEvent.click(screen.getByRole("button", { name: "CONFIRMAR TRIAGEM" }));
    expect(aoAgir).toHaveBeenCalledWith("confirmar_triagem");
  });

  it("botão bloqueado fica desligado e mostra o motivo numa linha", () => {
    const aoAgir = vi.fn();
    render(<OQueFazerAgora caixa={{ ...CAIXA, bloqueio: "Só a coordenação confirma a triagem." }} aoAgir={aoAgir} />);

    const botao = screen.getByRole("button", { name: "CONFIRMAR TRIAGEM" }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.getByText("Só a coordenação confirma a triagem.")).toBeTruthy();
  });
});

const CASO = {
  id: "c1",
  protocolo: "CC-AB12-CD34",
  etapa: "encaminhamento",
  rito: "encaminhamento",
  escopo: "fora",
  categoria: "F",
  destino: "dp",
  situacao: "em_andamento",
  prazo_em: "2026-11-27",
  prazo_vencido: false,
  faltam_dias: 4,
  relato: "Meu banco de horas está errado há três meses.",
  papel: "coordenacao",
  trilho: [
    { nome: "Triagem", estado: "atual" },
    { nome: "Encaminhado", estado: "pendente" },
  ],
  o_que_fazer_agora: {
    frase: "Este relato parece não ser do canal. Confira e envie a orientação.",
    botao: "ENVIAR ORIENTAÇÃO",
    como_fazer: ["a", "b", "c"],
    acao: "enviar_orientacao",
    bloqueio: null,
  },
  contestacao: null,
  pode_contestar: false,
  prorrogacao: null,
  orientacao: "Seu relato foi lido pelo Comitê. O assunto não é tratado neste canal. Procure o Departamento Pessoal.",
  triagem_em: "2026-11-20T10:00:00+00:00",
  conferida_em: "2026-11-20T11:00:00+00:00",
  encerrado_em: null,
  desfecho: null,
};

describe("a tela do caso", () => {
  it("mostra o trilho, o prazo, a resposta padrão e o relato", async () => {
    respostas = { "/casos/c1": CASO };
    render(<TelaDoCaso casoId="c1" />);

    expect((await screen.findByLabelText("Prazo")).textContent).toBe("Faltam 4 dias");
    const trilho = screen.getByRole("list", { name: "Trilho do rito" });
    expect(within(trilho).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Triagem", "Encaminhado"]);
    expect(within(screen.getByRole("region", { name: "Orientação" })).getByText(CASO.orientacao)).toBeTruthy();
    expect(screen.getByText(CASO.relato)).toBeTruthy();
  });

  it("no Encaminhamento, um clique envia a orientação e encerra", async () => {
    respostas = { "/casos/c1": CASO, "/casos/c1/encaminhamento": { caso: {} } };
    render(<TelaDoCaso casoId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: "ENVIAR ORIENTAÇÃO" }));

    await waitFor(() =>
      expect(chamadas.some((c) => c.method === "POST" && c.url === "/api/comite-de-conduta/casos/c1/encaminhamento")).toBe(true)
    );
  });

  it("a coordenação confirma a triagem pelo formulário", async () => {
    respostas = {
      "/casos/c1": {
        ...CASO,
        etapa: "triagem",
        rito: null,
        triagem_em: null,
        orientacao: null,
        o_que_fazer_agora: { ...CASO.o_que_fazer_agora, botao: "CONFIRMAR TRIAGEM", acao: "confirmar_triagem" },
      },
      "/casos/c1/triagem": { caso: {} },
    };
    render(<TelaDoCaso casoId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: "CONFIRMAR TRIAGEM" }));
    const formulario = screen.getByRole("form", { name: "Confirmar a triagem" });
    fireEvent.click(within(formulario).getByLabelText("Dentro do canal"));
    fireEvent.change(within(formulario).getByLabelText("Categoria"), { target: { value: "A" } });
    fireEvent.change(within(formulario).getByLabelText("Rito"), { target: { value: "completo" } });
    fireEvent.click(within(formulario).getByRole("button", { name: "CONFIRMAR TRIAGEM" }));

    await waitFor(() =>
      expect(chamadas.find((c) => c.url.endsWith("/casos/c1/triagem"))?.body).toEqual({
        escopo: "dentro",
        categoria: "A",
        rito: "completo",
        destino: null,
      })
    );
  });

  it("o Completo mostra a prorrogação bloqueada com o motivo", async () => {
    respostas = {
      "/casos/c1": {
        ...CASO,
        rito: "completo",
        etapa: "apuracao",
        prorrogacao: { justificativa: null, bloqueio: "Só a coordenação prorroga o prazo." },
      },
    };
    render(<TelaDoCaso casoId="c1" />);

    const botao = (await screen.findByRole("button", { name: "PRORROGAR PRAZO" })) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.getByText("Só a coordenação prorroga o prazo.")).toBeTruthy();
  });
});

const PASTAS = [resolve(process.cwd(), "src/components/conduta"), resolve(process.cwd(), "src/app/comite-de-conduta")];

function arquivos(pasta: string): string[] {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = join(pasta, nome);
    if (statSync(caminho).isDirectory()) return arquivos(caminho);
    return /\.tsx?$/.test(nome) && !nome.includes(".test.") ? [caminho] : [];
  });
}

describe("as telas a 375 px", () => {
  it("o detector acha os arquivos das telas (piso)", () => {
    expect(PASTAS.flatMap(arquivos).length).toBeGreaterThanOrEqual(9);
  });

  it("nenhuma largura fixa, que quebraria a tela a 375 px", () => {
    for (const caminho of PASTAS.flatMap(arquivos)) {
      expect(readFileSync(caminho, "utf8"), caminho).not.toMatch(/\b(?:min-)?w-\[\d+px\]|\bw-(?:9[6-9]|[1-9]\d{2,})\b/);
    }
  });

  it("sem travessão nem meia-risca", () => {
    for (const caminho of PASTAS.flatMap(arquivos)) {
      const texto = readFileSync(caminho, "utf8");
      expect(texto.includes(String.fromCharCode(0x2014)), caminho).toBe(false);
      expect(texto.includes(String.fromCharCode(0x2013)), caminho).toBe(false);
    }
  });
});
