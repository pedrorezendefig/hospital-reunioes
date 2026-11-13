/**
 * @vitest-environment jsdom
 */

/**
 * O endereço curto do cartaz, `/a/{código}` (issue #1617, ADR 0086 decisão 5).
 *
 * É o que o cartaz A4 imprime e o que o QR carrega. Desde a issue #1622 ele
 * abre a nota de 1 a 5 (telas N1, N2 e N3 da especificação), e só quem pede
 * retorno, quer deixar um elogio ou toca em "Prefiro registrar uma
 * manifestação" segue para a Manifestação guiada. O que só existe aqui, e que a
 * suíte do backend não vê:
 *
 * * a nota vai para a rota da avaliação, e nunca para a de manifestações;
 * * quem segue da nota leva o id da avaliação no envio, menos no anonimato;
 * * o código da URL é o que vai no envio da manifestação, e o lugar do passo
 *   "Quando e onde" chega com o nome público do ponto, nunca com o setor;
 * * cartaz aposentado abre a manifestação direto, sem tela de erro.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EnderecoCurtoDoCartaz from "./page";

let codigoDaUrl = "AB2CD3";

vi.mock("next/navigation", () => ({
  useParams: () => ({ codigo: codigoDaUrl }),
  useSearchParams: () => new URLSearchParams(),
}));

const RECIBO = {
  protocolo: "2026-0042",
  data_abertura: "2026-09-01",
  prazo_resposta: "2026-09-08",
  status: "em_classificacao",
};

const LOCAIS = [
  { nome: "Centro Médico", ala_internacao: false },
  { nome: "Emergência adulta", ala_internacao: false },
];

const CARTAZ = { nome_publico: "Emergência adulta", titulo_cartaz: "um_minuto" };

let consultas: string[] = [];
let avaliacoes: { url: string; corpo: Record<string, unknown> }[] = [];
let enviados: Record<string, unknown>[] = [];
let respostaDaAvaliacao = 201;
let conviteGoogle = false;

/** O servidor: a rota pública do ponto responde `cartaz` (ou 404, quando o
 *  ponto está aposentado), a da avaliação grava a nota, a de locais devolve a
 *  lista e a de manifestações devolve o recibo. */
function servidor(cartaz: Record<string, unknown> | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/avaliacoes")) {
        const corpo = JSON.parse(String(init?.body ?? "{}"));
        avaliacoes.push({ url, corpo });
        return {
          ok: respostaDaAvaliacao < 300,
          status: respostaDaAvaliacao,
          json: async () => ({ id: "avaliacao-7", nota: corpo.nota, convite_google: conviteGoogle }),
        } as Response;
      }
      if (url.includes("/publico/pontos/")) {
        consultas.push(url);
        return (cartaz
          ? { ok: true, status: 200, json: async () => cartaz }
          : { ok: false, status: 404, json: async () => ({}) }) as Response;
      }
      if (url.includes("/publico/locais")) {
        return { ok: true, status: 200, json: async () => ({ locais: LOCAIS }) } as Response;
      }
      enviados.push(JSON.parse(String(init?.body ?? "{}")));
      return { ok: true, status: 201, json: async () => RECIBO } as Response;
    })
  );
}

beforeEach(() => {
  codigoDaUrl = "AB2CD3";
  consultas = [];
  avaliacoes = [];
  enviados = [];
  respostaDaAvaliacao = 201;
  conviteGoogle = false;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function botao(nome: string | RegExp) {
  return screen.getByRole("button", { name: nome }) as HTMLButtonElement;
}

/** Do passo 1 até o "Quando e onde". */
function ateOQuandoEOnde(identificacao: RegExp = /Anônimo/) {
  fireEvent.click(botao(identificacao));
  fireEvent.click(botao("Continuar"));
  fireEvent.click(botao("Sobre mim"));
  fireEvent.click(botao("Continuar"));
}

/** Do "Quando e onde" até o envio, com o lugar que já veio preenchido. */
async function terminarEEnviar(identificado = false) {
  await waitFor(() => expect(onde().value).toBe("Emergência adulta"));
  fireEvent.click(botao("Tarde"));
  fireEvent.click(botao("Continuar"));
  fireEvent.change(screen.getByLabelText("Seu relato"), {
    target: { value: "Esperei duas horas." },
  });
  fireEvent.click(botao("Uma resposta"));
  fireEvent.click(botao("Continuar"));
  if (identificado) {
    fireEvent.change(screen.getByLabelText("Seu nome"), { target: { value: "Maria Souza" } });
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "maria@exemplo.com" } });
  }
  fireEvent.click(botao(/Enviar manifestação/));
  await waitFor(() => expect(enviados).toHaveLength(1));
}

function onde() {
  return screen.getByLabelText("Onde foi?") as HTMLSelectElement;
}

/** Dá a nota e manda a avaliação pela tela N2. */
async function avaliar(nota: number) {
  fireEvent.click(await screen.findByRole("button", { name: `Nota ${nota}` }));
  fireEvent.click(botao("Enviar avaliação"));
  await waitFor(() => expect(avaliacoes).toHaveLength(1));
}

describe("a tela de nota (N1 e N2)", () => {
  it("abre com o nome público e o título do cartaz daquele ponto", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    expect(await screen.findByText("Emergência adulta")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Um minuto para nos contar" })).toBeTruthy();
    for (const nota of [1, 2, 3, 4, 5]) {
      expect(botao(`Nota ${nota}`)).toBeTruthy();
    }
    expect(screen.getByText("Muito ruim")).toBeTruthy();
    expect(screen.getByText("Muito bom")).toBeTruthy();
  });

  it("tocar na nota avança para os motivos, e enviar grava a avaliação sem abrir manifestação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    fireEvent.click(await screen.findByRole("button", { name: "Nota 2" }));
    expect(screen.getByText("O que mais marcou seu atendimento?")).toBeTruthy();
    fireEvent.click(botao("Tempo de espera"));
    fireEvent.click(botao("Limpeza"));
    fireEvent.change(screen.getByLabelText(/Quer contar mais/), {
      target: { value: "  Demorou muito.  " },
    });
    fireEvent.click(botao("Enviar avaliação"));

    await waitFor(() => expect(avaliacoes).toHaveLength(1));
    expect(avaliacoes[0].url).toBe("/api/ouvidoria/publico/pontos/AB2CD3/avaliacoes");
    expect(avaliacoes[0].corpo).toEqual({
      nota: 2,
      motivos: ["tempo_espera", "limpeza"],
      comentario: "Demorou muito.",
    });
    expect(enviados).toEqual([]);
  });

  it("Pular grava só a nota", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    fireEvent.click(await screen.findByRole("button", { name: "Nota 4" }));
    fireEvent.click(botao("Limpeza"));
    fireEvent.click(botao("Pular"));

    await waitFor(() => expect(avaliacoes).toHaveLength(1));
    expect(avaliacoes[0].corpo).toEqual({ nota: 4 });
  });

  it("o código digitado em minúscula vai em maiúscula, como o cartaz imprime", async () => {
    codigoDaUrl = "ab2cd3";
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    await avaliar(3);

    expect(avaliacoes[0].url).toBe("/api/ouvidoria/publico/pontos/AB2CD3/avaliacoes");
  });

  it("a nota recusada pelo limite diz o que aconteceu e oferece a manifestação", async () => {
    respostaDaAvaliacao = 429;
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    await avaliar(2);

    expect(await screen.findByText(/Já recebemos algumas notas deste cartaz/)).toBeTruthy();
    fireEvent.click(botao("Registrar uma manifestação"));
    expect(await screen.findByRole("heading", { name: "Identificação" })).toBeTruthy();
  });
});

describe("depois de enviar (N3)", () => {
  it("nota 1 a 3 pergunta se quer retorno, e Não, obrigado encerra sem manifestação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    await avaliar(2);

    expect(await screen.findByText(/Sua avaliação já chegou à Ouvidoria/)).toBeTruthy();
    expect(screen.getByText("Quer que a Ouvidoria entre em contato?")).toBeTruthy();
    expect(screen.queryByText(/elogio/i)).toBeNull();
    fireEvent.click(botao("Não, obrigado"));
    expect(await screen.findByText(/Pode fechar esta página/)).toBeTruthy();
    expect(enviados).toEqual([]);
  });

  it("Sim, quero retorno leva à manifestação, e o caso vai ligado à avaliação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(1);

    fireEvent.click(await screen.findByRole("button", { name: "Sim, quero retorno" }));
    ateOQuandoEOnde(/Com identificação/);
    await terminarEEnviar(true);

    expect(enviados[0]).toMatchObject({ p: "AB2CD3", avaliacao_id: "avaliacao-7", anonimo: false });
  });

  it("seguindo anônimo, a manifestação não leva a ligação com a avaliação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(3);

    fireEvent.click(await screen.findByRole("button", { name: "Sim, quero retorno" }));
    ateOQuandoEOnde(/Anônimo/);
    await terminarEEnviar();

    expect(enviados[0]).toMatchObject({ anonimo: true });
    expect(enviados[0]).not.toHaveProperty("avaliacao_id");
  });

  it("nota 4 ou 5 agradece e oferece o elogio, já escolhido na manifestação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(5);

    expect(await screen.findByText("Obrigado por nos contar.")).toBeTruthy();
    expect(screen.queryByText("Quer que a Ouvidoria entre em contato?")).toBeNull();
    fireEvent.click(botao("Quer deixar um elogio para a equipe?"));
    fireEvent.click(botao(/Com identificação/));
    fireEvent.click(botao("Continuar"));

    expect(botao("Elogio").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(botao("Sobre mim"));
    fireEvent.click(botao("Continuar"));
    await terminarEEnviar(true);
    expect(enviados[0]).toMatchObject({ natureza_informada: "elogio", avaliacao_id: "avaliacao-7" });
  });
});

describe("o convite ao Google (issue #1625)", () => {
  const TEXTO_DO_CONVITE = "Se quiser, conte também no Google. Isso ajuda outras pessoas a nos conhecer.";

  it("com o teste ligado, a nota 4 ou 5 mostra o convite, e o botão passa pela rota que conta o clique", async () => {
    conviteGoogle = true;
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(4);

    expect(await screen.findByText(TEXTO_DO_CONVITE)).toBeTruthy();
    const link = screen.getByRole("link", { name: "Avaliar no Google" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/api/ouvidoria/publico/avaliacoes/avaliacao-7/convite-google");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    // O elogio continua oferecido.
    expect(botao("Quer deixar um elogio para a equipe?")).toBeTruthy();
  });

  it("com o teste desligado, a nota 5 não mostra o convite", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(5);

    expect(await screen.findByText("Obrigado por nos contar.")).toBeTruthy();
    expect(screen.queryByText(TEXTO_DO_CONVITE)).toBeNull();
    expect(screen.queryByRole("link", { name: "Avaliar no Google" })).toBeNull();
  });

  it("nota de 1 a 3 nunca mostra o convite", async () => {
    conviteGoogle = true;
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);
    await avaliar(3);

    expect(await screen.findByText("Quer que a Ouvidoria entre em contato?")).toBeTruthy();
    expect(screen.queryByText(TEXTO_DO_CONVITE)).toBeNull();
    expect(screen.queryByRole("link", { name: "Avaliar no Google" })).toBeNull();
  });
});

describe("o atalho e o cartaz aposentado", () => {
  it("Prefiro registrar uma manifestação vai direto, sem nota e sem ligação", async () => {
    servidor(CARTAZ);
    render(<EnderecoCurtoDoCartaz />);

    fireEvent.click(await screen.findByRole("button", { name: "Prefiro registrar uma manifestação" }));
    ateOQuandoEOnde();
    await terminarEEnviar();

    expect(avaliacoes).toEqual([]);
    expect(enviados[0]).toMatchObject({ p: "AB2CD3", local_informado: "Emergência adulta" });
    expect(enviados[0]).not.toHaveProperty("avaliacao_id");
  });

  it("de ponto aposentado, abre a manifestação direto, com o lugar em branco", async () => {
    servidor(null);
    render(<EnderecoCurtoDoCartaz />);

    expect(await screen.findByRole("heading", { name: "Identificação" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Nota 1" })).toBeNull();
    ateOQuandoEOnde();
    expect(onde().value).toBe("");
  });

  it("de cartaz sem nome público, não oferece nem escolhe o rótulo do ponto", async () => {
    // Sem nome público, o servidor devolve o rótulo do ponto, que não está na
    // lista de locais. No anônimo, "Poltrona 12" reidentifica (issue #375,
    // item 12): o lugar fica para a pessoa escolher.
    servidor({ nome_publico: "Poltrona 12", titulo_cartaz: "atendimento_hoje" });
    render(<EnderecoCurtoDoCartaz />);
    fireEvent.click(await screen.findByRole("button", { name: "Prefiro registrar uma manifestação" }));

    ateOQuandoEOnde();
    await screen.findByRole("option", { name: "Centro Médico" });

    expect(onde().value).toBe("");
    expect(screen.queryByRole("option", { name: "Poltrona 12" })).toBeNull();
  });

  it("nunca mostra o nome do setor", async () => {
    // Um servidor antigo devolvia o setor. A página só lê o nome público.
    servidor({ setor: "Recepção", ponto: "Poltrona 12" });
    render(<EnderecoCurtoDoCartaz />);

    await screen.findByRole("button", { name: "Nota 1" });
    expect(screen.queryByText("Recepção")).toBeNull();
  });
});
