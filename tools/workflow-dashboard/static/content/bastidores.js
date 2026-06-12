'use strict';

/* Conteúdo da aba "Bastidores" — como o próprio painel funciona.
   Reflete o que serve.py + collect.py realmente fazem (só leitura). */

/* O caminho de um dado, do clique até a tela */
export const DATA_FLOW = [
  { n: '1', title: 'Você abre o painel', text: 'O serve.py (Python puro, sem instalar nada) sobe um servidor só na sua máquina e abre o navegador.' },
  { n: '2', title: 'O painel pede os dados', text: 'A cada carga — e sozinho a cada 60s — o navegador chama /api/data. A resposta fica em cache por 60s para não pesar.' },
  { n: '3', title: 'O collect.py junta tudo', text: 'Ele lê o GitHub pelo gh, os deploys e releases direto da origin/main (git fetch + show), os arquivos do clone (snapshots, decisões) e o git local, e monta um pacote único.' },
  { n: '4', title: 'As abas desenham', text: 'Cada aba recebe esse pacote e desenha. O painel só LÊ — nunca escreve, nunca muda produção, nunca commita.' },
];

/* De onde vem cada bloco de dado: ao vivo (rede) vs do último git pull (arquivos do clone) */
export const SOURCES = [
  { src: 'Issues, PRs e comentários', live: true, origin: 'gh — GitHub ao vivo' },
  { src: 'Seu git local (branch, commits)', live: true, origin: 'git no seu clone' },
  { src: 'Produção e deploys (aba Agora / Deploys)', live: true, origin: 'docs/spec/deploy/*.json na origin/main (git)' },
  { src: 'Mapa da app — rotas, schema, entidades', live: false, origin: 'docs/spec/snapshots/' },
  { src: 'Timeline de releases', live: true, origin: 'docs/spec/CHANGELOG.md na origin/main (git)' },
  { src: 'Decisões e glossário (aba Domínio)', live: false, origin: 'docs/adr/ + CONTEXT.md' },
];

/* Fatos técnicos (vão no "detalhes técnicos" recolhível) */
export const TECH_FACTS = [
  'Servidor: Python da biblioteca padrão, zero dependências para instalar.',
  'Acesso: escuta só em 127.0.0.1 (a sua máquina) — ninguém na rede alcança.',
  'Cache: a coleta vale 60s; o botão ⟳ no topo força uma nova na hora.',
  'Atualização: o painel recoleta sozinho a cada 60s, sem recarregar a página.',
  'Garantia: é só leitura — não há rota de escrita; nada é alterado na working tree nem em produção (o git fetch só atualiza referências remotas).',
];
