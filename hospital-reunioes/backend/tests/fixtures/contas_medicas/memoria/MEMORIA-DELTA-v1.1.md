---
# Memória sintética para os testes da prévia da importação (issue #1486).
# Em relação à v1.0: DELTA-PRI-02 muda o texto, DELTA-PRI-03 foi validada,
# DELTA-DIA-02 saiu e DELTA-DIA-03 entrou. A operadora não existe.
operadora: DELTA
nome: Delta Saúde
versao_memoria: "1.1"
situacao: PARCIAL
---

# MEMÓRIA DA OPERADORA, DELTA SAÚDE

Arquivo sintético. Não contém dado de paciente nem número de atendimento.

## 1. PRINCÍPIOS

| ID | Regra | Tipo | Origem | Status | Data | Modelo |
|---|---|---|---|---|---|---|
| DELTA-PRI-01 | Identificar sempre pelo número do atendimento, nunca pelo número da conta. | OPERACIONAL | PRÁTICA | | | |
| DELTA-PRI-02 | Escopo: itens, divergência de valor e pacote. | OPERACIONAL | PRÁTICA | VIGENTE | 01/11/2026 | |
| DELTA-PRI-03 | Ampola: integral, mesmo com uso parcial. | OPERACIONAL | REFERÊNCIA | VIGENTE | 01/11/2026 | HSM-MED-01 |

## 3. DIÁRIAS

| ID | Regra | Tipo | Origem |
|---|---|---|---|
| DELTA-DIA-01 | A diária vence às 12h. | CONTRATUAL | CONTRATO |
| DELTA-DIA-03 | Diária de acompanhante só com autorização prévia. | CONTRATUAL | CONTRATO |
