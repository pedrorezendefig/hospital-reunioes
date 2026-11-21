"use client";

import { FilaDeTriagem } from "@/components/seguranca-do-paciente/FilaDeTriagem";
import { TelaDoNucleo } from "@/components/seguranca-do-paciente/TelaDoNucleo";
import { ORIENTACAO_DA_TRIAGEM } from "@/lib/seguranca-do-paciente/triagem";

/** A fila de triagem do Núcleo (issue #1992). */
export default function FilaDeTriagemPage() {
  return (
    <TelaDoNucleo titulo="Fila de triagem" orientacao={ORIENTACAO_DA_TRIAGEM} recurso="triagem">
      <FilaDeTriagem />
    </TelaDoNucleo>
  );
}
