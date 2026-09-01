/**
 * @vitest-environment jsdom
 */

/**
 * A fila da Ouvidoria e o caminho para o caso (issue #476, PRD #468).
 *
 * O detalhe da manifestação era um modal sobre esta lista: sem URL, sem
 * voltar do navegador e sem link para o email de cobrança apontar. Esta suíte
 * trava o que mudou aqui, que é a saída da lista: um link de verdade para o
 * endereço do caso.
 *
 * Um `<a href>` é justamente o que um teste pega e um humano olhando a tela
 * não distingue de um botão. Sem este arquivo, alguém trocaria o link de volta
 * por um `onClick` e a suíte seguiria verde.
 */

import { cleanup, render, screen } from "@testing-library/react";
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

const INDICE = {
  protocolos: [
    {
      id: "uuid-7",
      numero: 7,
      protocolo: "2026-0007",
      data_abertura: "2026-08-14",
      prazo_resposta: "2026-08-21",
      status: "em_classificacao",
      tipo_manifestacao: null,
      sigilo_reforcado: false,
      categoria: "A classificar",
      setor: "A definir",
      resumo: "Paciente relata espera acima de duas horas na recepção.",
      conversa_id: "",
      gravidade: null,
      prazo_area_em: null,
      prazo_estourado: false,
      rotulo_prazo: "",
      minutos_uteis_restantes: null,
    },
  ],
};

function montar() {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => INDICE }) as Response));
  render(<OuvidoriaPage />);
}

describe("a fila da Ouvidoria leva ao caso por endereço (issue #476)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "ouvidor";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("abrir a manifestação é navegar para a página do caso, pelo protocolo", async () => {
    montar();

    const abrir = await screen.findByRole("link", { name: /Abrir manifestação/ });
    expect(abrir.getAttribute("href")).toBe("/ouvidoria/m/2026-0007");
  });

  it("quem está fora da Ouvidoria vê a linha do índice, mas não o caminho do caso", async () => {
    sessao.perfilOuvidoria = null;
    montar();

    // A linha aparece: o índice é da equipe de Reuniões inteira (ADR 0034).
    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Abrir manifestação/ })).toBeNull();
  });
});
