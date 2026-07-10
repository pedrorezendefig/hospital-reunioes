---
status: superseded
superseded_by: 0011
---

# Nota: registro dinâmico paralelo à Reunião

A diretoria precisa registrar **conversas, feedback e eventos** informais — "o que foi tratado" — sem a cerimônia Reunião → Transcrição → Ata → ClickSign. Hoje o único jeito de gerar uma Pendência é por uma Reunião que passa pelo Pipeline de IA e chega a estado terminal (ASSINADA/APROVADA, ADR 0003). Não existe registro leve nem Pendência avulsa, e o glossário já separa "evento" de "Reunião".

A decisão: criar a **Nota**, entidade nova e leve, **paralela** à Reunião (não uma variante). Uma Nota é um **corpo de texto livre** redigido pelo Facilitador — por teclado ou por **voz** (transcrição via endpoint `/audio/transcriptions` do OpenRouter, modelo `gpt-4o-mini-transcribe`; o texto cai editável no campo e o áudio é descartado após transcrever) — com um **roster opcional de Participantes** (Colaborador do cadastro **ou** nome avulso, para externos não cadastrados como "o fulano aliado"). A partir do corpo, a **IA propõe** Pendências — responsável casado contra o roster, prazo parseado de linguagem natural ("sexta") — que o Facilitador **confirma/edita/descarta** antes de criar; o add manual fica sempre disponível. Reusa `_find_participante`, `_normalizar_prazo` e o passo de estruturação JSON do Pipeline.

As Pendências da Nota caem na **mesma tabela `pendencias`** e no mesmo acompanhamento (painel, cron `alerta_prazo`, Repactuação, comentários, emails). Para isso, `pendencias` ganha um FK nulável **`id_nota`** ao lado do `id_reuniao` (também nulável), com um **CHECK** garantindo exatamente uma origem preenchida. O acesso **espelha o modelo atual**: o autor vê as suas Notas, Secretária e Super admin veem todas. A Nota é **editável** pelo autor e usa **soft-delete** (`deleted_at`); as Pendências geradas são **independentes** — sobrevivem ao arquivamento ou à edição da Nota.

## Por que é surpreendente

A intuição do domínio é "ação nasce de uma Reunião assinada/aprovada" — o ADR 0003 já abriu uma segunda origem terminal. A Nota abre uma **terceira porta**: uma Pendência com `id_reuniao` **nulo** e `id_nota` preenchido, vinda de um artefato que **nunca toca** Transcrição, Ata nem ClickSign. Quem lê o código esperando `pendencia.id_reuniao` sempre presente vai quebrar.

## Alternativas descartadas

- **Dobrar a Reunião** (modo rápido que pula transcrição+IA e nasce APROVADA): reusaria `liberar_pendencias`, mas obrigaria a mexer no `StatusAta` (enum backend + CHECK no banco + 2 lugares no frontend) e carregaria 25+ colunas sem sentido para um bilhete. O glossário já separa "evento" de "Reunião"; forçar a fusão polui o conceito central.
- **Só Pendência avulsa** (sem container de registro): joga fora o pedido central — o histórico narrativo. Sobra a tarefa, perde-se o "log do que foi tratado".
- **Par genérico `origem_tipo`/`origem_id`** em vez de FKs reais: aceitaria origens futuras sem migration, mas perde integridade referencial e o ON DELETE CASCADE viraria lógica manual no app. Com só duas origens (Reunião e Nota), dois FKs nuláveis + CHECK é mais seguro.
- **IA cria a Pendência direto** (sem confirmação): dispararia cobrança real a partir de tarefa possivelmente alucinada. O passo de confirmação é a guarda.
- **Voz que transcreve E extrai numa tacada** (LLM multimodal de áudio): mais "mágico", mas acopla os dois eixos (input e extração) e tira a revisão do texto cru. Fica como evolução.
- **Visibilidade global ou compartilhável caso a caso**: "dar publicidade" foi lido como "ficar de record", não "broadcast"; espelhar o acesso atual protege o feedback sensível sem conceito novo. Compartilhar entre Facilitadores fica como aditivo futuro.

## Consequências

- `pendencias` passa a ter **três origens** lógicas (Reunião ASSINADA, Reunião APROVADA, Nota). Qualquer código que assuma `id_reuniao` preenchido — ex.: o link "ver reunião de origem" no painel — precisa tratar o caso `id_nota`.
- Novas tabelas `notas` e `nota_participantes` (espelha `reuniao_participantes`, mas aceita nome avulso para externos). Migration nova: `id_nota` + CHECK em `pendencias`.
- Nova dependência de produção no endpoint de transcrição do OpenRouter (mesma chave e billing do Pipeline). Custo desprezível no volume esperado (fração de centavo por Nota).
- Glossário atualizado: **Participante** generalizado (Reunião **ou** Nota), verbete de **Pendência** passou a citar as origens, novo verbete **Nota**.
- Trade-off consciente: **sem campo de "data do evento"** — o histórico ordena por data de criação. Se virar necessidade, é aditivo.
