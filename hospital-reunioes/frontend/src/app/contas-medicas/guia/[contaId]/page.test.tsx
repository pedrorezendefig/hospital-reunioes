/**
 * @vitest-environment jsdom
 */

/**
 * A tela do Guia da faturista (issue #1121, PRD #1113, ADR 0070).
 *
 * A tela não decide nada: quem marca, recusa e conclui é o servidor. O que se
 * trava aqui é o que a faturista vê (os três números, os grupos, os botões, a
 * evidência fechada) e o que cada clique dispara (a URL e o corpo).
 *
 * Todo teste de ausência tem irmão de presença no mesmo estado: afirmar que a
 * linha Validar não tem botão é vazio se nenhuma linha tivesse.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import type { Guia, LinhaGuia } from "@/lib/contas-medicas/guia";

import GuiaPage from "./page";

const CONTA = "11111111-1111-1111-1111-111111111111";
const PROXIMA = "22222222-2222-2222-2222-222222222222";

const navegacao = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ contaId: "11111111-1111-1111-1111-111111111111" }),
  useRouter: () => ({ push: navegacao.push }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

function linha(campos: Partial<LinhaGuia>): LinhaGuia {
  return {
    id: "l-luva",
    acao: "INCLUIR",
    data: "2026-10-03",
    data_fim: "2026-10-05",
    setor: "CTI",
    codigo: "70012345",
    descricao: "Luva de procedimento",
    quantidade_lancada: 0,
    quantidade_devida: 180,
    preco_lancado: null,
    preco_tabela: 0.38,
    valor_diferenca: 68.4,
    regra_codigo: "ASSIM-INS-03",
    motivo: "3 diárias de CTI pagas",
    evidencia_pagina: 2,
    evidencia_trecho: "Luva de procedimento 60 por dia",
    nivel_evidencia: "REGISTRADO",
    confianca: "ALTA",
    estado: "ABERTA",
    motivo_nao_procede: null,
    texto_nao_procede: null,
    nao_conferido: false,
    ...campos,
  };
}

function guia(campos: Partial<Guia> = {}): Guia {
  return {
    cabecalho: {
      numero_atendimento: "31245",
      paciente_rotulo: "Maria S.",
      numero_conta: "48811",
      operadora: "ASSIM",
      coluna_preco: "CARIOCA",
      periodo_inicio: "2026-10-03",
      periodo_fim: "2026-10-07",
      situacao: "EM_CORRECAO",
      parecer_parcial: false,
      faltantes: [],
    },
    numeros: {
      nota_entrada: 74,
      valor_a_ajustar: 584.6,
      itens_a_ajustar: 9,
      valor_em_validacao: 1212,
      itens_feitos: 0,
      itens_total: 3,
      itens_sem_marcacao: 3,
    },
    grupos: [
      {
        data: "2026-10-03",
        setor: "CTI",
        linhas: [
          linha({}),
          linha({
            id: "l-lavagem",
            acao: "AJUSTAR_QUANTIDADE",
            data_fim: null,
            codigo: "80055501",
            descricao: "Lavagem de sonda",
            quantidade_lancada: 12,
            quantidade_devida: 9,
            valor_diferenca: -4.17,
            nao_conferido: true,
            confianca: "BAIXA",
          }),
        ],
      },
      {
        data: "2026-10-04",
        setor: "ENFERMARIA",
        linhas: [
          linha({
            id: "l-fita",
            data: "2026-10-04",
            data_fim: null,
            setor: "ENFERMARIA",
            codigo: "80077702",
            descricao: "Fita de glicemia",
            quantidade_devida: 4,
            valor_diferenca: 36,
          }),
          linha({
            id: "l-unidade",
            acao: "VALIDAR",
            data: "2026-10-04",
            data_fim: null,
            setor: "ENFERMARIA",
            codigo: "90011122",
            descricao: "Dieta enteral",
            valor_diferenca: 1212,
            motivo: "A unidade do preço ainda está pendente",
            estado: "EM_VALIDACAO",
          }),
        ],
      },
    ],
    ...campos,
  };
}

let chamadas: { url: string; metodo: string; corpo: unknown }[] = [];
let respostaDoGuia: Guia;
let respostaDaConclusao: Record<string, unknown>;

beforeEach(() => {
  chamadas = [];
  respostaDoGuia = guia();
  respostaDaConclusao = { situacao: "CONCLUIDA_COM_PENDENCIA", pendencias: 3, proxima_conta_id: PROXIMA };
  navegacao.push.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpoEnviado =
        init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : undefined;
      chamadas.push({ url, metodo, corpo: corpoEnviado });
      const corpo = url.endsWith("/concluir")
        ? respostaDaConclusao
        : url.endsWith("/reenvio")
          ? { nota_saida: 86, corrigidas: 2, ainda_na_conta: 1, linhas: {} }
        : metodo === "GET"
          ? respostaDoGuia
          : { ok: true };
      return new Response(JSON.stringify(corpo), { status: 200 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function abrir() {
  render(
    <ToastProvider>
      <GuiaPage />
    </ToastProvider>,
  );
  await screen.findByRole("heading", { level: 1, name: "Atendimento 31245" });
}

function aLinha(descricao: string) {
  return screen.getByRole("article", { name: descricao });
}

describe("o topo do Guia", () => {
  it("mostra o cabeçalho e os três números", async () => {
    await abrir();

    expect(screen.getByText(/Maria S\. · conta 48811 · ASSIM · coluna Carioca · parcial de 03\/10 a 07\/10/)).toBeTruthy();
    expect(screen.getByText("Em correção")).toBeTruthy();
    const numeros = screen.getByRole("region", { name: "Números do guia" });
    expect(within(numeros).getByText("Nota de entrada")).toBeTruthy();
    expect(within(numeros).getByText("74")).toBeTruthy();
    expect(within(numeros).getByText("R$ 584,60")).toBeTruthy();
    expect(within(numeros).getByText("em 9 itens, mais 1.212,00 em validação")).toBeTruthy();
    expect(within(numeros).getByText("0 de 3")).toBeTruthy();
  });

  it("pede o guia da conta da URL, com o token", async () => {
    await abrir();

    expect(chamadas[0]).toEqual({ url: `/api/contas-medicas/contas/${CONTA}/guia`, metodo: "GET", corpo: undefined });
  });

  it("com parecer parcial, mostra a faixa e o que faltou", async () => {
    respostaDoGuia = guia({
      cabecalho: { ...guia().cabecalho, parecer_parcial: true, faltantes: ["Balanço hídrico"] },
    });
    await abrir();

    const faixa = screen.getByRole("note", { name: "Parecer parcial" });
    expect(faixa.textContent).toContain("PARECER PARCIAL");
    expect(faixa.textContent).toContain("Balanço hídrico");
  });
});

describe("as linhas por dia e setor", () => {
  it("agrupa com o cabeçalho do dia e o Marcar o dia como feito", async () => {
    await abrir();

    expect(screen.getByRole("heading", { name: "03/10 · CTI" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "04/10 · ENFERMARIA" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Marcar o dia como feito" })).toHaveLength(2);
  });

  it("a linha traz a ação, o texto com verbo, o valor com sinal e o código", async () => {
    await abrir();

    const luva = aLinha("Luva de procedimento");
    expect(within(luva).getByText("Incluir", { selector: "span" })).toBeTruthy();
    expect(within(luva).getByText("Incluir 180, de 03/10 a 05/10")).toBeTruthy();
    expect(within(luva).getByText("+R$ 68,40")).toBeTruthy();
    expect(within(luva).getByRole("button", { name: "Copiar código 70012345" })).toBeTruthy();
    expect(within(aLinha("Lavagem de sonda")).getByText("-R$ 4,17")).toBeTruthy();
  });

  it("Não conferido e conferir evidência aparecem só onde cabem", async () => {
    await abrir();

    expect(within(aLinha("Lavagem de sonda")).getByText("Não conferido")).toBeTruthy();
    expect(within(aLinha("Lavagem de sonda")).getByText("conferir evidência")).toBeTruthy();
    expect(within(aLinha("Luva de procedimento")).queryByText("Não conferido")).toBeNull();
    expect(within(aLinha("Luva de procedimento")).queryByText("conferir evidência")).toBeNull();
  });

  it("a linha aberta tem Feito, Não procede e Bloqueado; a Validar não tem botão", async () => {
    await abrir();

    const luva = aLinha("Luva de procedimento");
    for (const nome of ["Feito", "Não procede", "Bloqueado"]) {
      expect(within(luva).getByRole("button", { name: nome })).toBeTruthy();
    }
    const validar = aLinha("Dieta enteral");
    for (const nome of ["Feito", "Não procede", "Bloqueado"]) {
      expect(within(validar).queryByRole("button", { name: nome })).toBeNull();
    }
    expect(validar.textContent).toContain("Você não precisa decidir: o item já foi para a validação");
    expect(validar.textContent).toContain("Em jogo: R$ 1.212,00");
  });

  it("a linha se necessário sem registro tem a etiqueta âmbar e o texto; as outras não (issue #1134)", async () => {
    respostaDoGuia = guia();
    respostaDoGuia.grupos[0].linhas.push(
      linha({
        id: "l-dipirona",
        data_fim: null,
        codigo: "91000002",
        descricao: "DIPIRONA 1 G AMP",
        quantidade_devida: 1,
        valor_diferenca: 2,
        nivel_evidencia: "PRESCRITO_SN",
        motivo:
          "Se necessário (DIPIRONA 1G AMP), sem registro de uso no MV: 1 por dia de prescrição, quantidade " +
          "provisória. Confira a checagem em papel. Sem uso, marque NÃO PROCEDE.",
      }),
    );
    await abrir();

    const dipirona = aLinha("DIPIRONA 1 G AMP");
    const etiqueta = within(dipirona).getByText("SE NECESSÁRIO · SEM REGISTRO NO MV");
    expect(etiqueta.className).toContain("bg-[#FEF3C7]");
    expect(dipirona.textContent).toContain("Confira a checagem em papel. Sem uso, marque NÃO PROCEDE.");
    expect(within(aLinha("Luva de procedimento")).queryByText("SE NECESSÁRIO · SEM REGISTRO NO MV")).toBeNull();

    fireEvent.click(within(dipirona).getByRole("button", { name: "Não procede" }));
    expect((within(dipirona).getByLabelText("Sem evidência no prontuário") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(dipirona).getByRole("button", { name: "Confirmar Não procede" }));
    await waitFor(() => expect(chamadas[1]?.corpo).toEqual({ estado: "NAO_PROCEDE", motivo: "SEM_EVIDENCIA" }));

    fireEvent.click(within(aLinha("Luva de procedimento")).getByRole("button", { name: "Não procede" }));
    expect(within(aLinha("Luva de procedimento")).getAllByRole("radio").some((r) => (r as HTMLInputElement).checked)).toBe(
      false,
    );
  });

  it("Ver evidência vem fechado e abre a página e o trecho com o nível", async () => {
    await abrir();
    const luva = aLinha("Luva de procedimento");
    expect(within(luva).queryByText("Luva de procedimento 60 por dia")).toBeNull();

    fireEvent.click(within(luva).getByRole("button", { name: "Ver evidência" }));

    expect(within(luva).getByText("Prontuário, p. 2")).toBeTruthy();
    expect(within(luva).getByText("Luva de procedimento 60 por dia")).toBeTruthy();
    expect(within(luva).getByText("Registrado")).toBeTruthy();
  });
});

describe("o código copia com um clique", () => {
  it("copia para a área de transferência e mostra o toast", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: "Copiar código 70012345" }));

    expect(writeText).toHaveBeenCalledWith("70012345");
    expect(await screen.findByText("Código copiado")).toBeTruthy();
  });
});

describe("os botões da linha", () => {
  it("Feito manda a marcação da linha e recarrega o guia", async () => {
    await abrir();

    fireEvent.click(within(aLinha("Luva de procedimento")).getByRole("button", { name: "Feito" }));

    await waitFor(() => expect(chamadas).toHaveLength(3));
    expect(chamadas[1]).toEqual({
      url: `/api/contas-medicas/contas/${CONTA}/guia/linhas/l-luva/marcacao`,
      metodo: "POST",
      corpo: { estado: "FEITO" },
    });
    expect(chamadas[2].metodo).toBe("GET");
  });

  it("Bloqueado é um clique", async () => {
    await abrir();

    fireEvent.click(within(aLinha("Luva de procedimento")).getByRole("button", { name: "Bloqueado" }));

    await waitFor(() => expect(chamadas[1]?.corpo).toEqual({ estado: "BLOQUEADO" }));
  });

  it("Não procede abre os 4 motivos; em outro, o texto é obrigatório", async () => {
    await abrir();
    const luva = aLinha("Luva de procedimento");

    fireEvent.click(within(luva).getByRole("button", { name: "Não procede" }));
    const motivos = within(luva).getAllByRole("radio").map((radio) => radio.closest("label")?.textContent);
    expect(motivos).toEqual(["Já está na conta", "Sem evidência no prontuário", "A regra é outra", "Outro"]);

    fireEvent.click(within(luva).getByLabelText("Outro"));
    const confirmar = within(luva).getByRole("button", { name: "Confirmar Não procede" });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(within(luva).getByRole("textbox"), { target: { value: "Já vem no kit" } });
    expect((confirmar as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(confirmar);

    await waitFor(() =>
      expect(chamadas[1]?.corpo).toEqual({ estado: "NAO_PROCEDE", motivo: "OUTRO", texto: "Já vem no kit" }),
    );
  });

  it("Não procede com motivo e sem texto passa direto", async () => {
    await abrir();
    const luva = aLinha("Luva de procedimento");

    fireEvent.click(within(luva).getByRole("button", { name: "Não procede" }));
    fireEvent.click(within(luva).getByLabelText("Já está na conta"));
    fireEvent.click(within(luva).getByRole("button", { name: "Confirmar Não procede" }));

    await waitFor(() =>
      expect(chamadas[1]?.corpo).toEqual({ estado: "NAO_PROCEDE", motivo: "JA_ESTA_NA_CONTA" }),
    );
  });

  it("linha Feito recolhe em verde com Desfazer, que manda o DELETE", async () => {
    respostaDoGuia = guia();
    respostaDoGuia.grupos[0].linhas[0] = linha({ estado: "FEITO" });
    await abrir();
    const luva = aLinha("Luva de procedimento");
    expect(within(luva).queryByRole("button", { name: "Feito" })).toBeNull();
    expect(within(luva).getByText("Feito", { selector: "span" })).toBeTruthy();

    fireEvent.click(within(luva).getByRole("button", { name: "Desfazer" }));

    await waitFor(() =>
      expect(chamadas[1]).toEqual({
        url: `/api/contas-medicas/contas/${CONTA}/guia/linhas/l-luva/marcacao`,
        metodo: "DELETE",
        corpo: undefined,
      }),
    );
  });

  it("Marcar o dia como feito manda o dia e o setor do grupo", async () => {
    await abrir();

    fireEvent.click(screen.getAllByRole("button", { name: "Marcar o dia como feito" })[1]);

    await waitFor(() =>
      expect(chamadas[1]).toEqual({
        url: `/api/contas-medicas/contas/${CONTA}/guia/dia/feito`,
        metodo: "POST",
        corpo: { data: "2026-10-04", setor: "ENFERMARIA" },
      }),
    );
  });
});

describe("concluir", () => {
  it("com item sem marcação pergunta antes; negar não conclui", async () => {
    const confirmar = vi.spyOn(window, "confirm").mockReturnValue(false);
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: "Concluir e abrir a próxima" }));

    expect(confirmar).toHaveBeenCalledWith("3 itens sem marcação. Concluir assim mesmo?");
    expect(chamadas.some((c) => c.url.endsWith("/concluir"))).toBe(false);
  });

  it("confirmando, conclui com a observação e abre a próxima", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await abrir();

    fireEvent.change(screen.getByLabelText("Observação para a gestão de contas médicas"), {
      target: { value: "Luva já vem no kit do CTI" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Concluir e abrir a próxima" }));

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith(`/contas-medicas/guia/${PROXIMA}`));
    expect(chamadas[1]).toEqual({
      url: `/api/contas-medicas/contas/${CONTA}/guia/concluir`,
      metodo: "POST",
      corpo: { observacao: "Luva já vem no kit do CTI" },
    });
  });

  it("sem item sem marcação não pergunta, e sem próxima volta para a fila", async () => {
    const confirmar = vi.spyOn(window, "confirm");
    respostaDoGuia = guia({ numeros: { ...guia().numeros, itens_sem_marcacao: 0 } });
    respostaDaConclusao = { situacao: "CONCLUIDA", pendencias: 0, proxima_conta_id: null };
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: "Concluir e abrir a próxima" }));

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/contas-medicas"));
    expect(confirmar).not.toHaveBeenCalled();
  });

  it("o botão está sempre habilitado, com o texto de apoio", async () => {
    await abrir();

    const botao = screen.getByRole("button", { name: "Concluir e abrir a próxima" }) as HTMLButtonElement;
    expect(botao.disabled).toBe(false);
    expect(screen.getByText(/Você pode concluir com pendência/)).toBeTruthy();
  });

  it("conta concluída não tem botões de linha nem Concluir", async () => {
    respostaDoGuia = guia({ cabecalho: { ...guia().cabecalho, situacao: "CONCLUIDA" } });
    await abrir();

    expect(screen.getByText("Concluída")).toBeTruthy();
    expect(within(aLinha("Luva de procedimento")).queryByRole("button", { name: "Feito" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Concluir e abrir a próxima" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Marcar o dia como feito" })).toBeNull();
  });
});

describe("o botão Reanalisar (issue #1130)", () => {
  it("aparece quando o guia diz que pode e manda a conta para a análise de novo", async () => {
    respostaDoGuia = guia({ pode_reanalisar: true });
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: "Reanalisar" }));

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/contas-medicas"));
    expect(chamadas[1]).toEqual({
      url: `/api/contas-medicas/contas/${CONTA}/reanalisar`,
      metodo: "POST",
      corpo: undefined,
    });
  });

  it("não aparece quando o guia diz que não pode", async () => {
    respostaDoGuia = guia({ pode_reanalisar: false });
    await abrir();

    expect(screen.getByRole("button", { name: "Concluir e abrir a próxima" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reanalisar" })).toBeNull();
  });
});

describe("o reenvio da conta corrigida (issue #1136)", () => {
  function concluida(campos: Partial<Guia> = {}): Guia {
    return guia({ cabecalho: { ...guia().cabecalho, situacao: "CONCLUIDA" }, pode_reenviar: true, ...campos });
  }

  it("o botão fica no rodapé da conta concluída e manda só o PDF da conta", async () => {
    respostaDoGuia = concluida();
    await abrir();

    expect(screen.getByRole("button", { name: "Reenviar conta corrigida" })).toBeTruthy();
    const pdf = new File(["%PDF"], "conta-48811.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF da conta corrigida"), { target: { files: [pdf] } });

    await waitFor(() => expect(chamadas.filter((c) => c.metodo === "GET")).toHaveLength(2));
    const reenvio = chamadas[1];
    expect([reenvio.url, reenvio.metodo]).toEqual([`/api/contas-medicas/contas/${CONTA}/reenvio`, "POST"]);
    const enviado = reenvio.corpo as FormData;
    expect([...enviado.keys()]).toEqual(["arquivo"]);
    expect((enviado.get("arquivo") as File).name).toBe("conta-48811.pdf");
    expect(await screen.findByText("2 corrigidas no MV, 1 ainda na conta, nota de saída 86")).toBeTruthy();
  });

  it("conta em aberto não tem o botão", async () => {
    respostaDoGuia = guia({ pode_reenviar: false });
    await abrir();

    expect(screen.getByRole("button", { name: "Concluir e abrir a próxima" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reenviar conta corrigida" })).toBeNull();
  });

  it("mostra a nota de saída ao lado da de entrada e a marca de cada linha Feito", async () => {
    const base = concluida();
    respostaDoGuia = concluida({
      reenvio: { nota_saida: 86, reenviada_em: "2026-10-13T10:00:00+00:00", corrigidas: 1, ainda_na_conta: 1 },
      grupos: [
        {
          data: "2026-10-03",
          setor: "CTI",
          linhas: [
            linha({ estado: "FEITO", reenvio: "CORRIGIDA" }),
            linha({ id: "l-senha", acao: "RETIRAR", descricao: "Senha de acesso", estado: "FEITO", reenvio: "AINDA_NA_CONTA" }),
            linha({ id: "l-gaze", descricao: "Gaze", estado: "NAO_PROCEDE", reenvio: null }),
          ],
        },
      ],
      numeros: base.numeros,
    });
    await abrir();

    const numeros = screen.getByRole("region", { name: "Números do guia" });
    expect(within(numeros).getByText("Nota de saída")).toBeTruthy();
    expect(within(numeros).getByText("86")).toBeTruthy();
    expect(within(aLinha("Luva de procedimento")).getByText("corrigida no MV")).toBeTruthy();
    expect(within(aLinha("Senha de acesso")).getByText("ainda na conta")).toBeTruthy();
    expect(within(aLinha("Gaze")).queryByText(/corrigida no MV|ainda na conta/)).toBeNull();
  });

  it("sem reenvio não há nota de saída", async () => {
    respostaDoGuia = concluida();
    await abrir();

    const numeros = screen.getByRole("region", { name: "Números do guia" });
    expect(within(numeros).getByText("Nota de entrada")).toBeTruthy();
    expect(within(numeros).queryByText("Nota de saída")).toBeNull();
  });
});

describe("a marca regra nova desde a análise (issue #1141)", () => {
  it("conta analisada antes da regra nova mostra a marca e o botão Reanalisar com a regra nova", async () => {
    respostaDoGuia = guia({ pode_reanalisar: true, regra_nova_desde_analise: true });
    await abrir();

    expect(screen.getByText("Regra nova desde a análise")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reanalisar com a regra nova" }));

    await waitFor(() => expect(navegacao.push).toHaveBeenCalledWith("/contas-medicas"));
    expect(chamadas[1].url).toBe(`/api/contas-medicas/contas/${CONTA}/reanalisar`);
  });

  it("conta analisada com a memória de agora fica sem a marca e com o botão Reanalisar", async () => {
    respostaDoGuia = guia({ pode_reanalisar: true, regra_nova_desde_analise: false });
    await abrir();

    expect(screen.getByRole("button", { name: "Reanalisar" })).toBeTruthy();
    expect(screen.queryByText("Regra nova desde a análise")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reanalisar com a regra nova" })).toBeNull();
  });

  it("a faturista vê a marca mesmo sem o botão", async () => {
    respostaDoGuia = guia({ pode_reanalisar: false, regra_nova_desde_analise: true });
    await abrir();

    expect(screen.getByText("Regra nova desde a análise")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Reanalisar/ })).toBeNull();
  });
});
