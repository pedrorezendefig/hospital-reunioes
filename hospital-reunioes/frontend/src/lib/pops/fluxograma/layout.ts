/**
 * Layout determinístico do Fluxograma de POP (ADR 0024, issues #221 e #222).
 *
 * Função pura (sem DOM, sem motor de layout externo) que transforma a estrutura
 * validada em posições de cards, trajetos de setas e chips de ramo. Mesma
 * estrutura produz sempre as mesmas posições e trajetos (garantido por teste de
 * snapshot). A geometria segue o gabarito visual do PRD #210: coluna principal
 * central, decisões com desvios laterais à direita e retornos ortogonais.
 *
 * Semântica da gramática: a lista `nos` é a coluna principal (Início antes do
 * primeiro, Fim depois do último). Numeração 1..N acompanha o fluxo: cada
 * `passo` e cada card de `desvio` recebem o próximo número; a `decisao` recebe
 * o badge "?". Uma decisão tem 2 ou mais ramos (caso N-ário, fatia #222): os
 * ramos que seguem reto viram chips na seta vertical; ramos com `desvio` viram
 * cards empilhados à direita (a coluna reserva espaço vertical para a pilha,
 * sem sobreposição), retornando a um nó (`retorna_para`) ou seguindo o fluxo;
 * ramos com `vai_para` viram setas ortogonais de salto pela lateral esquerda,
 * até um nó qualquer ou o terminal Fim.
 */

import type { FluxogramaEstrutura, FluxogramaNo, FluxogramaRamo } from "./tipos";

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
// Pilha de desvios de uma decisão N-ária (#222): vão entre cards empilhados e
// folga mínima entre o fundo da pilha e o próximo elemento da coluna.
const DESVIO_STACK_GAP = 18;
const RESERVA_LATERAL = 20;
// Trilhos verticais dos retornos que contornam a pilha pela direita.
const RETORNO_RAIL_STEP = 14;
// Saltos (vai_para): trilhos verticais pela lateral esquerda da coluna.
const SALTO_RAIL_X = 136; // CARD_X - 46
const SALTO_RAIL_STEP = 16;

// Texto centrado, deslocado à direita do badge (que fica na borda esquerda).
const CARD_TEXT_CX = CX + 6; // 306
const BASELINE = 5; // ajuste da baseline do texto ao centro vertical do card

// Chips de ramo: largura mínima (Sim/Não) e crescimento por caractere para
// rótulos livres (ex.: "Amarelo"), sem DOM, determinístico.
const CHIP_W = 44;
const CHIP_H = 22;
const CHIP_GAP = 4;
const CHIP_CHAR_W = 6.6;

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

function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

/** Baselines absolutas das linhas de um card, centradas na vertical. */
function linhasCentradas(linhas: string[], cx: number, cy: number): LinhaTexto[] {
  const inicio = cy - ((linhas.length - 1) * LINE_H) / 2 + BASELINE;
  return linhas.map((texto, i) => ({ texto, x: cx, y: inicio + i * LINE_H }));
}

/** Separa os ramos de uma decisão por destino, preservando a ordem: retos
 * (seguem para o próximo nó), desvios (card lateral) e saltos (vai_para). */
function classificarRamos(no: FluxogramaNo) {
  const retos: FluxogramaRamo[] = [];
  const desvios: FluxogramaRamo[] = [];
  const saltos: FluxogramaRamo[] = [];
  for (const ramo of no.ramos ?? []) {
    if (ramo.desvio) desvios.push(ramo);
    else if (ramo.vai_para != null) saltos.push(ramo);
    else retos.push(ramo);
  }
  return { retos, desvios, saltos };
}

/** Linhas e altura de cada card de desvio de uma decisão, na ordem dos ramos. */
function medidasDesvios(ramos: FluxogramaRamo[]) {
  return ramos.map((ramo) => {
    const linhas = quebrarLinhas(ramo.desvio!.texto, DESVIO_TEXT_MAX);
    return { linhas, h: alturaCard(linhas.length, 20) };
  });
}

/** Fundo da pilha de desvios de uma decisão centrada em `cy` (o primeiro card
 * alinha ao centro da decisão; os demais empilham abaixo). */
function fundoDaPilha(cy: number, alturas: number[]): number {
  const total = alturas.reduce((soma, h) => soma + h, 0);
  return Math.round(cy - alturas[0] / 2 + total + (alturas.length - 1) * DESVIO_STACK_GAP);
}

export function calcularLayout(estrutura: FluxogramaEstrutura): FluxogramaLayout {
  const nos = estrutura.nos;

  // Numeração 1..N em ordem de fluxo: cada passo recebe o próximo número; ao
  // encontrar uma decisão, os cards de desvio dela (se houver) recebem os
  // próximos, na ordem dos ramos, antes do passo seguinte. Assim "Solicitar
  // reposição" fica entre "Reunir" e "Realizar", como no gabarito. A chave do
  // desvio é `id:índice na pilha` (uma decisão N-ária pode ter vários).
  const numeroDoPasso = new Map<string, number>();
  const numeroDoDesvio = new Map<string, number>();
  {
    let numero = 0;
    for (const no of nos) {
      if (no.tipo === "passo") {
        numeroDoPasso.set(no.id, ++numero);
      } else {
        let indicePilha = 0;
        for (const ramo of no.ramos ?? []) {
          if (ramo.desvio) numeroDoDesvio.set(`${no.id}:${indicePilha++}`, ++numero);
        }
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
    indicePilha: number;
    ultimoDaPilha: boolean;
  }[] = [];
  const setas: LayoutSeta[] = [];
  const chips: LayoutChip[] = [];
  let bordaDireita = DESVIO_X + DESVIO_W + 20; // trilhos de retorno podem alargar

  // Passo 1: posiciona a coluna principal e numera passos/desvios em ordem.
  let y = TOP;
  const inicio: LayoutTerminal = { tipo: "inicio", x: CX - INICIO_W / 2, y, w: INICIO_W, h: TERMINAL_H };
  let prevBottom = y + TERMINAL_H; // fundo do Início
  y = prevBottom + GAP;

  const posicoes: { no: FluxogramaNo; card: LayoutCard }[] = [];
  const cardPorId = new Map<string, LayoutCard>();

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
    cardPorId.set(no.id, card);
    centroYPorId.set(no.id, cy);

    // Seta vertical da coluna: do fundo do elemento anterior ao topo deste.
    setas.push({ d: `M ${CX} ${prevBottom} V ${y}` });

    prevBottom = y + h;
    let proximoY = prevBottom + GAP;
    if (ehDecisao) {
      const { retos, desvios: ramosDesvio } = classificarRamos(no);
      // Vão extra para a pilha de chips dos ramos retos (N-ário).
      proximoY += Math.max(0, retos.length - 1) * (CHIP_H + CHIP_GAP);
      // A pilha de desvios laterais não pode invadir o próximo elemento.
      if (ramosDesvio.length > 0) {
        const alturas = medidasDesvios(ramosDesvio).map((m) => m.h);
        proximoY = Math.max(proximoY, fundoDaPilha(cy, alturas) + RESERVA_LATERAL);
      }
    }
    y = proximoY;
  }

  const fim: LayoutTerminal = { tipo: "fim", x: CX - FIM_W / 2, y, w: FIM_W, h: TERMINAL_H };
  setas.push({ d: `M ${CX} ${prevBottom} V ${y}` });
  const alturaTotal = y + TERMINAL_H + BOTTOM_MARGIN;

  // Passo 2: desenha os desvios laterais, os saltos e os chips das decisões.
  let contadorSaltos = 0;
  for (let idx = 0; idx < posicoes.length; idx++) {
    const { no, card } = posicoes[idx];
    if (no.tipo !== "decisao") continue;

    const decisaoCy = card.y + card.h / 2;
    const decisaoBottom = card.y + card.h;
    const proxTop = idx + 1 < posicoes.length ? posicoes[idx + 1].card.y : fim.y;
    const { retos, desvios: ramosDesvio, saltos } = classificarRamos(no);

    // Ramos retos: chips empilhados na seta vertical, centrados no vão (que o
    // Passo 1 alargou quando há mais de um).
    const passoChip = CHIP_H + CHIP_GAP;
    const baseRetos = (decisaoBottom + proxTop) / 2 - ((retos.length - 1) * passoChip) / 2;
    retos.forEach((ramo, i) => chips.push(chipRamo(ramo.rotulo, CX, baseRetos + i * passoChip)));

    // Ramos laterais: pilha de cards à direita; o primeiro alinha ao centro da
    // decisão e os demais empilham abaixo (o Passo 1 reservou o espaço).
    const medidas = medidasDesvios(ramosDesvio);
    let topoPilha = Math.round(decisaoCy - (medidas[0]?.h ?? 0) / 2);
    ramosDesvio.forEach((ramo, i) => {
      const { linhas: desvioLinhas, h: desvioH } = medidas[i];
      const desvioY = topoPilha;
      const desvioCy = desvioY + desvioH / 2;
      const desvioCard: LayoutCard = {
        tipo: "desvio",
        x: DESVIO_X,
        y: desvioY,
        w: DESVIO_W,
        h: desvioH,
        badge: { tipo: "numero", cx: DESVIO_X, cy: desvioCy, numero: numeroDoDesvio.get(`${no.id}:${i}`) },
        linhas: linhasCentradas(desvioLinhas, DESVIO_TEXT_CX, desvioCy),
      };
      cards.push(desvioCard);

      if (i === 0) {
        // Seta horizontal: da borda direita da decisão à borda esquerda do desvio.
        setas.push({ d: `M ${CARD_X + CARD_W} ${decisaoCy} H ${DESVIO_X - 4}` });
        chips.push(chipRamo(ramo.rotulo, (CARD_X + CARD_W + DESVIO_X) / 2, decisaoCy));
      } else {
        // Cotovelo ortogonal: sai mais abaixo na borda direita da decisão e
        // desce até o card seguinte da pilha; o chip fica no trecho vertical.
        const saidaY = Math.min(decisaoCy + i * 12, decisaoBottom - 6);
        const mx = CARD_X + CARD_W + 12 + i * 14;
        setas.push({
          d:
            `M ${CARD_X + CARD_W} ${saidaY} H ${mx} Q ${mx + 8} ${saidaY} ${mx + 8} ${saidaY + 8} ` +
            `V ${desvioCy - 8} Q ${mx + 8} ${desvioCy} ${mx + 16} ${desvioCy} H ${DESVIO_X - 4}`,
        });
        chips.push(chipRamo(ramo.rotulo, mx + 8, (saidaY + desvioCy) / 2));
      }

      desvios.push({
        card: desvioCard,
        decisaoCy,
        decisaoBottom,
        proxTop,
        retornaPara: ramo.desvio!.retorna_para,
        indicePilha: i,
        ultimoDaPilha: i === ramosDesvio.length - 1,
      });
      topoPilha = desvioY + desvioH + DESVIO_STACK_GAP;
    });

    // Saltos (vai_para): seta ortogonal pela lateral esquerda até o nó alvo ou
    // o terminal Fim, cada salto num trilho vertical próprio (sem sobreposição).
    saltos.forEach((ramo, i) => {
      // Saídas alternam acima/abaixo do centro, longe do badge "?" da decisão.
      const saidaY = Math.round(decisaoCy + (i % 2 === 0 ? -1 : 1) * (14 + Math.floor(i / 2) * 24));
      const trilho = SALTO_RAIL_X - contadorSaltos * SALTO_RAIL_STEP;
      contadorSaltos += 1;
      const paraFim = ramo.vai_para === "fim";
      const alvoY = paraFim ? fim.y + TERMINAL_H / 2 : centroYPorId.get(ramo.vai_para!);
      if (alvoY == null) return; // estrutura validada nunca chega aqui
      const alvoX = paraFim ? fim.x - 4 : CARD_X - 4;
      const dir = alvoY > saidaY ? 1 : -1;
      setas.push({
        d:
          `M ${CARD_X} ${saidaY} H ${trilho + 8} Q ${trilho} ${saidaY} ${trilho} ${saidaY + 8 * dir} ` +
          `V ${alvoY - 8 * dir} Q ${trilho} ${alvoY} ${trilho + 8} ${alvoY} H ${alvoX}`,
      });
      const chipSalto = chipRamo(ramo.rotulo, 0, saidaY);
      chipSalto.x = CARD_X - 12 - chipSalto.w; // encostado à esquerda da decisão
      chips.push(chipSalto);
    });
  }

  // Passo 3: setas de retorno e de "segue o fluxo" dos desvios (dependem das
  // posições finais de todos os nós). Cards abaixo do primeiro da pilha não
  // podem atravessar os de cima: contornam a pilha por trilhos à direita.
  for (const d of desvios) {
    const desvioCx = d.card.x + d.card.w / 2;
    const desvioCy = d.card.y + d.card.h / 2;
    const fundo = d.card.y + d.card.h;
    const alvoCy = d.retornaPara != null ? centroYPorId.get(d.retornaPara) : undefined;
    if (alvoCy != null) {
      if (alvoCy + 8 >= d.card.y) {
        // Alvo no mesmo nível ou abaixo do topo do card (ex.: retorno à própria
        // decisão): sai pela borda esquerda e entra na borda direita do alvo,
        // acima da seta de ida, sem atravessar o card.
        const alvoCard = cardPorId.get(d.retornaPara!);
        const alvoTopo = alvoCard ? alvoCard.y : alvoCy - CARD_H_MIN / 2;
        const alvoFundo = alvoCard ? alvoCard.y + alvoCard.h : alvoCy + CARD_H_MIN / 2;
        const entradaY = clamp(alvoCy - 14, alvoTopo + 8, alvoFundo - 8);
        const saidaY = clamp(entradaY, d.card.y + 10, fundo - 10);
        if (saidaY === entradaY) {
          setas.push({ d: `M ${DESVIO_X} ${saidaY} H ${CARD_X + CARD_W + 4}` });
        } else {
          const mx = (CARD_X + CARD_W + DESVIO_X) / 2 + 18;
          const dir = entradaY > saidaY ? 1 : -1;
          setas.push({
            d:
              `M ${DESVIO_X} ${saidaY} H ${mx + 8} Q ${mx} ${saidaY} ${mx} ${saidaY + 8 * dir} ` +
              `V ${entradaY - 8 * dir} Q ${mx} ${entradaY} ${mx - 8} ${entradaY} H ${CARD_X + CARD_W + 4}`,
          });
        }
      } else if (d.indicePilha === 0) {
        // Retorno a um nó (alvo acima, laço): sobe pelo topo e entra à direita.
        setas.push({
          d: `M ${desvioCx} ${d.card.y} V ${alvoCy + 8} Q ${desvioCx} ${alvoCy} ${desvioCx - 8} ${alvoCy} H ${CARD_X + CARD_W + 4}`,
        });
      } else {
        const trilho = DESVIO_X + DESVIO_W + 12 + (d.indicePilha - 1) * RETORNO_RAIL_STEP;
        bordaDireita = Math.max(bordaDireita, trilho + 10);
        setas.push({
          d:
            `M ${DESVIO_X + DESVIO_W} ${desvioCy} H ${trilho - 8} Q ${trilho} ${desvioCy} ${trilho} ${desvioCy - 8} ` +
            `V ${alvoCy + 8} Q ${trilho} ${alvoCy} ${trilho - 8} ${alvoCy} H ${CARD_X + CARD_W + 4}`,
        });
      }
    } else if (d.ultimoDaPilha) {
      // Segue o fluxo: desce e reentra na coluna abaixo da decisão (a junta
      // nunca sobe: fica abaixo do fundo do próprio card).
      const junta = Math.max(Math.round((d.decisaoBottom + d.proxTop) / 2), fundo + 8);
      setas.push({
        d: `M ${desvioCx} ${fundo} V ${junta} Q ${desvioCx} ${junta + 8} ${desvioCx - 8} ${junta + 8} H ${CX + 4}`,
      });
    } else {
      // Segue o fluxo sem ser o último da pilha: contorna pela direita e
      // reentra na coluna no vão reservado antes do próximo elemento.
      const trilho = DESVIO_X + DESVIO_W + 12 + d.indicePilha * RETORNO_RAIL_STEP;
      bordaDireita = Math.max(bordaDireita, trilho + 10);
      const junta = d.proxTop - 10;
      setas.push({
        d:
          `M ${DESVIO_X + DESVIO_W} ${desvioCy} H ${trilho - 8} Q ${trilho} ${desvioCy} ${trilho} ${desvioCy + 8} ` +
          `V ${junta - 8} Q ${trilho} ${junta} ${trilho - 8} ${junta} H ${CX + 4}`,
      });
    }
  }

  const largura = bordaDireita;
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
  const texto = rotulo.trim();
  const norm = texto.toLowerCase();
  const tom: LayoutChip["tom"] = norm === "sim" ? "sim" : norm === "não" || norm === "nao" ? "nao" : "neutro";
  // Largura mínima cobre Sim/Não; rótulos livres (neutros) crescem com o texto.
  const w = Math.max(CHIP_W, Math.round(texto.length * CHIP_CHAR_W) + 20);
  return {
    rotulo,
    tom,
    x: Math.round(centroX - w / 2),
    y: Math.round(centroY - CHIP_H / 2),
    w,
    h: CHIP_H,
  };
}
