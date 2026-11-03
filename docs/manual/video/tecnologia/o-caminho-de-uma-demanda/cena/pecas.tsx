/* =====================================================================================
   videos/Tecnologia/pecas.tsx: as peças do Vídeo de visão geral da Tecnologia, o chat do
   Assistente (PRD #1380; o molde é o de
   Contas médicas, o piloto do estilo).

   A tela do app mora numa JANELA fixa (1440x810, no alto do quadro). Dentro dela, a câmera anda
   sobre o print real (1920x1080 em pixels da janela do navegador) de um alvo ao outro, presa às
   palavras da fala. As caixas dos alvos vêm do roteiro de prints (alvos.json, gravado pelo
   docs/manual/prints/tecnologia.py --video): o destaque contorna o elemento inteiro, com ar em
   volta, sem medir a olho.

   Plano = o que a câmera mostra a partir de uma palavra: a tela, o foco e o zoom, os destaques,
   para onde o cursor vai e se ele clica. Entre dois planos a câmera desliza (curva `corte`); dentro
   do plano ela empurra devagar (nada fica parado).
   ===================================================================================== */
import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion';
import { Fala, useLayoutFala } from '../../Fala';
import { useCenaM } from '../../cena';
import { BRILHO, clamp01, CORM, janelaM, lerp, PALETA, RGB, type Palavra } from '../../tema';
import ALVOS from './alvos.json';

export const JANELA = { x: 240, y: 70, w: 1440, h: 810, r: 20 };
const TELA = { w: 1920, h: 1080 };
const BASE = JANELA.w / TELA.w;
/** folga do destaque em volta do elemento, em pixels da tela do app */
const FOLGA = 9;

type Caixa = [number, number, number, number];
const TELAS = ALVOS as unknown as Record<string, Record<string, Caixa>>;

export const caixa = (tela: string, nome: string): Caixa => {
  const c = TELAS[tela]?.[nome];
  if (!c) throw new Error(`alvos: ${tela}/${nome} não existe`);
  return c;
};

/** A união de várias caixas (para o foco cobrir mais de um elemento). */
export const uniao = (tela: string, nomes: string[]): Caixa => {
  const cs = nomes.map((n) => caixa(tela, n));
  const x0 = Math.min(...cs.map((c) => c[0]));
  const y0 = Math.min(...cs.map((c) => c[1]));
  const x1 = Math.max(...cs.map((c) => c[0] + c[2]));
  const y1 = Math.max(...cs.map((c) => c[1] + c[3]));
  return [x0, y0, x1 - x0, y1 - y0];
};

/* ---------------------------------------------------------------- tempo das palavras */

/** Índice da primeira palavra da lista que começa com `inicio` (sem acento e caixa), a partir de `de`. */
export const achar = (fala: Palavra[], inicio: string, de = 0): number => {
  const limpa = (t: string) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9$]/g, '');
  const alvo = limpa(inicio);
  for (let i = de; i < fala.length; i++) if (limpa(fala[i].t).startsWith(alvo)) return i;
  throw new Error(`fala: "${inicio}" não aparece depois da palavra ${de} (${fala.map((p) => p.t).join(' ')})`);
};

/* ---------------------------------------------------------------- planos */

export type Plano = {
  /** quadro local da palavra que dispara o plano */
  em: number;
  tela: string;
  /** onde a câmera centra: nome de alvo, lista de alvos (união) ou caixa; ausente = tela inteira */
  foco?: string | string[] | Caixa;
  /** 1 = a tela inteira na janela */
  zoom?: number;
  destaque?: string[];
  cursor?: string;
  clique?: boolean;
  /** etiquetas de arquivo presas ao cursor (arrastar) */
  carrega?: string[];
};

type Cam = { z: number; fx: number; fy: number };

const caixaDoFoco = (p: Plano): Caixa | null => {
  if (!p.foco) return null;
  return typeof p.foco === 'string' ? caixa(p.tela, p.foco) : Array.isArray(p.foco) && typeof p.foco[0] === 'string' ? uniao(p.tela, p.foco as string[]) : (p.foco as Caixa);
};

/** margem mínima em volta do foco, em pixels da janela: o elemento entra inteiro, com ar */
const MARGEM = 48;

/** a câmera chega à palavra: começa a andar ANTES quadros antes e leva DUR quadros */
const ANTES = 9;
const DUR = 22;

/** o empurrão lento, por segundo: a mesma velocidade em cena curta e em cena longa */
const DERIVA_POR_S = 0.008;

const camera = (planos: Plano[], f: number, folga: number): Cam => {
  const alvoDe = (p: Plano): Cam => {
    const c = caixaDoFoco(p);
    if (!c) return { z: p.zoom ?? 1, fx: TELA.w / 2, fy: TELA.h / 2 };
    // o zoom pedido nunca corta o foco: cabe inteiro, com MARGEM, na janela
    // o empurrão ainda cresce até o fim da cena: o foco cabe com ele no máximo (folga)
    const cabe = Math.min((JANELA.w - 2 * MARGEM) / (c[2] * BASE), (JANELA.h - 2 * MARGEM) / (c[3] * BASE)) / folga;
    return { z: Math.max(1, Math.min(p.zoom ?? 1, cabe)), fx: c[0] + c[2] / 2, fy: c[1] + c[3] / 2 };
  };
  let cam = alvoDe(planos[0]);
  for (let k = 1; k < planos.length; k++) {
    const t = janelaM(f, planos[k].em - ANTES, planos[k].em - ANTES + DUR, 'corte');
    if (t <= 0) break;
    const a = alvoDe(planos[k]);
    cam = { z: lerp(cam.z, a.z, t), fx: lerp(cam.fx, a.fx, t), fy: lerp(cam.fy, a.fy, t) };
  }
  return cam;
};

/** zoom e foco viram escala e deslocamento, sem mostrar o lado de fora do print */
const transformar = (cam: Cam) => {
  const s = BASE * cam.z;
  const tx = Math.min(0, Math.max(JANELA.w - TELA.w * s, JANELA.w / 2 - cam.fx * s));
  const ty = Math.min(0, Math.max(JANELA.h - TELA.h * s, JANELA.h / 2 - cam.fy * s));
  return { s, tx, ty };
};

const indiceAtivo = (planos: Plano[], f: number) => {
  let k = 0;
  for (let i = 1; i < planos.length; i++) if (f >= planos[i].em - 3) k = i;
  return k;
};

/* ---------------------------------------------------------------- a tela na janela */

export const TelaNaJanela: React.FC<{ planos: Plano[] }> = ({ planos }) => {
  const c = useCenaM();
  const f = c.frame;
  const folga = 1 + DERIVA_POR_S * (c.seqDuracao / 30);
  const cam = camera(planos, f, folga);
  // o empurrão lento, em velocidade constante até o fim da sequência: com easing ele assentava
  // antes da saída e o freezedetect acusava 0,5 a 1 s de tela parada no fim de cada cena
  const empurra = 1 + DERIVA_POR_S * (clamp01(f / Math.max(1, c.seqDuracao)) * c.seqDuracao / 30);
  const { s, tx, ty } = transformar({ ...cam, z: cam.z * empurra });

  // as telas: a que muda entra por cima da anterior em 12 quadros
  const telas: { tela: string; desde: number }[] = [];
  planos.forEach((p) => {
    if (!telas.length || telas[telas.length - 1].tela !== p.tela) telas.push({ tela: p.tela, desde: p.em - 6 });
  });
  telas[0].desde = -999;

  const k = indiceAtivo(planos, f);
  return (
    <div
      style={{
        position: 'absolute',
        left: JANELA.x,
        top: JANELA.y,
        width: JANELA.w,
        height: JANELA.h,
        borderRadius: JANELA.r,
        overflow: 'hidden',
        background: '#FFFFFF',
        boxShadow: `0 30px 80px rgba(0,0,0,.55), 0 0 0 1px rgba(${RGB.claro},.28), 0 0 60px rgba(${RGB.acento},.18)`,
      }}
    >
      {/* O print vai no tamanho final, sem transform: escalado pelo transform, o navegador às vezes
          entrega o quadro com a camada ainda em baixa resolução, e some o que é claro e fino (a data
          da Conversa, a borda dos campos). */}
      {telas.map((t, i) => {
        const op = i === 0 ? 1 : janelaM(f, t.desde, t.desde + 12, 'sai');
        if (op <= 0) return null;
        return <Img key={t.tela} src={staticFile(`${t.tela}.png`)} style={{ position: 'absolute', left: tx, top: ty, width: TELA.w * s, height: TELA.h * s, opacity: op }} />;
      })}
      <div style={{ position: 'absolute', left: 0, top: 0, width: TELA.w, height: TELA.h, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${s})` }}>
        <Destaques planos={planos} k={k} f={f} s={s} />
        <Cursor planos={planos} f={f} s={s} />
      </div>
    </div>
  );
};

/* ---------------------------------------------------------------- destaque */

const Destaques: React.FC<{ planos: Plano[]; k: number; f: number; s: number }> = ({ planos, k, f, s }) => {
  // o plano anterior ainda some enquanto o novo acende
  const vivos = [k - 1, k].filter((i) => i >= 0 && planos[i].destaque?.length);
  const caixas: { c: Caixa; op: number; t: number }[] = [];
  vivos.forEach((i) => {
    const p = planos[i];
    const proximo = planos[i + 1]?.em ?? Infinity;
    (p.destaque ?? []).forEach((nome, j) => {
      const q = p.em + j * 5;
      const entra = janelaM(f, q, q + 8, 'sai');
      const sai = Number.isFinite(proximo) ? 1 - janelaM(f, proximo - 5, proximo + 3, 'entra') : 1;
      const op = entra * sai;
      if (op > 0.001) caixas.push({ c: caixa(p.tela, nome), op, t: f - q });
    });
  });
  if (!caixas.length) return null;
  const veu = Math.max(...caixas.map((x) => x.op));
  const borda = 3.2 / s;
  const raio = 12 / s;
  return (
    <>
      <svg width={TELA.w} height={TELA.h} style={{ position: 'absolute', left: 0, top: 0 }}>
        <defs>
          <mask id="furos">
            <rect x={0} y={0} width={TELA.w} height={TELA.h} fill="white" />
            {caixas.map(({ c }, i) => (
              <rect key={i} x={c[0] - FOLGA} y={c[1] - FOLGA} width={c[2] + 2 * FOLGA} height={c[3] + 2 * FOLGA} rx={raio} fill="black" />
            ))}
          </mask>
        </defs>
        <rect x={0} y={0} width={TELA.w} height={TELA.h} fill={`rgba(${RGB.fundo},${0.3 * veu})`} mask="url(#furos)" />
      </svg>
      {caixas.map(({ c, op, t }, i) => {
        const pop = 1 + 0.05 * (1 - janelaM(t, 0, 10, 'sai'));
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: c[0] - FOLGA,
              top: c[1] - FOLGA,
              width: c[2] + 2 * FOLGA,
              height: c[3] + 2 * FOLGA,
              borderRadius: raio,
              border: `${borda}px solid ${PALETA.acento}`,
              boxShadow: `0 0 ${18 / s}px rgba(${RGB.acento},.75), inset 0 0 ${10 / s}px rgba(${RGB.acento},.25)`,
              opacity: op,
              transform: `scale(${pop})`,
            }}
          />
        );
      })}
    </>
  );
};

/* ---------------------------------------------------------------- cursor */

const SETA = 'M2 2 L2 26 L8.5 19.5 L13 30 L17 28 L12.6 17.8 L21.5 17.8 Z';

const Cursor: React.FC<{ planos: Plano[]; f: number; s: number }> = ({ planos, f, s }) => {
  const usados = planos.filter((p) => p.cursor);
  if (!usados.length || f < usados[0].em - 24) return null;
  const centro = (p: Plano): [number, number] => {
    const c = caixa(p.tela, p.cursor as string);
    // botão e link: um pouco à esquerda do meio, onde a mão para; área grande (soltar arquivo): o meio
    return [c[0] + (c[2] > 400 ? c[2] * 0.5 : Math.min(c[2] * 0.5, 60)), c[1] + c[3] * 0.62];
  };
  // entra pela borda de baixo, à direita do primeiro alvo
  let [x, y] = centro(usados[0]);
  let pos: [number, number] = [x + 260, y + 300];
  let carrega: string[] = [];
  let soltou = 0;
  for (const p of usados) {
    const t = janelaM(f, p.em - 20, p.em - 1, 'corte');
    if (t <= 0) break;
    const alvo = centro(p);
    pos = [lerp(pos[0], alvo[0], t), lerp(pos[1], alvo[1], t)];
    carrega = p.carrega ?? [];
    soltou = p.carrega ? janelaM(f, p.em + 6, p.em + 16, 'entra') : 0;
  }
  [x, y] = pos;
  const aparece = janelaM(f, usados[0].em - 24, usados[0].em - 14, 'sai');
  const cliques = usados.filter((p) => p.clique).map((p) => p.em);
  const ultimo = cliques.filter((q) => f >= q).pop();
  const dt = ultimo === undefined ? 99 : f - ultimo;
  const aperta = dt < 6 ? 1 - 0.14 * Math.sin((dt / 6) * Math.PI) : 1;
  const k = 1 / s;
  return (
    <>
      {dt < 16 ? (
        <div
          style={{
            position: 'absolute',
            left: x - 30 * k * janelaM(dt, 0, 16, 'sai'),
            top: y - 30 * k * janelaM(dt, 0, 16, 'sai'),
            width: 60 * k * janelaM(dt, 0, 16, 'sai'),
            height: 60 * k * janelaM(dt, 0, 16, 'sai'),
            borderRadius: '50%',
            border: `${3 * k}px solid ${PALETA.acento}`,
            opacity: 1 - janelaM(dt, 4, 16, 'sai'),
          }}
        />
      ) : null}
      {carrega.map((nome, i) => (
        <div
          key={nome}
          style={{
            position: 'absolute',
            left: x + (26 + i * 10) * k,
            top: y + (30 + i * 46) * k,
            transformOrigin: '0 0',
            transform: `scale(${k * (1 - 0.3 * soltou)})`,
            opacity: aparece * (1 - soltou),
            padding: '8px 14px',
            borderRadius: 10,
            background: CORM.fundo,
            color: CORM.papel,
            fontFamily: 'HP Simplified',
            fontSize: 26,
            whiteSpace: 'nowrap',
            boxShadow: `0 8px 24px rgba(0,0,0,.35), 0 0 0 1.5px rgba(${RGB.claro},.6)`,
          }}
        >
          {nome}
        </div>
      ))}
      <svg
        width={34 * k}
        height={34 * k}
        viewBox="0 0 32 32"
        style={{ position: 'absolute', left: x - 2 * k, top: y - 2 * k, opacity: aparece, transform: `scale(${aperta})`, transformOrigin: '2px 2px', overflow: 'visible' }}
      >
        <path d={SETA} fill="#FFFFFF" stroke={CORM.fundo} strokeWidth={1.8} strokeLinejoin="round" style={{ filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))' }} />
      </svg>
    </>
  );
};

/* ---------------------------------------------------------------- fala escrita na tela */

export const ESTILO_LEGENDA = { tamanho: 54, peso: 400, tracking: -0.005, familia: 'HP Simplified', entrelinha: 1.16 };
const BASE_LEGENDA = 1050;

/** Uma frase da narração, alinhada pelo pé, com a saída presa ao início da frase seguinte. */
export const Legenda: React.FC<{ palavras: Palavra[]; destaque?: number[]; ate?: number; x?: number; largura?: number; centro?: boolean; estilo?: typeof ESTILO_LEGENDA; base?: number }> = ({
  palavras,
  destaque = [],
  ate,
  x = JANELA.x,
  largura = JANELA.w,
  centro = false,
  estilo = ESTILO_LEGENDA,
  base = BASE_LEGENDA,
}) => {
  const props = { palavras, x: centro ? 960 : x, y: 0, largura, estilo, alinhar: centro ? ('centro' as const) : ('esquerda' as const) };
  const lf = useLayoutFala(props);
  const y = base - lf.altura;
  return (
    <Fala
      {...props}
      y={y}
      cor={CORM.papel}
      corDestaque={PALETA.acentoClaro}
      brilhoDestaque={BRILHO.verdeLeve}
      destaque={destaque}
      limpar={false}
      sai={ate === undefined ? undefined : { em: ate, stagger: 0.4 }}
    />
  );
};

/* ---------------------------------------------------------------- capítulo */

export const CAPITULOS = ['Conversa', 'Bug', 'Melhoria', 'Acompanhar'];

/** O capítulo no alto, à esquerda, e os pontos do caminho, à direita. */
export const Capitulo: React.FC<{ n: number }> = ({ n }) => {
  const f = useCurrentFrame();
  const nome = `${n}  ·  ${CAPITULOS[n - 1]}`.toUpperCase();
  const letras = Math.ceil(nome.length * janelaM(f, 4, 18, 'sai'));
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: JANELA.x,
          top: 20,
          fontFamily: 'HP Simplified',
          fontSize: 30,
          letterSpacing: '0.08em',
          color: CORM.dim,
          whiteSpace: 'pre',
        }}
      >
        <span style={{ color: PALETA.acentoClaro }}>{nome.slice(0, Math.min(letras, String(n).length))}</span>
        {nome.slice(String(n).length, letras)}
      </div>
      <div style={{ position: 'absolute', right: JANELA.x, top: 32, display: 'flex', gap: 14 }}>
        {CAPITULOS.map((_, i) => {
          const atual = i === n - 1;
          const acende = atual ? janelaM(f, 6, 16, 'sai') : 1;
          return (
            <div
              key={i}
              style={{
                width: atual ? 12 + 26 * acende : 12,
                height: 12,
                borderRadius: 6,
                background: i < n - 1 ? `rgba(${RGB.claro},.55)` : atual ? PALETA.acento : `rgba(${RGB.claro},.18)`,
                boxShadow: atual ? `0 0 14px rgba(${RGB.acento},.7)` : undefined,
              }}
            />
          );
        })}
      </div>
    </>
  );
};

/** Fundo comum das cenas de tela: o azul-marinho com a grade, sem grão. */
export const FundoDaTela: React.FC = () => <AbsoluteFill style={{ background: `radial-gradient(ellipse 80% 70% at 50% 42%, ${PALETA.florestaClara} 0%, ${PALETA.fundo} 75%)` }} />;
