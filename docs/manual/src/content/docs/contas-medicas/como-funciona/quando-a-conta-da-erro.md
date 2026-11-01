---
title: Quando a conta dá erro
description: O que cada Código do erro quer dizer, quem resolve e o que o Copiar para a TI leva.
prd: [1335]
draft: true
busca: [falha, deu erro, travou, código de erro, não analisou, tente de novo]
sidebar:
  order: 34
---

## O que o cartão mostra

A conta que a análise não consegue terminar fica em **Erro**. No cartão dela,
em **Meus envios**, aparecem a frase com o motivo, o **Código** e, em
vermelho, o quadrado do arquivo em que a análise parou.

O botão do cartão diz o que fazer:

- **Analisar de novo**: o problema não estava no PDF. A conta volta para a
  análise com os arquivos que já estão no sistema, sem anexar nada.
- **Enviar de novo**: o problema está no PDF, ou ele já passou dos 7 dias e
  saiu do sistema. Exporte de novo pelo MV e envie.

Nada se repete sozinho: a conta fica em **Erro** até alguém clicar.

## Os códigos

O começo do código diz onde está o problema: CM-ARQ no PDF, CM-CFG numa
configuração da gestão, CM-IA na IA que lê o prontuário e CM-APP num defeito
do app. Onde a frase traz N, o cartão mostra o número lido, e onde traz
[etapa], o passo em que a análise parou (a leitura do prontuário, por
exemplo).

| Código | Frase no cartão | Causa | Quem resolve |
| --- | --- | --- | --- |
| `CM-ARQ-SEM-TEXTO` | `Este PDF não tem texto. Exporte de novo pelo MV` | O PDF é só imagem, sem texto para ler. | Quem enviou, com **Enviar de novo**. |
| `CM-ARQ-ILEGIVEL` | `Não consegui ler o PDF. Confira se ele abre no computador e envie de novo.` | O arquivo está corrompido ou não é um PDF que abre. | Quem enviou, com **Enviar de novo**. |
| `CM-ARQ-GRANDE` | `O PDF tem N páginas e é grande demais para ler de uma vez.` | O PDF passa do tamanho que o sistema lê. | Quem enviou confere se exportou o arquivo certo e usa **Enviar de novo**. Se repetir, a TI. |
| `CM-ARQ-SOMA` | `Não consegui ler a conta inteira: os itens lidos somam R$ N e o total da conta é R$ N.` | Os itens lidos não fecham com o total. A frase também pode citar o item e a página que não batem, ou dizer que o PDF não traz o total. | Quem enviou exporta a conta de novo pelo MV e usa **Enviar de novo**. |
| `CM-ARQ-CABECALHO` | `Não achei o atendimento e o plano no cabeçalho da conta.` | O cabeçalho da conta veio cortado ou fora do modelo do MV. | Quem enviou, com **Enviar de novo**. |
| `CM-ARQ-INCOMPLETO` | `Prontuário com arquivo incompleto: o rodapé indica N páginas e vieram N.` | Faltam páginas no prontuário. | Quem enviou exporta o prontuário completo e usa **Enviar de novo**. |
| `CM-ARQ-SEM-PRONTUARIO` | `O prontuário deste atendimento não está no sistema. Envie o prontuário de novo.` | O prontuário do atendimento não chegou ou já saiu do sistema. | Quem enviou, mandando o prontuário de novo. |
| `CM-ARQ-VENCIDO` | `O PDF já passou dos 7 dias e saiu do sistema.` | O sistema guarda os PDFs por 7 dias. | Quem enviou, com **Enviar de novo**. |
| `CM-CFG-MEMORIA` | `A operadora N está sem memória carregada. A gestão carrega em Operadoras.` | A operadora da conta ainda não tem memória. | A gestão carrega a memória em **Operadoras**, e depois quem enviou clica em **Analisar de novo**. |
| `CM-IA-CHAVE` | `A chave da IA não está configurada.` | O acesso do app à IA não está configurado. | A TI. Depois, **Analisar de novo**. |
| `CM-IA-CREDITO` | `A IA está sem crédito. Avise o Pedro.` | O crédito da IA acabou. | A TI. Depois, **Analisar de novo**. |
| `CM-IA-MODELO` | `O modelo da IA não foi encontrado.` | O app pediu uma versão da IA que não existe mais. | A TI. Depois, **Analisar de novo**. |
| `CM-IA-FORA-DO-AR` | `A IA está fora do ar ou sobrecarregada agora.` | A IA não respondeu nas três tentativas. | Quem enviou, com **Analisar de novo** mais tarde. |
| `CM-IA-TAMANHO` | `O prontuário é maior do que a IA aceita de uma vez.` | O prontuário passa do tamanho que a IA lê. Analisar de novo não resolve. | A TI. |
| `CM-IA-FORMATO` | `A resposta da IA veio fora do formato combinado.` | A IA respondeu, mas a resposta não pôde ser lida. | Quem enviou, com **Analisar de novo**. Se repetir, a TI. |
| `CM-IA-ANTIGO` | `Tente de novo em alguns minutos` | Erro gravado antes de existirem os códigos, sem a causa. | Quem enviou, com **Analisar de novo**. |
| `CM-APP-DEFEITO` | `A análise parou na [etapa] por um defeito do app.` | Um defeito do app interrompeu a análise. | Quem enviou tenta **Analisar de novo**. Se repetir, a TI. |
| `CM-APP-TENTATIVAS` | `A análise não terminou em três tentativas: o app reiniciou ou travou na [etapa].` | O app reiniciou ou travou três vezes durante a análise. | Quem enviou tenta **Analisar de novo**. Se repetir, a TI. |

## O que vai para a TI

**Ver detalhes** abre uma linha técnica, que é o que a TI usa para achar o
erro. **Copiar para a TI** copia, uma informação por linha:

- o código do erro;
- o número do atendimento e o da conta;
- a data e a hora do erro;
- o detalhe técnico.

Cole na conversa com a TI. Nada do prontuário vai junto: o detalhe só diz em
que etapa e em que parte do app a análise parou.
