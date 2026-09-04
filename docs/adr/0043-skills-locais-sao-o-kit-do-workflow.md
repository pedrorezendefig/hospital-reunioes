---
status: accepted
---

# Skills locais são o kit completo do workflow, duplicata com as globais é intencional

O repo versiona em `.claude/skills/` todas as skills do ciclo de ponta a ponta (`grill-with-docs`, `to-prd`, `to-issues`, `triage`, `pegar-issue`, `tdd`, `ship`, `deploy`, mais as de apoio e as exclusivas da casa). Onze delas também existem na pasta global do Pedro (`~/.claude/skills/`) em versão genérica, e uma sessão de limpeza pode ser tentada a "desduplicar" apagando as cópias locais. Não apague.

## Decisões

1. **O repo é autossuficiente em skills.** Um sócio clona o repositório no GitHub e recebe o workflow inteiro funcionando, sem depender de nenhuma pasta global da máquina do Pedro. Isso é requisito, não acidente.

2. **A cópia local é a fonte de verdade do Hospital.** As skills locais carregam adaptações de propósito: vocabulário do `CONTEXT.md` (Reunião, Ata, Facilitador), comandos reais de verificação (`ruff`, `pytest`, `tsc`) e referências aos ADRs e a `docs/agents/`. Melhoria de skill para este repo se faz aqui, na cópia local.

3. **A versão global é outra linhagem.** A global é a generalização que o Pedro usa nos demais projetos; ela delega os detalhes ao `CLAUDE.md` de cada repo. Divergência entre local e global não é drift a corrigir, é especialização registrada. Sincronizar as duas é decisão humana, caso a caso, nunca limpeza automática.
