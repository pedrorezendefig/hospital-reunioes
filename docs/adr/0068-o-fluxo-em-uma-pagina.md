---
status: accepted
supersedes: 0020, 0022, 0028, 0029, 0035, 0043, 0053, 0061, 0062, 0063, 0064, 0065, 0066, 0067
---

# O fluxo em uma página

O que o pipeline faz hoje, de issue a produção. O histórico de como se chegou aqui fica nas ADRs que esta substitui e nos PRs da poda (#1033, #1034, #1036).

## Trabalho

1. **O trabalho vive nas GitHub Issues.** PRD vira issues com dependência (`blocked_by`). Só entra na fila issue `ready-for-agent`, sem dono, sem bloqueio aberto e de autor de dentro do repositório (`OWNER`, `MEMBER`, `COLLABORATOR`). O status da issue nunca mente e ninguém o mantém à mão: o `/ship` marca os critérios de aceite com os gates verdes, a Action de higiene limpa as labels no fechamento e fecha o PRD quando a última filha fecha, e comentário do revisor (`revisor-comentou`) reabre e refaz na mesma issue. O bloqueio entre issues é a dependência nativa do GitHub (`blocked_by`), única fonte da verdade: a fila é `-is:blocked` e destrava sozinha quando a bloqueadora fecha.
2. **Dois jeitos de andar:** à mão (`/pegar-issue`, `/tdd`, `/ship`) ou AFK (`/onda-enxuta`): uma sessão de fundo por onda, até 3 issues em paralelo. O único separador de ondas é a dependência, não o arquivo.
3. **Três agentes:** `hr-implementador` (claim, TDD, PR, morre), `hr-revisor` e `hr-corretor`. Esforço sobe por disparo (`xhigh` na fatia G, `max` na segunda falha de CI), não por agente novo.

## Gates

4. **PR de ferramenta** (nenhum arquivo em `hospital-reunioes/`): só o CI.
5. **PR do app:** o `hr-revisor` roda uma vez, olha só as linhas que o diff muda e reporta só must-fix (spec não cumprida, bug que o teste não pega, teste vácuo, segredo, regressão de permissão). Rota sem login ou migration (`sensivel.py`) acrescenta a lente de segurança no mesmo revisor. Must-fix vai a um `hr-corretor` fresco, uma vez; depois dele, quem confere é o CI.
6. **Nenhum agente para para perguntar.** Dúvida ou impasse é baixa: `ready-for-human` com uma linha de motivo. A fatia tem 3 tentativas, somando implementação, correções e conflitos.

6a. **Não existe auditoria de PRD.** O PRD fecha quando a última sub-issue fecha; a segurança e a spec são conferidas por PR, pelo `hr-revisor`.

## Até produção

7. **A `main` é protegida:** PR e CI verde obrigatórios, sem exigir a branch em dia com a base. O único bypass é a deploy key da Action pós-merge, num job que não instala nada.
8. **O rabo é um só, o `fechar_onda.py`**, para PR avulso e para onda: merge PR a PR pela API (squash, no head do CI verde), versão pelo tipo dos commits sem commit (`APP_VERSION` e tag), um build, health com conferência de versão, registro em `history.json` e `state.json`. Health ruim: rollback automático para a imagem anterior, revert dos squashes e issue reaberta. PR de ferramenta: só o merge.
9. **Quatro coisas esperam o humano:** (1) a migration (ele cola no Studio; o rabo espera o `/api/health` devolver o número dela, até 24 h); (2) o draft do vídeo da fatia de manual; (3) o rollback que o rabo não conseguiu sozinho (saídas 3, 4 e 8 do `fechar_onda.py`: `/deploy rollback` à mão); (4) a baixa `ready-for-human` (3 tentativas esgotadas, dúvida, corretor pendente).
10. **A onda seguinte sai no PR verde**, antes do rabo da atual; o semáforo ordena os deploys.
11. **Snapshot e draft do Manual** saem na Action do push da `main`, não no rabo.

## Regra de casa

12. **Cada regra tem uma casa:** script ou skill, nunca as duas. Decisão de ferramenta vai no corpo do PR, não em ADR nova; ADR é para o app e para mudança deste fluxo inteiro. As skills de `.claude/skills/` são o kit completo do fluxo e a fonte de verdade do Hospital; a cópia global é outra linhagem, e a duplicata é intencional. O fluxo é exportável pelo roteiro versionado em `tools/instalar-fluxo/` (`ROTEIRO.md` e `MANIFESTO.md`), que copia a árvore viva, nunca por prompt solto; skill do pipeline criada, renomeada ou apagada atualiza o `MANIFESTO.md` e o `/ask-pedro` no mesmo commit.
