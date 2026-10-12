---
# Memória sintética para os testes da carga da operadora (issue #1119).
# Só a seção 8 tem regra; a 10 e a 11 repetem IDs dela e não podem virar regra.
operadora: BETA
nome: Beta Saúde
versao_memoria: "1.0"
data: 2026-10-01
situacao: PARCIAL
---

# MEMÓRIA DA OPERADORA, BETA SAÚDE

## 8. QUANTIDADES E INSUMOS POR TEMPO

**Princípios de quantidade**

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| BETA-INS-00 | A operadora paga equipos, cateteres e conectores por regra de tempo, não pelo número de dispensações. | OPERACIONAL | MANUAL DA OPERADORA | VIGENTE | 23/09/2026 |

**Insumos por gatilho**

| ID | Gatilho (terapia registrada) | Insumo | Código | Quantidade | Origem | Status |
|---|---|---|---|---|---|---|
| BETA-INS-01 | Acesso venoso periférico em uso | Cateter periférico | 70135266 | 1 a cada 96 h, mais trocas justificadas | MANUAL DA OPERADORA | VIGENTE |
| BETA-INS-02 | Monitorização cardíaca | Eletrodos | 70204284 | 5 por instalação; troca diária a validar | MANUAL DA OPERADORA | PENDENTE |

## 10. PENDENTES (RESUMO)

| ID | O que falta decidir | Quem resolve |
|---|---|---|
| BETA-INS-02 | Eletrodos por dia | Diretoria |
| BETA-PRC-09 | Edição do Brasíndice usada pela operadora | Diretoria e gestão de contas médicas |

## 11. HISTÓRICO

| ID | Versão | O que mudou |
|---|---|---|
| BETA-INS-01 | 1.0 | Primeira versão da regra do cateter |
