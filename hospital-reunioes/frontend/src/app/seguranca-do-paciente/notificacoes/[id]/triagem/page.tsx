"use client";

import { useParams } from "next/navigation";

import { TelaDoNucleo } from "@/components/seguranca-do-paciente/TelaDoNucleo";
import { TriagemDoCaso } from "@/components/seguranca-do-paciente/TriagemDoCaso";
import { ORIENTACAO_DA_TRIAGEM } from "@/lib/seguranca-do-paciente/triagem";

/** A tela única da triagem de um caso (issue #1992). */
export default function TriagemDoCasoPage() {
  const params = useParams();
  return (
    <TelaDoNucleo titulo="Triagem" orientacao={ORIENTACAO_DA_TRIAGEM} recurso="triagem" larga>
      <TriagemDoCaso id={params.id as string} />
    </TelaDoNucleo>
  );
}
