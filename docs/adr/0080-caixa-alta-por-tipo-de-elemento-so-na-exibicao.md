---
status: accepted
---

# Caixa alta por tipo de elemento, só na exibição

Decisão do Pedro (06/11/2026, grill técnico do PRD do diretor #1428). O diretor pediu títulos, botões e textos curtos em caixa alta em todo o aplicativo, nas telas públicas, nos títulos dos PDFs e dos e-mails e nos títulos que a IA escreve, com o texto digitado pela equipe como foi escrito e tudo numa entrega só.

## Decisões

1. **O limite é o tipo de elemento.** Ficam em Caixa alta: item de menu, título e subtítulo (h1 a h3), botão, aba, nome de campo, cabeçalho de coluna e etiqueta de situação. O resto é Texto corrido (parágrafo, toast, erro, ajuda, placeholder, corpo de diálogo, aviso do sino, conversa e resumo da Tecnologia, menos os subtítulos do resumo). Rejeitado: critério por número de palavras ou por "tem verbo" (cada pessoa julga de um jeito).

2. **Só na exibição, nunca no dado.** Na tela, uma regra `text-transform: uppercase` no `@layer base` do `globals.css`, por elemento, com espaçamento leve. Nos PDFs (ata, POP, relatório, cartaz), `text-transform` nos títulos dos templates do WeasyPrint. Nos e-mails, o filtro `upper` do Jinja só na variável do título. O texto da fonte e do banco continua com maiúscula e minúscula. Rejeitado: reescrever as strings em maiúscula (cerca de 800, sem componente comum) e `upper()` na geração da IA (altera o dado, sem volta).

3. **Texto digitado dentro de elemento em caixa alta leva `normal-case`.** Título ou botão que mostra dado do banco (nome da reunião, título do POP, nome da operadora) desliga a regra no trecho do dado.

4. **Exceções fechadas.** O assunto do e-mail fica normal (spam e leitura da caixa de entrada). Códigos e siglas ficam como estão. No POP com modelo anexado pelo hospital, o título da IA também sai em caixa alta no PDF.

5. **Uma subida só.** Quatro fatias (telas, PDFs, e-mails, lista de conferência) sobem juntas num `fechar_onda.py --prs`, para o aplicativo não ficar com telas misturadas. A conferência é a lista de prints por rota (desktop e 390px), mais um PDF e um e-mail de cada tipo, que vai ao diretor para o aceite por amostra.

## Consequências

- Quem chega encontra `normal-case` espalhado: é o dado digitado protegido. Não "consertar" gravando em maiúscula.
- O Manual saiu do escopo: a decisão 8 do diretor pedia atualizá-lo, mas ele foi aposentado na véspera (ADR 0078). O diretor é avisado na Conversa da Demanda.
- Sem migration e sem lint novo: a regra base cobre o elemento que nasce, e `normal-case` mal posto só o print pega.
