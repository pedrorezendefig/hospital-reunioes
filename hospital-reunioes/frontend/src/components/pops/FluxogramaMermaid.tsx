"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Image as ImageIcon, RefreshCw, ZoomIn, ZoomOut, Maximize2, AlertTriangle } from "lucide-react";
import mermaid from "mermaid";

interface FluxogramaMermaidProps {
  /** Sintaxe Mermaid emitida pelo agente (conteudo da seção tipo=fluxograma). */
  codigoMermaid: string;
  /** Id estável da seção — chave do diagrama e da captura do SVG. */
  secaoId: string;
  /** Legenda do export (código e nome do POP), impressa abaixo do diagrama. */
  legenda: string;
  /** Reporta o SVG renderizado para a tela persistir na Versão (ADR 0017).
   * Chamado uma vez por sintaxe, após render bem-sucedido. */
  onSvgCaptured?: (svg: string) => void;
}

// Inicializa o mermaid uma vez no módulo: sem auto-start (renderizamos sob
// demanda) e com securityLevel "strict" — o conteúdo vem do agente, nada de
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

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 3;
const ZOOM_PASSO = 0.2;

/**
 * Renderiza o fluxograma do POP a partir da sintaxe Mermaid (ADR 0017): desenho
 * vetorial na tela com zoom e arraste, export em PNG e SVG (com legenda) e
 * captura do SVG renderizado para a tela persistir na Versão (o PDF embute o
 * mesmo desenho). Sintaxe inválida cai num fallback que mostra o texto e
 * oferece regerar, sem quebrar a tela.
 */
export default function FluxogramaMermaid({
  codigoMermaid,
  secaoId,
  legenda,
  onSvgCaptured,
}: FluxogramaMermaidProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [erro, setErro] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const arrastando = useRef(false);
  const ultimoPonto = useRef({ x: 0, y: 0 });
  // Evita re-disparar a captura para a mesma sintaxe já reportada.
  const sintaxeCapturada = useRef<string | null>(null);
  // Mantém o callback num ref: o render do diagrama depende SÓ da sintaxe, não
  // da identidade da função (que muda a cada render do pai) — assim o zoom/pan
  // não se perde quando o pai re-renderiza.
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
        setZoom(1);
        setPan({ x: 0, y: 0 });
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

  const ajustarZoom = useCallback((delta: number) => {
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((z + delta).toFixed(2)))));
  }, []);

  const reset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
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

  // Export SVG: anexa a legenda ao SVG e baixa como arquivo .svg.
  const baixarSvg = useCallback(() => {
    if (!svg) return;
    const blob = new Blob([comLegenda(svg, legenda)], { type: "image/svg+xml;charset=utf-8" });
    baixarBlob(blob, `${nomeBase(legenda)}_fluxograma.svg`);
  }, [svg, legenda]);

  // Export PNG: rasteriza o SVG (com legenda) num canvas em 2x e baixa .png.
  const baixarPng = useCallback(async () => {
    if (!svg) return;
    try {
      const png = await svgParaPng(comLegenda(svg, legenda), 2);
      baixarBlob(png, `${nomeBase(legenda)}_fluxograma.png`);
    } catch {
      // Falha de rasterização não quebra a tela; o SVG segue disponível.
    }
  }, [svg, legenda]);

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
          <BotaoFerramenta titulo="Ajustar à tela" onClick={reset} disabled={!svg}>
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

      {/* Palco do diagrama: zoom por scroll, arraste com o mouse */}
      <div
        className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50/60 h-[340px] select-none"
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
            // O SVG vem do mermaid (securityLevel strict): markup confiável.
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

// ─── Helpers de export ────────────────────────────────────────────────────────

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
