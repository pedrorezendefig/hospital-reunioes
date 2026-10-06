'use strict';

/* Cor fixa por pessoa (ADR 0062, decisão 5). Os três sócios têm cor curada;
   quem mais aparecer ganha a próxima cor da paleta, na ordem em que aparece.
   Uma função só, reusada pelos chips da aba Issues e, depois, pelas raias do
   quadro de PRs e pelos nós do desenho das ondas. Só tokens do :root. */

const SOCIOS = {
  pedrorezendefig: 'var(--brand)',
  lucassampaioc1: 'var(--green)',
  pedroribbe: 'var(--coral)',
};
const PALETA = ['var(--purple)', 'var(--amber)', 'var(--teal)', 'var(--navy)'];
const SEM_DONO = 'var(--ink-soft)';
const outras = new Map();

export function corDaPessoa(login) {
  if (!login) return SEM_DONO;
  if (SOCIOS[login]) return SOCIOS[login];
  if (!outras.has(login)) outras.set(login, PALETA[outras.size % PALETA.length]);
  return outras.get(login);
}
