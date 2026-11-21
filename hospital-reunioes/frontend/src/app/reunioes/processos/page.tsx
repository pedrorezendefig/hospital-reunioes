"use client";

import { ListaDeDefinicoesDeProcesso } from "@/components/reunioes/ListaDeDefinicoesDeProcesso";

/**
 * As Definições de processo do setor (issue #1875, ADR 0098, decisão 9): as
 * linhas do tipo Processo das atas, por setor da reunião, com o trecho copiado.
 */
export default function DefinicoesDeProcessoPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl text-text">Definições de processo</h1>
        <p className="text-sm text-text-secondary mt-1">
          O que as reuniões do setor combinaram sobre como se faz dali para frente, com o trecho da ata. Não tem
          responsável nem prazo: é para consultar quando precisar.
        </p>
      </div>
      <ListaDeDefinicoesDeProcesso />
    </div>
  );
}
