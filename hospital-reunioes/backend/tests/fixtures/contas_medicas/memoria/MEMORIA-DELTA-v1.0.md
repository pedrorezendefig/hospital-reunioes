---
# Memória sintética para os testes da regra que nasce Vigente e da prévia da
# importação (issue #1486). A operadora não existe.
operadora: DELTA
nome: Delta Saúde
versao_memoria: "1.0"
situacao: PARCIAL
---

# MEMÓRIA DA OPERADORA, DELTA SAÚDE

Arquivo sintético. Não contém dado de paciente nem número de atendimento.

## 1. PRINCÍPIOS

A DELTA-PRI-03 é a Regra técnica HSM copiada do modelo como PENDENTE.

| ID | Regra | Tipo | Origem | Status | Data | Modelo |
|---|---|---|---|---|---|---|
| DELTA-PRI-01 | Identificar sempre pelo número do atendimento, nunca pelo número da conta. | OPERACIONAL | PRÁTICA | | | |
| DELTA-PRI-02 | Escopo: itens e divergência de valor. | OPERACIONAL | PRÁTICA | VIGENTE | 01/10/2026 | |
| DELTA-PRI-03 | Ampola: integral, mesmo com uso parcial. | OPERACIONAL | REFERÊNCIA | PENDENTE | | HSM-MED-01 |

## 3. DIÁRIAS

Esta tabela não tem a coluna Status.

| ID | Regra | Tipo | Origem |
|---|---|---|---|
| DELTA-DIA-01 | A diária vence às 12h. | CONTRATUAL | CONTRATO |
| DELTA-DIA-02 | Diária de UTI inclui o monitor multiparamétrico. | CONTRATUAL | CONTRATO |
