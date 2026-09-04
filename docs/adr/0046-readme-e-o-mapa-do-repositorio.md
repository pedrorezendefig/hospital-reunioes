---
status: accepted
amends: 0044
---

# O `README.md` da raiz é o mapa do repositório

O mapa do repositório (o que é cada pasta, por que existe, o que tem dentro, para que serve, onde as chaves moram) nasceu em `.claude/skills/setup-maquina/references/mapa-do-repo.md`, como referência da skill. Ali só o agente achava. Quem clona abre a página do repo no GitHub e não vê nada: a raiz não tinha `README.md`, por decisão do ADR 0044 (decisão 2), que limitava a raiz a `CLAUDE.md`, `CONTEXT.md`, `CONTEXT-MAP.md` e `skills-lock.json`.

## Decisões

1. **O mapa mora em `README.md`, na raiz.** É o único arquivo que o GitHub mostra sem clicar, e é onde qualquer pessoa procura. A decisão 2 do ADR 0044 passa a admitir `README.md` na lista da raiz. Nada mais muda ali: continua proibido documento paralelo de estado ou processo (`CLAUDE.md`).

2. **Uma cópia só.** O `/setup-maquina --mapa` lê o `README.md`; o script de diagnóstico confere a lista de cobertura dele. `references/mapa-do-repo.md` deixa de existir. Um guia de organização em outro arquivo (`GUIA-DE-ORGANIZACAO.md`, `docs/ESTRUTURA.md`) é regressão: dois mapas, um envelhece.

3. **O README abre com "Primeiro dia".** Clonar (ou atualizar o clone), rodar `/setup-maquina`, abrir `/ask-pedro`. O passo a passo humano continua em `docs/onboarding/`; o README aponta, não repete.

4. **O README diz onde as chaves de produção moram e quem mexe.** Só no Coolify, por serviço, com a lista em `docs/spec/deploy/project.json` e a conferência pelo `/deploy setup`. Na máquina de quem desenvolve ficam só os tokens do Coolify e três valores fictícios para o snapshot importar o app. O `/setup-maquina` deixa de comparar o `.env` local com o `.env.example`: chave a mais ou a menos no local não muda o pipeline.

## Consequências

- O `/setup-maquina` passa a acusar clone com a `main` atrás da `origin/main`, com o `git pull --ff-only` como conserto. O script só diagnostica; quem puxa é a skill, com confirmação.
- Pasta nova no repo entra no `README.md` no mesmo commit; o script avisa quando falta.
- O ADR 0044 continua valendo em tudo o mais.
