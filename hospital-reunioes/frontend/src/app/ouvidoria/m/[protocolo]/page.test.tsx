/**
 * @vitest-environment jsdom
 */

/**
 * A página do caso, endereçada pelo protocolo (issue #476, PRD #468, RN-53).
 *
 * O que esta suíte cobre é a fiação da página, que é justamente o que sumiria
 * sem ninguém notar: o endereço da URL virar o caso na tela, e cada recusa do
 * backend virar a mensagem certa em vez de uma tela em branco.
 *
 * Os quatro caminhos da issue estão aqui na ponta da tela; a régua de quem
 * pode ver o quê é do backend, e tem suíte própria em
 * `test_ouvidoria_pagina_do_caso.py`. Aqui se prova que a página respeita a
 * resposta dele: caso negado não mostra pedaço nenhum do Dossiê.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PaginaDoCaso from "./page";

const rota = vi.hoisted(() => ({ protocolo: "2026-0007" }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ protocolo: rota.protocolo }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

const RELATO = "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.";

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-7",
    protocolo: "2026-0007",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "em_classificacao",
    tipo_manifestacao: null,
    categoria: "A classificar",
    setor: "A definir",
    resumo: "Paciente relata espera acima de duas horas na recepção.",
    relato_integral: RELATO,
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "(31) 99999-0000",
    manifestante_vinculo: "acompanhante",
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: null,
    desfecho_descricao: null,
    gravidade: null,
    prazo_area_em: null,
    validada_em: null,
    respondida_em: null,
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: null,
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "ana",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    ...overrides,
  };
}

function respostaJson(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body } as Response;
}

/** As URLs que a página pediu, na ordem. É por elas que se prova o endereço. */
const pedidos: string[] = [];

function montar(dossie: { corpo: unknown; status?: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      pedidos.push(url);
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      return respostaJson(dossie.corpo, dossie.status ?? 200);
    })
  );
  render(<PaginaDoCaso />);
}

describe("a página do caso por protocolo (issue #476)", () => {
  beforeEach(() => {
    pedidos.length = 0;
    rota.protocolo = "2026-0007";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("protocolo válido: o caso da URL vira o Dossiê na tela", async () => {
    montar({ corpo: caso() });

    // O relato primeiro: é o que só existe depois de o caso chegar. Esperar
    // pelo título seria esperar por nada, porque o cabeçalho já mostra o
    // protocolo da URL enquanto carrega.
    expect(await screen.findByText(RELATO)).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Manifestação 2026-0007/ })).toBeTruthy();
    expect(screen.getByText("Joana da Silva")).toBeTruthy();
    // O caso é procurado pelo protocolo da URL, e não por um id que a página
    // teria de aprender na lista: é isso que faz o link do email funcionar.
    expect(pedidos).toContain("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007");
  });

  it("protocolo inexistente: diz que não encontrou, sem inventar caso", async () => {
    montar({ corpo: { detail: "Manifestação não encontrada" }, status: 404 });

    expect(await screen.findByText(/não encontrada/i)).toBeTruthy();
    expect(screen.queryByText(RELATO)).toBeNull();
  });

  it("sem Perfil da Ouvidoria: a recusa aparece e nada do caso vaza junto", async () => {
    montar({ corpo: { detail: "Acesso restrito à Ouvidoria" }, status: 403 });

    expect(await screen.findByText(/perfil não permite/i)).toBeTruthy();
    expect(screen.queryByText(RELATO)).toBeNull();
    expect(screen.queryByText("Joana da Silva")).toBeNull();
  });

  it("caso sigiloso aberto por quem pode mostra o aviso de sigilo", async () => {
    montar({ corpo: caso({ sigilo_reforcado: true, tipo_manifestacao: "denuncia" }) });

    expect(
      await screen.findByText(/restrito ao Ouvidor e à Diretoria Executiva/)
    ).toBeTruthy();
    expect(screen.getByText(RELATO)).toBeTruthy();
  });

  it("as ações do caso vêm junto com o caso, e não só na linha da lista", async () => {
    // Quem chega pelo link do email cai aqui direto: sem os botões na página,
    // validar e encerrar exigiriam voltar para a fila e achar a linha.
    montar({ corpo: caso({ status: "em_classificacao" }) });

    expect(await screen.findByText(RELATO)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Validar e acionar/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Encerrar$/ })).toBeTruthy();
  });

  it("caso já encerrado não oferece ação de encerrar nem de validar", async () => {
    montar({ corpo: caso({ status: "encerrado", desfecho: "resolvido" }) });

    expect(await screen.findByText(RELATO)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Validar e acionar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Encerrar$/ })).toBeNull();
  });

  it("a volta para a fila é um link de verdade, para o voltar do navegador servir", async () => {
    montar({ corpo: caso() });

    const voltar = await screen.findByRole("link", { name: /Painel da Ouvidoria/ });
    expect(voltar.getAttribute("href")).toBe("/ouvidoria");
  });
});
