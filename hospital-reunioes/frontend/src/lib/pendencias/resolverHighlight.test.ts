import { describe, expect, it, vi } from "vitest";
import { resolverHighlight } from "./resolverHighlight";

type P = { id_acao: string; descricao?: string };

describe("resolverHighlight (clique na notificação abre o card certo, issue #270)", () => {
  it("abre a pendência quando ela já está entre as carregadas, sem buscar no backend", async () => {
    const carregadas: P[] = [{ id_acao: "A001" }, { id_acao: "A002" }];
    const buscar = vi.fn();

    const resultado = await resolverHighlight("A002", carregadas, buscar);

    expect(resultado).toEqual({ acao: "abrir", pendencia: { id_acao: "A002" } });
    expect(buscar).not.toHaveBeenCalled();
  });

  it("busca no backend quando a pendência não veio no board (board truncado ou vazio)", async () => {
    const buscar = vi.fn(async (id: string): Promise<P | null> => ({ id_acao: id, descricao: "Revisar escala" }));

    const resultado = await resolverHighlight("A777", [], buscar);

    expect(buscar).toHaveBeenCalledWith("A777");
    expect(resultado).toEqual({
      acao: "abrir",
      pendencia: { id_acao: "A777", descricao: "Revisar escala" },
    });
  });

  it("sinaliza não encontrada quando o backend nega (excluída ou sem acesso)", async () => {
    const buscar = vi.fn(async (): Promise<P | null> => null);

    const resultado = await resolverHighlight("A404", [{ id_acao: "A001" }], buscar);

    expect(resultado).toEqual({ acao: "nao-encontrada" });
  });
});
