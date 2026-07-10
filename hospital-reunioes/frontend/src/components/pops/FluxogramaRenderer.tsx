"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import FluxogramaPalco from "@/components/pops/FluxogramaPalco";
import { fluxogramaValido } from "@/lib/pops/fluxograma/validar";
import { fluxogramaParaSvg } from "@/lib/pops/fluxograma/svg";
import type { FluxogramaEstrutura } from "@/lib/pops/fluxograma/tipos";

interface FluxogramaRendererProps {
  /** Conteúdo da seção `tipo=fluxograma`: o objeto JSON da gramática restrita
   * (ADR 0024), ou a string JSON serializada quando o objeto saiu fora da
   * gramática (o backend faz isso; aqui vira o aviso de regeração). */
  conteudo: string | FluxogramaEstrutura;
  /** Legenda do export (código e nome do POP), impressa abaixo do diagrama. */
  legenda: string;
  /** Reporta o SVG desenhado para a tela persistir na Versão (ADR 0017).
   * Chamado uma vez por estrutura nova (pipeline intocado do Mermaid). */
  onSvgCaptured?: (svg: string) => void;
}

/** Extrai a estrutura válida do conteúdo, ou null (string Mermaid, JSON
 * inválido, ou objeto fora da gramática). */
function estruturaValida(conteudo: string | FluxogramaEstrutura): FluxogramaEstrutura | null {
  let obj: unknown = conteudo;
  if (typeof conteudo === "string") {
    const t = conteudo.trim();
    if (!t.startsWith("{")) return null;
    try {
      obj = JSON.parse(t);
    } catch {
      return null;
    }
  }
  return fluxogramaValido(obj) ? obj : null;
}

/** Há conteúdo de fluxograma para desenhar (objeto, ou string JSON)? Distingue
 * "seção vazia" (placeholder) de "conteúdo presente mas inválido" (aviso). */
function temConteudoBruto(conteudo: string | FluxogramaEstrutura): boolean {
  if (typeof conteudo === "string") return conteudo.trim().startsWith("{");
  return conteudo != null;
}

/**
 * Renderer próprio do Fluxograma (ADR 0024): desenha o objeto JSON da gramática
 * restrita com o design system (layout determinístico + SVG em código), e
 * reusa o palco compartilhado para zoom/arraste/export e a captura do SVG que o
 * pipeline do ADR 0017 persiste com a Versão (o PDF embute o mesmo desenho).
 *
 * JSON inválido: mostra o aviso de pedir a regeração no chat. Durante o
 * streaming da conversa, mantém o último JSON válido renderizado (o conteúdo
 * transitório inválido não apaga o desenho que já estava na tela).
 */
export default function FluxogramaRenderer({ conteudo, legenda, onSvgCaptured }: FluxogramaRendererProps) {
  const estrutura = useMemo(() => estruturaValida(conteudo), [conteudo]);
  const svg = useMemo(() => (estrutura ? fluxogramaParaSvg(estrutura) : null), [estrutura]);

  // Último desenho válido: preserva o diagrama na tela quando um turno de
  // streaming chega com JSON transitório inválido.
  const [ultimoSvg, setUltimoSvg] = useState<string | null>(null);
  const capturadoRef = useRef<string | null>(null);
  const onSvgCapturedRef = useRef(onSvgCaptured);
  useEffect(() => {
    onSvgCapturedRef.current = onSvgCaptured;
  }, [onSvgCaptured]);

  useEffect(() => {
    if (!svg) return;
    setUltimoSvg(svg);
    if (capturadoRef.current !== svg) {
      capturadoRef.current = svg;
      onSvgCapturedRef.current?.(svg);
    }
  }, [svg]);

  const svgAExibir = svg ?? ultimoSvg;
  if (svgAExibir) {
    return <FluxogramaPalco svg={svgAExibir} legenda={legenda} />;
  }

  if (!temConteudoBruto(conteudo)) {
    return (
      <p className="text-sm text-slate-300 italic">
        O fluxograma toma forma conforme a conversa com o agente.
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-center gap-2 text-amber-700">
        <AlertTriangle className="w-4 h-4" />
        <p className="text-sm font-semibold">Não consegui desenhar o fluxograma.</p>
      </div>
      <p className="text-xs text-amber-700 mt-1">
        O formato do fluxograma saiu inválido. Peça ao agente, no chat, para refazer o fluxograma.
      </p>
    </div>
  );
}
