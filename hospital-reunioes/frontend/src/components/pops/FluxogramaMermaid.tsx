"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import mermaid from "mermaid";
import FluxogramaPalco from "@/components/pops/FluxogramaPalco";

interface FluxogramaMermaidProps {
  /** Sintaxe Mermaid emitida pelo agente (conteudo legado da seção fluxograma). */
  codigoMermaid: string;
  /** Id estável da seção, chave do diagrama e da captura do SVG. */
  secaoId: string;
  /** Legenda do export (código e nome do POP), impressa abaixo do diagrama. */
  legenda: string;
  /** Reporta o SVG renderizado para a tela persistir na Versão (ADR 0017).
   * Chamado uma vez por sintaxe, após render bem-sucedido. */
  onSvgCaptured?: (svg: string) => void;
}

// Inicializa o mermaid uma vez no módulo: sem auto-start (renderizamos sob
// demanda) e com securityLevel "strict": o conteúdo vem do agente, nada de
// HTML/script solto no diagrama (privacidade e segurança do self-hosted).
let mermaidInicializado = false;
function garantirMermaid() {
  if (mermaidInicializado) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    flowchart: { useMaxWidth: false, htmlLabels: false, curve: "basis" },
    themeVariables: {
      primaryColor: "#EEF0FB",
      primaryBorderColor: "#2B2E7E",
      primaryTextColor: "#1E293B",
      lineColor: "#94A3B8",
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
    },
  });
  mermaidInicializado = true;
}

/**
 * Renderiza o fluxograma LEGADO a partir da sintaxe Mermaid (ADR 0017): render
 * no cliente e captura do SVG para a tela persistir na Versão. O desenho, o
 * zoom/arraste e o export ficam no palco compartilhado. A partir do ADR 0024 o
 * conteúdo novo é objeto JSON desenhado pelo FluxogramaRenderer; este componente
 * atende só o conteúdo legado em string Mermaid durante a transição (migração é
 * a #224). Sintaxe inválida cai num fallback que orienta pedir a regeração.
 */
export default function FluxogramaMermaid({
  codigoMermaid,
  secaoId,
  legenda,
  onSvgCaptured,
}: FluxogramaMermaidProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [erro, setErro] = useState(false);

  // Evita re-disparar a captura para a mesma sintaxe já reportada.
  const sintaxeCapturada = useRef<string | null>(null);
  // Mantém o callback num ref: o render do diagrama depende SÓ da sintaxe, não
  // da identidade da função (que muda a cada render do pai).
  const onSvgCapturedRef = useRef(onSvgCaptured);
  useEffect(() => {
    onSvgCapturedRef.current = onSvgCaptured;
  }, [onSvgCaptured]);

  const codigo = (codigoMermaid || "").trim();

  useEffect(() => {
    let cancelado = false;
    if (!codigo) {
      setSvg(null);
      setErro(false);
      return;
    }
    garantirMermaid();
    // Id único por render para o mermaid não colidir definições no DOM.
    const renderId = `fluxograma-${secaoId}-${Math.random().toString(36).slice(2, 8)}`;
    mermaid
      .render(renderId, codigo)
      .then(({ svg: svgRenderizado }) => {
        if (cancelado) return;
        setSvg(svgRenderizado);
        setErro(false);
        if (sintaxeCapturada.current !== codigo) {
          sintaxeCapturada.current = codigo;
          onSvgCapturedRef.current?.(svgRenderizado);
        }
      })
      .catch(() => {
        if (cancelado) return;
        setSvg(null);
        setErro(true);
      });
    return () => {
      cancelado = true;
    };
  }, [codigo, secaoId]);

  if (!codigo) {
    return (
      <p className="text-sm text-slate-300 italic">
        O fluxograma toma forma conforme a conversa com o agente.
      </p>
    );
  }

  if (erro) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
        <div className="flex items-center gap-2 text-amber-700">
          <AlertTriangle className="w-4 h-4" />
          <p className="text-sm font-semibold">Não consegui desenhar o fluxograma.</p>
        </div>
        <p className="text-xs text-amber-700 mt-1">
          A sintaxe do diagrama saiu inválida. Peça ao agente, no chat, para refazer o fluxograma.
        </p>
        <pre className="mt-2.5 max-h-48 overflow-auto rounded-lg bg-white/70 border border-amber-100 p-2.5 text-[11px] leading-relaxed text-slate-600 whitespace-pre-wrap">
          {codigo}
        </pre>
      </div>
    );
  }

  return <FluxogramaPalco svg={svg} legenda={legenda} />;
}
