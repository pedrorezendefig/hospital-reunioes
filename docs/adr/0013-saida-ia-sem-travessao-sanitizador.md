---
status: accepted
---

# Saída da IA sem travessão: sanitizador determinístico + convenção nos prompts

O travessão (`—`) é marca de texto gerado por IA e foi banido de tudo que o produto exibe ou gera (Atas, POPs, emails). O travessão que aparece dentro desses documentos não está no código estático: nasce do texto que o LLM escreve. Limpar só template e string de UI não resolve o miolo do documento gerado.

A decisão: defesa em duas camadas. (1) Os prompts de sistema (`extracao_ata.md`, `chat_ata_guiada_system.md`, `chat_elaboracao_pop_system.md` e afins) passam a instruir o modelo a nunca usar travessão. (2) Um sanitizador determinístico processa a saída da IA antes de virar Ata/POP/email: troca `—` e `–` por vírgula, e por hífen quando está entre dígitos. O prompt reduz na origem; o sanitizador garante no destino.

## Por que é surpreendente

Um dev vai encontrar uma função que reescreve a saída do LLM e pode achar que é frescura ou removê-la. Sem este registro não fica claro que é uma garantia de produto (o dono não quer ver travessão em lugar nenhum) e que o prompt sozinho não basta, porque o modelo escorrega.

## Alternativas descartadas

- **Só instruir no prompt**: mais simples, mas LLM não é determinístico; um travessão vaza pro PDF de vez em quando, e o dono quer garantia, não probabilidade.
- **Só sanitizar, sem tocar no prompt**: funciona, mas deixa o modelo gerando travessão que depois é mascarado; instruir também melhora o texto na origem.
- **Sanitizar genérico demais** (remover tudo ou trocar tudo por hífen): erra em casos de número e empobrece a pontuação; a regra vírgula + hífen-entre-dígitos cobre o uso real em português.

## Consequências

- Passa a existir uma função de sanitização de texto de IA no pipeline de geração (Ata, Ata Guiada, POP, email), com teste.
- A convenção "sem travessão" vive nos prompts e no `CLAUDE.md` (global do dono e, se preciso, do projeto), além de um lint no CI para o código estático.
- Mudar a política (por exemplo, voltar a permitir travessão) exige mexer em prompt, sanitizador e lint juntos.
