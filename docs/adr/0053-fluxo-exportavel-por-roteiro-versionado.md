---
status: accepted
---

# O fluxo de trabalho é exportável por um roteiro versionado no repositório, não por prompt solto

O fluxo deste repositório (painel de 7 abas, skills do pipeline, labels, CIs de higiene, contrato de deploy) passou a ser pedido por gente de fora, começando por um parceiro que está começando a programar e quer o mesmo sistema num projeto de stack diferente. A primeira ideia foi "um prompt grande que recria tudo". Este ADR fixa o outro caminho.

## Decisões

1. **A instalação é um roteiro versionado em `tools/instalar-fluxo/`**, não um prompt que circula por mensagem. O prompt que a pessoa cola tem três linhas: clonar este repositório, ler o roteiro, seguir. A inteligência mora no `ROTEIRO.md`, o inventário no `MANIFESTO.md`.

2. **Copia da árvore viva, não recria por descrição.** O painel tem 3.400 linhas e um design system de um bloco `:root`. Recriar por descrição nunca sai igual. O roteiro copia o que é neutro byte a byte, adapta o que cita o Hospital, e só gera do zero o que depende da stack (`/deploy`, `/snapshot`, `/atualizar-app`, `ci.yml`). O manifesto aponta para os arquivos deste repositório; nada é duplicado dentro de `tools/instalar-fluxo/`.

3. **O instalador é um agente exploratório com entrevista.** Antes de perguntar, lê a base do destino e monta uma ficha. Depois entrevista uma pergunta por vez, duas opções, recomendação derivada da ficha na frente. Fato se acha no código; decisão se pergunta.

4. **O contrato que não pode quebrar** é o que o painel lê: os três JSONs de `docs/spec/deploy/`, os sete arquivos de `docs/spec/snapshots/` no formato que `areas.py` e `diagramas.py` esperam, `CONTEXT.md`, `docs/adr/` com frontmatter de `status`, e as labels canônicas. As skills geradas para outra stack podem mudar por dentro, mas escrevem nesse contrato.

5. **As regras vão fechadas.** Idioma pt-BR, zero travessão, merge é decisão humana, estado vive nas Issues e nos JSONs, ADR só `accepted`, os três workflows de CI. Só o nome do router muda (`/ask-pedro` vira `/ask-<nome>`). Quem quiser mudar uma regra faz por ADR no próprio repositório, como aqui.

6. **O roteiro termina com o fluxo em uso, não só instalado.** PR aberto (o merge é do humano) e uma issue `ready-for-human` na fila. O primeiro merge e a aba Pendências ensinam o gate humano e a fila sem ninguém explicar.

7. **Fica de fora o que é do Hospital e não é método:** `/divulgar`, `docs/manual/`, `docs/comunicacao/`, `docs/pops/`, as ADRs de domínio. As ADRs que explicam o fluxo (0013, 0020, 0022, 0025, 0027, 0028, 0043, 0044) viram resumo de um parágrafo cada na ADR 0001 do destino, com link para o arquivo daqui.

## Consequências

- Quem cria, renomeia ou apaga skill do pipeline atualiza o `MANIFESTO.md` no mesmo commit, junto com o `/ask-pedro`.
- O roteiro se prova num repositório de brinquedo: painel de pé com as 7 abas, CI verde no PR, issue na aba Pendências. Sem isso, o roteiro está quebrado.
- A regra "toda pasta de nível 1 e 2 aparece no `README.md`" vale para `tools/instalar-fluxo/`.
- O repositório precisa estar acessível a quem instala (público, ou colaborador). O roteiro lê de um clone local, então acesso de leitura basta.

## Alternativas descartadas

- **Prompt auto-suficiente que recria tudo.** Portátil por WhatsApp, mas cada cópia envelhece, ninguém vê a versão nova, e o design nunca sai idêntico.
- **Instalar sem `/deploy`, `/snapshot` e `/atualizar-app`.** Mais rápido, mas o `/ship` para no merge e as abas Produção e Mapa ficam vazias: meio framework.
- **Perguntar regra por regra na entrevista.** Cada "não" quebra um pedaço do CI ou do painel, e quem está começando aceita tudo mesmo.
