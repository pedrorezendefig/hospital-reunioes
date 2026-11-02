/* =====================================================================================
   videos/ContasMedicas: o Vídeo de visão geral de Contas médicas (Manual, ADR 0076).

   14 cenas, uma por tela do app (as frases da mesma tela dividem a cena e a câmera anda de um
   alvo ao outro), narradas com a voz A e com a fala escrita na tela palavra a palavra:
     1 gancho (dois PDFs viram a lista)      8 Concluir e abrir a próxima
     2 envio e Último envio                  9 Devolver à fila e a Fila de novo
     3 Meus envios e o cartão                10 Erro, Analisar de novo, Copiar para a TI
     4 a Fila e o Abrir                      11 Validação
     5 o topo do guia e as linhas            12 Coordenação
     6 código, Feito e Ver evidência         13 Painel
     7 Não procede e Bloqueado               14 virada e assinatura (logo inteira e parada)
   Telas: docs/manual/src/assets/contas-medicas/video-*.png (roteiro de prints, --video), copiadas
   para public/. Tempos: tempos.json, de scripts/tempos-da-narracao.mjs.
   ===================================================================================== */
import React from 'react';
import { AbsoluteFill, Composition, Img, staticFile, useCurrentFrame } from 'remotion';
import { FundoM } from '../../blocos';
import { useCenaM } from '../../cena';
import { montarRoteiro, VideoMontado } from '../../montagem';
import { clamp01, janelaM, mola, PALETA, RGB, type Palavra } from '../../tema';
import { criarTempos, type TemposJson } from '../../tempos';
import { entrada } from '../../transicoes/catalogo';
import { achar, Capitulo, ESTILO_LEGENDA, JANELA, Legenda, TelaNaJanela, type Plano } from './pecas';
import TEMPOS from './tempos.json';

const T = criarTempos(TEMPOS as TemposJson);
const FRASES = (TEMPOS as unknown as { frases: { frase: number; palavra: number; cena: number }[] }).frases;
const FPS = 30;
/** depois da última palavra: a virada assenta, a logo entra e fica parada */
const LOGO_ENTRA_S = 0.6;
const LOGO_ASSENTA_S = LOGO_ENTRA_S + 0.5;
const CAUDA_S = 3.4;
export const DURACAO = Math.round((T.fimFala + CAUDA_S) * FPS);

/* ---------------------------------------------------------------- fala da cena */

/** As palavras da cena e as frases dela (índices locais), com a marcação das palavras-chave. */
const useFrases = (n: number) => {
  const fala = T.falaDaCena(n);
  const primeira = T.PALAVRAS.indexOf(fala[0]);
  const frases = FRASES.filter((f) => f.cena === n).map((f, j, todas) => {
    const de = f.palavra - primeira;
    const ate = j + 1 < todas.length ? todas[j + 1].palavra - primeira : fala.length;
    return { de, palavras: fala.slice(de, ate) };
  });
  return { fala, frases };
};

/** Índices das palavras-chave, em ordem; prefixo com "~" só ancora a busca. */
const marcar = (palavras: Palavra[], ...prefixos: string[]) => {
  const out: number[] = [];
  let de = 0;
  for (const p of prefixos) {
    const i = achar(palavras, p.replace(/^~/, ''), de);
    if (!p.startsWith('~')) out.push(i);
    de = i + 1;
  }
  return out;
};

/** As legendas das frases da cena: cada uma sai 12 quadros antes da seguinte começar. */
const Legendas: React.FC<{ n: number; destaques: string[][] }> = ({ n, destaques }) => {
  const c = useCenaM();
  const { frases } = useFrases(n);
  return (
    <>
      {frases.map((fr, j) => {
        const prox = frases[j + 1];
        const ate = prox ? c.local(prox.palavras[0].s) - 12 : undefined;
        const comeca = c.local(fr.palavras[0].s) - 4;
        if (c.frame < comeca - 2) return null;
        if (ate !== undefined && c.frame > ate + 14) return null;
        return <Legenda key={j} palavras={fr.palavras} destaque={marcar(fr.palavras, ...(destaques[j] ?? []))} ate={ate} />;
      })}
    </>
  );
};

/** Quadro local da palavra (a primeira que começa com o prefixo, depois de `depois`). */
const useQuando = (n: number) => {
  const c = useCenaM();
  const { fala } = useFrases(n);
  return (prefixo: string, depois?: string) => c.local(fala[achar(fala, prefixo, depois ? achar(fala, depois) + 1 : 0)].s);
};

/* ---------------------------------------------------------------- cena de tela */

const Fundo: React.FC = () => <FundoM brilho={[50, 44]} grade={0.45} deriva={0.22} forcaBrilho={0.9} />;

const cenaDeTela = (n: number, capitulo: number, planos: (q: ReturnType<typeof useQuando>) => Plano[], destaques: string[][]): React.FC => {
  const Cena: React.FC = () => {
    const q = useQuando(n);
    return (
      <AbsoluteFill>
        <Fundo />
        <Capitulo n={capitulo} />
        <TelaNaJanela planos={planos(q)} />
        <Legendas n={n} destaques={destaques} />
      </AbsoluteFill>
    );
  };
  return Cena;
};

const C2 = cenaDeTela(
  2,
  1,
  (q) => [
    { em: 0, tela: 'video-01-contas', zoom: 1 },
    { em: q('arraste'), tela: 'video-01-contas', foco: 'envio', zoom: 1.16, destaque: ['envio'] },
    { em: q('prontuário'), tela: 'video-01-contas', foco: 'envio', zoom: 1.16, destaque: ['envio'], cursor: 'envio', carrega: ['conta-900412.pdf', 'prontuario-900412.pdf'] },
    { em: q('sistema'), tela: 'video-02-ultimo-envio', foco: 'quadro', zoom: 1.3 },
    { em: q('junta'), tela: 'video-02-ultimo-envio', foco: 'quadro', zoom: 1.3, destaque: ['completo'] },
  ],
  [['arraste'], ['junta']],
);

const C3 = cenaDeTela(
  3,
  1,
  (q) => [
    { em: 0, tela: 'video-03-meus-envios', zoom: 1 },
    { em: q('Meus'), tela: 'video-03-meus-envios', foco: ['aba', 'cartao'], zoom: 1.12, destaque: ['aba'], cursor: 'aba', clique: true },
    { em: q('cartão'), tela: 'video-03-meus-envios', foco: 'cartao', zoom: 1.22, destaque: ['cartao'] },
    { em: q('um', 'quadrados'), tela: 'video-03-meus-envios', foco: 'cartao', zoom: 1.22, destaque: ['conta'] },
    { em: q('outro'), tela: 'video-03-meus-envios', foco: 'cartao', zoom: 1.22, destaque: ['prontuario'] },
    { em: q('botão'), tela: 'video-03-meus-envios', foco: 'enviar', zoom: 1.85, destaque: ['enviar'], cursor: 'enviar' },
    { em: q('falta', 'só'), tela: 'video-03-meus-envios', foco: 'enviar', zoom: 1.85, destaque: ['enviar'], cursor: 'enviar', clique: true },
  ],
  [['Meus', 'envios'], ['dois', 'quadrados'], ['~só', 'falta']],
);

const C4 = cenaDeTela(
  4,
  2,
  (q) => [
    { em: 0, tela: 'video-01-contas', foco: ['abas', 'linha'], zoom: 1.1 },
    { em: q('Fila'), tela: 'video-01-contas', foco: ['abas', 'linha'], zoom: 1.1, destaque: ['aba_fila'] },
    { em: q('mesma'), tela: 'video-01-contas', foco: ['abas', 'linha'], zoom: 1.1, destaque: ['linha'] },
    { em: q('Abrir'), tela: 'video-01-contas', foco: 'abrir', zoom: 2.1, destaque: ['abrir'], cursor: 'abrir', clique: true },
  ],
  [['Fila'], ['Abrir']],
);

const C5 = cenaDeTela(
  5,
  3,
  (q) => [
    { em: 0, tela: 'video-04-guia', zoom: 1 },
    { em: q('nota'), tela: 'video-04-guia', foco: 'numeros', zoom: 1.5, destaque: ['nota'] },
    { em: q('ajustar'), tela: 'video-04-guia', foco: 'numeros', zoom: 1.5, destaque: ['ajustar'] },
    { em: q('linhas'), tela: 'video-04-guia', foco: ['grupo', 'verbo_validar'], zoom: 1.2 },
    { em: q('dia'), tela: 'video-04-guia', foco: ['grupo', 'verbo_validar'], zoom: 1.2, destaque: ['grupo'] },
    { em: q('verbo'), tela: 'video-04-guia', foco: ['grupo', 'verbo_validar'], zoom: 1.2, destaque: ['verbo_incluir', 'verbo_preco', 'verbo_validar'] },
  ],
  [['nota', 'de', 'entrada'], ['verbo']],
);

const C6 = cenaDeTela(
  6,
  3,
  (q) => [
    { em: 0, tela: 'video-05-guia-linhas', foco: 'linha', zoom: 1.3 },
    { em: q('Copie'), tela: 'video-05-guia-linhas', foco: 'linha', zoom: 1.6, destaque: ['codigo'], cursor: 'codigo', clique: true },
    { em: q('Feito'), tela: 'video-05-guia-linhas', foco: 'linha', zoom: 1.6, destaque: ['feito'], cursor: 'feito', clique: true },
    { em: q('Ver'), tela: 'video-05-guia-linhas', foco: 'trecho', zoom: 1.75, destaque: ['trecho'], cursor: 'evidencia' },
  ],
  [['Feito'], ['Ver', 'evidência']],
);

const C7 = cenaDeTela(
  7,
  3,
  (q) => [
    { em: 0, tela: 'video-06-nao-procede', foco: 'linha', zoom: 1.12 },
    { em: q('procede'), tela: 'video-06-nao-procede', foco: 'motivos', zoom: 1.45, destaque: ['motivos'] },
    { em: q('Bloqueado'), tela: 'video-06-nao-procede', foco: ['bloqueado', 'motivos'], zoom: 1.35, destaque: ['bloqueado'], cursor: 'bloqueado', clique: true },
  ],
  [['~marque', 'Não', 'procede', 'Bloqueado']],
);

const C8 = cenaDeTela(
  8,
  3,
  (q) => [
    { em: 0, tela: 'video-07-concluir', foco: 'rodape', zoom: 1.2 },
    { em: q('Concluir'), tela: 'video-07-concluir', foco: 'concluir', zoom: 1.8, destaque: ['concluir'], cursor: 'concluir' },
    { em: q('próxima'), tela: 'video-07-concluir', foco: 'concluir', zoom: 1.8, destaque: ['concluir'], cursor: 'concluir', clique: true },
  ],
  [['Concluir', 'e', 'abrir', 'a', 'próxima']],
);

const C9 = cenaDeTela(
  9,
  4,
  (q) => [
    { em: 0, tela: 'video-04-guia', foco: 'devolver', zoom: 1.3 },
    { em: q('Devolver'), tela: 'video-04-guia', foco: 'devolver', zoom: 2.1, destaque: ['devolver'], cursor: 'devolver' },
    { em: q('solta'), tela: 'video-04-guia', foco: 'devolver', zoom: 2.1, destaque: ['devolver'], cursor: 'devolver', clique: true },
    { em: q('Outra'), tela: 'video-08-fila-devolvida', foco: 'fila', zoom: 1.2 },
    { em: q('continua'), tela: 'video-08-fila-devolvida', foco: 'fila', zoom: 1.35, destaque: ['linha'] },
  ],
  [['Devolver', 'à', 'fila'], ['continua']],
);

const C10 = cenaDeTela(
  10,
  5,
  (q) => [
    { em: 0, tela: 'video-03-meus-envios', foco: 'erro', zoom: 1.15 },
    { em: q('Erro'), tela: 'video-03-meus-envios', foco: 'erro', zoom: 1.2, destaque: ['erro'] },
    { em: q('motivo'), tela: 'video-03-meus-envios', foco: ['motivo', 'codigo'], zoom: 1.6, destaque: ['motivo'] },
    { em: q('código'), tela: 'video-03-meus-envios', foco: ['motivo', 'codigo'], zoom: 1.6, destaque: ['codigo'] },
    { em: q('Analisar'), tela: 'video-03-meus-envios', foco: 'analisar', zoom: 2.2, destaque: ['analisar'], cursor: 'analisar' },
    { em: q('refaz'), tela: 'video-03-meus-envios', foco: 'analisar', zoom: 2.2, destaque: ['analisar'], cursor: 'analisar', clique: true },
    { em: q('Copiar'), tela: 'video-03-meus-envios', foco: 'copiar', zoom: 2.2, destaque: ['copiar'], cursor: 'copiar' },
    { em: q('leva'), tela: 'video-03-meus-envios', foco: 'copiar', zoom: 2.2, destaque: ['copiar'], cursor: 'copiar', clique: true },
  ],
  [['Erro'], ['Analisar', 'de', 'novo'], ['Copiar', 'para', 'a', 'TI']],
);

const C11 = cenaDeTela(
  11,
  6,
  (q) => [
    { em: 0, tela: 'video-09-validacao', zoom: 1 },
    { em: q('Validar'), tela: 'video-09-validacao', foco: 'regra', zoom: 1.12, destaque: ['regra'] },
    { em: q('bloqueado'), tela: 'video-09-validacao', foco: 'bloqueado', zoom: 1.12, destaque: ['bloqueado'] },
    { em: q('observação'), tela: 'video-09-validacao', foco: 'observacao', zoom: 1.12, destaque: ['observacao'] },
    { em: q('Validação'), tela: 'video-09-validacao', zoom: 1 },
    { em: q('tema'), tela: 'video-09-validacao', foco: 'regra', zoom: 1.4, destaque: ['regra'] },
  ],
  [['Validação'], ['tema']],
);

const C12 = cenaDeTela(
  12,
  7,
  (q) => [
    { em: 0, tela: 'video-10-coordenacao', zoom: 1 },
    { em: q('lembretes'), tela: 'video-10-coordenacao', foco: 'lembrete', zoom: 1.3, destaque: ['lembrete'] },
    { em: q('insumo'), tela: 'video-10-coordenacao', foco: 'insumos', zoom: 1.75, destaque: ['insumos'] },
  ],
  [['segunda', 'checagem'], ['insumo']],
);

const C13 = cenaDeTela(
  13,
  8,
  (q) => [
    { em: 0, tela: 'video-11-painel', zoom: 1 },
    { em: q('nota'), tela: 'video-11-painel', foco: 'nota', zoom: 1.7, destaque: ['nota'] },
    { em: q('perda'), tela: 'video-11-painel', foco: 'causa', zoom: 1.4, destaque: ['causa'] },
    { em: q('Farmácia'), tela: 'video-11-painel', foco: 'causa', zoom: 1.75, destaque: ['causa'] },
  ],
  [['nota', '~da', 'semana', 'perda'], ['valor']],
);

/* ---------------------------------------------------------------- gancho e virada */

const LINHAS_DO_GUIA = [
  { verbo: 'INCLUIR', item: 'Pantoprazol 40 mg injetável' },
  { verbo: 'CORRIGIR PREÇO', item: 'Agulha hipodérmica 25 x 7' },
  { verbo: 'RETIRAR', item: 'Diária de enfermaria' },
];

const Documento: React.FC<{ titulo: string; x: number; y: number; rot: number; escala: number; op: number }> = ({ titulo, x, y, rot, escala, op }) => (
  <div
    style={{
      position: 'absolute',
      left: x - 130,
      top: y - 170,
      width: 260,
      height: 340,
      borderRadius: 18,
      background: '#F4F6FB',
      boxShadow: `0 24px 60px rgba(0,0,0,.45), 0 0 0 1px rgba(${RGB.claro},.35)`,
      transform: `rotate(${rot}deg) scale(${escala})`,
      opacity: op,
      padding: 26,
      fontFamily: 'HP Simplified',
    }}
  >
    <div style={{ display: 'inline-block', padding: '4px 12px', borderRadius: 8, background: PALETA.florestaClara, color: '#FFFFFF', fontSize: 28, letterSpacing: '0.06em' }}>PDF</div>
    <div style={{ marginTop: 20, fontSize: 40, color: PALETA.florestaClara }}>{titulo}</div>
    {[0.92, 0.7, 0.84, 0.6, 0.78].map((w, i) => (
      <div key={i} style={{ marginTop: i ? 14 : 22, height: 12, width: `${w * 100}%`, borderRadius: 6, background: '#D5DCEC' }} />
    ))}
  </div>
);

/** A lista do que corrigir (as linhas do atendimento de exemplo do guia). */
const Lista: React.FC<{ escala: number; op: number; linhaQ: (i: number) => number; feitoQ?: (i: number) => number; brilho?: number }> = ({ escala, op, linhaQ, feitoQ, brilho = 0 }) => {
  const f = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 960 - 420,
        top: 200,
        width: 840,
        borderRadius: 26,
        background: '#FFFFFF',
        padding: '30px 36px 18px',
        fontFamily: 'HP Simplified',
        transform: `scale(${escala})`,
        opacity: op,
        boxShadow: `0 30px 80px rgba(0,0,0,.5), 0 0 ${60 * brilho}px rgba(${RGB.acento},${0.8 * brilho}), 0 0 0 ${2 + 2 * brilho}px rgba(${RGB.acento},${0.25 + 0.6 * brilho})`,
      }}
    >
      <div style={{ fontSize: 40, color: PALETA.florestaClara }}>Atendimento 900412</div>
      {LINHAS_DO_GUIA.map((l, i) => {
        const t = f - linhaQ(i);
        const m = mola(f, 'assenta', linhaQ(i));
        const feito = feitoQ ? mola(f, 'estalo', feitoQ(i)) : 0;
        return (
          <div
            key={l.item}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 20,
              marginTop: 22,
              padding: '18px 20px',
              borderRadius: 16,
              border: '1.5px solid #E2E8F0',
              background: feito > 0.5 ? '#ECFDF3' : '#FFFFFF',
              opacity: clamp01(t / 4),
              transform: `translateY(${(1 - m) * 40}px)`,
            }}
          >
            <span style={{ padding: '5px 12px', borderRadius: 8, background: '#EEEEF6', color: PALETA.florestaClara, fontSize: 28, letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>{l.verbo}</span>
            <span style={{ fontSize: 34, color: '#1E293B', flex: 1 }}>{l.item}</span>
            {feitoQ ? (
              <span
                style={{
                  width: 46,
                  height: 46,
                  borderRadius: 23,
                  background: '#2B2E7E',
                  color: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 30,
                  transform: `scale(${feito})`,
                }}
              >
                ✓
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

const ESTILO_GRANDE = { ...ESTILO_LEGENDA, tamanho: 76, entrelinha: 1.12 };

const C1: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(1);
  const { fala } = useFrases(1);
  const qDois = q('Dois');
  const qPdfs = q('PDFs');
  const qViram = q('viram');
  const qLista = q('lista');
  const juntar = janelaM(f, qViram - 2, qViram + 12, 'entra');
  const doc = (de: number, lado: number, para: number) => {
    const m = mola(f, 'estalo', de);
    return { x: lerpX(lado * 1300 + 960, para, m) + (960 - para) * juntar, op: clamp01((f - de) / 4) * (1 - juntar), escala: 1 - 0.4 * juntar };
  };
  const esq = doc(qDois - 4, -1, 720);
  const dir = doc(qPdfs - 4, 1, 1200);
  const lista = mola(f, 'assenta', qViram + 6);
  // a lista assentada segue empurrando devagar até o corte: sem isto, 0,8 s parado antes da cena 2
  const empurra = 1 + 0.06 * clamp01(f / Math.max(1, c.seqDuracao));
  return (
    <AbsoluteFill>
      <Fundo />
      <Documento titulo="Conta" x={esq.x} y={420} rot={-4 * (1 - juntar)} escala={esq.escala} op={esq.op} />
      <Documento titulo="Prontuário" x={dir.x} y={420} rot={4 * (1 - juntar)} escala={dir.escala} op={dir.op} />
      <Lista escala={(0.86 + 0.14 * lista) * empurra} op={clamp01((f - qViram - 6) / 6)} linhaQ={(i) => qLista - 6 + i * 6} />
      <Legenda palavras={fala} destaque={marcar(fala, 'lista')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
    </AbsoluteFill>
  );
};
const lerpX = (a: number, b: number, t: number) => a + (b - a) * t;

const C14: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(14);
  const { fala } = useFrases(14);
  const fimFala = c.local(T.fimFala);
  const qConta = q('conta');
  const qConferida = q('conferida');
  const logoQ = fimFala + Math.round(LOGO_ENTRA_S * FPS);
  const some = janelaM(f, logoQ - 10, logoQ, 'entra');
  const entra = mola(f, 'estalo', 0);
  const logo = janelaM(f, logoQ, logoQ + Math.round((LOGO_ASSENTA_S - LOGO_ENTRA_S) * FPS), 'sai');
  const brilho = clamp01((f - qConferida) / 6) * (1 - janelaM(f, qConferida + 8, qConferida + 30, 'sai') * 0.6);
  return (
    <AbsoluteFill>
      {/* o fundo da virada não deriva: a assinatura é a única parada do vídeo */}
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 80% 70% at 50% 44%, ${PALETA.halo} 0%, ${PALETA.fundo} 72%)` }} />
      <AbsoluteFill style={{ opacity: 1 - some }}>
        {/* a lista empurra devagar até a logo: nada fica parado antes da assinatura */}
        <Lista escala={(0.92 + 0.08 * entra) * (1 + 0.04 * janelaM(f, 0, logoQ, 'suave'))} op={clamp01(f / 6)} linhaQ={() => -20} feitoQ={(i) => qConta + i * 5} brilho={brilho} />
        <Legenda palavras={fala} destaque={marcar(fala, 'conferida')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <Img src={staticFile('logo-hsm-branca.png')} style={{ width: 620, opacity: logo, transform: `scale(${0.96 + 0.04 * logo})` }} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------------- montagem */

const JANELA_T = { x: JANELA.x, y: JANELA.y, w: JANELA.w, h: JANELA.h, r: JANELA.r };

const CENAS = montarRoteiro({
  cenasFala: T.CENAS_FALA,
  entradas: [
    null,
    entrada('pontoAbre', { origem: [960, 420] }),
    entrada('fusao'),
    entrada('chicoteLuz', { yLuz: 475 }),
    entrada('estica', { de: JANELA_T }),
    entrada('flash'),
    entrada('flood'),
    entrada('peliculaGira'),
    entrada('retangulo', { de: JANELA_T }),
    entrada('glitchRGB'),
    entrada('tunel', { de: JANELA_T }),
    entrada('pulsoJanela', { de: { x: 860, y: 375, w: 200, h: 200, r: 20 }, para: JANELA_T }),
    entrada('corteBatida'),
    entrada('despenca', { caixas: [JANELA_T], semente: 'virada' }),
  ],
  nomes: ['gancho', 'envio', 'meus-envios', 'fila', 'guia-topo', 'guia-linha', 'nao-procede', 'concluir', 'devolver', 'erro', 'validacao', 'coordenacao', 'painel', 'virada'],
  duracao: DURACAO,
});

export const ContasMedicas: React.FC = () => (
  <VideoMontado cenas={CENAS} componentes={[C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14]} audio="narracao.wav" />
);

export const ComposicaoContasMedicas: React.FC = () => (
  <Composition id="ContasMedicas" component={ContasMedicas} durationInFrames={DURACAO} fps={FPS} width={1920} height={1080} />
);

/** Para o meta.json: a janela da assinatura parada, em segundos (da entrada da logo ao fim). */
export const PARADA_S = [T.fimFala + LOGO_ENTRA_S, DURACAO / FPS];
