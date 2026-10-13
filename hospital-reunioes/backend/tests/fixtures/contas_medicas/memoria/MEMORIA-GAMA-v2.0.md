---
operadora: GAMA
nome: Gama Saúde
versao_memoria: '2.0'
data: '2026-10-11'
situacao: PARCIAL
diaria:
  hora_vencimento: '10:00'
  sempre_integral: true
tetos_por_dia:
  luva_procedimento:
    codigo: '70802726'
    cti: 60
    enfermaria: 20
transicao:
  prescrito_vale_como_checado: true
  se_necessario_doses_por_dia_sem_registro: 1
---

# MEMÓRIA DA OPERADORA: Gama Saúde

## 1. PRINCÍPIOS

| ID | Regra | Tipo | Origem | Status | Data | Modelo |
|---|---|---|---|---|---|---|
| GAMA-PRI-01 | Identificar sempre pelo número do atendimento, nunca pelo número da conta. | OPERACIONAL | PRÁTICA | VIGENTE | 23/09/2026 | HSM-PRI-01 |
| GAMA-PRI-02 | Escopo: itens e divergência de valor \| sem prazo nem elegibilidade. | OPERACIONAL | PRÁTICA | PENDENTE |  |  |

## 3. DIÁRIAS

| ID | Regra | Tipo | Origem | Status | Data | Modelo |
|---|---|---|---|---|---|---|
| GAMA-DIA-01 | A diária vence às 10h e é sempre integral. | CONTRATUAL | CONTRATO | VIGENTE | 06/10/2026 |  |

## 8. QUANTIDADES E INSUMOS POR TEMPO

| ID | Regra | Tipo | Origem | Status | Data | Modelo |
|---|---|---|---|---|---|---|
| GAMA-INS-01 | Gatilho (terapia registrada): ventilação mecânica<br>Insumo: filtro HME<br>Quantidade: 1 a cada 24 h |  | PROTOCOLO | PENDENTE |  |  |
