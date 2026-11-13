/**
 * O Fluxograma do manual (issue #1719, emenda da ADR 0094): a leitura do bloco
 * e a geometria do desenho, sem React. O componente `Fluxograma` só pinta o
 * que sai daqui.
 *
 * ## O formato do bloco `fluxograma`
 *
 * Uma declaração por linha. Linha em branco e linha que começa com `#` são
 * ignoradas.
 *
 * Passo, com a posição na grade (linha,coluna, contadas a partir de 1), o
 * rótulo depois dos dois-pontos e, se quiser, o detalhe depois da barra:
 *
 *     inicio abrir 1,1: Abrir a reunião
 *     passo pauta 2,1: Montar a pauta | O Secretário escolhe os itens.
 *     decisao quorum 3,1: Tem quórum?
 *     fim ata 4,1: Ata assinada
 *
 * As formas são `inicio`, `passo`, `decisao` e `fim` (com ou sem acento). O
 * identificador (`abrir`, `pauta`) é o nome do passo dentro do bloco: letras,
 * números, `-` e `_`, sem espaço.
 *
 * Ligação, da origem ao destino, com o rótulo opcional depois dos dois-pontos:
 *
 *     abrir -> pauta
 *     quorum -> ata: sim
 *     quorum -> remarcar: não
 *
 * Quem escreve a página não mexe em coordenada de pixel: a grade decide onde
 * cada passo fica, e as ligações saem sozinhas em ângulo reto. No celular a
 * grade desce para uma coluna, na ordem do fluxo.
 *
 * Bloco com passo repetido, ligação para passo que não existe, posição já
 * ocupada ou linha que não se entende vira mensagem de erro no lugar do
 * desenho, com o número da linha.
 */

export type Forma = "inicio" | "passo" | "decisao" | "fim";

export interface Passo {
  id: string;
  forma: Forma;
  linha: number;
  coluna: number;
  rotulo: string;
  detalhe: string;
}

export interface Ligacao {
  de: string;
  para: string;
  rotulo: string;
}

export interface Fluxo {
  passos: Passo[];
  ligacoes: Ligacao[];
}

export type Leitura = { ok: true; fluxo: Fluxo } | { ok: false; erros: string[] };

const FORMAS: Record<string, Forma> = {
  inicio: "inicio",
  "início": "inicio",
  passo: "passo",
  decisao: "decisao",
  "decisão": "decisao",
  fim: "fim",
};

const LINHA_DE_PASSO = /^(\S+)\s+([\w-]+)\s+(\d+)\s*,\s*(\d+)\s*:\s*(.+)$/u;
const LINHA_DE_LIGACAO = /^([\w-]+)\s*->\s*([\w-]+)\s*(?::\s*(.*))?$/u;

/** Lê o texto do bloco `fluxograma`. */
export function lerFluxograma(fonte: string): Leitura {
  const passos: Passo[] = [];
  const ligacoes: (Ligacao & { linhaDoBloco: number })[] = [];
  const erros: string[] = [];

  fonte.split("\n").forEach((cru, i) => {
    const texto = cru.trim();
    const n = i + 1;
    if (!texto || texto.startsWith("#")) return;

    const ligacao = LINHA_DE_LIGACAO.exec(texto);
    if (ligacao) {
      ligacoes.push({ de: ligacao[1], para: ligacao[2], rotulo: (ligacao[3] ?? "").trim(), linhaDoBloco: n });
      return;
    }

    const passo = LINHA_DE_PASSO.exec(texto);
    const forma = passo ? FORMAS[passo[1].toLowerCase()] : undefined;
    if (!passo || !forma) {
      erros.push(`Linha ${n}: não entendi "${texto}".`);
      return;
    }
    const [rotulo, ...detalhe] = passo[5].split("|");
    const novo: Passo = {
      id: passo[2],
      forma,
      linha: Number(passo[3]),
      coluna: Number(passo[4]),
      rotulo: rotulo.trim(),
      detalhe: detalhe.join("|").trim(),
    };
    if (passos.some((p) => p.id === novo.id)) {
      erros.push(`Linha ${n}: o passo "${novo.id}" já foi declarado.`);
      return;
    }
    const dono = passos.find((p) => p.linha === novo.linha && p.coluna === novo.coluna);
    if (dono) {
      erros.push(`Linha ${n}: a posição ${novo.linha},${novo.coluna} já é do passo "${dono.id}".`);
      return;
    }
    passos.push(novo);
  });

  const ids = new Set(passos.map((p) => p.id));
  for (const l of ligacoes) {
    for (const ponta of [l.de, l.para]) {
      if (!ids.has(ponta)) erros.push(`Linha ${l.linhaDoBloco}: a ligação ${l.de} -> ${l.para} cita o passo "${ponta}", que não existe.`);
    }
  }

  if (erros.length) return { ok: false, erros };
  if (!passos.length) return { ok: false, erros: ["O fluxograma não tem nenhum passo."] };
  return { ok: true, fluxo: { passos, ligacoes: ligacoes.map(({ de, para, rotulo }) => ({ de, para, rotulo })) } };
}

/**
 * A ordem do fluxo: a partir do início (ou dos passos sem ligação chegando),
 * seguindo as ligações em largura. Passo que nenhuma ligação alcança entra no
 * fim, na ordem em que foi declarado. É a ordem em que os passos aparecem, a
 * do "Percorrer" e a da lista do leitor de tela.
 */
export function ordemDoFluxo(fluxo: Fluxo): Passo[] {
  const porId = new Map(fluxo.passos.map((p) => [p.id, p]));
  const chegam = new Set(fluxo.ligacoes.map((l) => l.para));
  let fila = fluxo.passos.filter((p) => p.forma === "inicio");
  if (!fila.length) fila = fluxo.passos.filter((p) => !chegam.has(p.id));
  const vistos = new Set<string>();
  const ordem: Passo[] = [];
  while (fila.length) {
    const atual = fila.shift()!;
    if (vistos.has(atual.id)) continue;
    vistos.add(atual.id);
    ordem.push(atual);
    for (const l of fluxo.ligacoes) if (l.de === atual.id && !vistos.has(l.para)) fila.push(porId.get(l.para)!);
  }
  for (const p of fluxo.passos) if (!vistos.has(p.id)) ordem.push(p);
  return ordem;
}

/** O caminho que passa por um passo: o que leva até ele e o que sai dele. */
export function caminhoPor(fluxo: Fluxo, id: string): { passos: Set<string>; ligacoes: Set<string> } {
  const alcance = (ida: boolean) => {
    const achados = new Set<string>([id]);
    const fila = [id];
    while (fila.length) {
      const atual = fila.shift()!;
      for (const l of fluxo.ligacoes) {
        const [daqui, dali] = ida ? [l.de, l.para] : [l.para, l.de];
        if (daqui === atual && !achados.has(dali)) {
          achados.add(dali);
          fila.push(dali);
        }
      }
    }
    return achados;
  };
  const antes = alcance(false);
  const depois = alcance(true);
  const ligacoes = new Set(
    fluxo.ligacoes
      .filter((l) => (antes.has(l.de) && antes.has(l.para)) || (depois.has(l.de) && depois.has(l.para)))
      .map(chaveDaLigacao),
  );
  return { passos: new Set([...antes, ...depois]), ligacoes };
}

export function chaveDaLigacao(l: Ligacao): string {
  return `${l.de}->${l.para}`;
}

// ─── Geometria ───────────────────────────────────────────────────────────

const LARGURA_DA_COLUNA = 240;
const ALTURA_DA_LINHA = 140;
const MARGEM = 24;
/** Folga à direita, para a ligação que volta por fora da coluna. */
const FOLGA_DA_VOLTA = 40;

const TAMANHO: Record<Forma, { w: number; h: number }> = {
  inicio: { w: 184, h: 52 },
  passo: { w: 184, h: 64 },
  decisao: { w: 176, h: 100 },
  fim: { w: 184, h: 52 },
};

export interface PassoDesenhado extends Passo {
  x: number;
  y: number;
  w: number;
  h: number;
  /** O rótulo quebrado em linhas que cabem na forma. */
  linhasDoRotulo: string[];
}

export interface LigacaoDesenhada extends Ligacao {
  chave: string;
  pontos: [number, number][];
  comprimento: number;
  posicaoDoRotulo: [number, number] | null;
}

export interface Desenho {
  largura: number;
  altura: number;
  passos: PassoDesenhado[];
  ligacoes: LigacaoDesenhada[];
}

function quebrar(texto: string, porLinha: number): string[] {
  const linhas: string[] = [];
  let atual = "";
  for (const palavra of texto.split(/\s+/)) {
    if (atual && (atual + " " + palavra).length > porLinha) {
      linhas.push(atual);
      atual = palavra;
    } else {
      atual = atual ? `${atual} ${palavra}` : palavra;
    }
  }
  if (atual) linhas.push(atual);
  return linhas;
}

/**
 * Onde cada passo e cada ligação ficam. Com `umaColuna`, a grade desce para
 * uma coluna na ordem do fluxo (o celular).
 */
export function desenharFluxo(fluxo: Fluxo, umaColuna = false): Desenho {
  const posicao = new Map<string, { linha: number; coluna: number }>();
  if (umaColuna) ordemDoFluxo(fluxo).forEach((p, i) => posicao.set(p.id, { linha: i + 1, coluna: 1 }));
  else for (const p of fluxo.passos) posicao.set(p.id, { linha: p.linha, coluna: p.coluna });

  const passos: PassoDesenhado[] = fluxo.passos.map((p) => {
    const { linha, coluna } = posicao.get(p.id)!;
    const { w, h } = TAMANHO[p.forma];
    return {
      ...p,
      linha,
      coluna,
      x: MARGEM + (coluna - 1) * LARGURA_DA_COLUNA + LARGURA_DA_COLUNA / 2,
      y: MARGEM + (linha - 1) * ALTURA_DA_LINHA + ALTURA_DA_LINHA / 2,
      w,
      h,
      linhasDoRotulo: quebrar(p.rotulo, p.forma === "decisao" ? 16 : 22),
    };
  });
  const porId = new Map(passos.map((p) => [p.id, p]));
  const colunas = Math.max(...passos.map((p) => p.coluna));
  const linhas = Math.max(...passos.map((p) => p.linha));

  const ligacoes = fluxo.ligacoes.map((l): LigacaoDesenhada => {
    const o = porId.get(l.de)!;
    const d = porId.get(l.para)!;
    const pontos = rota(o, d, passos);
    const comprimento = pontos
      .slice(1)
      .reduce((soma, [x, y], i) => soma + Math.abs(x - pontos[i][0]) + Math.abs(y - pontos[i][1]), 0);
    return { ...l, chave: chaveDaLigacao(l), pontos, comprimento, posicaoDoRotulo: l.rotulo ? ondeVaiORotulo(pontos) : null };
  });

  return {
    largura: MARGEM * 2 + colunas * LARGURA_DA_COLUNA + FOLGA_DA_VOLTA,
    altura: MARGEM * 2 + linhas * ALTURA_DA_LINHA,
    passos,
    ligacoes,
  };
}

/** A rota em ângulo reto entre dois passos. */
function rota(o: PassoDesenhado, d: PassoDesenhado, todos: PassoDesenhado[]): [number, number][] {
  const topo = (p: PassoDesenhado): [number, number] => [p.x, p.y - p.h / 2];
  const base = (p: PassoDesenhado): [number, number] => [p.x, p.y + p.h / 2];
  const esquerda = (p: PassoDesenhado): [number, number] => [p.x - p.w / 2, p.y];
  const direita = (p: PassoDesenhado): [number, number] => [p.x + p.w / 2, p.y];
  const ladoRumoA = (p: PassoDesenhado, alvo: PassoDesenhado) => (alvo.x > p.x ? direita(p) : esquerda(p));
  /** Volta por fora, pela direita da coluna. */
  const porFora = (): [number, number][] => {
    const xFora = o.x + LARGURA_DA_COLUNA / 2 - 8;
    return [direita(o), [xFora, o.y], [xFora, d.y], direita(d)];
  };

  if (o.coluna === d.coluna) {
    const entre = todos.some(
      (p) => p.coluna === o.coluna && p.linha > Math.min(o.linha, d.linha) && p.linha < Math.max(o.linha, d.linha),
    );
    if (d.linha > o.linha && !entre) return [base(o), topo(d)];
    return porFora();
  }
  if (o.linha === d.linha) return [ladoRumoA(o, d), ladoRumoA(d, o)];
  if (d.linha > o.linha) {
    if (o.forma === "decisao") return [ladoRumoA(o, d), [d.x, o.y], topo(d)];
    const [bx, by] = base(o);
    const [, ty] = topo(d);
    const meio = by + (ty - by) / 2;
    return [[bx, by], [bx, meio], [d.x, meio], topo(d)];
  }
  return [ladoRumoA(o, d), [d.x, o.y], base(d)];
}

/** O rótulo da ligação ("sim", "não") fica logo na saída da origem. */
function ondeVaiORotulo(pontos: [number, number][]): [number, number] {
  const [[x0, y0], [x1]] = pontos;
  if (x0 !== x1) return [x0 + (x1 > x0 ? 10 : -10), y0 - 8];
  return [x0 + 8, y0 + 18];
}

/**
 * Quando cada coisa aparece na entrada (em ms). O passo aparece pela ordem do
 * fluxo; a ligação se desenha depois que a origem dela apareceu. Tudo cabe em
 * menos de um segundo e meio.
 */
export const DURACAO_DO_PASSO = 300;
export const DURACAO_DA_LIGACAO = 300;

export function tempos(fluxo: Fluxo): { passo: Map<string, number>; ligacao: Map<string, number> } {
  const ordem = ordemDoFluxo(fluxo);
  const intervalo = Math.min(120, 700 / Math.max(ordem.length, 1));
  const passo = new Map(ordem.map((p, i) => [p.id, Math.round(i * intervalo)]));
  const ligacao = new Map(
    fluxo.ligacoes.map((l) => [chaveDaLigacao(l), passo.get(l.de)! + Math.round(DURACAO_DO_PASSO / 2)]),
  );
  return { passo, ligacao };
}
