---
status: accepted
supersedes: 0018
amends: 0016
---

# Rollback da Natureza: Elaboração única ancorada no Material anexado

O ADR 0018 especializou a Elaboração de POP por Natureza do Setor (assistencial, administrativa, de apoio): coluna em `pops_setores`, inferência pelo nome no cadastro, e system prompt composto por blocos (persona da Natureza + índice + refino + núcleo). As quatro fatias foram entregues em produção (v0.35.0 a v0.38.0, PRD #167).

O uso real mostrou que a arquitetura resolve um problema menor que o verdadeiro. Em 99% dos casos o Elaborador anexa um Material de referência com o modelo do POP, e o que decide a qualidade do resultado é a fidelidade a esse modelo, não a persona da Natureza. Enquanto isso, o campo Natureza no cadastro de Setor virou atrito sem retorno: mais uma decisão para quem mantém Setores, sustentando um mecanismo cuja contribuição o documento anexado atropela.

A decisão reverte o mecanismo e reancora o prompt:

1. **A Natureza deixa de existir como atributo do Setor.** Sai a coluna, a inferência pelo nome, o endpoint de sugestão e o campo no cadastro. Nenhum usuário classifica nada.
2. **O system prompt volta a ser único, com curadoria compacta.** O corpo de normas curado nas fatias #171/#172 (trabalhista/eSocial/faturamento; sanitária/biossegurança/ABNT) não é descartado: entra resumido no prompt único como referência das três áreas, que a IA evoca conforme o caso.
3. **O Setor é interpretado pela IA na requisição, de forma rasa.** O nome do Setor já viaja no contexto; o system prompt orienta a IA a inferir dele a área e o corpo de normas pertinente. Interpretação leve, sem classificação persistida e sem código de roteamento.
4. **A âncora é o Material anexado.** A estrutura do POP obedece fielmente ao modelo anexado (ordem, títulos, conteúdo), reforçando o ADR 0016. Sem Material com modelo, vale o template institucional como ponto de partida.
5. **O Fluxograma é a única exceção à fidelidade.** A IA sempre produz a seção de Fluxograma (ADR 0017), mesmo quando o modelo anexado não traz uma. É o único ponto em que o app melhora o modelo; isso emenda o "nenhuma seção é forçada" do ADR 0016.

## Por que é surpreendente

Um futuro leitor verá quatro fatias entregues e removidas semanas depois. O 0018 descartou o "agente único geral melhorado" por diluir a persona; este ADR o adota de olhos abertos porque o dado novo inverte o peso: com o modelo anexado dominando a estrutura e o conteúdo, a persona especializada contribui pouco, e o custo dela (campo no cadastro, coluna, heurística de inferência, quatro arquivos de prompt) passou a ser o lado caro da balança. O viés assistencial que motivou o 0018 é mitigado agora pela curadoria compacta das três áreas dentro do prompt único, algo que o prompt original de antes do 0018 não tinha.

## Alternativas descartadas

- **Manter a coluna dormente e esconder só a UI**: economiza a migration, mas deixa uma classificação invisível influenciando prompts, exatamente a opacidade que o 0018 quis evitar. Reverter é reverter.
- **Manter a composição por Natureza com seleção 100% automática**: mantém quatro prompts para sincronizar e a heurística de inferência para manter, pagando o custo de manutenção por um ganho que o Material anexado torna marginal.
- **Descartar também a curadoria normativa** (rollback seco): joga fora conteúdo curado e barato de manter em forma compacta; a referência resumida é a rede contra o viés assistencial voltar.

## Consequências

- Migration de drop da coluna `natureza` em `pops_setores`; a 054 (backfill), nunca aplicada em produção, sai do repositório sem ser executada.
- Removem-se `services/natureza.py`, o endpoint `GET /pops/setores/sugerir-natureza`, os schemas de Natureza, o select e a coluna no `SetoresManager`, e a composição em `montar_system_elaboracao`.
- Os quatro arquivos de prompt da composição colapsam em um `chat_elaboracao_pop_system.md` único, que ganha: referência normativa compacta das três áreas, instrução de interpretar o Setor pelo nome, fidelidade reforçada ao modelo anexado e Fluxograma obrigatório.
- O ADR 0018 passa a superseded; o ADR 0016 fica emendado no ponto do Fluxograma; o verbete Natureza sai do `docs/pops/CONTEXT.md`.
