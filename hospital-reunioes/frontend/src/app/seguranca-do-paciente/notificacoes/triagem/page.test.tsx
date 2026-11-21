/**
 * @vitest-environment jsdom
 */

/**
 * As telas da triagem (issue #1992) abrem com a linha de orientação da seção
 * 17 da especificação, e só para quem tem o recurso de triagem. A entrada da
 * fila fica em Notificações, para quem confirma a triagem.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";

import FilaDeTriagemPage from "./page";
import TriagemDoCasoPage from "../[id]/triagem/page";
import NotificacoesPage from "../page";

const sessao = vi.hoisted(() => ({ participante: null as CurrentParticipante | null }));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({ participante: sessao.participante, loading: false, error: null }),
}));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "c1" }) }));
vi.mock("@/components/seguranca-do-paciente/FilaDeTriagem", () => ({ FilaDeTriagem: () => <p>A fila</p> }));
vi.mock("@/components/seguranca-do-paciente/TriagemDoCaso", () => ({ TriagemDoCaso: () => <p>O caso</p> }));
vi.mock("@/components/seguranca-do-paciente/NotificacoesDoNucleo", () => ({
  NotificacoesDoNucleo: () => <p>Os casos</p>,
}));
vi.mock("@/components/seguranca-do-paciente/RegistroRapido", () => ({ RegistroRapido: () => <p>O registro</p> }));

function entrar(recursos: string[]) {
  sessao.participante = { id: "p1", nome_completo: "Pessoa de Teste", email: "pessoa@hsm", recursos_nsp: recursos };
}

afterEach(() => {
  cleanup();
  sessao.participante = null;
});

// O texto literal da seção 17 da especificação (tela "Fila de triagem"), e não a
// constante: trocar o texto da tela tem que quebrar este teste.
const LINHA_DA_SECAO_17 =
  "Leia o relato, confira a sugestão e confirme. Se discordar, ajuste: o sistema aprende com a diferença.";

describe("as telas da triagem", () => {
  it.each([
    ["a fila", FilaDeTriagemPage, "Fila de triagem", "A fila"],
    ["o caso", TriagemDoCasoPage, "Triagem", "O caso"],
  ] as const)("%s abre com a linha de orientação da seção 17", (_nome, Pagina, titulo, conteudo) => {
    entrar(["ver_modulo", "casos", "triagem"]);
    render(<Pagina />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(titulo);
    expect(screen.getByText(LINHA_DA_SECAO_17).tagName).toBe("P");
    expect(screen.getByText(conteudo)).toBeTruthy();
  });

  it("o membro sem o recurso de triagem não abre a fila", () => {
    entrar(["ver_modulo", "casos"]);
    render(<FilaDeTriagemPage />);

    expect(screen.queryByText("A fila")).toBeNull();
    expect(screen.getByText("Esta tela ainda não está liberada para você.")).toBeTruthy();
  });

  it.each([
    ["a Presidência", ["ver_modulo", "casos", "triagem"], true],
    ["o membro", ["ver_modulo", "casos"], false],
  ] as const)("em Notificações, %s vê a entrada da fila: %s", (_quem, recursos, ve) => {
    entrar([...recursos]);
    render(<NotificacoesPage />);

    const link = screen.queryByRole("link", { name: "Fila de triagem" });
    expect(link !== null).toBe(ve);
    if (link) expect(link.getAttribute("href")).toBe("/seguranca-do-paciente/notificacoes/triagem");
  });
});
