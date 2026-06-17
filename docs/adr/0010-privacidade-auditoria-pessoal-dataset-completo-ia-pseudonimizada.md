---
status: accepted
---

# Privacidade da Auditoria de Pessoal: dataset completo persistido, IA pseudonimizada, retenção definida

O contexto Auditoria de Pessoal custodia salário, CPF e situação de saúde (afastamentos) de ~500 funcionários — o dado mais sensível do sistema. A postura de privacidade tem quatro pontos:

1. **Persistimos o dataset estruturado completo** de cada Competência (ponto diário, Rubricas, cadastro, Achados) mais os PDFs originais em storage privado, como cadeia de evidência — em vez de guardar só os Achados ou processar-e-apagar. É o que habilita tendência mês a mês, reprocessar Regras novas sobre meses antigos e drill-down do Achado até a fonte (arquivo e página).
2. **A IA nunca recebe nome nem CPF.** Prompts pseudonimizados por matrícula (+ cargo, setor e números); o frontend re-hidrata matrícula → nome só na exibição. Vale para o Sumário Executivo e para qualquer uso futuro (chat, detecção de anomalias). É contrato de implementação — com teste cobrindo.
3. **Acesso exclusivo do Auditor** (flag explícita; hoje, só o diretor) e dado de RH proibido em logs e mensagens de erro.
4. **Retenção alvo de 26 meses** por Competência (horizonte de prescrição trabalhista; número a confirmar com o jurídico). O ponto é existir política explícita de expurgo — não acumular para sempre.

## Por que é surpreendente

Guardar a folha inteira parece imprudência LGPD — o reflexo seria minimizar (persistir só Achados). Mas auditoria sem fonte não sustenta confronto ("me mostra de onde saiu esse número") e o "monitorar" pedido pelo diretor exige histórico comparável. A minimização foi posta onde não custa capacidade: na superfície de IA (pseudonimização) e na audiência (um Auditor).

## Consequências

- Artefatos derivados (export PDF executivo, sumários) herdam a postura: storage privado, nunca rota pública.
- A retenção exige rotina de expurgo por Competência, não deleção ad hoc.
- Base legal (legítimo interesse / obrigação do empregador) é assunto do jurídico do hospital; o sistema entrega os controles — acesso mínimo, evidência, retenção, pseudonimização.
