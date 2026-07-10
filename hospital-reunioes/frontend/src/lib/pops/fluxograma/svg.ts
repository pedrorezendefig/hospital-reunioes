/**
 * Renderer SVG do Fluxograma de POP (ADR 0024, issue #221).
 *
 * Função pura: recebe o layout determinístico e devolve o markup SVG desenhado
 * com o design system institucional (gabarito do PRD #210). É esse markup que a
 * tela exibe e que o pipeline do ADR 0017 captura, persiste com a Versão e o
 * PDF embute (o sanitizador do backend cobre estas tags). Cores, badges, chips
 * e setas seguem o gabarito; a sombra aparece na tela e o WeasyPrint a ignora.
 */

import type { FluxogramaEstrutura } from "./tipos";
import { calcularLayout, type FluxogramaLayout, type LayoutCard, type LayoutChip } from "./layout";

const FONTE = "'HP Simplified', system-ui, sans-serif";

/** Escapa texto para XML (o SVG precisa parsear no sanitizador do backend). */
function esc(texto: string): string {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Arredonda para no máximo uma casa (evita ruído de ponto flutuante). */
function n(valor: number): string {
  return String(Math.round(valor * 10) / 10);
}

function seta(d: string): string {
  return `<path d="${d}" fill="none" stroke="#94A3B8" stroke-width="1.8" marker-end="url(#ponta)"/>`;
}

function linhasTexto(card: LayoutCard, fill: string, peso: number): string {
  return card.linhas
    .map(
      (l) =>
        `<text x="${n(l.x)}" y="${n(l.y)}" text-anchor="middle" font-size="15" font-weight="${peso}" fill="${fill}" font-family="${FONTE}">${esc(l.texto)}</text>`
    )
    .join("");
}

function badgeNumero(cx: number, cy: number, numero: number): string {
  return (
    `<circle cx="${n(cx)}" cy="${n(cy)}" r="11" fill="#EEF0FB" stroke="#C7CBE8" stroke-width="1.2"/>` +
    `<text x="${n(cx)}" y="${n(cy + 4)}" text-anchor="middle" font-size="12" font-weight="700" fill="#2B2E7E" font-family="${FONTE}">${numero}</text>`
  );
}

function badgeDecisao(cx: number, cy: number): string {
  return (
    `<rect x="${n(cx - 8)}" y="${n(cy - 8)}" width="16" height="16" rx="3" transform="rotate(45 ${n(cx)} ${n(cy)})" fill="#FFFFFF" stroke="#F2C078" stroke-width="1.5"/>` +
    `<text x="${n(cx)}" y="${n(cy + 4.5)}" text-anchor="middle" font-size="12" font-weight="700" fill="#7A4E12" font-family="${FONTE}">?</text>`
  );
}

function card(c: LayoutCard): string {
  if (c.tipo === "decisao") {
    return (
      `<rect x="${n(c.x)}" y="${n(c.y)}" width="${c.w}" height="${c.h}" rx="8" fill="#FFF9EF" stroke="#F2C078" stroke-width="1.5" filter="url(#sombra)"/>` +
      badgeDecisao(c.badge.cx, c.badge.cy) +
      linhasTexto(c, "#7A4E12", 600)
    );
  }
  // passo e desvio compartilham o card branco com badge numerado.
  return (
    `<rect x="${n(c.x)}" y="${n(c.y)}" width="${c.w}" height="${c.h}" rx="8" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.5" filter="url(#sombra)"/>` +
    badgeNumero(c.badge.cx, c.badge.cy, c.badge.numero ?? 0) +
    linhasTexto(c, "#1E293B", 400)
  );
}

function terminalInicio(x: number, y: number, w: number, h: number): string {
  const cx = x + w / 2;
  return (
    `<rect x="${n(x)}" y="${n(y)}" width="${w}" height="${h}" rx="17" fill="#2B2E7E" filter="url(#sombra)"/>` +
    `<path d="M ${n(x + 22)} ${n(y + 11)} l 10 6 l -10 6 z" fill="#FFFFFF" opacity="0.9"/>` +
    `<text x="${n(cx + 7)}" y="${n(y + h / 2 + 5)}" text-anchor="middle" font-size="14.5" font-weight="700" fill="#FFFFFF" font-family="${FONTE}">Início</text>`
  );
}

function terminalFim(x: number, y: number, w: number, h: number): string {
  const cx = x + w / 2;
  const cy = y + h / 2;
  return (
    `<rect x="${n(x)}" y="${n(y)}" width="${w}" height="${h}" rx="17" fill="#88D7A4" stroke="#5FBE8A" stroke-width="1.5" filter="url(#sombra)"/>` +
    `<path d="M ${n(x + 20)} ${n(cy)} l 4.5 4.5 l 8 -8.5" stroke="#14532D" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<text x="${n(cx + 8)}" y="${n(cy + 5)}" text-anchor="middle" font-size="14.5" font-weight="700" fill="#14532D" font-family="${FONTE}">Fim</text>`
  );
}

const TONS_CHIP = {
  sim: { fill: "#E8F6EE", stroke: "#A9DEC2", texto: "#1F7A4D" },
  nao: { fill: "#FDEEEE", stroke: "#F3BFBF", texto: "#B4443E" },
  neutro: { fill: "#F1F5F9", stroke: "#CBD5E1", texto: "#475569" },
} as const;

function chip(c: LayoutChip): string {
  const t = TONS_CHIP[c.tom];
  const cx = c.x + c.w / 2;
  return (
    `<rect x="${n(c.x)}" y="${n(c.y)}" width="${c.w}" height="${c.h}" rx="11" fill="${t.fill}" stroke="${t.stroke}" stroke-width="1.2"/>` +
    `<text x="${n(cx)}" y="${n(c.y + c.h / 2 + 4.5)}" text-anchor="middle" font-size="12" font-weight="700" fill="${t.texto}" font-family="${FONTE}">${esc(c.rotulo)}</text>`
  );
}

const DEFS =
  '<defs>' +
  '<marker id="ponta" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
  '<path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#94A3B8"/></marker>' +
  '<filter id="sombra" x="-20%" y="-20%" width="140%" height="160%">' +
  '<feDropShadow dx="0" dy="1" stdDeviation="1.6" flood-color="#0F172A" flood-opacity="0.10"/></filter>' +
  '</defs>';

/** Monta o SVG a partir de um layout já calculado. */
export function layoutParaSvg(layout: FluxogramaLayout): string {
  const setas = layout.setas.map((s) => seta(s.d)).join("");
  const terminais = layout.terminais
    .map((t) => (t.tipo === "inicio" ? terminalInicio(t.x, t.y, t.w, t.h) : terminalFim(t.x, t.y, t.w, t.h)))
    .join("");
  const cards = layout.cards.map(card).join("");
  const chips = layout.chips.map(chip).join("");
  return (
    `<svg viewBox="0 0 ${layout.largura} ${layout.altura}" width="${layout.largura}" height="${layout.altura}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Fluxograma do procedimento">` +
    DEFS +
    setas +
    terminais +
    cards +
    chips +
    "</svg>"
  );
}

/** Atalho: estrutura validada direto para markup SVG. */
export function fluxogramaParaSvg(estrutura: FluxogramaEstrutura): string {
  return layoutParaSvg(calcularLayout(estrutura));
}
