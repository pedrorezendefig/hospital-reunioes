---
status: accepted
amends: 0070
---

# Contas médicas: o Auditor é uma conversa que só propõe, toda regra passa por prova, e o "Faltou isto" entra no Guia

Decisão do Pedro (07/11/2026, grilling) sobre os áudios do Diretor Executivo depois de usar o módulo. O modelo mental dele é o de um auditor humano que ele treina: ele explica o contrato, entrega os documentos, corrige quando o auditor erra, e o auditor anota na conta o que incluir, tirar e corrigir para a faturista lançar no MV e marcar feito. Ele quer conversar com esse auditor num lugar só, em vez de um botão por coisa, e tem medo de duas coisas: complexidade de uso e o agente "se confundir" com regra demais.

## Contexto

- O módulo já tem quase tudo do auditor: o Guia é a conta anotada, a Linha com Feito, Não procede e Bloqueado é a mesa da faturista. O "Ensinar uma regra nova" já aceita texto livre e devolve proposta com conflitos. A tabela de preço já entra por PDF, XLSX ou CSV com a IA propondo o mapeamento das colunas. A Memória já sai e volta por `.md`.
- O que falta: um lugar único para conversar; um jeito de apontar o que o módulo deixou passar (as faturistas acharam no prontuário a insulina de uma hiperglicemia que o módulo não viu, e não havia onde registrar); e uma forma de saber, antes de valer, o que uma regra nova faz nas contas.
- A fila de Validação passou de 80 itens. Quase 60 vêm dos próprios arquivos do diretor: toda Regra que o `.md` não marca como VIGENTE entra Pendente (18 na ASSIM, 13 na Leve, 28 na Unimed), e cada uma vira um cartão.
- O Passo B recebe a Memória inteira da operadora (100 a 150 Regras, uns 10 mil tokens, em cache). O tamanho não é o risco; Regra duplicada ou contraditória é.
- A decisão 12 da ADR 0070 proibiu a palavra "auditoria" no módulo, a pedido do diretor. Agora ele quer "auditor".

## Decisões

1. **O Auditor é uma conversa que sempre termina em proposta.** O que ele recebe (texto, tabela, contrato) volta como proposta estruturada: Regra nova ou alterada, Tabela de preço, parâmetro da Memória ou card para a Tecnologia, com Confirmar. Nada vale sem o Confirmar. Os envios atuais da tela de Operadoras continuam, como atalhos dentro da conversa.
2. **Duas conversas, cada uma com o seu contexto.** A da Operadora (ensinar Regra, subir tabela e contrato) e a da Conta, aberta do Guia, para explicar um erro. Nada de uma Operadora entra na conversa de outra (decisão 3 da ADR 0070).
3. **A conversa não é memória.** Só o que foi confirmado e virou Regra ou tabela pesa nas análises. A conversa fica guardada como histórico, ligada à versão da Memória que gerou. Descartado: pôr conversas no prompt das análises, que é o caminho para o agente se contradizer com o tempo sem que ninguém veja por quê.
4. **"Faltou isto" no Guia.** Quem vê o Guia aponta, por dia, o item e a página que o módulo não achou. Abre a conversa da Conta; o Auditor explica por que não achou e classifica a origem: regra, leitura (página não lida, OCR, folha digitalizada) ou defeito do código. Regra vira proposta de Regra; leitura e defeito viram issue no GitHub com label `needs-triage`, código da Conta, página, trecho desidentificado, a explicação do Auditor e a mensagem de quem apontou, depois de um Confirmar. A issue nunca leva texto de prontuário além do trecho desidentificado de até 300 caracteres (decisão 8 da ADR 0070; o repositório é público).
5. **Quem ensina, quem aponta.** A conversa da Operadora é de quem tem "Regra contratual e tabelas" (gestão e diretorias), e o que essa pessoa confirma nasce Vigente. O "Faltou isto" é de qualquer um que vê o Guia; a Regra que nasce de faturista ou coordenadora entra Pendente e vai para a Validação.
6. **Regra Pendente só quando alguém de fato precisa decidir.** Regra que a diretoria ou a gestão ensina ou importa nasce Vigente. Pendente fica para a Regra técnica HSM copiada e para a proposta de quem não decide. As Pendentes que já existem se resolvem numa conversa "revisar pendentes" da Operadora, em lote.
7. **Prova antes do Confirmar.** Toda Regra nova ou alterada refaz o Passo B nas 10 últimas Contas concluídas da Operadora (os eventos ficam guardados depois que o PDF é apagado) e mostra o que o Guia teria dito de diferente, sem mexer nessas Contas. Linha marcada Feito que sumiria é destacada. "Não mudaria nada" também aparece, como sinal de que a Regra não pega como se imagina. Descartado: prova com 30 dias, que passa de cem Contas por Regra.
8. **Conflito em vez de teto.** Sem limite de Regras por Operadora; a proposta acusa a Regra existente com que conflita e propõe juntar ou substituir, em vez de empilhar.
9. **Contrato vira Regras.** O contrato subido na conversa da Operadora gera propostas cláusula a cláusula e preenche o "o contrato diz" das Regras que já existem, pelo mesmo trilho de proposta e prova. A extração de datas para o aviso de reajuste continua.
10. **O `.md` continua sendo a rota para trabalhar fora do app.** Exportar e importar ficam como estão; a importação passa a mostrar o que mudou Regra a Regra antes de gravar, para não sobrescrever às cegas o que foi ensinado pela conversa.
11. **XLS antigo entra**, convertido para XLSX no servidor.
12. **Custo sem teto, na tela.** Conversa e prova gravam em `cm_chamada_ia` e entram no custo da semana do Painel. O Painel ganha também o "Faltou isto" por semana e por origem.
13. **"Auditor" volta, só como nome do agente.** Revoga a decisão 12 da ADR 0070: o agente se chama Auditor na tela ("Falar com o auditor"). Guia, Linha, Memória e Validação ficam com esses nomes; rotas e tabelas continuam `cm_`. Sem nome de pessoa.

## Consequências

- O diretor ensina por conversa sem perder o que torna a análise previsível: tudo que pesa está escrito numa Regra que ele lê, prova e desfaz.
- O app passa a medir omissões, não só acertos. É o número que diz se o Auditor melhora entre uma auditoria em papel e a seguinte.
- Prova e conversa somam custo de IA por Regra ensinada (em torno de US$ 1 por prova de 10 Contas, com a Memória em cache).
- A fila de Validação encolhe para o que só a diretoria decide.
- Pede migration (conversa, mensagens, prova, apontamento "Faltou isto"), aplicada no Studio como as outras do módulo.
