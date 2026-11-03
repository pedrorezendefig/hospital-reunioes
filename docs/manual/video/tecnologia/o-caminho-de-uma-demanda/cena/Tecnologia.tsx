/* =====================================================================================
   videos/Tecnologia: o Vídeo de visão geral da Tecnologia (Manual, ADR 0076; refeito no PRD #1380,
   ADR 0077, com a conversa do Assistente como cena central).

   9 cenas, uma por tela do app (as frases da mesma tela dividem a cena e a câmera anda de um alvo
   ao outro), narradas com a voz A e com a fala escrita na tela palavra a palavra:
     1 gancho: a pergunta que abre a conversa   6 o resumo da melhoria e o Criar o card
     2 a aba aberta: Nova conversa, Bug ou      7 a lista: Registrada e a Etapa que anda
       Melhoria, a caixa, o microfone, o print   8 o pedido aberto e O que muda
     3 o bug: as perguntas e o print            9 virada e assinatura (logo inteira e parada)
     4 o resumo do bug, Não bateu, Criar o card
     5 a melhoria: a pergunta, as opções, a Recomendada, Fechar e resumir
   Telas: docs/manual/src/assets/tecnologia/video-*.png (roteiro de prints, --video), copiadas
   para public/. Tempos: tempos.json, de scripts/tempos-da-narracao.mjs.
   ===================================================================================== */
import React from 'react';
import { AbsoluteFill, Composition, Img, staticFile } from 'remotion';
import { FundoM } from '../../blocos';
import { useCenaM } from '../../cena';
import { montarRoteiro, VideoMontado } from '../../montagem';
import { clamp01, janelaM, lerp, mola, PALETA, RGB, type Palavra } from '../../tema';
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

/** As palavras da cena e as frases dela (índices locais). */
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

const ABERTURA = 'video-01-abertura';
const BUG = 'video-02-bug';
const RESUMO_DO_BUG = 'video-03-resumo-do-bug';
const ENVIADO = 'video-04-enviado';
const MELHORIA = 'video-05-melhoria';
const RESUMO_DA_MELHORIA = 'video-06-resumo-da-melhoria';
const LISTA = 'video-07-lista';
const ACOMPANHAMENTO = 'video-08-acompanhamento';

const C2 = cenaDeTela(
  2,
  1,
  (q) => [
    { em: 0, tela: ABERTURA, zoom: 1 },
    { em: q('pergunta'), tela: ABERTURA, foco: ['pergunta', 'opcoes'], zoom: 1.7, destaque: ['pergunta'] },
    { em: q('Nova'), tela: ABERTURA, foco: ['nova_conversa', 'opcoes'], zoom: 1.5, destaque: ['nova_conversa'], cursor: 'nova_conversa' },
    { em: q('conversa', 'Nova'), tela: ABERTURA, foco: ['nova_conversa', 'opcoes'], zoom: 1.5, destaque: ['nova_conversa'], cursor: 'nova_conversa', clique: true },
    { em: q('escolha'), tela: ABERTURA, foco: ['pergunta', 'opcoes'], zoom: 1.9, destaque: ['bug', 'melhoria'], cursor: 'bug' },
    { em: q('escrever'), tela: ABERTURA, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['mensagem'] },
    { em: q('microfone'), tela: ABERTURA, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['microfone'], cursor: 'microfone' },
    { em: q('print'), tela: ABERTURA, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['print'], cursor: 'print' },
    { em: q('dúvida'), tela: ABERTURA, foco: 'chat', zoom: 1.15, destaque: ['chat'] },
  ],
  [['pergunta'], ['Nova', 'conversa'], ['microfone', 'print'], ['dúvida']],
);

const C3 = cenaDeTela(
  3,
  2,
  (q) => [
    { em: 0, tela: BUG, foco: 'conversa', zoom: 1.1 },
    { em: q('cinco'), tela: BUG, foco: 'conversa', zoom: 1.2, destaque: ['onde', 'o_que'] },
    { em: q('Onde'), tela: BUG, foco: ['onde', 'o_que'], zoom: 1.6, destaque: ['onde'] },
    { em: q('aconteceu'), tela: BUG, foco: ['onde', 'o_que'], zoom: 1.6, destaque: ['o_que'] },
    { em: q('print'), tela: BUG, foco: ['pede_print', 'print'], zoom: 1.4, destaque: ['pede_print'] },
    { em: q('botão'), tela: BUG, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['print'], cursor: 'print' },
    { em: q('imagem'), tela: BUG, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['print'], cursor: 'print', clique: true },
    { em: q('guardado'), tela: BUG, foco: 'conversa', zoom: 1.15 },
  ],
  [['cinco'], ['repetir'], ['guardado']],
);

const C4 = cenaDeTela(
  4,
  2,
  (q) => [
    { em: 0, tela: RESUMO_DO_BUG, foco: 'resumo', zoom: 1.05 },
    { em: q('resumo'), tela: RESUMO_DO_BUG, foco: 'campos', zoom: 1.5, destaque: ['campos'] },
    { em: q('resolvido'), tela: RESUMO_DO_BUG, foco: 'criterios', zoom: 1.8, destaque: ['criterios'] },
    { em: q('Não'), tela: RESUMO_DO_BUG, foco: ['criar', 'nao_bateu'], zoom: 2.4, destaque: ['nao_bateu'], cursor: 'nao_bateu' },
    { em: q('Criar'), tela: RESUMO_DO_BUG, foco: ['criar', 'nao_bateu'], zoom: 2.4, destaque: ['criar'], cursor: 'criar' },
    { em: q('Vitta'), tela: RESUMO_DO_BUG, foco: ['criar', 'nao_bateu'], zoom: 2.4, destaque: ['criar'], cursor: 'criar', clique: true },
    { em: q('fila'), tela: ENVIADO, foco: 'enviado', zoom: 1.5, destaque: ['enviado'] },
  ],
  [['resolvido'], ['Não', 'bateu'], ['Criar', 'o', 'card'], ['fila']],
);

const C5 = cenaDeTela(
  5,
  3,
  (q) => [
    { em: 0, tela: MELHORIA, foco: 'conversa', zoom: 1.05 },
    { em: q('Vitta'), tela: MELHORIA, foco: 'pergunta', zoom: 1.8, destaque: ['pergunta'] },
    { em: q('decidido'), tela: MELHORIA, foco: 'pergunta', zoom: 1.9, destaque: ['pergunta'] },
    { em: q('opções'), tela: MELHORIA, foco: ['pergunta', 'opcoes'], zoom: 1.6, destaque: ['opcoes'] },
    { em: q('recomendada'), tela: MELHORIA, foco: ['pergunta', 'opcoes'], zoom: 1.6, destaque: ['selo_recomendada'] },
    { em: q('Escolha'), tela: MELHORIA, foco: ['pergunta', 'opcoes'], zoom: 1.6, destaque: ['recomendada'], cursor: 'recomendada' },
    { em: q('voz'), tela: MELHORIA, foco: ['mensagem', 'microfone'], zoom: 1.9, destaque: ['microfone'], cursor: 'microfone' },
    { em: q('Fechar'), tela: MELHORIA, foco: 'fechar', zoom: 2.4, destaque: ['fechar'], cursor: 'fechar' },
    { em: q('encerra'), tela: MELHORIA, foco: 'fechar', zoom: 2.4, destaque: ['fechar'], cursor: 'fechar', clique: true },
  ],
  [['Vitta'], ['decidido'], ['recomendada'], ['seu', 'jeito'], ['Fechar', 'e', 'resumir']],
);

const C6 = cenaDeTela(
  6,
  3,
  (q) => [
    { em: 0, tela: RESUMO_DA_MELHORIA, foco: 'resumo', zoom: 1.05 },
    { em: q('decisão'), tela: RESUMO_DA_MELHORIA, foco: 'decisoes', zoom: 1.4, destaque: ['decisoes'] },
    { em: q('porquê'), tela: RESUMO_DA_MELHORIA, foco: 'decisoes', zoom: 1.4, destaque: ['porque'] },
    { em: q('aberto'), tela: RESUMO_DA_MELHORIA, foco: ['em_aberto', 'criar'], zoom: 1.6, destaque: ['em_aberto'] },
    { em: q('Nada'), tela: RESUMO_DA_MELHORIA, foco: ['criar', 'nao_bateu'], zoom: 2.4 },
    { em: q('clique'), tela: RESUMO_DA_MELHORIA, foco: ['criar', 'nao_bateu'], zoom: 2.4, destaque: ['criar'], cursor: 'criar' },
    { em: q('card'), tela: RESUMO_DA_MELHORIA, foco: ['criar', 'nao_bateu'], zoom: 2.4, destaque: ['criar'], cursor: 'criar', clique: true },
  ],
  [['porquê'], ['Criar', 'o', 'card']],
);

const C7 = cenaDeTela(
  7,
  4,
  (q) => [
    { em: 0, tela: LISTA, foco: 'lista', zoom: 1.2 },
    { em: q('lista'), tela: LISTA, foco: 'lista', zoom: 1.3, destaque: ['lista'] },
    { em: q('Registrada'), tela: LISTA, foco: 'pedido_registrado', zoom: 2.4, destaque: ['registrada'], cursor: 'pedido_registrado' },
    { em: q('continue'), tela: LISTA, foco: 'pedido_registrado', zoom: 2.4, destaque: ['pedido_registrado'], cursor: 'pedido_registrado', clique: true },
    { em: q('Etapa'), tela: LISTA, foco: 'lista', zoom: 1.5 },
    { em: q('análise'), tela: LISTA, foco: 'lista', zoom: 1.5, destaque: ['em_analise'] },
    { em: q('desenvolvimento'), tela: LISTA, foco: 'lista', zoom: 1.5, destaque: ['em_desenvolvimento'] },
    { em: q('produção'), tela: LISTA, foco: 'lista', zoom: 1.5, destaque: ['em_producao'] },
  ],
  [['lista'], ['Registrada'], ['sozinha']],
);

const C8 = cenaDeTela(
  8,
  4,
  (q) => [
    { em: 0, tela: ACOMPANHAMENTO, foco: ['pedido_na_lista', 'o_que_muda'], zoom: 1.1 },
    { em: q('Abra'), tela: ACOMPANHAMENTO, foco: ['pedido_na_lista', 'o_que_muda'], zoom: 1.2, destaque: ['pedido_na_lista'], cursor: 'pedido_na_lista' },
    { em: q('pedido'), tela: ACOMPANHAMENTO, foco: ['pedido_na_lista', 'o_que_muda'], zoom: 1.2, destaque: ['pedido_na_lista'], cursor: 'pedido_na_lista', clique: true },
    { em: q('muda'), tela: ACOMPANHAMENTO, foco: ['selo', 'o_que_muda'], zoom: 1.6, destaque: ['selo', 'o_que_muda'] },
  ],
  [['O', 'que', 'muda']],
);

/* ---------------------------------------------------------------- gancho e virada */

const PERGUNTA = 'Isso é um bug, algo que não funciona como deveria, ou uma melhoria?';
const TITULO_DO_EXEMPLO = 'Nome do setor no cartaz do QR da Ouvidoria';

/** A fala da IA, no desenho do chat do app. */
const FalaDaIA: React.FC<{ texto: string; x: number; y: number; w: number; op: number; escala: number }> = ({ texto, x, y, w, op, escala }) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: w,
      padding: '26px 34px',
      borderRadius: 30,
      background: '#F1F5F9',
      color: '#1E293B',
      fontFamily: 'HP Simplified',
      fontSize: 44,
      lineHeight: 1.22,
      opacity: op,
      transform: `scale(${escala})`,
      transformOrigin: '0 50%',
      boxShadow: '0 24px 60px rgba(0,0,0,.45)',
    }}
  >
    {texto}
  </div>
);

/** Um dos dois botões da pergunta, no desenho do app. */
const Botao: React.FC<{ texto: string; x: number; y: number; op: number; escala: number; aceso: number }> = ({ texto, x, y, op, escala, aceso }) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      padding: '18px 40px',
      borderRadius: 22,
      background: '#FFFFFF',
      border: `3px solid rgba(${RGB.acento},${0.55 + 0.45 * aceso})`,
      color: '#2B2E7E',
      fontFamily: 'HP Simplified',
      fontSize: 46,
      fontWeight: 700,
      opacity: op,
      transform: `scale(${escala})`,
      transformOrigin: '0 50%',
      boxShadow: `0 20px 50px rgba(0,0,0,.4), 0 0 ${50 * aceso}px rgba(${RGB.acento},${0.8 * aceso})`,
    }}
  >
    {texto}
  </div>
);

/** O pedido que chegou à Vitta: o título, O que muda e a Etapa. */
const Pedido: React.FC<{ x: number; y: number; w: number; escala: number; op: number; oQueMuda: number; selo: number; brilho: number }> = ({
  x,
  y,
  w,
  escala,
  op,
  oQueMuda,
  selo,
  brilho,
}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: w,
      padding: '24px 30px',
      borderRadius: 22,
      background: '#FFFFFF',
      fontFamily: 'HP Simplified',
      opacity: op,
      transform: `scale(${escala})`,
      transformOrigin: '50% 50%',
      boxShadow: `0 24px 60px rgba(0,0,0,.45), 0 0 ${60 * brilho}px rgba(${RGB.acento},${0.8 * brilho}), 0 0 0 ${1.5 + 2 * brilho}px rgba(${RGB.acento},${0.25 + 0.6 * brilho})`,
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
      <div style={{ fontSize: 40, lineHeight: 1.2, color: '#1E293B', fontWeight: 700 }}>{TITULO_DO_EXEMPLO}</div>
      <div
        style={{
          padding: '6px 16px',
          borderRadius: 10,
          background: '#F1F5F9',
          color: '#475569',
          fontSize: 30,
          whiteSpace: 'nowrap',
          opacity: clamp01(selo * 3),
          transform: `scale(${0.6 + 0.4 * selo})`,
          transformOrigin: '0 50%',
        }}
      >
        Em análise
      </div>
    </div>
    {oQueMuda > 0 ? (
      <div
        style={{
          marginTop: 18 * oQueMuda,
          maxHeight: 220 * oQueMuda,
          overflow: 'hidden',
          opacity: oQueMuda,
          padding: `${16 * oQueMuda}px 22px`,
          borderRadius: 14,
          background: '#F8FAFC',
          border: '1.5px solid #E2E8F0',
        }}
      >
        <div style={{ fontSize: 28, letterSpacing: '0.06em', color: '#64748B' }}>O QUE MUDA</div>
        <div style={{ marginTop: 8, fontSize: 34, lineHeight: 1.25, color: '#1E293B' }}>O cartaz com o QR e a página de manifestação passam a mostrar o nome do setor.</div>
      </div>
    ) : null}
  </div>
);

const ESTILO_GRANDE = { ...ESTILO_LEGENDA, tamanho: 76, entrelinha: 1.12 };

const C1: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(1);
  const { fala } = useFrases(1);
  const qIsso = q('Isso');
  const qBug = q('bug');
  const qMelhoria = q('melhoria');
  const entra = mola(f, 'estalo', qIsso - 6);
  const b1 = mola(f, 'estalo', qBug - 2);
  const b2 = mola(f, 'estalo', qMelhoria - 2);
  // os dois botões acendem na palavra deles e seguem respirando até o corte: nada fica parado
  const respira = 0.5 + 0.5 * Math.sin(f / 9);
  const empurra = 1 + 0.05 * clamp01(f / Math.max(1, c.seqDuracao));
  return (
    <AbsoluteFill>
      <Fundo />
      <AbsoluteFill style={{ transform: `scale(${empurra})` }}>
        <FalaDaIA texto={PERGUNTA} x={300} y={250 + 30 * (1 - entra)} w={1320} op={clamp01((f - qIsso + 6) / 4)} escala={0.94 + 0.06 * entra} />
        <Botao texto="Bug" x={300} y={500 + 24 * (1 - b1)} op={clamp01((f - qBug + 2) / 4)} escala={0.9 + 0.1 * b1} aceso={clamp01((f - qBug) / 6) * (0.6 + 0.4 * respira)} />
        <Botao
          texto="Melhoria"
          x={520}
          y={500 + 24 * (1 - b2)}
          op={clamp01((f - qMelhoria + 2) / 4)}
          escala={0.9 + 0.1 * b2}
          aceso={clamp01((f - qMelhoria) / 6) * (0.6 + 0.4 * (1 - respira))}
        />
      </AbsoluteFill>
      <Legenda palavras={fala} destaque={marcar(fala, 'bug', 'melhoria')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
    </AbsoluteFill>
  );
};

const C9: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(9);
  const { fala } = useFrases(9);
  const fimFala = c.local(T.fimFala);
  const qPergunta = q('pergunta');
  const qVitta = q('Vitta');
  const qDecidiu = q('decidiu');
  const logoQ = fimFala + Math.round(LOGO_ENTRA_S * FPS);
  const some = janelaM(f, logoQ - 10, logoQ, 'entra');
  const logo = janelaM(f, logoQ, logoQ + Math.round((LOGO_ASSENTA_S - LOGO_ENTRA_S) * FPS), 'sai');
  // a pergunta abre a virada (já no primeiro quadro) e sobe; o pedido chega na Vitta e ganha
  // O que muda no "decidiu"
  const fala1 = clamp01(f / 6);
  const acende = clamp01((f - qPergunta + 2) / 6) * (1 - janelaM(f, qPergunta + 10, qPergunta + 30, 'sai'));
  const sobe = janelaM(f, qVitta - 6, qVitta + 14, 'sai');
  const chega = mola(f, 'estalo', qVitta - 2);
  const muda = janelaM(f, qDecidiu - 4, qDecidiu + 12, 'sai');
  const brilho = clamp01((f - qDecidiu) / 6) * (1 - janelaM(f, qDecidiu + 8, qDecidiu + 30, 'sai') * 0.6);
  return (
    <AbsoluteFill>
      {/* o fundo da virada não deriva: a assinatura é a única parada do vídeo */}
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 80% 70% at 50% 44%, ${PALETA.halo} 0%, ${PALETA.fundo} 72%)` }} />
      {/* tudo empurra devagar até a logo: nada fica parado antes da assinatura */}
      <AbsoluteFill style={{ opacity: 1 - some, transform: `scale(${1 + 0.06 * janelaM(f, 0, logoQ, 'linear')})` }}>
        <FalaDaIA
          texto="Isso é um bug ou uma melhoria?"
          x={lerp(460, 300, sobe)}
          y={lerp(300, 110, sobe)}
          w={1000}
          op={fala1 * (1 - 0.45 * sobe)}
          escala={(1 - 0.25 * sobe) * (1 + 0.03 * acende)}
        />
        {/* o pedido empurra devagar até a logo: nada fica parado antes da assinatura */}
        <Pedido
          x={960 - 560}
          y={lerp(380, 300, sobe)}
          w={1120}
          escala={(0.9 + 0.1 * chega) * (1 + 0.04 * janelaM(f, 0, logoQ, 'suave'))}
          op={clamp01((f - qVitta + 2) / 6)}
          oQueMuda={muda}
          selo={mola(f, 'estalo', qDecidiu - 2)}
          brilho={brilho}
        />
        <Legenda palavras={fala} destaque={marcar(fala, 'decidiu')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
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
    entrada('estica', { de: JANELA_T }),
    entrada('tunel', { de: JANELA_T }),
    entrada('retangulo', { de: JANELA_T }),
    entrada('chicoteLuz', { yLuz: 475 }),
    entrada('peliculaGira'),
    entrada('despenca', { caixas: [JANELA_T], semente: 'virada' }),
  ],
  nomes: ['gancho', 'abertura', 'bug', 'resumo-do-bug', 'melhoria', 'resumo-da-melhoria', 'lista', 'pedido', 'virada'],
  duracao: DURACAO,
});

export const Tecnologia: React.FC = () => (
  <VideoMontado cenas={CENAS} componentes={[C1, C2, C3, C4, C5, C6, C7, C8, C9]} audio="narracao.wav" />
);

export const ComposicaoTecnologia: React.FC = () => (
  <Composition id="Tecnologia" component={Tecnologia} durationInFrames={DURACAO} fps={FPS} width={1920} height={1080} />
);

/** Para o meta.json: a janela da assinatura parada, em segundos (da entrada da logo ao fim). */
export const PARADA_S = [T.fimFala + LOGO_ENTRA_S, DURACAO / FPS];
