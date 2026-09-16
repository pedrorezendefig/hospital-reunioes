# `/manual #PRD` e a página Novidades

## `/manual #PRD`: a Fatia de manual

Todo PRD com tela ganha, do `/to-issues`, uma última fatia "docs: manual do PRD
#N", bloqueada pelas fatias de código. Rodar `/manual #PRD` é a receita dessa
fatia.

1. **Leia a seção "Manual: páginas que nascem ou mudam"** do PRD
   (`gh issue view <N>`) e as issues filhas entregues. É essa seção que diz
   quais páginas existem; não invente página que o PRD não previu, e se a
   seção estiver vazia ou errada, diga isso em comentário no PRD antes de
   escrever.
2. **Escreva só essas páginas**, no molde da Página de tarefa, com
   `prd: [<N>]` e **`draft: true` em todas**, inclusive nas que só mudaram. A
   funcionalidade ainda não está em produção: é o `/deploy ship` que tira o
   draft quando ela sobe, e é por isso que o `draft` é o único mecanismo de
   invisibilidade do manual.
3. **Prints e vídeo** das páginas novas, pelas receitas de `prints.md` e
   `video-de-tarefa.md`.
4. **Uma entrada em `novidades.md`** do módulo (formato abaixo).
5. **Não publique.** A Fatia de manual para no checkpoint de merge, com o
   caminho do draft do vídeo no comentário do PR. Quem publica é o
   `/deploy ship`, depois que a funcionalidade sobe.

Página que o PRD apaga (tela que deixou de existir) sai do repositório no mesmo
PR, junto com a composição do vídeo dela: o conferidor acusa composição órfã.

## A página Novidades

Uma por módulo, do mais novo para o mais antigo, uma entrada por entrega. É a
página que a pessoa abre para saber o que mudou desde a última vez que usou.

```markdown
## 16/09/2026 · O caso muda de área num clique

O que mudou, em duas ou três linhas, do ponto de vista de quem usa.

Tarefas que mudaram: [Encaminhar para outra área](./encaminhar-para-outra-area/)
```

- A **data é a do deploy**, lida do `docs/spec/deploy/history.json`, não a da
  issue nem a de hoje.
- O **título é o valor entregue**, na língua do usuário, não o título do PRD.
- Entrada de PRD que ainda não subiu nasce junto com as páginas, na mesma
  página em `draft`, e aparece quando o módulo republica.
- Se a entrega tem Vídeo de percepção de valor em `docs/comunicacao/`, embuta
  ele aqui com `<video controls muted playsinline>`: a publicação copia o MP4
  para dentro do site e trava se não achar.
- Novidades não leva `papel`: não é Página de tarefa e não tem selo.
