'use strict';

/* Conteúdo da aba "Guia" — o método em 6 passos e os bastidores do painel.
   O passo a passo de máquina nova vive em setup.js (seção recolhida do Guia).
   A narrativa longa do workflow antigo morreu: o essencial virou a microcopy
   da aba Plano; aqui fica só 1 frase por passo. */

export const METODO = [
  { cmd: '/grill-with-docs', frase: 'A ideia apanha do domínio: perguntas afiadas contra o glossário e as decisões já tomadas, até o plano ficar redondo.' },
  { cmd: '/to-prd', frase: 'O plano vira PRD — uma issue no GitHub com problema, solução e critérios de aceite.' },
  { cmd: '/to-issues', frase: 'O PRD é cortado em fatias verticais independentes, com tamanho (P/M/G) e bloqueios explícitos.' },
  { cmd: '/pegar-issue', frase: 'Claim atômico: a fatia sai da fila já com dono e branch — várias sessões em paralelo, sem colisão.' },
  { cmd: '/tdd', frase: 'Cada critério de aceite vira um teste que falha primeiro; o código vem só para fazê-lo passar.' },
  { cmd: '/ship', frase: 'Commit, PR, 3 gates (code-review, security-review, CI), merge e deploy — a issue fecha sozinha.' },
];

export const BASTIDORES =
  'Este painel é só leitura: um servidor local em Python puro (zero dependências, ouvindo apenas a sua máquina) ' +
  'junta o que o workflow já produziu — issues e PRs ao vivo pelo gh, produção e deploys da origin/main ' +
  '(git fetch + show), mapa e decisões do seu clone — e desenha estas abas. Recoleta sozinho a cada 60s ' +
  '(o ⟳ no topo força na hora), nunca escreve nada e nunca toca produção.';
