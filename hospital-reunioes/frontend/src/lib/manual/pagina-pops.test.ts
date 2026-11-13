/**
 * A página de POPs do manual (issue #1722, ADR 0094, decisões 4 e 5).
 *
 * Lê a página de verdade, em `public/manual/pops/pagina.md`, e o roteiro que
 * refaz os prints dela, em `scripts/manual/pops/`. Quem vê a página, o que
 * cada tarefa traz e a origem dos prints são promessas desta página; as que
 * valem para toda página (módulo no menu, imagem existente) moram em
 * `paginas.test.ts`.
 */

import { describe, expect, it } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import { paginasVisiveis } from "./paginas";

function pessoa(campos: Partial<CurrentParticipante>): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
    ...campos,
  };
}

const PAGINAS = carregarPaginasDoManual();
const POPS = PAGINAS.find((pagina) => pagina.pasta === "pops");

describe("a página de POPs", () => {
  it("existe e declara o módulo POPs", () => {
    expect(POPS?.modulo).toBe("pops");
    expect(POPS?.titulo).toBe("POPs");
  });

  it("aparece para quem acessa POPs e some para quem não acessa", () => {
    const dePops = paginasVisiveis(PAGINAS, pessoa({ access_profile: null, perfil_pop: "coordenador" }));
    const facilitador = paginasVisiveis(PAGINAS, pessoa({ access_profile: "regular" }));

    expect(dePops.map((p) => p.pasta)).toContain("pops");
    expect(facilitador.map((p) => p.pasta)).not.toContain("pops");
  });
});
