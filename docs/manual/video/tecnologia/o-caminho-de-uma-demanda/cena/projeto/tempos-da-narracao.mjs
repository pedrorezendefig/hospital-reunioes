// Converte o narracao.json da voz A (~/.claude/voz/narrar.py) no tempos.json da skill motion.
//
// Uso: node scripts/tempos-da-narracao.mjs public/narracao.json <narracao.txt> "1|2,3|4,5,6|..." > src/videos/<Nome>/tempos.json
//
// Cada parágrafo do narracao.txt é uma frase. O terceiro argumento junta as frases em cenas
// (uma cena por tela do app): "2,3" põe as frases 2 e 3 na mesma cena. A grafia vem do
// narracao.txt (o narrar.py já devolve as palavras do roteiro), os tempos vêm da narração.
// Além do formato da skill motion, grava `frases`: o início de cada frase em segundos, a cena
// dela e o índice da primeira palavra, para a legenda trocar de frase dentro da mesma cena.
import { readFileSync } from 'node:fs';

const [, , arqJson, arqTxt, grupos] = process.argv;
const narr = JSON.parse(readFileSync(arqJson, 'utf8'));
const paragrafos = readFileSync(arqTxt, 'utf8')
  .trim()
  .split(/\n\s*\n/)
  .map((p) => p.split(/\s+/).filter(Boolean));
const total = paragrafos.reduce((a, p) => a + p.length, 0);
if (total !== narr.words.length) {
  console.error(`palavras: ${total} no texto e ${narr.words.length} na narração`);
  process.exit(1);
}
const FPS = 30;
const r3 = (v) => Math.round(v * 1000) / 1000;
const palavras = narr.words.map((w) => ({ t: w.text, s: r3(w.start), e: r3(w.end) }));

const frases = [];
let i = 0;
paragrafos.forEach((p, n) => {
  frases.push({ frase: n + 1, palavra: i, inicio_s: palavras[i].s });
  i += p.length;
});

const cenas = grupos.split('|').map((g, n) => ({ cena: n + 1, frases: g.split(',').map(Number) }));
const fim = r3(palavras[palavras.length - 1].e);
const saida = {
  fps: FPS,
  fim_fala_s: fim,
  cenas: cenas.map((c, n) => {
    const inicio = n === 0 ? 0 : frases[c.frases[0] - 1].inicio_s;
    const prox = cenas[n + 1];
    const fimS = prox ? frases[prox.frases[0] - 1].inicio_s : fim;
    return { cena: c.cena, inicio_s: inicio, fim_s: fimS, inicio_f: Math.round(inicio * FPS), dur_f: Math.round(fimS * FPS) - Math.round(inicio * FPS) };
  }),
  frases: frases.map((f) => ({ ...f, cena: cenas.find((c) => c.frases.includes(f.frase)).cena })),
  palavras,
};
process.stdout.write(JSON.stringify(saida, null, 1) + '\n');
