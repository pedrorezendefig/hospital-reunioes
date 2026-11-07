/**
 * @vitest-environment jsdom
 */

/**
 * O filtro de várias escolhas da Administração e a Caixa alta (issue #1455, ADR 0080).
 *
 * O filtro faz as vezes de um `select`: o botão mostra a escolha e a lista
 * mostra os nomes que vêm do banco (setor, cargo). Como é feito de botões, ele
 * herdaria a caixa alta da regra base; o nome do banco aparece como foi escrito.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { caixaDoDado } from "@/lib/testes/caixaDoDado";

import { MultiSelectFilter } from "./MultiSelectFilter";

afterEach(cleanup);

const SETORES = [
  { value: "s-1", label: "Centro Cirúrgico" },
  { value: "s-2", label: "Recepção da Emergência" },
];

describe("Caixa alta no filtro", () => {
  it("o nome escolhido e os nomes da lista aparecem como foram escritos", () => {
    render(<MultiSelectFilter label="Setor" options={SETORES} value={["s-1"]} onChange={() => undefined} />);

    const escolhido = screen.getByText("Centro Cirúrgico");
    expect(caixaDoDado(escolhido)).toBe("normal-case");

    fireEvent.click(escolhido);
    expect(caixaDoDado(screen.getByRole("option", { name: "Recepção da Emergência" }))).toBe("normal-case");
  });
});
