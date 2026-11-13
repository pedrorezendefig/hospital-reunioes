# Lente de design

Entra quando o Projeto tem guia de design (`fluxo.py design`) e o PR muda tela. Compare a tela com o guia da `origin/main` (`git show origin/main:<guia>`) e com a referência visual que a issue citar.

1. `design.py subir --pr <PR>`. Saída 1: a linha `design (não rodou: <motivo>)` que ele imprime troca o `design` da linha `Lentes:`, com `Prints: nenhum`; vá ao passo 5. Navegador que falha também é "não rodou".
2. `playwright-cli open <url>` e vá à tela que o PR mudou. Na pasta `prints:`, `resize 1440 900` e `screenshot --filename=<prints>/computador.png`; `resize 390 844` e `celular.png`. Leia os dois e feche com `playwright-cli close`.
3. Um achado por linha num arquivo: `- P<n> · <onde> · <o que, contra o guia ou a referência>`. P0: a tela não deixa fazer a tarefa. P1: confunde ou foge do guia no essencial. P2: incomoda, mas dá para usar. P3: acabamento. Gosto sem guia nem referência não é achado.
4. `design.py achados --pr <PR> <arquivo>`: as linhas P0 e P1 que ele devolve entram no must-fix; a `Polimento:` vai para o veredito.
5. `design.py descer --pr <PR>`, sempre.

Scripts em `.claude/skills/onda-enxuta/scripts/`. Na tela, nada de clique que grava, apaga ou publica.
