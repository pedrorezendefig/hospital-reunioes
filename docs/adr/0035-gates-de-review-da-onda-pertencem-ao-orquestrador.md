---
status: accepted
amends: 0029
---

# Gates de review da onda pertencem ao orquestrador

Na onda do PRD #317 (24-25/08), os gates internos de `/code-review` e `/security-review` do sub-agente travaram em 4 de 4 fatias sem devolver veredito, mesmo com re-engajamento. A causa é estrutural: essas skills fazem fan-out de review-agents, e as notificações de término chegam no **orquestrador**, não no sub-agente que as disparou. O sub-agente espera um veredito que nunca chega; o orquestrador espera o sub-agente, espera de novo, re-engaja e dispara revisores v2. Resultado medido: ~40 minutos por issue, dos quais ~25-30 são espera pura (caso do PR #351: 48 minutos de sessão, a maior parte em polling de `gh pr view`).

O formato que funcionou (2 de 2 vezes na mesma onda): o orquestrador dispara um `Agent` fresco de revisão, só-leitura, contexto limpo, que comenta o resultado no PR. E a revisão independente é melhor que a interna: a auto-revisão do autor no PR #348 deixou passar 2 achados ALTOS que o revisor independente pegou.

## Decisões

1. **Sub-agente da onda não roda mais review interna.** O sub-agente executa `/ship "<desc>" --issue <N> --no-merge --skip-review`: commit, push, PR, CI. Ele não invoca `/code-review` nem `/security-review`. O Gate 1.5 (spec × diff) continua dentro do sub-agente: não faz fan-out, funciona em worktree e já reprovou bugs reais (#325, duas vezes, até a correção).

2. **O orquestrador é o dono do gate de review.** Assim que o PR abre, o orquestrador dispara **1 revisor independente** (Agent fresco, sem `isolation: worktree`, prompt só-leitura: "ache problemas, não aprove, não edite") com **2 lentes no mesmo prompt**: código e segurança. O revisor lê o diff do PR via `gh` (GitHub), nunca a working tree, e comenta o resultado no PR. Exceção: diff que toca auth, permissions, migrations, endpoint público ou env vars ganha um **segundo revisor** dedicado só a segurança, em paralelo.

3. **Loop de fix com teto.** Achado must-fix volta ao sub-agente da issue via `SendMessage` (worktree ainda vivo); ele corrige, pusha, e o orquestrador dispara nova rodada de revisão. Máximo **2 rodadas**; sem veredito limpo, a issue vira `ready-for-human` (mesma política de baixa do ADR 0022).

4. **Nada de espera dupla.** O orquestrador não faz Monitor esperando gate interno do sub-agente e não dispara revisores "v2" por timeout. O único wait de review é a task-notification do revisor que ele mesmo disparou.

O invariante do ADR 0022 não muda: merge e deploy continuam atrás do checkpoint humano. "PR verde" para o checkpoint passa a significar: CI verde + spec × diff verde + veredito limpo do revisor independente.

## Considered options

- **Manter os gates internos e re-engajar quando travarem:** rejeitado. Foi a política vigente e falhou 4 de 4; cada trava custa duas esperas longas e um re-engajamento. Prompt não conserta o problema de roteamento das notificações (fan-out dentro de Agent async).
- **Manter os gates internos e só cortar a segunda espera:** rejeitado. Economiza menos (a primeira espera continua) e mantém um gate que estruturalmente não responde.
- **Orquestrador corrige os achados direto no worktree:** rejeitado. Quebra o orquestrador magro (ADR 0029) e mistura autor e revisor no mesmo contexto.
- **2 revisores sempre (código + segurança separados):** rejeitado como default. Dobra o custo de tokens com ganho marginal em fatia comum; a lente dedicada de segurança fica reservada a diffs de área sensível.

## Consequences

- Tempo por issue cai de ~40 min para ~15-20 min (o trabalho real de tdd + PR).
- A revisão fica mais confiável: revisor independente com contexto limpo, não auto-revisão de quem escreveu o código.
- O bug do `/security-review` ler o diff da árvore principal em worktree ([[project_security_review_diff_errado]]) deixa de afetar a onda: o revisor lê o diff do PR no GitHub.
- O `/ship` interativo (humano rodando fora da onda) não muda: os 3 gates internos continuam lá; a mudança vale para o contexto async da `/onda`.
