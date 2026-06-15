---
status: accepted
---

# DS Select próprio para seleção única, sem `<select>` nativo

O `<select>` nativo do HTML não deixa estilizar a lista aberta: o sistema operacional a desenha (no macOS, com fundo escuro), fora do Design System. Hoje 15 telas (admin, POPs, reuniões, secretaria, pendências, notas) usam `<select>` nativo e exibem esse menu fora do padrão. O `MultiSelect` que já existe no app fica branco justamente porque desenha a própria lista.

A decisão: criar um componente `Select` de seleção única em `components/ui/`, hand-rolled (React + Tailwind + lucide, o mesmo stack do `MultiSelect`), com o fundo branco do Design System, e substituir todos os `<select>` nativos por ele. Sem adotar lib headless (Radix, Headless UI): o projeto não tem nenhuma dependência de UI além do lucide, e o padrão hand-rolled já existe e é a referência visual.

Contrapartida obrigatória: o `Select` precisa ter acessibilidade de teclado de verdade (setas, Enter, Esc, Home/End, type-ahead, `role="listbox"`/`option`, `aria-activedescendant`), porque o `<select>` nativo que ele substitui já entregava isso de graça. Um clone do `MultiSelect` sem teclado regrediria a navegação.

## Por que é surpreendente

Um dev acostumado a React vai perguntar por que não usamos Radix Select, que entrega a11y completa de fábrica. A resposta é consistência e zero dependência: o app inteiro é hand-rolled sobre Tailwind, e introduzir uma lib headless criaria dois padrões convivendo (o `MultiSelect` hand-rolled e um `Select` de lib). O custo aceito é assumir a a11y de teclado na mão.

## Alternativas descartadas

- **Radix / Headless UI**: a11y de fábrica, mas seria a primeira dependência headless do projeto e um segundo padrão ao lado do `MultiSelect`. Reavaliar se o custo de manter a a11y hand-rolled se mostrar alto.
- **Manter o `<select>` nativo**: impossível deixar branco; a lista aberta é desenhada pelo SO, fora do alcance do CSS.
- **Clonar o `MultiSelect` sem teclado**: rápido de entregar, mas regride a navegação por teclado em relação ao nativo.

## Consequências

- Novo componente `components/ui/Select.tsx`, irmão do `MultiSelect`, passa a ser a única forma de dropdown de seleção única daqui pra frente. O `<select>` nativo fica banido (candidato a regra de lint).
- O `MultiSelect` segue como está; se a duplicação de lógica de listbox incomodar, extrair um primitivo compartilhado vira tarefa de `/improve-codebase-architecture`.
- As 15 telas trocam o `<select>` pelo `Select`; o comportamento de teclado precisa de teste.
