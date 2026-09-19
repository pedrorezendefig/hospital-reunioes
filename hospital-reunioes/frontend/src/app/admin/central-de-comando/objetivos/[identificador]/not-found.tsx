import Link from "next/link";
import { ArrowLeft, SearchX } from "lucide-react";

import { CAMINHO_OBJETIVOS } from "@/components/central-de-comando/Objetivos";

/**
 * A página de Objetivo não encontrado (issue #820). O backend responde 404 para
 * identificador que não é de um Objetivo com lente (inexistente ou em
 * construção), e a lente cai aqui.
 */
export default function ObjetivoNaoEncontrado() {
  return (
    <div className="animate-fade-in-up space-y-6">
      <Link
        href={CAMINHO_OBJETIVOS}
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text"
      >
        <ArrowLeft className="h-4 w-4" />
        Objetivos
      </Link>
      <div role="status" className="flex gap-3 rounded-2xl border border-border bg-white p-6 text-text shadow-premium">
        <SearchX className="mt-0.5 h-5 w-5 shrink-0 text-text-secondary" />
        <div className="space-y-1">
          <p className="font-semibold">Objetivo não encontrado</p>
          <p className="text-sm text-text-secondary">
            Esse Objetivo não existe ou ainda está em construção. Volte para a galeria e escolha um dos Objetivos
            disponíveis.
          </p>
        </div>
      </div>
    </div>
  );
}
