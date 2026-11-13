---
name: ship
description: Leva uma mudança até o PR verde (branch, commit, PR, gates da decisão do fluxo) e roda a subida, o fechar_onda.py, sem parar. Sintaxe `/ship "<descrição>" [--issue N] [--type ...] [--skip-review]`.
---

# ship

Do código ao PR verde e, com os gates verdes, a subida (`fechar_onda.py`), sem esperar mensagem (decisão do fluxo). Merge, versão, `APP_VERSION`, build, health e registro são só da subida (decisão do fluxo); o `/ship` nunca faz nenhum deles. Config do deploy em `docs/spec/deploy/project.json`; o que muda de um Projeto para outro (pasta do app, comando de testes, leitor do PR) em `.claude/fluxo.json` (`python3 .claude/skills/onda-enxuta/scripts/fluxo.py`). O que `fluxo.py notas ship` imprimir vale por cima desta skill.

## Sintaxe

```bash
/ship "<descrição curta>" [--issue N] [--type fix|feature|chore|refactor|docs|test|spec] [--skip-review] [--hotfix] [--draft] [--from-diff] [--resume]
```

| Flag | Efeito |
|---|---|
| `--issue N` | Vincula a issue: `Closes #N` no PR, critérios de aceite como checklist. |
| `--type` | Prefixo de branch e commit. Sem ele: "bug/corrigir/fix" → `fix`, "nova/adicionar" → `feature`, "refactor/limpar" → `refactor`, "doc/readme" → `docs`, senão `chore`. |
| `--skip-review` | Pula Gates 1 e 2 e termina no PR aberto, sem a subida. Modo do `onda-implementador` da onda. |
| `--hotfix` | Roda Gate 2 e CI e termina no PR verde, sem a subida. |
| `--draft` | PR como draft. |
| `--from-diff` | O código já está no working tree: vai direto ao commit. |
| `--resume` | Retoma pelo estado do git e do PR (tabela no fim). |

**Nunca pare para perguntar** (decisão do fluxo): dúvida, impasse ou revisor sem veredito é baixa, com uma linha de motivo.

## Passos 1 a 8: branch, código, testes, commit, PR

1. **Pre-flight:** `git fetch origin`. Arquivo alheio no working tree fica de fora do commit, sem perguntar. Com `--issue N` fora da `main`, a branch tem que terminar em `-<N>`; senão, pare (a árvore pode ser de outra sessão).
2. **Branch:** `<type>/<slug>[-<N>]` (slug minúsculo, ASCII, até 50 caracteres). Já na branch do `/pegar-issue`, pule.
3. **Issue:** `gh issue view N --json title,body,labels`. "O que construir" vira o contexto do PR; os critérios de aceite, o checklist e a lista de testes do `/tdd`.
4. **Código:** chame a Skill tool com `tdd`. Com `--from-diff`, pule.
5. **Testes locais, o mesmo comando do CI:** o `testes` do `fluxo.py` diz o comando de cada lado (ferramenta e app) neste Projeto; sem ele, rode o que o `.github/workflows/ci.yml` roda para os arquivos que o diff toca e, se tocou uma skill, `python3 tools/lint_skills.py --dir .claude/skills` quando o arquivo existir. O `python3` do macOS é velho: prefira o `uv run --no-project --python ">=3.12"` do CI. Vermelho local nunca vira PR: o CI inteiro é a prova, não a lista de arquivos que você lembrou de rodar (o #1046 da origem do fluxo caiu por trocar uma string que um teste de outro arquivo asserta).
6. **Commit:** Conventional Commits, `git add` com lista explícita (nunca `-A` nem `.`), nada do `hard_excluded` do `project.json`. Sem versão no PR: a versão sai na subida.
7. **Push:** `git push -u origin "$BRANCH"`. Falhou: reporte o erro bruto e pare.
8. **PR:** `gh pr create --base main --title "$SUBJECT" --body-file <scratchpad>/pr-$BRANCH.md`, mais `--label type:$TYPE --label area:<...>` só quando a label existe no repositório (`gh label list`): o `gh pr create` recusa label que não existe, e nem todo Projeto tem as `type:*` e as `area:*`. O arquivo do corpo leva o nome da branch: agentes paralelos na mesma sessão já se atropelaram num `pr.md` compartilhado (o #796 saiu com o `Closes` da issue errada). Corpo pelo `.github/PULL_REQUEST_TEMPLATE.md`: **Valor entregue** (um parágrafo `**O que muda:**` de 1 a 3 frases, escrito a partir da issue como quem explica a <leitor> (o `leitor` do `fluxo.py`) o que ela entrega, sem jargão; passe o parágrafo pela skill `humanizer` em modo embutido antes de abrir o PR), contexto (sem `--issue`, o Contexto abre com "Decisão registrada neste PR" e o porquê da mudança: é a casa da decisão de ferramenta, decisão do fluxo, regra 12), critérios de aceite, **Evidência** (antes e depois: o teste que falhava e passa, a saída de comando que mudou ou o print; nunca só "testes verdes"), **Perigo do merge** (porta de uma ou duas vias pela lista do template, com o motivo, e o raio) e `Closes #N`. Cada linha `Candidata: <slug>/<sessao>-onda<N> #<n>` que vier no pedido (a `/retro-onda` imprime uma por Candidata aceita) vai copiada para o corpo do PR sem mudança, uma por linha, no fim do corpo: é por ela que o PedroOS dá a Candidata por corrigida quando o PR entra na main. Aberto o PR com `--issue N`, apague os anexos que o `anexos.py` do Projeto tenha baixado: `rm -rf local/anexos/<N>` na raiz do clone (sem a pasta, o comando não faz nada). Com migration nova, a seção `## Migration NNN (conferência por hash)` com o `sha256` do arquivo (`shasum -a 256`) e o SQL completo: a subida confere e para se faltar ou divergir.

## Passo 8: gates

**PR de ferramenta** (`fluxo.py classe --pr "$PR"` diz `ferramenta`: nenhum arquivo na pasta do app, decisão do fluxo): só o CI. Verde, vá ao Passo 9.

**PR do app**, na ordem:

- **Gate 2, `sensivel.py`** (rode primeiro): `uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py "$PR"`. Saída 0: o prompt do revisor leva `Sensível: <arquivos impressos>`. Saída 1: nada. Outra saída: rode de novo; na segunda falha, baixa.
- **Gate 1, `onda-revisor`**, prompt de `.claude/skills/onda-enxuta/references/prompts.md`. Última linha do comentário: `VEREDITO: LIMPO` ou `VEREDITO: MUST-FIX (n)`. Com issue vinculada, o revisor também confere spec × diff.
- **Gate 3, CI:** `gh pr checks "$PR" --watch`.

Correção:
- `MUST-FIX` → `onda-corretor` motivo `revisao` com o comentário inteiro. Uma revisão, uma correção, sem re-revisão: depois do corretor, quem confere é o CI. Corretor com `pendente` é baixa.
- CI vermelho → `onda-corretor` motivo `ci` com as últimas 60 linhas de `gh run view <id> --log-failed`; a segunda falha da fatia vai com `effort: max`. Depois, `gh pr checks --watch` de novo.
- Cada falha conta uma tentativa; na terceira, baixa.

**Baixa:** `gh issue edit N --remove-label in-progress --add-label ready-for-human`, comentário com `<!-- automacao -->` na primeira linha e o diagnóstico (gate, achado, hipótese) e `PushNotification` de uma linha ("<nome do Projeto>: #N ficou com você, <gate>"; dentro de uma Onda, quem avisa é a `/onda-enxuta`, pelo evento `pronto-para-voce`). O PR fica aberto e a subida não roda.

Todo comentário do agente no GitHub leva `<!-- automacao -->` na primeira linha.

## Passo 9: critérios de aceite na issue

Com issue vinculada, confira cada critério contra o diff antes da subida: o que ficou de fora vai riscado no corpo **da issue** (`- [ ] ~~...~~`) com o motivo no PR. Marcar o resto é da subida: logo depois do merge, o `fechar_onda.py` vira em `- [x]` toda caixa vazia que não está riscada, no avulso e na onda. Critério não entregue e não riscado sai marcado como entregue.

## Passo 10: a subida

```bash
python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs "$PR"
```

Em segundo plano (builds levam minutos); leia só a saída. O que fazer em cada código de saída está na docstring do script. Os dois que pedem ação de quem rodou:
- **Saída 2 com `conflito no merge de #N em: <arquivos>`:** `onda-corretor` motivo `conflito` com os arquivos, CI de novo, subida de novo. Conta tentativa.
- **Saídas 6, 7 e 8:** `PushNotification` com a linha que o script imprimiu. A 6 conta tentativa.
- **`migration: <como aplicar> <arquivo> (...); copie com: pbcopy < <caminho>`:** a subida espera o `/api/health` devolver o número dela (até 24 h). Repasse a linha por `PushNotification`. Nunca mostre o caminho com `:1` nem abra o `.sql` num editor: o humano copia o arquivo inteiro pelo `pbcopy` (ou pelo botão do painel, quando o Projeto tem um). Quem aplica é o humano, do jeito que `migrations.aplicar` do `fluxo.py` diz; o `/ship` nunca aplica migration.

**Sem plataforma:** enquanto o `services` do `docs/spec/deploy/project.json` estiver vazio (`/deploy status` diz), a subida trata todo PR como ferramenta e termina no merge: sem versão, tag, build, health, registro nem espera de migration. A saída 0 já é o PR mergeado com o CI verde.

**Pendência só humana** (import na virada, credencial, ato externo): uma issue `ready-for-human` por pendência, ligada ao PRD pelo corpo ("Pai: #N"), nunca como sub-issue nativa.

## Saída

```
✅ ship PR #<PR> verde · gates: <lista> · Issue #<N> com critérios marcados
   Subida: <última linha do fechar_onda.py>
```

Baixa: `❌` e, na segunda linha, o gate e o motivo.

## Retomada (`--resume`)

| Estado | Retoma em |
|---|---|
| Sem commit | Passo 5 |
| Commit sem push | Passo 7 |
| Push sem PR | Passo 8 |
| PR aberto, gates pendentes | Passo 8 |
| Gates verdes | Passos 9 e 10 |
| PR mergeado | Nada; a subida já rodou |

## Regras

- Nunca `git push --force` na `main`; `--force-with-lease` só na branch própria.
- Nunca rodar `/ship` numa branch que já tem PR aberto sem `--resume`.
- Nunca logar token ou segredo.
