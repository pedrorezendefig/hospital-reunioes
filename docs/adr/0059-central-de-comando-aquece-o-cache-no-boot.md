---
status: accepted
amends: 0058
---

# Central de Comando aquece o cache uma vez no boot, só no período padrão

Decisão do dono na triagem da issue #867 (23/set/2026), depois da conferência da #858. Emenda a última consequência da ADR 0058, que dizia que a primeira leitura depois de cada deploy vai à fonte.

## Contexto

- O cache da Central é da memória do processo, vale 1 hora e é zerado a cada deploy do backend (ADR 0058, decisão 2). O backend sobe várias vezes por dia.
- Na conferência de 23/09 (#858), com o cache cheio as telas responderam em 0,1 a 0,6 s. Com ele vazio, a primeira leitura foi à fonte na hora, e a galeria dos Objetivos, que junta Google e Instagram, chegou a 29 s.
- Depois da #858, uma aba aberta renova a memória na hora certa. A espera sobra quase só para a primeira abertura depois de um deploy e para a abertura depois de horas sem ninguém olhando.

## Decisões

1. **Uma rodada de aquecimento por processo, logo depois do boot.** O `lifespan` do backend dispara a rodada, e ela lê cada chave que a primeira abertura de cada tela pede: os dois blocos de fonte da Visão Geral, Dados do Google, Instagram, a galeria dos Objetivos e a lente de cada Objetivo navegável.
2. **Só o período padrão, 28 dias.** A troca para 7 ou 90 dias continua indo à fonte na primeira vez.
3. **Pelas mesmas leituras das rotas, sem forçar.** A chave aquecida é a que a rota lê, e a rodada não vence as telas vizinhas como o Atualizar agora vence. A lista sai dos registros de telas e de Objetivos, então tela nova entra sem regra duplicada.
4. **Numa thread própria, nunca no event loop, e o boot não espera.** O backend é um processo só e atende o app inteiro. Uma leitura síncrona de dezenas de segundos no event loop travaria reuniões, atas, POPs e Ouvidoria, e poderia reprovar o health check do deploy. Uma tela aberta durante a rodada espera a ida que já está no ar, sem abrir outra (uma ida por chave, #858).
5. **Falha não derruba nada.** Falha da fonte, credencial ausente ou defeito numa chave vai para o log, e a rodada segue para a próxima. Sem credencial (CI, localhost sem `.env`), nenhuma ida à rede.
6. **Desligável sem deploy de código.** `CENTRAL_AQUECER_NO_BOOT=false` e um restart desligam a rodada. A suíte de testes roda com ela desligada, para nenhum teste ir ao Google ou ao Instagram.

Rejeitado:

- **Renovar as chaves antes de vencer, o dia todo.** A Central nunca ficaria fria, mas gastaria cota das fontes 24 horas por dia, com ou sem alguém olhando, e ganharia uma tarefa agendada que ela não tem.
- **Não fazer**, aceitando a primeira abertura lenta como a ADR 0058 registrava. O backend sobe várias vezes por dia, e a primeira pessoa a abrir a Central depois de cada deploy esperava dezenas de segundos.
- **Aquecer também 7 e 90 dias.** Triplicaria as idas por deploy para períodos pouco abertos.

## Consequências

- O deploy continua zerando o cache, mas o backend aquece o período padrão logo depois de subir. A primeira abertura de cada tela depois do deploy, no período padrão, sai do cache quando a rodada já passou por ela. Continuam indo à fonte: a troca de período, a abertura depois de horas sem ninguém olhando e a abertura que chega antes de a rodada passar pela chave (essa espera a ida no ar, sem abrir outra).
- A Central continua sem tarefa agendada: a rodada é uma por processo, fora do scheduler.
- Cada deploy custa algumas idas ao Google e ao Instagram, uma por chave aquecida, com ou sem alguém abrindo a Central.
- O Ao vivo continua fora do cache e fora da rodada.
- Nada muda no estado: sem banco, sem volume, um processo só.
