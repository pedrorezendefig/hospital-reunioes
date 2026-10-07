/**
 * @vitest-environment jsdom
 */

/**
 * Status da pendência em caixa alta e acentuado (issue #1055).
 *
 * O rótulo sai do PENDENCIA_STATUS_CONFIG, que a lista, o kanban e o modal de
 * detalhe também usam; o badge é a vitrine dele.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { StatusPendencia } from "@/types";
import { StatusBadge } from "./StatusBadge";

afterEach(cleanup);

const ESPERADO: [StatusPendencia, string][] = [
  ["PENDENTE", "PENDENTE"],
  ["EM_PROGRESSO", "EM PROGRESSO"],
  ["CONCLUIDO", "CONCLUÍDO"],
  ["ATRASADO", "ATRASADO"],
  ["CANCELADO", "CANCELADO"],
  ["REPACTUADA", "REPACTUADA"],
];

describe("badge de status da pendência", () => {
  it.each(ESPERADO)("%s aparece como %s", (status, rotulo) => {
    const { container } = render(<StatusBadge status={status} />);

    expect(container.textContent).toBe(rotulo);
    expect(screen.getByText(rotulo)).toBeTruthy();
  });
});
