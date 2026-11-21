"use client";

import { CortesDeFrequencia } from "@/components/seguranca-do-paciente/CortesDeFrequencia";
import { QrDaNotificacao } from "@/components/seguranca-do-paciente/QrDaNotificacao";
import { TelaDoNucleo } from "@/components/seguranca-do-paciente/TelaDoNucleo";

/** Configuração do módulo (ADR 0095, decisão 4): o QR e o endereço da notificação (issue #2046) e os cortes de frequência da matriz de prioridade (issue #1992). */
export default function ConfiguracaoPage() {
  return (
    <TelaDoNucleo
      titulo="Configuração"
      orientacao="O que o módulo usa para funcionar no hospital."
      recurso="configuracao"
    >
      <div className="space-y-4">
        <QrDaNotificacao />
        <CortesDeFrequencia />
      </div>
    </TelaDoNucleo>
  );
}
