/**
 * @vitest-environment jsdom
 */

/**
 * O bloco AGUARDANDO SEU ENCERRAMENTO no topo da fila (issue #486, PRD #470,
 * RN-67).
 *
 * O trabalho do dia do ouvidor é o caso que a área respondeu e que ele ainda
 * não olhou. Antes disso ele descia a fila inteira para achá-lo. Agora o bloco
 * traz esses casos para cima de tudo, com o total no cabeçalho, e some sozinho
 * quando não há nenhum.
 *
 * Toda consulta desta suíte é ancorada na região do bloco (`within` do
 * `aria-label` dele), e nunca na página inteira: o caso destacado continua no
 * grupo de estado dele, então um `screen.getByText` do protocolo acharia a
 * linha do grupo e passaria com o bloco apagado.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "./page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: null as string | null }));

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

const BLOCO = /aguardando seu encerramento/i;

function linha(
  numero: number,
  status: string,
  temNovidade: boolean,
  resumo = `Caso numero ${numero}.`
) {
  return {
    id: `uuid-${numero}`,
    numero,
    protocolo: `2026-${String(numero).padStart(4, "0")}`,
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status,
    tipo_manifestacao: "reclamacao",
    sigilo_reforcado: false,
    categoria: "Demora",
    setor: "Recepcao",
    resumo,
    conversa_id: "",
    gravidade: null,
    prazo_area_em: null,
    prazo_estourado: false,
    rotulo_prazo: "",
    minutos_uteis_restantes: null,
    tem_novidade: temNovidade,
  };
}

function montar(protocolos: ReturnType<typeof linha>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({ ok: true, status: 200, json: async () => ({ protocolos, degradado: [] }) }) as Response
    )
  );
  render(<OuvidoriaPage />);
}

/**
 * A primeira carga vem boa e a recarga seguinte falha: o estado em que a tela
 * tem lista velha na memória E o aviso de falha na tela.
 */
function montarComRecargaQuebrada(protocolos: ReturnType<typeof linha>[]) {
  let cargas = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/transicoes")) {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      cargas += 1;
      if (cargas === 1) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ protocolos, degradado: [] }),
        } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    })
  );
  render(<OuvidoriaPage />);
}

describe("bloco aguardando seu encerramento (issue #486)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "ouvidor";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("destaca o caso respondido com novidade, e só ele", async () => {
    montar([
      linha(7, "respondido", true),
      linha(8, "respondido", false),
      linha(9, "aguardando_area", true),
    ]);

    const bloco = within(await screen.findByRole("region", { name: BLOCO }));

    expect(bloco.getByText("2026-0007")).toBeTruthy();
    expect(bloco.queryByText("2026-0008")).toBeNull();
    expect(bloco.queryByText("2026-0009")).toBeNull();
  });

  it("o cabeçalho conta os casos do bloco, e não a fila inteira", async () => {
    montar([
      linha(7, "respondido", true),
      linha(8, "respondido", true),
      linha(9, "aguardando_area", true),
      linha(10, "encerrado", true),
    ]);

    const bloco = within(await screen.findByRole("region", { name: BLOCO }));

    expect(bloco.getByText("2 manifestações")).toBeTruthy();
  });

  it("um caso só é contado no singular", async () => {
    montar([linha(7, "respondido", true)]);

    const bloco = within(await screen.findByRole("region", { name: BLOCO }));

    expect(bloco.getByText("1 manifestação")).toBeTruthy();
  });

  it("some quando nenhum caso espera o encerramento", async () => {
    montar([linha(8, "respondido", false), linha(9, "aguardando_area", true)]);

    expect(await screen.findByText("2026-0008")).toBeTruthy();
    expect(screen.queryByRole("region", { name: BLOCO })).toBeNull();
  });

  it("caso aberto pelo ouvidor sai do bloco e continua na fila", async () => {
    // Abrir o Dossiê carimba o visto (issue #484), e a carga seguinte traz o
    // mesmo caso sem novidade: ele sai do destaque sem sair da lista.
    montar([linha(7, "respondido", false)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByRole("region", { name: BLOCO })).toBeNull();
  });

  it("fica acima de todos os grupos de estado", async () => {
    montar([linha(7, "respondido", true), linha(9, "aguardando_area", true)]);

    const bloco = await screen.findByRole("region", { name: BLOCO });
    const primeiroGrupo = screen.getByText("Aguardando área");

    // DOCUMENT_POSITION_FOLLOWING: o grupo vem DEPOIS do bloco na página.
    expect(bloco.compareDocumentPosition(primeiroGrupo) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  it("é destaque e não filtro: o caso destacado continua no grupo Respondida", async () => {
    montar([linha(7, "respondido", true)]);

    await screen.findByRole("region", { name: BLOCO });

    // Uma vez no bloco, outra na linha do grupo de estado.
    expect(screen.getAllByText("2026-0007")).toHaveLength(2);
    expect(screen.getByText("Respondida")).toBeTruthy();
  });

  it("o encerramento do caso destacado sai dentro do próprio bloco", async () => {
    // O bloco existe para o ouvidor agir sem descer a fila. Sem o botão aqui,
    // ele viraria só um aviso e a viagem até o grupo continuaria.
    montar([linha(7, "respondido", true)]);

    const bloco = within(await screen.findByRole("region", { name: BLOCO }));

    expect(bloco.getByRole("button", { name: /encerrar/i })).toBeTruthy();
  });

  it("quem está fora da Ouvidoria não recebe novidade e não vê o bloco", async () => {
    // O backend desliga a flag para esse público (issue #484), e o bloco fala
    // do encerramento, que é ato da Ouvidoria.
    sessao.perfilOuvidoria = null;
    montar([linha(7, "respondido", false)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByRole("region", { name: BLOCO })).toBeNull();
  });
  it("a recarga que falhou leva o bloco junto, e não deixa dado velho no topo", async () => {
    // O ouvidor encerra um caso e a recarga falha. O card abaixo já avisa que
    // não foi possível carregar; o bloco no topo não pode seguir mostrando a
    // fila velha com o botão Encerrar aceso, convidando a agir sobre um estado
    // que não vale mais. Duas histórias na mesma tela, e a de cima é a falsa.
    montarComRecargaQuebrada([linha(7, "respondido", true)]);

    const bloco = within(await screen.findByRole("region", { name: BLOCO }));
    fireEvent.click(bloco.getByRole("button", { name: "Encerrar" }));

    fireEvent.click(await screen.findByRole("button", { name: "Improcedente" }));
    // O rótulo mudou na issue #494: o campo passou a sair do hospital por
    // email, e a tela deixou de apresentá-lo como registro interno.
    fireEvent.change(screen.getByLabelText(/desfecho para o manifestante/i), {
      target: { value: "Apurado com a área e sem procedência." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Encerrar caso" }));

    await waitFor(() =>
      expect(screen.getByText("Não foi possível carregar as manifestações")).toBeTruthy()
    );
    expect(screen.queryByRole("region", { name: BLOCO })).toBeNull();
  });
});
