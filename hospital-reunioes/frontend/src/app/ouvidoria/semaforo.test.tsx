/**
 * @vitest-environment jsdom
 */

/**
 * O semáforo de prazo na fila da Ouvidoria (issue #488, PRD #471, RN-58).
 *
 * A régua de quem acende qual cor vive em `lib/ouvidoria/prazo` e tem suíte
 * própria. Este arquivo trava a FIAÇÃO: que a linha pinta o que a régua diz.
 * Sem ele, alguém deixaria o "vence hoje" caindo no ramo neutro do `PrazoCell`
 * e a suíte da régua seguiria verde, com a tela mostrando cinza no caso que
 * precisa de resposta ainda hoje.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "./page";

/**
 * O fuso do PROCESSO, e não o do hospital: este arquivo finge um navegador
 * aberto fora do Brasil, que é a única situação em que o dia do navegador e o
 * dia do hospital chegam a discordar. Numa máquina em `America/Sao_Paulo` os
 * dois são o mesmo dia sempre, e o teste da virada passaria até com a leitura
 * errada, que é o buraco que ele existe para fechar.
 */
const FUSO_DO_PROCESSO = process.env.TZ;
process.env.TZ = "UTC";
afterAll(() => {
  // `TZ` não existe no ambiente do dev nem no do CI, e atribuir `undefined` a
  // uma variável de ambiente grava a STRING "undefined": o processo ficaria
  // pinado num fuso inválido para os arquivos jsdom que rodam depois no mesmo
  // fork. Ausente se restaura apagando, não escrevendo.
  if (FUSO_DO_PROCESSO === undefined) delete process.env.TZ;
  else process.env.TZ = FUSO_DO_PROCESSO;
});

/** Uma terça qualquer, às 10h de Brasília. */
const AGORA = new Date("2026-08-25T13:00:00Z");

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
      perfil_ouvidoria: "ouvidor",
    },
    loading: false,
  }),
}));

const BASE = {
  data_abertura: "2026-08-20",
  prazo_resposta: "2026-09-30",
  status: "aguardando_area",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: "Paciente relata espera acima de duas horas.",
  conversa_id: "",
  gravidade: "media",
  prazo_estourado: false,
  minutos_uteis_restantes: 180,
  tem_novidade: false,
};

const INDICE = {
  protocolos: [
    {
      ...BASE,
      id: "uuid-1",
      numero: 1,
      protocolo: "2026-0001",
      prazo_area_em: "2026-08-24T20:00:00+00:00",
      prazo_estourado: true,
      rotulo_prazo: "vencido há 1 dia útil",
      minutos_uteis_restantes: 0,
    },
    {
      ...BASE,
      id: "uuid-2",
      numero: 2,
      protocolo: "2026-0002",
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 7 horas úteis",
    },
    {
      ...BASE,
      id: "uuid-3",
      numero: 3,
      protocolo: "2026-0003",
      prazo_area_em: "2026-08-26T20:00:00+00:00",
      rotulo_prazo: "vence em 1 dia útil",
      minutos_uteis_restantes: 540,
    },
    {
      ...BASE,
      id: "uuid-4",
      numero: 4,
      protocolo: "2026-0004",
      prazo_area_em: "2026-08-28T20:00:00+00:00",
      rotulo_prazo: "vence em 3 dias úteis",
      minutos_uteis_restantes: 3 * 540,
    },
    {
      ...BASE,
      id: "uuid-5",
      numero: 5,
      protocolo: "2026-0005",
      status: "encerrado",
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 7 horas úteis",
    },
  ],
};

/**
 * A linha inteira do protocolo, que é onde a cor de fundo do caso urgente
 * mora. Desde a issue #495 a fila é uma lista de dois níveis, e não mais uma
 * tabela: a linha é o `<li>`, e não o `<tr>`.
 */
async function linhaDe(protocolo: string): Promise<HTMLElement> {
  await screen.findByText(protocolo);
  const linha = document.querySelector<HTMLElement>(`[data-protocolo="${protocolo}"]`);
  if (!linha) throw new Error(`sem linha para o protocolo ${protocolo}`);
  return linha;
}

describe("o semáforo de prazo da fila (issue #488, RN-58)", () => {
  beforeEach(() => {
    // `shouldAdvanceTime` mantém o relógio andando sob o tempo falso: sem ele
    // o `findBy` do testing-library espera para sempre um timer que nunca corre.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => INDICE }) as Response)
    );
    render(<OuvidoriaPage />);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("caso vencido aparece em vermelho, com o carimbo de estourado", async () => {
    const linha = await linhaDe("2026-0001");

    expect(within(linha).getByText("Estourado")).toBeTruthy();
    expect(within(linha).getByText(/vencido há 1 dia útil/).className).toContain("text-red");
    expect(linha.className).toContain("bg-red-50");
  });

  it("caso que vence hoje aparece no mesmo vermelho, dito com outro carimbo", async () => {
    const linha = await linhaDe("2026-0002");

    expect(within(linha).getByText("Vence hoje")).toBeTruthy();
    expect(within(linha).queryByText("Estourado")).toBeNull();
    expect(within(linha).getByText(/vence em 7 horas úteis/).className).toContain("text-red");
    expect(linha.className).toContain("bg-red-50");
  });

  it("caso com um dia útil de folga aparece em âmbar, sem carimbo e sem fundo", async () => {
    const linha = await linhaDe("2026-0003");

    expect(within(linha).getByText(/vence em 1 dia útil/).className).toContain("text-amber");
    expect(within(linha).queryByText("Vence hoje")).toBeNull();
    expect(linha.className || "").not.toContain("bg-red-50");
  });

  it("caso com folga acima de um dia útil fica neutro, sem cor de alerta", async () => {
    const linha = await linhaDe("2026-0004");
    const prazo = within(linha).getByText(/vence em 3 dias úteis/).className;

    expect(prazo).not.toContain("text-red");
    expect(prazo).not.toContain("text-amber");
  });

  it("caso encerrado que venceria hoje segue sem semáforo: o relógio parou", async () => {
    const linha = await linhaDe("2026-0005");

    expect(within(linha).queryByText("Vence hoje")).toBeNull();
    expect(within(linha).queryByText("Estourado")).toBeNull();
    expect(linha.className || "").not.toContain("bg-red-50");
  });

  it("o contador do topo conta só o que rompeu, e não o que vence hoje", async () => {
    expect(await screen.findByText("1 com prazo estourado")).toBeTruthy();
  });
});

/**
 * A virada do dia (issue #488). Duas armadilhas moram aqui, e as duas só
 * aparecem quando o dia do navegador e o dia do hospital discordam:
 *
 * * ler "hoje" no fuso do navegador antecipa ou atrasa o vermelho de todo
 *   caso da fila;
 * * ler "hoje" uma vez só, na montagem, congela o semáforo: a fila deixada
 *   aberta atravessa a meia-noite mostrando as cores de ontem.
 */
describe("a virada do dia e o fuso de quem abre a fila (issue #488)", () => {
  /** Um caso que vence às 17h de 26/08, com um dia útil de folga. */
  const VENCE_EM_26 = {
    ...BASE,
    id: "uuid-9",
    numero: 9,
    protocolo: "2026-0009",
    prazo_area_em: "2026-08-26T20:00:00+00:00",
    rotulo_prazo: "vence em 1 dia útil",
    minutos_uteis_restantes: 540,
  };

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("navegador de outro fuso não antecipa o vermelho do hospital", async () => {
    // 02h UTC de 26/08 são 23h de 25/08 em Brasília: para o navegador o dia já
    // virou, para o hospital não. O caso vence no dia 26, que é amanhã no
    // hospital e hoje no navegador. Manda quem o hospital diz.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-08-26T02:00:00Z"));
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({ ok: true, status: 200, json: async () => ({ protocolos: [VENCE_EM_26] }) }) as Response
      )
    );
    render(<OuvidoriaPage />);

    const linha = await linhaDe("2026-0009");

    expect(within(linha).queryByText("Vence hoje")).toBeNull();
    expect(within(linha).getByText(/vence em 1 dia útil/).className).toContain("text-amber");
  });

  it("fila aberta antes da meia-noite repinta na carga seguinte", async () => {
    // A tela monta às 23h59 do dia 25 e a resposta da fila chega às 00h01 do
    // dia 26, já no hospital. O caso que vence no dia 26 passou de "amanhã"
    // para "hoje" no meio do caminho, e é a carga que manda, não a montagem.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-08-26T02:59:00Z"));
    let responder: (() => void) | null = null;
    const resposta = {
      ok: true,
      status: 200,
      json: async () => ({ protocolos: [VENCE_EM_26] }),
    } as Response;
    // Só a carga da FILA fica pendurada: a tela também lê o cadastro de
    // responsáveis (issue #495), e prender as duas na mesma variável faria a
    // segunda chamada roubar o gatilho da primeira.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (!String(url).includes("/protocolos")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as Response);
        }
        return new Promise<Response>((resolve) => {
          responder = () => resolve(resposta);
        });
      })
    );
    render(<OuvidoriaPage />);

    await vi.waitFor(() => expect(responder).not.toBeNull());
    vi.setSystemTime(new Date("2026-08-26T03:01:00Z"));
    responder!();

    const linha = await linhaDe("2026-0009");

    expect(within(linha).getByText("Vence hoje")).toBeTruthy();
    expect(linha.className).toContain("bg-red-50");
  });
});
