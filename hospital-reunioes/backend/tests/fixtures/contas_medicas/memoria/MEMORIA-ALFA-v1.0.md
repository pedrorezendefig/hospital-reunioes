---
# Memória sintética para os testes da carga da operadora (issue #1119).
# Formato do MODELO-MEMORIA-OPERADORA.md do diretor; a operadora não existe.
operadora: ALFA
nome: Alfa Saúde
versao_memoria: "1.0"
data: 2026-10-01
origem: "Fixture sintética, sem contrato real"
situacao: PARCIAL            # PRONTA | PARCIAL | SEM_MEMORIA

contrato:
  assinatura: 2015-10-01
  ultimo_aditivo: { numero: 12, inicio_vigencia: 2026-05-01 }
  aviso_antecedencia_dias: 60

colunas_de_preco:
  padrao: COMUM
  CARIOCA:
    - Alfa Max Qc
    - Alfa Intermediário Qp

diaria:
  hora_vencimento: "10:00"
  limite_madrugada: "05:00"
  sempre_integral: true
  diaria_extra_na_origem_apos_vencimento: [TRANSFERENCIA_DE_SETOR, OBITO]

opme:                        # chave que o código ainda não lê
  fornecida_por: OPERADORA
  negociacao: "direta entre o fornecedor e a operadora"
---

# MEMÓRIA DA OPERADORA, ALFA SAÚDE

Arquivo sintético. Não contém dado de paciente nem número de atendimento.

## 1. PRINCÍPIOS

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| ALFA-PRI-01 | Identificar sempre pelo número do atendimento, nunca pelo número da conta. | OPERACIONAL | PRÁTICA | VIGENTE | 23/09/2026 |
| ALFA-PRI-02 | Escopo: itens e divergência de valor. Não analisar prazo nem elegibilidade. | OPERACIONAL | PRÁTICA | VIGENTE | 23/09/2026 |
| ALFA-PRI-03 | Edição do Brasíndice usada pela operadora. | CONTRATUAL | CONTRATO | PENDENTE | |

## 3. DIÁRIAS

Os parâmetros numéricos estão no cabeçalho (`diaria`).

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| ALFA-DIA-01 | A diária começa em qualquer horário, vence às 10h e é sempre integral. | CONTRATUAL | PRÁTICA | VIGENTE | 06/10/2026 |
| ALFA-DIA-02 | Transferência de setor antes das 10h: gera ou não diária extra no setor de origem. | CONTRATUAL | PRÁTICA | PENDENTE | |
