/* =====================================================================================
   videos/Tecnologia: o Vídeo de visão geral da Tecnologia (Manual, ADR 0076, issue #1373).

   14 cenas, uma por tela do app (as frases da mesma tela dividem a cena e a câmera anda de um
   alvo ao outro), narradas com a voz A e com a fala escrita na tela palavra a palavra. A cena
   central é o Planejamento da Demanda (6 a 9):
     1 gancho (a mensagem solta vira card)   8 Fechar e resumir, o resumo e o não
     2 o Quadro e Nova Demanda               9 o sim, Em análise e O que muda
     3 o assistente e o Rascunho             10 o Vínculo
     4 Nova, o dono e as raias               11 a Etapa nos selos do Quadro
     5 a Conversa                            12 Com você, no Painel
     6 o botão Planejar com a IA             13 Concluir e a Conversa da entrega
     7 a pergunta, as opções e o microfone   14 virada e assinatura (logo inteira e parada)
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

const QUADRO = 'video-01-quadro';
const ASSISTENTE = 'video-02-assistente';
const CONVERSA = 'video-03-conversa';
const PLANEJAR = 'video-04-planejar';
const PLANEJAMENTO = 'video-05-planejamento';
const RESUMO = 'video-06-resumo';
const ENVIADO = 'video-07-enviado';
const EM_ANALISE = 'video-08-em-analise';
const O_QUE_MUDA = 'video-09-o-que-muda';
const VINCULO = 'video-10-vinculo';
const PAINEL = 'video-11-painel';
const ENTREGA = 'video-12-entrega';
const ENTREGA_CONVERSA = 'video-13-entrega-conversa';

const C2 = cenaDeTela(
  2,
  1,
  (q) => [
    { em: 0, tela: QUADRO, zoom: 1 },
    { em: q('Demanda'), tela: QUADRO, foco: 'raias', zoom: 1.1, destaque: ['raias'] },
    { em: q('abra'), tela: QUADRO, foco: 'nova_demanda', zoom: 2.2, destaque: ['nova_demanda'], cursor: 'nova_demanda' },
    { em: q('Demanda', 'Nova'), tela: QUADRO, foco: 'nova_demanda', zoom: 2.2, destaque: ['nova_demanda'], cursor: 'nova_demanda', clique: true },
  ],
  [['Demanda'], ['Nova', 'Demanda']],
);

const C3 = cenaDeTela(
  3,
  1,
  (q) => [
    { em: 0, tela: ASSISTENTE, zoom: 1 },
    { em: q('escrevendo'), tela: ASSISTENTE, foco: 'mensagem', zoom: 2.2, destaque: ['mensagem'] },
    { em: q('falando'), tela: ASSISTENTE, foco: 'mensagem', zoom: 2.2, destaque: ['microfone'], cursor: 'microfone' },
    { em: q('print'), tela: ASSISTENTE, foco: 'mensagem', zoom: 2.2, destaque: ['print'], cursor: 'print' },
    { em: q('assistente'), tela: ASSISTENTE, foco: 'conversa', zoom: 1.2, destaque: ['conversa'] },
    { em: q('Rascunho'), tela: ASSISTENTE, foco: 'rascunho', zoom: 1.3, destaque: ['rascunho'] },
    { em: q('Criar'), tela: ASSISTENTE, foco: 'criar', zoom: 2.4, destaque: ['criar'], cursor: 'criar' },
    { em: q('Demanda', 'Criar'), tela: ASSISTENTE, foco: 'criar', zoom: 2.4, destaque: ['criar'], cursor: 'criar', clique: true },
  ],
  [['seu', 'jeito'], ['Rascunho'], ['Criar', 'Demanda']],
);

const C4 = cenaDeTela(
  4,
  2,
  (q) => [
    { em: 0, tela: QUADRO, foco: 'raias', zoom: 1.1 },
    { em: q('Nova'), tela: QUADRO, foco: 'raia_nova', zoom: 1.5, destaque: ['raia_nova'] },
    { em: q('dono'), tela: QUADRO, foco: 'cartao_nova', zoom: 2.3, destaque: ['dono_nova'] },
    { em: q('Entre'), tela: QUADRO, foco: 'raias', zoom: 1.1, destaque: ['raia_nova'] },
    { em: q('andamento'), tela: QUADRO, foco: 'raias', zoom: 1.1, destaque: ['raia_andamento'] },
    { em: q('Aguardando'), tela: QUADRO, foco: 'raias', zoom: 1.1, destaque: ['raia_aguardando'] },
    { em: q('gente'), tela: QUADRO, foco: 'raias', zoom: 1.15 },
  ],
  [['Nova'], ['gente']],
);

const C5 = cenaDeTela(
  5,
  3,
  (q) => [
    { em: 0, tela: CONVERSA, foco: 'conversa', zoom: 1.15 },
    { em: q('Conversa'), tela: CONVERSA, foco: 'conversa', zoom: 1.25, destaque: ['conversa'] },
    { em: q('arroba'), tela: CONVERSA, foco: 'linha_mencao', zoom: 1.7, destaque: ['linha_mencao'] },
    { em: q('combina'), tela: CONVERSA, foco: 'linhas', zoom: 1.45, destaque: ['linhas'] },
    { em: q('autor'), tela: CONVERSA, foco: 'linha_mencao', zoom: 1.8, destaque: ['linha_mencao'] },
  ],
  [['arroba'], ['guardado']],
);

const C6 = cenaDeTela(
  6,
  4,
  (q) => [
    { em: 0, tela: PLANEJAR, foco: ['titulo', 'planejar'], zoom: 1.15 },
    { em: q('Planejar'), tela: PLANEJAR, foco: 'planejar', zoom: 2.4, destaque: ['planejar'], cursor: 'planejar' },
    { em: q('IA'), tela: PLANEJAR, foco: 'planejar', zoom: 2.4, destaque: ['planejar'], cursor: 'planejar', clique: true },
  ],
  [['Planejar', 'com', 'a', 'IA']],
);

const C7 = cenaDeTela(
  7,
  4,
  (q) => [
    { em: 0, tela: PLANEJAMENTO, zoom: 1 },
    { em: q('perguntas'), tela: PLANEJAMENTO, foco: 'pergunta', zoom: 1.5, destaque: ['pergunta'] },
    { em: q('opções'), tela: PLANEJAMENTO, foco: ['pergunta', 'opcoes'], zoom: 1.5, destaque: ['opcoes'] },
    { em: q('recomendada'), tela: PLANEJAMENTO, foco: ['pergunta', 'opcoes'], zoom: 1.5, destaque: ['recomendada'] },
    { em: q('Escolha'), tela: PLANEJAMENTO, foco: ['pergunta', 'opcoes'], zoom: 1.5, destaque: ['opcoes'], cursor: 'recomendada' },
    { em: q('microfone'), tela: PLANEJAMENTO, foco: ['resposta', 'microfone'], zoom: 1.8, destaque: ['microfone'], cursor: 'microfone', clique: true },
    { em: q('direita'), tela: PLANEJAMENTO, foco: 'decididos', zoom: 2.2, destaque: ['decididos'] },
  ],
  [['Vitta'], ['recomendada'], ['microfone'], ['O', 'que', 'já', 'decidimos']],
);

const C8 = cenaDeTela(
  8,
  4,
  (q) => [
    { em: 0, tela: PLANEJAMENTO, foco: ['fechar', 'decididos'], zoom: 1.3 },
    { em: q('Fechar'), tela: PLANEJAMENTO, foco: 'fechar', zoom: 2.4, destaque: ['fechar'], cursor: 'fechar' },
    { em: q('resumir'), tela: PLANEJAMENTO, foco: 'fechar', zoom: 2.4, destaque: ['fechar'], cursor: 'fechar', clique: true },
    { em: q('resumo'), tela: RESUMO, foco: 'resumo', zoom: 1.25 },
    { em: q('porquê'), tela: RESUMO, foco: 'decisoes', zoom: 1.5, destaque: ['decisoes'] },
    { em: q('aberto'), tela: RESUMO, foco: ['decisoes', 'em_aberto'], zoom: 1.4, destaque: ['em_aberto'] },
    { em: q('bateu'), tela: RESUMO, foco: ['sim', 'nao'], zoom: 2.2, destaque: ['nao'], cursor: 'nao' },
  ],
  [['Fechar', 'e', 'resumir'], ['porquê'], ['bateu']],
);

const C9 = cenaDeTela(
  9,
  4,
  (q) => [
    { em: 0, tela: RESUMO, foco: ['sim', 'nao'], zoom: 2.0 },
    { em: q('sim'), tela: RESUMO, foco: ['sim', 'nao'], zoom: 2.0, destaque: ['sim'], cursor: 'sim' },
    { em: q('manda'), tela: RESUMO, foco: ['sim', 'nao'], zoom: 2.0, destaque: ['sim'], cursor: 'sim', clique: true },
    { em: q('desenvolvedores'), tela: ENVIADO, foco: 'enviado', zoom: 1.6, destaque: ['enviado'] },
    { em: q('Demanda'), tela: EM_ANALISE, foco: 'cartao', zoom: 2.0 },
    { em: q('análise'), tela: EM_ANALISE, foco: 'cartao', zoom: 2.0, destaque: ['selo'] },
    { em: q('card'), tela: O_QUE_MUDA, foco: 'o_que_muda', zoom: 1.3 },
    { em: q('muda'), tela: O_QUE_MUDA, foco: 'o_que_muda', zoom: 1.3, destaque: ['o_que_muda'] },
  ],
  [['sim'], ['Em', 'análise']],
);

const C10 = cenaDeTela(
  10,
  5,
  (q) => [
    { em: 0, tela: VINCULO, foco: 'vinculo', zoom: 1.2 },
    { em: q('Vínculo'), tela: VINCULO, foco: 'vinculo', zoom: 1.3, destaque: ['vinculo'] },
    { em: q('número'), tela: VINCULO, foco: ['numero', 'levar'], zoom: 2.0, destaque: ['numero', 'vincular'], cursor: 'numero' },
    { em: q('Levar'), tela: VINCULO, foco: ['numero', 'levar'], zoom: 2.0, destaque: ['levar'], cursor: 'levar' },
  ],
  [['Vínculo'], ['Levar', 'para', 'desenvolvimento']],
);

const C11 = cenaDeTela(
  11,
  6,
  (q) => [
    { em: 0, tela: QUADRO, foco: 'raias', zoom: 1.1 },
    { em: q('selo'), tela: QUADRO, foco: 'raias', zoom: 1.15 },
    { em: q('Planejada'), tela: QUADRO, foco: 'selo_planejada', zoom: 2.4, destaque: ['selo_planejada'] },
    { em: q('desenvolvimento'), tela: QUADRO, foco: 'selo_desenvolvimento', zoom: 2.4, destaque: ['selo_desenvolvimento'] },
    { em: q('produção'), tela: QUADRO, foco: 'selo_producao', zoom: 2.4, destaque: ['selo_producao'] },
  ],
  [['sozinho']],
);

const C12 = cenaDeTela(
  12,
  7,
  (q) => [
    { em: 0, tela: PAINEL, foco: 'com_voce', zoom: 1.15 },
    { em: q('entrega'), tela: PAINEL, foco: 'entregue', zoom: 1.3, destaque: ['entregue'] },
    { em: q('volta'), tela: PAINEL, foco: 'recado', zoom: 2.4, destaque: ['recado'] },
    { em: q('Painel'), tela: PAINEL, foco: 'com_voce', zoom: 1.2, destaque: ['com_voce'] },
  ],
  [['Com', 'você']],
);

const C13 = cenaDeTela(
  13,
  7,
  (q) => [
    { em: 0, tela: ENTREGA, foco: 'o_que_muda', zoom: 1.3 },
    { em: q('Teste'), tela: ENTREGA, foco: 'o_que_muda', zoom: 1.35, destaque: ['o_que_muda'] },
    { em: q('Concluir'), tela: ENTREGA, foco: 'mover', zoom: 2.2, destaque: ['concluir'], cursor: 'concluir', clique: true },
    { em: q('faltou'), tela: ENTREGA_CONVERSA, foco: 'conversa', zoom: 1.2 },
    { em: q('Conversa'), tela: ENTREGA_CONVERSA, foco: ['caixa', 'responder'], zoom: 1.6, destaque: ['caixa'], cursor: 'responder' },
    { em: q('refaz'), tela: ENTREGA_CONVERSA, foco: 'conversa', zoom: 1.25 },
  ],
  [['Concluir'], ['Conversa']],
);

/* ---------------------------------------------------------------- gancho e virada */

const TITULO_DO_EXEMPLO = 'Mostrar o nome do setor no cartaz do QR da Ouvidoria';
const RAIAS = ['Nova', 'Em andamento', 'Aguardando'];
/** o quadro de mentira do gancho: três colunas no meio da tela */
const MINI = { x: 960 - 690, y: 150, w: 440, h: 560, gap: 35 };

/** Um balão de mensagem solta (sem marca de aplicativo nenhum). */
const Balao: React.FC<{ texto: string; hora: string; x: number; y: number; op: number; escala: number; rot: number }> = ({ texto, hora, x, y, op, escala, rot }) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      maxWidth: 820,
      padding: '22px 30px 16px',
      borderRadius: '28px 28px 28px 8px',
      background: '#FFFFFF',
      color: '#1E293B',
      fontFamily: 'HP Simplified',
      fontSize: 40,
      lineHeight: 1.22,
      opacity: op,
      transform: `rotate(${rot}deg) scale(${escala})`,
      transformOrigin: '0 100%',
      boxShadow: '0 24px 60px rgba(0,0,0,.45)',
    }}
  >
    {texto}
    <div style={{ marginTop: 6, textAlign: 'right', fontSize: 28, color: '#64748B' }}>{hora}</div>
  </div>
);

/** O card de uma Demanda, no desenho do Quadro do app. */
const Cartao: React.FC<{
  x: number;
  y: number;
  w: number;
  escala: number;
  op: number;
  selo?: { texto: string; acende: number };
  oQueMuda?: number;
  brilho?: number;
}> = ({ x, y, w, escala, op, selo, oQueMuda = 0, brilho = 0 }) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: w,
      padding: '20px 24px',
      borderRadius: 18,
      background: '#FFFFFF',
      fontFamily: 'HP Simplified',
      opacity: op,
      transform: `scale(${escala})`,
      transformOrigin: '50% 50%',
      boxShadow: `0 24px 60px rgba(0,0,0,.45), 0 0 ${60 * brilho}px rgba(${RGB.acento},${0.8 * brilho}), 0 0 0 ${1.5 + 2 * brilho}px rgba(${RGB.acento},${0.25 + 0.6 * brilho})`,
    }}
  >
    <div style={{ fontSize: 34, lineHeight: 1.2, color: '#1E293B' }}>{TITULO_DO_EXEMPLO}</div>
    <div style={{ marginTop: 10, fontSize: 28, color: '#64748B' }}>Ouvidoria · Rafael Moura</div>
    {oQueMuda > 0 ? (
      <div
        style={{
          marginTop: 16 * oQueMuda,
          maxHeight: 190 * oQueMuda,
          overflow: 'hidden',
          opacity: oQueMuda,
          padding: `${14 * oQueMuda}px 18px`,
          borderRadius: 12,
          background: '#F1F5F9',
          border: '1.5px solid #E2E8F0',
        }}
      >
        <div style={{ fontSize: 28, letterSpacing: '0.06em', color: '#64748B' }}>O QUE MUDA</div>
        <div style={{ marginTop: 6, fontSize: 30, lineHeight: 1.25, color: '#1E293B' }}>O nome do setor no cartaz e no formulário do QR.</div>
      </div>
    ) : null}
    {selo ? (
      <div
        style={{
          display: 'inline-block',
          marginTop: 14,
          padding: '6px 16px',
          borderRadius: 10,
          background: PALETA.florestaClara,
          color: '#FFFFFF',
          fontSize: 28,
          opacity: clamp01(selo.acende * 3),
          transform: `scale(${0.6 + 0.4 * selo.acende})`,
          transformOrigin: '0 50%',
        }}
      >
        {selo.texto}
      </div>
    ) : null}
  </div>
);

/** As três raias do Quadro, desenhadas como no app. */
const MiniQuadro: React.FC<{ op: number; sobe: number }> = ({ op, sobe }) => (
  <>
    {RAIAS.map((nome, i) => (
      <div
        key={nome}
        style={{
          position: 'absolute',
          left: MINI.x + i * (MINI.w + MINI.gap),
          top: MINI.y + 40 * (1 - sobe),
          width: MINI.w,
          height: MINI.h,
          borderRadius: 22,
          background: 'rgba(238,242,250,.96)',
          opacity: op * clamp01(sobe * 1.4 - i * 0.12),
          boxShadow: '0 24px 60px rgba(0,0,0,.4)',
          padding: '22px 24px',
          fontFamily: 'HP Simplified',
          fontSize: 34,
          color: PALETA.florestaClara,
        }}
      >
        {nome}
      </div>
    ))}
  </>
);

const ESTILO_GRANDE = { ...ESTILO_LEGENDA, tamanho: 76, entrelinha: 1.12 };

const C1: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(1);
  const { fala } = useFrases(1);
  const qPedido = q('pedido');
  const qWhats = q('WhatsApp');
  const qAgora = q('agora');
  const qLugar = q('lugar');
  // as mensagens chegam soltas; no "agora" elas viram o card que cai na raia Nova
  const m1 = mola(f, 'estalo', qPedido - 6);
  const m2 = mola(f, 'estalo', qWhats - 2);
  // as mensagens somem antes de o card chegar: as duas juntas na tela embolam o gancho
  const vira = janelaM(f, qAgora - 6, qAgora + 6, 'entra');
  const quadro = janelaM(f, qAgora - 4, qAgora + 14, 'sai');
  const pousa = mola(f, 'assenta', qLugar - 2);
  // tudo segue empurrando devagar até o corte: nada fica parado antes da cena 2
  const empurra = 1 + 0.05 * clamp01(f / Math.max(1, c.seqDuracao));
  const cartaoX = lerp(600, MINI.x + 20, pousa);
  const cartaoY = lerp(330, MINI.y + 90, pousa);
  return (
    <AbsoluteFill>
      <Fundo />
      <AbsoluteFill style={{ transform: `scale(${empurra})` }}>
        <MiniQuadro op={quadro} sobe={quadro} />
        <Balao
          texto="Oi! Dá pra mostrar o nome do setor no cartaz do QR?"
          hora="09:14"
          x={330}
          y={260 + 30 * (1 - m1) - 120 * vira}
          op={clamp01((f - qPedido + 6) / 4) * (1 - vira)}
          escala={(0.9 + 0.1 * m1) * (1 - 0.4 * vira)}
          rot={-2}
        />
        <Balao
          texto="Alguém viu?"
          hora="11:40"
          x={330}
          y={470 + 30 * (1 - m2) - 120 * vira}
          op={clamp01((f - qWhats + 2) / 4) * (1 - vira)}
          escala={(0.9 + 0.1 * m2) * (1 - 0.4 * vira)}
          rot={-1}
        />
        <Cartao x={cartaoX} y={cartaoY} w={MINI.w - 40 + 280 * (1 - pousa)} escala={0.9 + 0.1 * vira} op={clamp01((f - qAgora - 2) / 6)} />
      </AbsoluteFill>
      <Legenda palavras={fala} destaque={marcar(fala, 'lugar')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
    </AbsoluteFill>
  );
};

const C14: React.FC = () => {
  const c = useCenaM();
  const f = c.frame;
  const q = useQuando(14);
  const { fala } = useFrases(14);
  const fimFala = c.local(T.fimFala);
  const qWhats = q('WhatsApp');
  const qPlano = q('plano');
  const qEntregue = q('entregue');
  const logoQ = fimFala + Math.round(LOGO_ENTRA_S * FPS);
  const some = janelaM(f, logoQ - 10, logoQ, 'entra');
  const entra = mola(f, 'estalo', 0);
  const logo = janelaM(f, logoQ, logoQ + Math.round((LOGO_ASSENTA_S - LOGO_ENTRA_S) * FPS), 'sai');
  const balao = clamp01((f - qWhats + 4) / 5) * (1 - janelaM(f, qWhats + 8, qWhats + 24, 'entra'));
  const plano = janelaM(f, qPlano - 2, qPlano + 12, 'sai');
  const selo = mola(f, 'estalo', qEntregue - 2);
  const brilho = clamp01((f - qEntregue) / 6) * (1 - janelaM(f, qEntregue + 8, qEntregue + 30, 'sai') * 0.6);
  return (
    <AbsoluteFill>
      {/* o fundo da virada não deriva: a assinatura é a única parada do vídeo */}
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 80% 70% at 50% 44%, ${PALETA.halo} 0%, ${PALETA.fundo} 72%)` }} />
      <AbsoluteFill style={{ opacity: 1 - some }}>
        {/* o card empurra devagar até a logo: nada fica parado antes da assinatura */}
        <Balao texto="Alguém viu?" hora="11:40" x={300} y={170 - 40 * janelaM(f, qWhats, qWhats + 24, 'sai')} op={balao * 0.85} escala={0.9} rot={-2} />
        <Cartao
          x={960 - 450}
          y={250 - 60 * plano}
          w={900}
          escala={(0.92 + 0.08 * entra) * (1 + 0.04 * janelaM(f, 0, logoQ, 'suave'))}
          op={clamp01(f / 6)}
          oQueMuda={plano}
          selo={{ texto: 'Em produção', acende: selo }}
          brilho={brilho}
        />
        <Legenda palavras={fala} destaque={marcar(fala, 'entregue')} centro largura={1600} estilo={ESTILO_GRANDE} base={1010} />
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
    entrada('tunel', { de: JANELA_T }),
    entrada('peliculaGira'),
    entrada('retangulo', { de: JANELA_T }),
    entrada('glitchRGB'),
    entrada('flood'),
    entrada('pulsoJanela', { de: { x: 860, y: 375, w: 200, h: 200, r: 20 }, para: JANELA_T }),
    entrada('corteBatida'),
    entrada('despenca', { caixas: [JANELA_T], semente: 'virada' }),
  ],
  nomes: ['gancho', 'quadro', 'assistente', 'raias', 'conversa', 'planejar', 'pergunta', 'resumo', 'sim', 'vinculo', 'etapa', 'painel', 'entrega', 'virada'],
  duracao: DURACAO,
});

export const Tecnologia: React.FC = () => (
  <VideoMontado cenas={CENAS} componentes={[C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14]} audio="narracao.wav" />
);

export const ComposicaoTecnologia: React.FC = () => (
  <Composition id="Tecnologia" component={Tecnologia} durationInFrames={DURACAO} fps={FPS} width={1920} height={1080} />
);

/** Para o meta.json: a janela da assinatura parada, em segundos (da entrada da logo ao fim). */
export const PARADA_S = [T.fimFala + LOGO_ENTRA_S, DURACAO / FPS];

