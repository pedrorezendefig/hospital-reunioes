---
name: ship
description: Leva uma mudança até o PR verde (branch, commit, PR, 3 gates) e roda o rabo, o fechar_onda.py, sem parar. Sintaxe `/ship "<descrição>" [--issue N] [--type ...] [--skip-review]`.
---

# ship

Do código ao PR verde e, com os gates verdes, o rabo (`fechar_onda.py`), sem esperar mensagem (ADR 0063). Merge, versão, `APP_VERSION`, build, health e registro são só do rabo (ADR 0061); o `/ship` nunca faz nenhum deles. Config em `docs/spec/deploy/project.json`.

## Sintaxe

```bash
/ship "<descrição curta>" [--issue N] [--type fix|feature|chore|refactor|docs|test|spec] [--skip-review] [--hotfix] [--draft] [--from-diff] [--resume]
```

| Flag | Efeito |
|---|---|
| `--issue N` | Vincula a issue: `Closes #N` no PR, critérios de aceite como checklist. |
| `--type` | Prefixo de branch e commit. Sem ele: "bug/corrigir/fix" → `fix`, "nova/adicionar" → `feature`, "refactor/limpar" → `refactor`, "doc/readme" → `docs`, senão `chore`. |
| `--skip-review` | Pula Gates 1 e 2 e termina no PR aberto, sem o rabo. Modo do `hr-implementador` da onda. |
| `--hotfix` | Roda Gate 2 e CI e termina no PR verde, sem o rabo. |
| `--draft` | PR como draft. |
| `--from-diff` | O código já está no working tree: vai direto ao commit. |
| `--resume` | Retoma pelo estado do git e do PR (tabela no fim). |

**Nunca pare para perguntar** (ADR 0067): dúvida, impasse ou revisor sem veredito é baixa, com uma linha de motivo.

## Passos 1 a 7: branch, código, commit, PR

1. **Pre-flight:** `git fetch origin`. Arquivo alheio no working tree fica de fora do commit, sem perguntar. Com `--issue N` fora da `main`, a branch tem que terminar em `-<N>`; senão, pare (a árvore pode ser de outra sessão).
2. **Branch:** `<type>/<slug>[-<N>]` (slug minúsculo, ASCII, até 50 caracteres). Já na branch do `/pegar-issue`, pule.
3. **Issue:** `gh issue view N --json title,body,labels`. "O que construir" vira o contexto do PR; os critérios de aceite, o checklist e a lista de testes do `/tdd`.
4. **Código:** chame a Skill tool com `tdd`. Com `--from-diff`, pule.
5. **Commit:** Conventional Commits, `git add` com lista explícita (nunca `-A` nem `.`), nada do `hard_excluded` do `project.json`. Sem versão no PR: o `package.json` do frontend fica congelado, a versão sai no rabo.
6. **Push:** `git push -u origin "$BRANCH"`. Falhou: reporte o erro bruto e pare.
7. **PR:** `gh pr create --base main --title "$SUBJECT" --body-file <scratchpad>/pr-$BRANCH.md --label type:$TYPE --label area:<...>`. O arquivo do corpo leva o nome da branch: agentes paralelos na mesma sessão já se atropelaram num `pr.md` compartilhado (o #796 saiu com o `Closes` da issue errada). Corpo pelo `.github/PULL_REQUEST_TEMPLATE.md`: contexto (sem `--issue`, o Contexto abre com "Decisão registrada neste PR" e o porquê da mudança: é a casa da decisão de ferramenta, ADR 0068, regra 12), critérios de aceite, **Evidência** (antes e depois: o teste que falhava e passa, a saída de comando que mudou ou o print; nunca só "testes verdes"), **Perigo do merge** (porta de uma ou duas vias pela lista do template, com o motivo, e o raio) e `Closes #N`. Com migration nova, a seção `## Migration NNN (conferência por hash)` com o `sha256` do arquivo (`shasum -a 256`) e o SQL completo: o rabo confere e para se faltar ou divergir.

## Passo 8: gates

**PR de ferramenta** (nenhum arquivo em `hospital-reunioes/`, ADR 0067): só o CI. Verde, vá ao Passo 9.

**PR do app**, na ordem:

- **Gate 2, `sensivel.py`** (rode primeiro): `uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py "$PR"`. Saída 0: o prompt do revisor leva `Sensível: <arquivos impressos>`. Saída 1: nada. Outra saída: rode de novo; na segunda falha, baixa.
- **Gate 1, `hr-revisor`**, prompt de `.claude/skills/onda-enxuta/references/prompts.md`. Última linha do comentário: `VEREDITO: LIMPO` ou `VEREDITO: MUST-FIX (n)`. Com issue vinculada, o revisor também confere spec × diff.
- **Gate 3, CI:** `gh pr checks "$PR" --watch`.

Correção:
- `MUST-FIX` → `hr-corretor` motivo `revisao` com o comentário inteiro. Uma revisão, uma correção, sem re-revisão: depois do corretor, quem confere é o CI. Corretor com `pendente` é baixa.
- CI vermelho → `hr-corretor` motivo `ci` com as últimas 60 linhas de `gh run view <id> --log-failed`; a segunda falha da fatia vai com `effort: max`. Depois, `gh pr checks --watch` de novo.
- Cada falha conta uma tentativa; na terceira, baixa.

**Baixa:** `gh issue edit N --remove-label in-progress --add-label ready-for-human`, comentário com `<!-- automacao -->` na primeira linha e o diagnóstico (gate, achado, hipótese) e `PushNotification` de uma linha. O PR fica aberto e o rabo não roda.

Todo comentário do agente no GitHub leva `<!-- automacao -->` na primeira linha.

## Passo 9: critérios de aceite na issue

Com os gates verdes e issue vinculada, marque no corpo **da issue** cada critério entregue (`- [x]`) e risque o descopado (`- [ ] ~~...~~`). Sem descope e sem checkbox fora dos critérios, basta `sed 's/^- \[ \] /- [x] /'` no corpo e `gh issue edit N --body-file`.

## Passo 10: o rabo

```bash
python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs "$PR"
```

Em segundo plano (builds levam minutos); leia só a saída. O que fazer em cada código de saída está na docstring do script. Os dois que pedem ação de quem rodou:
- **Saída 2 com `conflito no merge de #N em: <arquivos>`:** `hr-corretor` motivo `conflito` com os arquivos, CI de novo, rabo de novo. Conta tentativa.
- **Saídas 6, 7 e 8:** `PushNotification` com a linha que o script imprimiu. A 6 conta tentativa.

**Migration nova:** o rabo imprime `migration: cole no Studio <arquivo>:1` e espera o `/api/health` devolver o número dela (até 24 h). Repasse a linha por `PushNotification`. Quem aplica é o humano, no SQL Editor do Studio de produção; o `/ship` nunca aplica migration.

**Fatia de manual** (ADR 0057): termina no PR verde, com o caminho do MP4 no corpo, e `PushNotification` "Draft do vídeo da #N no PR #P: <MP4>". Quem viu o vídeo roda o rabo.

**Pendência só humana** (import na virada, credencial, ato externo): uma issue `ready-for-human` por pendência, ligada ao PRD pelo corpo ("Pai: #N"), nunca como sub-issue nativa.

## Saída

```
✅ ship PR #<PR> verde · gates: <lista> · Issue #<N> com critérios marcados
   Rabo: <última linha do fechar_onda.py>
```

Baixa: `❌` e, na segunda linha, o gate e o motivo.

## Retomada (`--resume`)

| Estado | Retoma em |
|---|---|
| Sem commit | Passo 5 |
| Commit sem push | Passo 6 |
| Push sem PR | Passo 7 |
| PR aberto, gates pendentes | Passo 8 |
| Gates verdes | Passos 9 e 10 |
| PR mergeado | Nada; o rabo já rodou |

## Regras

- Nunca `git push --force` na `main`; `--force-with-lease` só na branch própria.
- Nunca rodar `/ship` numa branch que já tem PR aberto sem `--resume`.
- Nunca logar token ou segredo.
