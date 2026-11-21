"use client";

import { useState } from "react";

import { NotificacoesDoNucleo } from "@/components/seguranca-do-paciente/NotificacoesDoNucleo";
import { RegistroRapido } from "@/components/seguranca-do-paciente/RegistroRapido";
import { TelaDoNucleo } from "@/components/seguranca-do-paciente/TelaDoNucleo";

/** Notificações: os casos do Núcleo (issue #1987) e, no alto, o registro
 * rápido (issue #1998). Registrar recarrega a lista. */
export default function NotificacoesPage() {
  const [versaoDaLista, setVersaoDaLista] = useState(0);
  return (
    <TelaDoNucleo
      titulo="Notificações"
      orientacao="Toda notificação de incidente que chegou ao Núcleo, da mais nova à mais antiga."
      recurso="casos"
    >
      <div className="space-y-4">
        <RegistroRapido aoRegistrar={() => setVersaoDaLista((n) => n + 1)} />
        <NotificacoesDoNucleo key={versaoDaLista} />
      </div>
    </TelaDoNucleo>
  );
}
