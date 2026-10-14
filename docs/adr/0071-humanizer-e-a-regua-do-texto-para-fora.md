---
status: accepted
amends: 0057
---

# Humanizer é a régua de todo texto para fora; o manual e o Hospital OS são reescritos por ela

Decisão do Pedro (13/out/2026, grilling). O texto que o hospital lê (Manual do usuário, telas do app, PDFs de Ata e POP, hover do Hospital OS, mensagens e páginas de divulgação) é escrito por agente, e carrega os cacoetes de texto gerado: "não é X, é Y", fecho de uma linha que repete o parágrafo, tríade, rótulo em negrito. A ADR 0057 rejeitou em setembro uma "humanização separada" porque o texto do manual "já era humano"; um mês depois os cacoetes estão nas 106 páginas, no front e nos 200 PRs que o Hospital OS resume. Esta ADR fixa a skill global `humanizer` como régua de tudo que sai para fora e decide a reescrita do que já existe.

## Decisões

1. **Regra global, gate local.** O `~/.claude/CLAUDE.md` (regra 8) manda todo texto para leitor de fora passar pelo humanizer em modo embutido antes de ser gravado, em qualquer repositório. No Hospital, as skills que produzem texto (`/manual`, `/ship`, `/divulgar`, `/mensagem-prd`, `/to-prd`, `/to-issues`) chamam o humanizer no fechamento, e o que dá para pegar por regex trava no CI: `tools/lint_manual.py` e a regra do ESLint do front (que já travam travessão) ganham os tells mecânicos (contraste "não é X, é Y" e variantes "não só/apenas/somente... mas", fecho repetido, "não X: Y"). Um repositório pode somar amostra de voz, jargão e lint; nenhum dispensa a passagem. Rejeitado: só a regra global (ninguém trava); só o gate no Hospital (os outros repositórios ficam sem régua).

2. **Voz do canal manda no tom.** Onde há amostra aprovada (a regra 6 do CLAUDE.md global para WhatsApp, uma Página de tarefa publicada, o exemplo do template de PR), a skill casa o tom dela e só tira os cacoetes. O humanizer não escolhe registro: o canal escolhe.

3. **O front do app passa uma vez e depois só a trava.** Uma issue única varre o texto visível do frontend e dos templates de PDF do backend com o humanizer, uma vez. Daí em diante o ESLint trava o que entra. Rejeitado: só daqui para frente (o cliente continua lendo o que já está lá); varrer a cada PR (custo recorrente sem ganho).

4. **O hover do Hospital OS mostra o que muda, não antes e depois.** A seção "Valor entregue" do template de PR deixa de ter `**Antes:**` e `**Depois:**` e vira um parágrafo único, "O que muda", de 1 a 3 frases, como quem explica a um colega do hospital o que aquela issue entrega. O `/ship` escreve o parágrafo a partir da issue e passa pelo humanizer; o `collect.py` lê esse parágrafo e o `prs.js` o mostra sozinho no hover. Os PRs da janela do painel (os 200 mais recentes) são reescritos uma vez pela API, só nessa seção: `Closes #N`, a seção de migration conferida por hash e o resto do corpo ficam intactos. Rejeitado: fallback mostrando só o "Depois" dos antigos (histórico com duas caras); resumo gerado na hora por LLM no `collect.py` (o painel deixa de ser leitura de JSON e `gh`).

5. **O Manual é reescrito por módulo, dentro do molde.** Seis issues, uma por módulo, cada uma em worktree próprio como a `/montar-manual` já planeja, rodando o humanizer em modo arquivo página a página (Visão geral, Páginas de tarefa, Como funciona e Novidades). O molde da ADR 0057 não muda: até 6 passos, teto de 250 palavras, a palavra da tela em negrito, "você" e imperativo. A régua de linguagem da skill `/manual` cita o humanizer como passo obrigatório antes do lint. Rejeitado: uma issue para as 106 páginas (sessão e PR grandes demais); só as Páginas de tarefa (a Visão geral é a primeira coisa que o leitor vê).

6. **A busca é a atual, afinada.** O Manual já tem busca em toda página (Pagefind do Starlight, `Ctrl+K`); o que falta é achar com a palavra que a pessoa fala. A barra de busca fica visível e larga no topo também no celular (hoje é só a lupa); cada página pode declarar `busca:` no frontmatter com as palavras do dia a dia ("boleto", "guia") e elas entram no índice; o resultado mostra o título da tarefa com o módulo. A home abre com a barra de busca ("O que você quer fazer?") acima dos seis cartões de módulo, e cada Página de tarefa pode terminar com até três **Tarefas próximas** do mesmo módulo, escolhidas no frontmatter. A estrutura de pastas e o menu na ordem do app (ADR 0057, decisão 1) não mudam. Rejeitado: busca própria em JS (código para manter num site que entrega isso de graça); reestruturar por jornada (desalinha do item Ajuda do app, que abre por módulo).

7. **Dois PRDs.** Um para o texto (regra, lints, varredura do front, hover do Hospital OS, reescrita do Manual, busca e home) e um para os vídeos do Manual (emenda à ADR 0057, abaixo). Gates, sessões e ritmo são diferentes; o de vídeo depende só da regra do primeiro. A regra global foi gravada na própria sessão do grilling, porque vive fora do repositório.

## Consequências

- `~/.claude/CLAUDE.md` ganha a regra 8. Os CLAUDE.md dos outros repositórios não precisam repetir; podem somar amostra de voz.
- `.github/PULL_REQUEST_TEMPLATE.md`, `/ship`, `collect.py` e `prs.js` mudam juntos na mesma fatia; o `README.md` do Hospital OS descreve o hover novo.
- `tools/lint_manual.py` e o ESLint do front ganham os tells regexáveis. Falso positivo legítimo (contraste em que as duas metades informam) se resolve reescrevendo, como já é com o travessão.
- A `/manual` e a `/divulgar` ganham o passo do humanizer na régua; o `/ask-pedro` cita a ADR.
- A reescrita dos 200 PRs mergeados altera corpo de PR fechado; é ruído no histórico do GitHub, aceito uma vez.
