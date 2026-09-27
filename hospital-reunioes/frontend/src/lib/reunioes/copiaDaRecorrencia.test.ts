// A cópia que o painel Recorrência manda ao `agendar` (issue #761).
// Sem `facilitador_id`, o backend fazia de quem clicou o facilitador de toda a
// série, e a Secretária virava facilitadora de reuniões que não conduz. A série
// é a mesma reunião se repetindo: as cópias herdam o facilitador da original.
import { describe, expect, it } from "vitest";

import { copiaDaRecorrencia } from "./copiaDaRecorrencia";

const ORIGINAL = {
  titulo: "Diretoria",
  tipo: "Diretoria",
  objetivo: "Metas do mês",
  facilitador_id: "P_FACIL",
  participantes_programada: [{ id: "P_FACIL" }, { id: "P_ANA" }],
};

const SERIE = { horario: "09:00", idGrupo: "grupo-1", nomeGrupo: "Diretoria semanal" };

describe("copiaDaRecorrencia", () => {
  it("a cópia herda o facilitador da reunião original", () => {
    const copia = copiaDaRecorrencia(ORIGINAL, "2026-11-17", SERIE);

    expect(copia.facilitador_id).toBe("P_FACIL");
  });

  it("leva a data da cópia e o resto da reunião original", () => {
    expect(copiaDaRecorrencia(ORIGINAL, "2026-11-17", SERIE)).toEqual({
      titulo: "Diretoria",
      data: "2026-11-17",
      hora_inicio: "09:00",
      tipo: "Diretoria",
      objetivo: "Metas do mês",
      facilitador_id: "P_FACIL",
      participante_ids: ["P_FACIL", "P_ANA"],
      id_grupo_recorrencia: "grupo-1",
      nome_grupo_recorrencia: "Diretoria semanal",
    });
  });

  it("sem facilitador na original, o campo não vai e o backend decide como antes", () => {
    const copia = copiaDaRecorrencia({ ...ORIGINAL, facilitador_id: null }, "2026-11-17", SERIE);

    expect("facilitador_id" in copia).toBe(false);
  });

  it("sem título, usa o tipo; sem tipo, Reunião; vazios viram null", () => {
    const semNada = { titulo: null, tipo: null, objetivo: "", facilitador_id: "P_FACIL" };

    const copia = copiaDaRecorrencia(semNada, "2026-11-17", { horario: "", idGrupo: "g", nomeGrupo: "  " });

    expect(copia.titulo).toBe("Reunião");
    expect(copia.hora_inicio).toBeNull();
    expect(copia.objetivo).toBeNull();
    expect(copia.participante_ids).toEqual([]);
    expect(copia.nome_grupo_recorrencia).toBeNull();
  });
});
