"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { Download, Image as ImageIcon, RefreshCw, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { calcularFit } from "@/lib/pops/fluxograma/fit";

interface FluxogramaPalcoProps {
  /** Markup SVG a exibir (do Mermaid legado ou do renderer próprio, ADR 0024). */
  svg: string | null;
  /** Legenda do export (código e nome do POP), impressa abaixo do diagrama. */
  legenda: string;
}

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 3;
const ZOOM_PASSO = 0.2;

/**
 * Palco compartilhado do fluxograma (ADR 0017): dado um SVG já renderizado,
 * oferece zoom, arraste e export em PNG e SVG (com legenda). É o mesmo shell
 * para o Mermaid legado e para o renderer próprio (ADR 0024), que só diferem em
 * como produzem o SVG. A captura do SVG para persistir na Versão fica em cada
 * renderer (que sabe quando o conteúdo mudou); aqui é só apresentação.
 */
export default function FluxogramaPalco({ svg, legenda }: FluxogramaPalcoProps) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const palcoRef = useRef<HTMLDivElement>(null);
  const fitEscala = useRef(1);
  const arrastando = useRef(false);
  const ultimoPonto = useRef({ x: 0, y: 0 });

  // Fit-to-content (issue #235): enquadra o diagrama inteiro no palco.
  const aplicarFit = useCallback(() => {
    const palco = palcoRef.current;
    const el = palco?.querySelector("svg");
    if (!palco || !el) return;
    const fit = calcularFit(
      { largura: Number(el.getAttribute("width")), altura: Number(el.getAttribute("height")) },
      { largura: palco.clientWidth, altura: palco.clientHeight }
    );
    fitEscala.current = fit.escala;
    setZoom(fit.escala);
    setPan(fit.pan);
  }, []);

  // Enquadra na montagem e quando o desenho muda (agente alterou os passos).
  useLayoutEffect(() => {
    aplicarFit();
  }, [svg, aplicarFit]);

  const ajustarZoom = useCallback((delta: number) => {
    // ZOOM_MIN vale só para o gesto manual; quando o fit enquadrou abaixo
    // dele, o piso é a escala do fit (o zoom-out sempre alcança o fit).
    setZoom((z) => {
      const piso = Math.min(ZOOM_MIN, fitEscala.current);
      return Math.min(ZOOM_MAX, Math.max(piso, Number((z + delta).toFixed(2))));
    });
  }, []);

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!svg) return;
      e.preventDefault();
      ajustarZoom(e.deltaY < 0 ? ZOOM_PASSO : -ZOOM_PASSO);
    },
    [svg, ajustarZoom]
  );

  const onMouseDown = (e: React.MouseEvent) => {
    arrastando.current = true;
    ultimoPonto.current = { x: e.clientX, y: e.clientY };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!arrastando.current) return;
    const dx = e.clientX - ultimoPonto.current.x;
    const dy = e.clientY - ultimoPonto.current.y;
    ultimoPonto.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  };
  const pararArraste = () => {
    arrastando.current = false;
  };

  const baixarSvg = useCallback(() => {
    if (!svg) return;
    const blob = new Blob([comLegenda(svg, legenda)], { type: "image/svg+xml;charset=utf-8" });
    baixarBlob(blob, `${nomeBase(legenda)}_fluxograma.svg`);
  }, [svg, legenda]);

  const baixarPng = useCallback(async () => {
    if (!svg) return;
    try {
      const png = await svgParaPng(comLegenda(svg, legenda), 2);
      baixarBlob(png, `${nomeBase(legenda)}_fluxograma.png`);
    } catch {
      // Falha de rasterização não quebra a tela; o SVG segue disponível.
    }
  }, [svg, legenda]);

  return (
    <div className="space-y-2.5">
      {/* Barra de ferramentas: zoom, ajuste e export */}
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-0.5">
          <BotaoFerramenta titulo="Diminuir zoom" onClick={() => ajustarZoom(-ZOOM_PASSO)} disabled={!svg}>
            <ZoomOut className="w-4 h-4" />
          </BotaoFerramenta>
          <span className="px-1.5 text-xs font-medium text-slate-500 tabular-nums min-w-[3rem] text-center">
            {Math.round(zoom * 100)}%
          </span>
          <BotaoFerramenta titulo="Aumentar zoom" onClick={() => ajustarZoom(ZOOM_PASSO)} disabled={!svg}>
            <ZoomIn className="w-4 h-4" />
          </BotaoFerramenta>
          <BotaoFerramenta titulo="Ajustar à tela" onClick={aplicarFit} disabled={!svg}>
            <Maximize2 className="w-4 h-4" />
          </BotaoFerramenta>
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <button
            onClick={baixarPng}
            disabled={!svg}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50"
            title="Baixar como PNG"
          >
            <ImageIcon className="w-3.5 h-3.5" />
            PNG
          </button>
          <button
            onClick={baixarSvg}
            disabled={!svg}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50"
            title="Baixar como SVG"
          >
            <Download className="w-3.5 h-3.5" />
            SVG
          </button>
        </div>
      </div>

      {/* Palco do diagrama: abre enquadrado (fit), zoom por scroll, arraste
          com o mouse. Em destaque na página: a maior seção do documento. */}
      <div
        ref={palcoRef}
        className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50/60 h-[70vh] min-h-[340px] select-none"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={pararArraste}
        onMouseLeave={pararArraste}
        style={{ cursor: arrastando.current ? "grabbing" : "grab" }}
      >
        {svg ? (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "center center" }}
            // O SVG é confiável: vem do renderer próprio (markup construído
            // em código, texto escapado).
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <RefreshCw className="w-5 h-5 text-slate-300 animate-spin" />
          </div>
        )}
        <span className="absolute bottom-2 right-3 text-[10px] text-slate-400 pointer-events-none">
          Role para dar zoom, arraste para mover
        </span>
      </div>
      <p className="text-[11px] text-slate-400">{legenda}</p>
    </div>
  );
}

function BotaoFerramenta({
  titulo,
  onClick,
  disabled,
  children,
}: {
  titulo: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={titulo}
      aria-label={titulo}
      className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 transition-colors disabled:opacity-40"
    >
      {children}
    </button>
  );
}

// Helpers de export (compartilhados entre os renderers).

function nomeBase(legenda: string): string {
  // Primeiro token (geralmente o código HSM_...) vira a base do nome do arquivo.
  const token = legenda.trim().split(/\s+/)[0] || "pop";
  return token.replace(/[^\w.-]/g, "");
}

function baixarBlob(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}

/** Anexa a legenda ao rodapé do SVG, ampliando a altura para acomodá-la. */
function comLegenda(svgMarkup: string, legenda: string): string {
  try {
    const doc = new DOMParser().parseFromString(svgMarkup, "image/svg+xml");
    const el = doc.documentElement;
    if (el.nodeName.toLowerCase() !== "svg") return svgMarkup;

    const altura = Number(el.getAttribute("height")) || 0;
    const largura = Number(el.getAttribute("width")) || 0;
    if (!altura || !largura) return svgMarkup;

    const margem = 28;
    el.setAttribute("height", String(altura + margem));
    const vb = (el.getAttribute("viewBox") || `0 0 ${largura} ${altura}`).split(/\s+/).map(Number);
    if (vb.length === 4) el.setAttribute("viewBox", `${vb[0]} ${vb[1]} ${vb[2]} ${vb[3] + margem}`);

    const texto = doc.createElementNS("http://www.w3.org/2000/svg", "text");
    texto.setAttribute("x", String(largura / 2));
    texto.setAttribute("y", String(altura + margem - 9));
    texto.setAttribute("text-anchor", "middle");
    texto.setAttribute("font-size", "11");
    texto.setAttribute("fill", "#64748B");
    texto.setAttribute("font-family", "ui-sans-serif, system-ui, sans-serif");
    texto.textContent = legenda;
    el.appendChild(texto);

    return new XMLSerializer().serializeToString(doc);
  } catch {
    return svgMarkup;
  }
}

/** Rasteriza um SVG num PNG via canvas, na escala dada. */
function svgParaPng(svgMarkup: string, escala: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const doc = new DOMParser().parseFromString(svgMarkup, "image/svg+xml").documentElement;
    const largura = (Number(doc.getAttribute("width")) || 600) * escala;
    const altura = (Number(doc.getAttribute("height")) || 400) * escala;

    const url = URL.createObjectURL(new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" }));
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = largura;
      canvas.height = altura;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        URL.revokeObjectURL(url);
        reject(new Error("sem contexto 2d"));
        return;
      }
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, largura, altura);
      ctx.drawImage(img, 0, 0, largura, altura);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob falhou"))), "image/png");
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("falha ao carregar SVG"));
    };
    img.src = url;
  });
}
