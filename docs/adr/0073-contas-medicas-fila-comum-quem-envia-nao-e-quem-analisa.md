---
status: accepted
amends: 0070
---

# Contas médicas: fila comum, e quem envia não é quem analisa

A decisão 10 da ADR 0070, seguindo a spec v1.0 do diretor ("Faturista vê só as próprias contas"), amarrou a conta a quem subiu os PDFs: o envio grava `cm_conta.faturista_id` com o id de quem enviou, e a fila, a abertura do Guia, o "Concluir e abrir a próxima" e a linha de Produção do Painel filtram por ele. No primeiro uso real (29/10/2026) o diretor subiu as contas pelo login da Adriana; no dia seguinte as faturistas, cada uma com o seu login, viram a fila zerada. O modelo de trabalho que ele descreveu é outro: qualquer pessoa sobe a conta (até a secretária), as faturistas vão puxando da fila, e a produtividade conta quem analisou.

A decisão separa os dois papéis:

1. **Fila comum, a conta ganha dono na abertura.** Toda conta com Guia pronto (`A_FAZER`) é livre, qualquer que seja o `faturista_id`. Quem abre o Guia primeiro vira a faturista da conta, no mesmo UPDATE condicional `A_FAZER -> EM_CORRECAO` que já existia; quem perde a corrida recebe 409 e volta para a fila. O "Concluir e abrir a próxima" pega a primeira conta livre na ordem de envio.
2. **`faturista_id` passa a ser só quem analisa.** Nasce nulo no envio. Quem enviou sai de `cm_envio.usuario_id`, pelo `cm_arquivo`. O aviso de envio processado vai para quem enviou; o Retorno da Validação e a Produção do Painel continuam no `faturista_id`.
3. **A faturista vê duas listas:** "Fila" (livres, em ordem de envio) e "Minhas" (as que puxou e não concluiu). A conta que espera arquivo, processa ou deu erro não entra na Fila: fica em "Meus envios" de quem enviou, que é quem tem o PDF que falta. Quem tem "painel completo" vê tudo.
4. **Duas permissões no lugar de uma.** A chave `enviar_corrigir_contas` fica com o rótulo "Analisar contas" e soma-se `enviar_contas`, ligada pela migration para todo perfil que já tinha a antiga. Perfil novo `apoio_faturamento` (nome de tela a confirmar com o diretor), só com "Enviar contas".
5. **Devolver à fila.** A faturista devolve a conta dela em `EM_CORRECAO`, e quem tem "painel completo" devolve a de qualquer uma: volta a `A_FAZER` com `faturista_id` nulo, mantendo marcações e `aberta_em`. Conta em Retorno não se devolve. Na produção conta quem concluiu.

## Por que é surpreendente

Contraria a spec do próprio diretor e a decisão 10 da 0070, escritas antes do primeiro uso. Quem ler o código antigo vai achar que "faturista vê só as dela" é regra de sigilo entre faturistas; não era, era a suposição de que quem sobe é quem analisa.

## Consequências

- A fatia 1 (fila comum, dono na abertura) não tem migration: as contas de ontem, ainda em `A_FAZER` com a Adriana no `faturista_id`, voltam livres sem UPDATE em produção.
- A migration da fatia 2 só acrescenta (chave e perfil novos). O código velho continua funcionando entre a aplicação da migration e a subida.
- O que as faturistas concluírem pelo login da Adriana antes da fatia 1 conta como produção da Adriana, e não dá para separar depois.

## Alternativas descartadas

- **Coordenação distribui a conta antes do trabalho**: põe um ato manual entre o envio e a análise, que o diretor não pediu.
- **Fila sem dono, produção por quem concluiu**: duas faturistas podem trabalhar a mesma conta ao mesmo tempo, e o track record perde o começo da análise.
- **Coluna nova `enviado_por` em `cm_conta`**: migration para guardar o que `cm_envio.usuario_id` já guarda.
- **Renomear a chave para `analisar_contas`**: aplicada a migration antes do código, tira o acesso de todas as faturistas, a indisponibilidade que o diretor quer evitar.
- **Paliativo de ligar "painel completo" para faturista**: libera a fila, mas mostra o Painel inteiro e continua contando tudo para quem enviou.
