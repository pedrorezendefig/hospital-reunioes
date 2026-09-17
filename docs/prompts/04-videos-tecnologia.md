# Vídeos: Tecnologia

O espaço reservado para os vídeos da área de Demandas de Tecnologia.

## Antes de colar qualquer coisa, uma decisão que é sua

**Tecnologia está fora do site do Manual, por decisão registrada.** O ADR 0057,
decisão 1, diz "A aba Tecnologia fica fora", e o PRD #731 a colocou em Fora de
escopo com a justificativa explícita: *"público de duas pessoas; a divulgação do
#634 cobre"*.

Então "vídeo de Tecnologia" pode significar duas coisas muito diferentes, e o
prompt muda inteiro dependendo de qual:

**(a) Vídeo de percepção de valor**, que é o que as decisões atuais preveem. Mora
em `docs/comunicacao/`, é para o diretor, fala de uma entrega e não ensina
tarefa. É a skill `/divulgar`. Não mexe no Manual, não mexe no ADR, e é o
caminho que não contraria nada. **O prompt abaixo é este.**

**(b) Vídeo de tarefa para uma seção Tecnologia no Manual.** Isso exige antes
**emendar o ADR 0057** e reabrir a decisão de escopo, porque hoje o site tem
cinco seções e Tecnologia não é uma delas. Se for isso que você quer, me diga e
eu monto: o trabalho extra é a emenda do ADR, a seção nova no `astro.config.mjs`
e as páginas escritas antes dos vídeos, porque vídeo de tarefa ilustra página e
não existe sozinho.

## O módulo, levantado

Três PRDs, dois entregues e um em andamento:

| PRD | Estado | O que é |
|---|---|---|
| [#634](https://github.com/pedrorezendefig/hospital-reunioes/issues/634) | fechado | A aba Tecnologia, o quadro de Demandas entre o hospital e a Vitta (ADR 0050) |
| [#673](https://github.com/pedrorezendefig/hospital-reunioes/issues/673) | fechado | Demanda vinculada ao desenvolvimento, Etapa, O que muda no card, e o comentário do diretor no loop do revisor (ADR 0054) |
| [#726](https://github.com/pedrorezendefig/hospital-reunioes/issues/726) | **aberto** | Assistente de Tecnologia, a Demanda nasce conversando (ADR 0056) |

As telas vivem em `/admin/tecnologia` e `/admin/tecnologia/nova`, só para o Super
admin. Os componentes estão em `hospital-reunioes/frontend/src/components/tecnologia/`.

**O #726 ainda está aberto**, tocado noutra sessão. Se o vídeo cobrir o
Assistente, produza **depois** que ele fechar e deployar, senão o vídeo retrata
tela que ainda vai mudar.

---

## Prompt para a leitura (a): vídeo de percepção

Copie o bloco e cole num terminal do Claude Code, na raiz do repositório.

```
Produza o Vídeo de percepção de valor da área de Tecnologia do app do Hospital São Matheus, no repo pedrorezendefig/hospital-reunioes.

ANTES DE COMEÇAR, CONFIRA O QUE JÁ ESTÁ ENTREGUE
Leia os três PRDs e diga qual deles o vídeo vai cobrir antes de escrever roteiro:
- #634 (fechado): a aba Tecnologia e o quadro de Demandas entre o hospital e a Vitta, ADR 0050.
- #673 (fechado): Demanda vinculada ao desenvolvimento, Etapa, O que muda no card, e o comentário do diretor no loop do revisor, ADR 0054.
- #726 (ABERTO): Assistente de Tecnologia, a Demanda nasce conversando, ADR 0056.

Se o #726 ainda estiver aberto quando você rodar, NÃO o cubra: o vídeo retrataria tela que ainda vai mudar. Cubra o que está em produção e me diga o que deixou de fora.

Confira em docs/comunicacao/ se já existe material de divulgação do #634, porque o PRD #731 registrou que "a divulgação do #634 cobre" esse público. Se existir, o seu trabalho é o que falta, não o que já foi feito.

O QUE FAZER
Invoque a skill /divulgar. Ela é a receita de vídeo de percepção e sabe onde a saída mora.

VÍDEO DE PERCEPÇÃO NÃO É VÍDEO DE TAREFA. O de percepção é do diretor, fala de uma entrega e mostra o valor; o de tarefa é do usuário, ensina um caminho e mora no Manual. Este é o primeiro. Não escreva página de manual, não mexa em docs/manual/.

O PÚBLICO É DE DUAS PESSOAS
O quadro de Demandas é a conversa entre o diretor do hospital e a Vitta. O vídeo fala para o diretor, não para o time inteiro. Isso muda o tom e o tamanho: mostre o que mudou para ele, não um tour de funcionalidade.

FIDELIDADE
Confira no código (hospital-reunioes/, LEITURA APENAS, edição proibida) toda afirmação e todo rótulo de tela. Na dúvida entre bonito e fiel, fiel vence. Se alguma coisa que você ia mostrar não existir como você imaginou, PARE e reporte.

Um fato conhecido: a aba Tecnologia é visível só para o Super admin (a AdminSidebar a marca como somenteSuperAdmin), e o painel Admin inteiro deixa entrar quem tem qualquer papel de Reuniões, mas quem não é Super admin só alcança "Dados do Atendimento".

GATE ANTI-TÉCNICA
Varra todo texto visível procurando: migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt. Mais travessão (U+2014) e meia-risca (U+2013). Cada ocorrência vira linguagem funcional ou sai. Este vídeo fala com um diretor de hospital.

AUTO-REVISÃO DE FRAMES, OBRIGATÓRIA
  ffmpeg -i <mp4> -vf fps=1/3 frames/%02d.png
e OLHE cada imagem. Marcador no elemento certo, texto legível, tela batendo com o app real. O `check` do HyperFrames não vê nada disso.

PII: O REPOSITÓRIO É PÚBLICO
Use dados de exemplo em tudo, inclusive nas linhas de lista e nos blocos de conversa. Numa onda anterior foram achados cinco prints e três vídeos com e-mail real e telefone de terceiro, e dois escaparam por estar no corpo da imagem.

O QUE NÃO FAZER
- Não mexa em docs/manual/: o Manual do usuário não cobre Tecnologia, por decisão do ADR 0057.
- Não edite hospital-reunioes/.
- Não publique nada e não mergeie.

REPORTE NO FIM
Qual PRD cobriu, o que deixou de fora e por quê, o que a auto-revisão de frames pegou, e onde o arquivo ficou.
```
