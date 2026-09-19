/**
 * @vitest-environment jsdom
 */

/**
 * Os Contatos gerados na tela Dados do Google (issue #818).
 *
 * Porte do teste dos contatos da Central antiga (`ContactsBreakdown.test.tsx`).
 * O estado de cada canal chega pronto do backend: só o medido traz número, e
 * a tela nunca escreve zero para o que não é medido.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CanaisDeContato, type ContatoDoPayload } from "./CanaisDeContato";

afterEach(cleanup);

const CONTATOS: ContatoDoPayload[] = [
  { chave: "agendar", rotulo: "Cliques para agendar", estado: "em-construcao" },
  { chave: "whatsapp", rotulo: "WhatsApp", estado: "medido", cliques: 4514 },
  { chave: "fale-conosco", rotulo: "Fale Conosco", estado: "medido", cliques: 2272 },
  { chave: "telefone", rotulo: "Telefone", estado: "nao-medido" },
];

const itens = () => within(screen.getByRole("list", { name: "Contatos gerados por canal" })).getAllByRole("listitem");

describe("CanaisDeContato", () => {
  it("mostra os canais na ordem recebida, com o rótulo de cada um", () => {
    render(<CanaisDeContato contatos={CONTATOS} />);

    expect(itens()).toHaveLength(4);
    expect(itens().map((item) => within(item).getByTestId("rotulo").textContent)).toEqual([
      "Cliques para agendar",
      "WhatsApp",
      "Fale Conosco",
      "Telefone",
    ]);
  });

  it("o canal medido mostra os cliques em pt-BR e o selo de medido", () => {
    render(<CanaisDeContato contatos={CONTATOS} />);

    expect(within(itens()[1]).getByText("4.514")).toBeTruthy();
    expect(within(itens()[1]).getByText("medido")).toBeTruthy();
    expect(within(itens()[2]).getByText("2.272")).toBeTruthy();
  });

  it("o canal em construção diz isso, sem número nem selo de medido", () => {
    render(<CanaisDeContato contatos={CONTATOS} />);

    const agendar = itens()[0];
    expect(within(agendar).getByText("em construção")).toBeTruthy();
    expect(within(agendar).queryByText("medido")).toBeNull();
    expect(within(agendar).queryByText(/\d/)).toBeNull();
  });

  it("o canal não medido diz isso, e não inventa número, nem zero", () => {
    render(<CanaisDeContato contatos={[{ chave: "telefone", rotulo: "Telefone", estado: "nao-medido" }]} />);

    const telefone = itens()[0];
    expect(within(telefone).getByText("não medido")).toBeTruthy();
    expect(within(telefone).queryByText(/\d/)).toBeNull();
    expect(within(telefone).queryByText("medido")).toBeNull();
  });

  it("traz a nota que explica os três estados", () => {
    render(<CanaisDeContato contatos={CONTATOS} />);

    expect(screen.getByText(/nunca aparecem como zero/)).toBeTruthy();
  });
});
