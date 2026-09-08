---
status: accepted
amends: 0034
---

# Apagar manifestação é retenção antecipada, não DELETE

Decisão do Pedro (04/set/2026, grilling a partir do pedido do diretor): a Ouvidoria ganha dois atos sobre o caso encerrado, **arquivar** (esconde da lista, tem volta) e **apagar** (some o relato, não tem volta). O "apagar totalmente" que o diretor pediu **não apaga a linha** da manifestação nem a tira dos números: ele faz hoje, por ato humano, o que a Retenção do ADR 0034 faria em cinco anos.

## Contexto

O ADR 0034 fez a trilha do caso imutável (trigger recusa UPDATE e DELETE em `ouvidoria_movimentos`), amarrou toda tabela filha à manifestação com `ON DELETE RESTRICT` e criou a Retenção: cinco anos depois do encerramento, o Dossiê some e o caso vira estatística. A migration 079 abriu na trilha uma única fresta, zerar `observacao` de caso encerrado há mais de cinco anos, e é por ela que a Retenção passa.

O diretor quer poder apagar reclamações, principalmente encerradas, ou pelo menos esconder da lista. Um DELETE de verdade exigiria derrubar as travas de propósito do 0034 e faria um relatório quinzenal já enviado deixar de bater com o banco.

## Decisões

1. **Apagar = Retenção antecipada.** A `diretoria_executiva` marca o caso encerrado, um por vez, com motivo escrito obrigatório. O mesmo serviço da Retenção varre os mesmos cinco lugares (manifestação, anexos, `observacao` da trilha, texto das tentativas e prorrogações, `detalhe` das notificações). Ficam o protocolo, a trilha, as datas, o tipo, a área, a gravidade e o desfecho. O ato entra na trilha com autor e motivo. Rejeitado: DELETE da linha (abre a porta para sumir com reclamação incômoda e quebra a prestação de contas).

2. **A trava da trilha ganha uma segunda chave.** A guarda de UPDATE (migration 079) passa a aceitar zerar `observacao` também do caso que a Diretoria marcou para apagar, além do caso com cinco anos. DELETE continua barrado sem exceção.

3. **Só a Diretoria apaga; os dois papéis arquivam.** Apagar não volta, então fica com quem responde pelo hospital. O `ouvidor` sozinho não pode sumir com o relato de um caso sobre a própria equipe. Super admin continua de fora (RN-40).

4. **Arquivar é organização da lista, não fato do caso.** Só caso `encerrado` arquiva, por caso ou em lote. Não muda estado, não grava movimento (acenderia novidade), não sai das métricas. A lista nasce sem arquivados e os mostra atrás de um filtro. Caso apagado entra no arquivo sozinho.

5. **Caso apagado não reabre.** Reabrir por reincidência exige o relato para a área trabalhar. Vale para os dois apagados, o da Diretoria e o dos cinco anos. Quem volta abre caso novo. O Dossiê de caso apagado mostra o aviso (quando, quem, motivo) no lugar do relato.

## Consequências

- Hoje nada no app lê `anonimizada_em`, porque nenhum caso tem cinco anos. Com a porta antecipada, o Dossiê, a reabertura e a lista passam a ler o carimbo. Isso conserta de graça o comportamento da Retenção dos cinco anos, que hoje abriria como caso de relato vazio.
- O prazo de cinco anos continua escrito em dois lugares (`ANOS_DE_RETENCAO` e a guarda da migration 079); a segunda chave da trava também fica nos dois.
