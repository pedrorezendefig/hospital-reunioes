"use client";

/**
 * O módulo da aba Tecnologia (issue #636, PRD #634, ADR 0050).
 *
 * Desde a ADR 0077 a aba é uma tela só: o chat do Assistente (issue #1381),
 * com a lista lateral das conversas (issue #1384). O Quadro, o Painel, a tela
 * de Produtos e o formulário à mão saíram do código na issue #1386. O gate de
 * verdade é o `require_super_admin` do backend; a sidebar apenas esconde o item.
 */

import { Cpu } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";

import { ConversasDaTecnologia } from "./ConversasDaTecnologia";

export function TecnologiaModulo({ demandaInicial = null }: { demandaInicial?: string | null }) {
  const { token } = useAuth();

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

      <ConversasDaTecnologia token={token} demandaInicial={demandaInicial} />
    </div>
  );
}
