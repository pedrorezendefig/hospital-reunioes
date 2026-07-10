/**
 * Layout determinístico do Fluxograma de POP (ADR 0024, issue #221).
 *
 * Função pura (sem DOM, sem motor de layout externo) que transforma a estrutura
 * validada em posições de cards, trajetos de setas e chips de ramo. Mesma
 * estrutura produz sempre as mesmas posições e trajetos (garantido por teste de
 * snapshot). A geometria segue o gabarito visual do PRD #210: coluna principal
 * central, decisões com desvio lateral à direita e retorno ortogonal.
 *
 * Semântica da gramática (fatia #221, linear + Sim/Não): a lista `nos` é a
 * coluna principal (Início antes do primeiro, Fim depois do último). Numeração
 * 1..N acompanha o fluxo: cada `passo` e cada card de `desvio` recebem o
 * próximo número; a `decisao` recebe o badge "?". Uma decisão binária tem um
 * ramo que segue reto (chip na seta vertical) e, quando há `desvio`, um ramo
 * lateral (chip na seta horizontal) com card à direita que retorna a um nó
 * (`retorna_para`) ou segue o fluxo.
 */

import type { FluxogramaEstrutura, FluxogramaNo } from "./tipos";

// Geometria da coluna principal (coordenadas do gabarito do PRD #210).
const CX = 300; // centro horizontal da coluna
const CARD_W = 236;
const CARD_X = CX - CARD_W / 2; // 182
const CARD_H_MIN = 46;
const LINE_H = 18;
const FONT_SIZE = 15;
const GAP = 30; // folga vertical entre elementos (a seta vive aqui)
const TOP = 23;
const BOTTOM_MARGIN = 19;

// Terminais (pílulas Início/Fim).
const INICIO_W = 96;
const FIM_W = 88;
const TERMINAL_H = 34;

// Card lateral de desvio.
const DESVIO_X = 498;
const DESVIO_W = 204;
const DESVIO_TEXT_CX = 606;

// Texto centrado, deslocado à direita do badge (que fica na borda esquerda).
const CARD_TEXT_CX = CX + 6; // 306
const BASELINE = 5; // ajuste da baseline do texto ao centro vertical do card

// Chips de ramo (Sim/Não).
const CHIP_W = 44;
const CHIP_H = 22;

// Larguras máximas de texto (conservadoras: preferimos quebrar a mais do que
// cortar). Estimativa de largura por caractere sem DOM, determinística.
const CHAR_W = FONT_SIZE * 0.55;
const CARD_TEXT_MAX = 190;
const DESVIO_TEXT_MAX = 168;

export interface LinhaTexto {
  texto: string;
  x: number;
  y: number;
}

export interface LayoutBadge {
  tipo: "numero" | "decisao";
  cx: number;
  cy: number;
  numero?: number;
}

export interface LayoutCard {
  tipo: "passo" | "decisao" | "desvio";
  x: number;
  y: number;
  w: number;
  h: number;
  badge: LayoutBadge;
  linhas: LinhaTexto[];
}

export interface LayoutTerminal {
  tipo: "inicio" | "fim";
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LayoutSeta {
  d: string;
}

export interface LayoutChip {
  rotulo: string;
  tom: "sim" | "nao" | "neutro";
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface FluxogramaLayout {
  largura: number;
  altura: number;
  terminais: LayoutTerminal[];
  cards: LayoutCard[];
  setas: LayoutSeta[];
  chips: LayoutChip[];
}

/** Quebra o texto em linhas por largura estimada, sem DOM (determinístico).
 * Palavra isolada maior que o limite fica na própria linha (nunca some). */
function quebrarLinhas(texto: string, larguraMax: number): string[] {
  const palavras = texto.trim().split(/\s+/).filter(Boolean);
  if (palavras.length === 0) return [""];
  const maxChars = Math.max(1, Math.floor(larguraMax / CHAR_W));
  const linhas: string[] = [];
  let atual = "";
  for (const palavra of palavras) {
    const candidata = atual ? `${atual} ${palavra}` : palavra;
    if (candidata.length <= maxChars || !atual) {
      atual = candidata;
    } else {
      linhas.push(atual);
      atual = palavra;
    }
  }
  if (atual) linhas.push(atual);
  return linhas;
}

function alturaCard(nLinhas: number, base: number): number {
  return Math.max(CARD_H_MIN, base + nLinhas * LINE_H);
}

/** Baselines absolutas das linhas de um card, centradas na vertical. */
function linhasCentradas(linhas: string[], cx: number, cy: number): LinhaTexto[] {
  const inicio = cy - ((linhas.length - 1) * LINE_H) / 2 + BASELINE;
  return linhas.map((texto, i) => ({ texto, x: cx, y: inicio + i * LINE_H }));
}

/** Índice do ramo que segue reto (sem desvio) e do ramo lateral (com desvio).
 * Sem nenhum desvio, o primeiro ramo segue reto e o segundo também. */
function classificarRamos(no: FluxogramaNo) {
  const ramos = no.ramos ?? [];
  const iDesvio = ramos.findIndex((r) => r.desvio);
  const iReto = iDesvio === -1 ? 0 : ramos.findIndex((_, i) => i !== iDesvio);
  return { ramos, iReto, iDesvio };
}

export function calcularLayout(estrutura: FluxogramaEstrutura): FluxogramaLayout {
  const nos = estrutura.nos;

  // Numeração 1..N em ordem de fluxo: cada passo recebe o próximo número; ao
  // encontrar uma decisão, o card de desvio dela (se houver) recebe o próximo,
  // antes do passo seguinte. Assim "Solicitar reposição" fica entre "Reunir"
  // e "Realizar", como no gabarito.
  const numeroDoPasso = new Map<string, number>();
  const numeroDoDesvio = new Map<string, number>();
  {
    let numero = 0;
    for (const no of nos) {
      if (no.tipo === "passo") {
        numeroDoPasso.set(no.id, ++numero);
      } else if ((no.ramos ?? []).some((r) => r.desvio)) {
        numeroDoDesvio.set(no.id, ++numero);
      }
    }
  }

  const centroYPorId = new Map<string, number>();
  const cards: LayoutCard[] = [];
  const desvios: {
    card: LayoutCard;
    decisaoCy: number;
    decisaoBottom: number;
    proxTop: number;
    retornaPara?: string | null;
  }[] = [];
  const setas: LayoutSeta[] = [];
  const chips: LayoutChip[] = [];

  // Passo 1: posiciona a coluna principal e numera passos/desvios em ordem.
  let y = TOP;
  const inicio: LayoutTerminal = { tipo: "inicio", x: CX - INICIO_W / 2, y, w: INICIO_W, h: TERMINAL_H };
  let prevBottom = y + TERMINAL_H; // fundo do Início
  y = prevBottom + GAP;

  const posicoes: { no: FluxogramaNo; card: LayoutCard }[] = [];

  for (const no of nos) {
    const ehDecisao = no.tipo === "decisao";
    const linhasTexto = quebrarLinhas(no.texto, CARD_TEXT_MAX);
    const h = alturaCard(linhasTexto.length, 12);
    const cy = y + h / 2;
    const badge: LayoutBadge = ehDecisao
      ? { tipo: "decisao", cx: CARD_X, cy }
      : { tipo: "numero", cx: CARD_X, cy, numero: numeroDoPasso.get(no.id) };
    const card: LayoutCard = {
      tipo: ehDecisao ? "decisao" : "passo",
      x: CARD_X,
      y,
      w: CARD_W,
      h,
      badge,
      linhas: linhasCentradas(linhasTexto, CARD_TEXT_CX, cy),
    };
    cards.push(card);
    posicoes.push({ no, card });
    centroYPorId.set(no.id, cy);

    // Seta vertical da coluna: do fundo do elemento anterior ao topo deste.
    setas.push({ d: `M ${CX} ${prevBottom} V ${y}` });

    prevBottom = y + h;
    y = prevBottom + GAP;
  }

  const fim: LayoutTerminal = { tipo: "fim", x: CX - FIM_W / 2, y, w: FIM_W, h: TERMINAL_H };
  setas.push({ d: `M ${CX} ${prevBottom} V ${y}` });
  const alturaTotal = y + TERMINAL_H + BOTTOM_MARGIN;

  // Passo 2: desenha os desvios laterais e os chips de ramo das decisões.
  for (let idx = 0; idx < posicoes.length; idx++) {
    const { no, card } = posicoes[idx];
    if (no.tipo !== "decisao") continue;

    const decisaoCy = card.y + card.h / 2;
    const decisaoBottom = card.y + card.h;
    const proxTop = idx + 1 < posicoes.length ? posicoes[idx + 1].card.y : fim.y;
    const { ramos, iReto, iDesvio } = classificarRamos(no);

    // Ramo reto: chip na seta vertical entre a decisão e o próximo elemento.
    if (ramos[iReto]) {
      chips.push(chipRamo(ramos[iReto].rotulo, CX, (decisaoBottom + proxTop) / 2));
    }

    if (iDesvio === -1) {
      // Sem desvio: o segundo ramo também segue reto (caso degenerado).
      const outro = ramos.find((_, i) => i !== iReto);
      if (outro) chips.push(chipRamo(outro.rotulo, CX, (decisaoBottom + proxTop) / 2 + CHIP_H + 4));
      continue;
    }

    // Ramo lateral: card de desvio à direita, alinhado ao centro da decisão.
    const ramo = ramos[iDesvio];
    const desvioLinhas = quebrarLinhas(ramo.desvio!.texto, DESVIO_TEXT_MAX);
    const desvioH = alturaCard(desvioLinhas.length, 20);
    const desvioY = Math.round(decisaoCy - desvioH / 2);
    const desvioCard: LayoutCard = {
      tipo: "desvio",
      x: DESVIO_X,
      y: desvioY,
      w: DESVIO_W,
      h: desvioH,
      badge: { tipo: "numero", cx: DESVIO_X, cy: desvioY + desvioH / 2, numero: numeroDoDesvio.get(no.id) },
      linhas: linhasCentradas(desvioLinhas, DESVIO_TEXT_CX, desvioY + desvioH / 2),
    };
    cards.push(desvioCard);

    // Seta horizontal: da borda direita da decisão à borda esquerda do desvio.
    setas.push({ d: `M ${CARD_X + CARD_W} ${decisaoCy} H ${DESVIO_X - 4}` });
    // Chip do ramo lateral, sobre a seta horizontal.
    chips.push(chipRamo(ramo.rotulo, (CARD_X + CARD_W + DESVIO_X) / 2, decisaoCy));

    // Retorno: do topo do desvio de volta à borda direita do nó alvo.
    desvios.push({
      card: desvioCard,
      decisaoCy,
      decisaoBottom,
      proxTop,
      retornaPara: ramo.desvio!.retorna_para,
    });
  }

  // Passo 3: setas de retorno (dependem das posições finais de todos os nós).
  for (const d of desvios) {
    const desvioCx = d.card.x + d.card.w / 2;
    const alvoCy = d.retornaPara != null ? centroYPorId.get(d.retornaPara) : undefined;
    if (alvoCy != null) {
      // Retorno a um nó (alvo acima, laço): sobe pela lateral e entra à direita.
      const topo = d.card.y;
      setas.push({
        d: `M ${desvioCx} ${topo} V ${alvoCy + 8} Q ${desvioCx} ${alvoCy} ${desvioCx - 8} ${alvoCy} H ${CARD_X + CARD_W + 4}`,
      });
    } else {
      // Segue o fluxo: desce e reentra na coluna abaixo da decisão.
      const junta = Math.round((d.decisaoBottom + d.proxTop) / 2);
      const fundo = d.card.y + d.card.h;
      setas.push({
        d: `M ${desvioCx} ${fundo} V ${junta} Q ${desvioCx} ${junta + 8} ${desvioCx - 8} ${junta + 8} H ${CX + 4}`,
      });
    }
  }

  const largura = DESVIO_X + DESVIO_W + 20;
  return {
    largura,
    altura: Math.round(alturaTotal),
    terminais: [inicio, fim],
    cards,
    setas,
    chips,
  };
}

function chipRamo(rotulo: string, centroX: number, centroY: number): LayoutChip {
  const norm = rotulo.trim().toLowerCase();
  const tom: LayoutChip["tom"] = norm === "sim" ? "sim" : norm === "não" || norm === "nao" ? "nao" : "neutro";
  return {
    rotulo,
    tom,
    x: Math.round(centroX - CHIP_W / 2),
    y: Math.round(centroY - CHIP_H / 2),
    w: CHIP_W,
    h: CHIP_H,
  };
}
