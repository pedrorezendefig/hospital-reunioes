/**
 * @vitest-environment jsdom
 */

/**
 * O seletor de período da Central de Comando (issue #814, ADR 0058).
 *
 * Porte de `PeriodSelector.test.tsx` do repositório antigo: o período mora no
 * endereço (`?periodo=`), para o link guardado abrir no mesmo período e o
 * recarregar não voltar para o padrão.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SeletorDePeriodo } from "./SeletorDePeriodo";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const VISAO_GERAL = "/admin/central-de-comando/visao-geral";

afterEach(cleanup);

describe("SeletorDePeriodo", () => {
  it("mostra 7, 28 e 90 dias, cada um levando ao próprio ?periodo", () => {
    render(<SeletorDePeriodo ativo="28d" caminho={VISAO_GERAL} />);

    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("href")).toBe(`${VISAO_GERAL}?periodo=7d`);
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("href")).toBe(`${VISAO_GERAL}?periodo=28d`);
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("href")).toBe(`${VISAO_GERAL}?periodo=90d`);
  });

  it("marca o período ativo, e só ele", () => {
    render(<SeletorDePeriodo ativo="7d" caminho={VISAO_GERAL} />);

    expect(screen.getByRole("link", { name: "7 dias" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "28 dias" }).getAttribute("aria-current")).toBeNull();
    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("aria-current")).toBeNull();
  });

  it("respeita o caminho da tela", () => {
    render(<SeletorDePeriodo ativo="28d" caminho="/admin/central-de-comando/dados-do-google" />);

    expect(screen.getByRole("link", { name: "90 dias" }).getAttribute("href")).toBe(
      "/admin/central-de-comando/dados-do-google?periodo=90d",
    );
  });

  it("limita as opções quando a tela passa os períodos dela (o Instagram não tem 90 dias)", () => {
    render(<SeletorDePeriodo ativo="28d" caminho="/admin/central-de-comando/instagram" periodos={["7d", "28d"]} />);

    expect(screen.getByRole("link", { name: "7 dias" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "28 dias" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "90 dias" })).toBeNull();
  });
});
