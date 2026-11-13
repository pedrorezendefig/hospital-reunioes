"use client";

/**
 * O módulo da aba Tecnologia (issue #636, PRD #634, ADR 0050).
 *
 * Desde a ADR 0077 a aba é o chat do Assistente (issue #1381), com a lista
 * lateral das conversas (issue #1384). O Quadro, o Painel, a tela de Produtos
 * e o formulário à mão saíram do código na issue #1386. Desde a issue #1556
 * (ADR 0084, decisão 8) há duas abas: Conversas, o chat, e Entregas, o retrato
 * do que foi entregue. O gate de verdade é o `require_super_admin` do backend;
 * a sidebar apenas esconde o item.
 *
 * Na tela larga, a partir de 1280px, a aba Conversas se chama Quadro e mostra
 * as Demandas em colunas pela Etapa (issue #1642, ADR 0090, decisão 1). No
 * celular ela continua a lista de antes, com o nome de antes.
 */

import { useState } from "react";
import { Cpu } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";
import { useTelaLarga } from "@/hooks/useTelaLarga";

import { ConversasDaTecnologia } from "./ConversasDaTecnologia";
import { EntregasDaTecnologia } from "./EntregasDaTecnologia";

type Aba = "conversas" | "entregas";

export function TecnologiaModulo({ demandaInicial = null }: { demandaInicial?: string | null }) {
  const { token } = useAuth();
  const largo = useTelaLarga();
  const rotuloDasConversas = largo ? "Quadro" : "Conversas";
  const abas: { id: Aba; rotulo: string }[] = [
    { id: "conversas", rotulo: rotuloDasConversas },
    { id: "entregas", rotulo: "Entregas" },
  ];
  const [aba, setAba] = useState<Aba>("conversas");
  /** As Entregas só pedem ao servidor quando abertas pela primeira vez. */
  const [entregasAbertas, setEntregasAbertas] = useState(false);

  function escolher(id: Aba) {
    setAba(id);
    if (id === "entregas") setEntregasAbertas(true);
  }

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <Cpu className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Tecnologia</h1>
          <p className="text-sm text-text-secondary">
            Conte um bug ou peça uma melhoria nos sistemas que a Vitta cuida.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist" aria-label="Tecnologia">
        {abas.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={aba === a.id}
            onClick={() => escolher(a.id)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              aba === a.id ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text"
            }`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {/* A conversa fica montada atrás da aba: trocar de aba não perde o que foi escrito. */}
      <div role="tabpanel" aria-label={rotuloDasConversas} hidden={aba !== "conversas"}>
        <ConversasDaTecnologia token={token} demandaInicial={demandaInicial} />
      </div>
      {entregasAbertas && (
        <div role="tabpanel" aria-label="Entregas" hidden={aba !== "entregas"}>
          <EntregasDaTecnologia token={token} />
        </div>
      )}
    </div>
  );
}
