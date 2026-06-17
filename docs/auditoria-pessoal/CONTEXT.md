# Auditoria de Pessoal

Audita mensalmente o que o hospital paga contra o que o ponto registra: ingestão do **Espelho** (RH iD) e da **Folha** (Domínio) de cada **Competência** → **Conciliação** → **Achados** com evidência, monitorados mês a mês. Este arquivo é o glossário do contexto — não confundir termos daqui com os de [Reuniões](../../CONTEXT.md) ou [POPs](../pops/CONTEXT.md).

## Pessoas e papéis

**Auditor**:
Quem acessa o contexto e responde pelo ciclo mensal: sobe os documentos, revisa Achados, justifica ou confirma. Acesso concedido explicitamente, um a um — hoje, só o diretor. Nenhum papel de Reuniões ou POPs herda esse acesso.
_Evitar_: admin de RH, gestor, auditor externo.

**Funcionário**:
Pessoa do quadro (celetista ou estagiário) presente na Folha e/ou no Espelho. É a identidade canônica do contexto, unindo as duas matrículas de origem (RH iD e Domínio) pelo **Vínculo**. População própria — **não** é o Colaborador das Reuniões e não vive no cadastro de pessoas do app.
_Evitar_: colaborador (termo de Reuniões), empregado, servidor, pessoa.

## Documentos-fonte

**Competência**:
O mês de referência da auditoria (ex.: 05/2026). Cada Competência recebe um Espelho e uma Folha, e é a unidade de processamento, comparação e retenção.
_Evitar_: mês, período, fechamento.

**Espelho**:
O relatório mensal do ponto eletrônico (RH iD): marcações diárias de cada Funcionário, jornada realizada, tratamentos sobre os dados originais e horários contratuais. Contém marcações reais e fabricadas (ver **Batida Automática**).
_Evitar_: folha de ponto (colide com Folha), cartão de ponto, extrato de ponto.

**Folha**:
O relatório mensal de pagamento (Domínio/Thomson Reuters): as **Rubricas** pagas e descontadas por Funcionário, com bases e líquido. É a versão definitiva da Competência.
_Evitar_: folha de ponto, contracheque (é o recorte individual do Funcionário), holerite.

**Rubrica**:
Cada linha de provento ou desconto da Folha — código, descrição, referência (horas/quantidade) e valor. Ex.: 150 = horas extras 50%, 219 = atrasos.
_Evitar_: verba, evento, item da folha.

**Batida Automática**:
Marcação que o sistema de ponto pré-assinala em vez de registrada pelo Funcionário — hoje, a quase totalidade dos intervalos. Sinal de que o dado de origem é fabricado, não observado; insumo central da reparametrização do ponto.
_Evitar_: batida fantasma, marcação automática.

## Auditoria

**Vínculo**:
O casamento confirmado entre um Funcionário e suas matrículas nos dois sistemas de origem. Confirmado uma única vez (automaticamente ou pelo Auditor, quando ambíguo), vale para todas as Competências seguintes. Análogo à Resolução (Reuniões), mas é outro conceito em outro contexto.
_Evitar_: resolução, match, merge, de-para.

**Conciliação**:
O cruzamento de horas e valores entre Espelho e Folha de uma Competência, nas duas direções: o que foi pago sem lastro no ponto **e** o que foi trabalhado sem pagamento.
_Evitar_: cruzamento, batimento, reconciliação.

**Regra**:
Uma verificação parametrizada do catálogo de auditoria (ex.: horas extras acima do teto, interjornada mínima, atraso batido e não descontado). Tem **Parâmetros** e severidade.
_Evitar_: validação, check, alerta.

**Parâmetro**:
Valor calibrável de uma Regra — tolerâncias, tetos, classificação das escalas, cargos isentos de ponto. Nasce com os padrões da CLT e é calibrado em sessão com o Auditor sobre dados reais.
_Evitar_: configuração, setting.

**Achado**:
O resultado de uma Regra sobre um Funcionário numa Competência: evidência (apontando o trecho do documento-fonte), severidade e valor estimado. Estados: `NOVO → JUSTIFICADO | CONFIRMADO`. JUSTIFICADO carrega a nota do Auditor; CONFIRMADO indica que procede — a tratativa acontece fora do sistema.
_Evitar_: ocorrência (colide com OCORR do Espelho), apontamento (em RH significa marcação de ponto), alerta, finding.

**Reincidência**:
O elo entre Achados da mesma Regra e mesmo Funcionário em Competências consecutivas ("3º mês seguido"). É o que transforma o relatório mensal em monitoramento.
_Evitar_: repetição, recorrência.

**Sumário Executivo**:
A leitura do mês gerada por IA sobre os Achados da Competência — priorizada por severidade × valor, em linguagem de gestão, com a Reincidência em destaque.
_Evitar_: relatório de IA, resumo automático.

## Diálogo de exemplo

> **Dev:** O diretor mandou "a folha de ponto de maio" — subo onde?
> **Auditor:** Cuidado com o termo: o arquivo do RH iD é o **Espelho**; **Folha** é a do Domínio, com as Rubricas. A Competência é 05/2026 — o sistema reconhece cada arquivo pelo conteúdo.
> **Dev:** O RH garante que os descontos de atraso estão corretos.
> **Auditor:** A **Conciliação** responde: a Regra de atrasos compara o Espelho com a Rubrica 219, minuto a minuto. E atraso batido que **não** foi descontado também vira Achado — leniência é achado, não favor.
> **Dev:** E quando um Achado tem explicação legítima?
> **Auditor:** Marco **JUSTIFICADO** com a nota — "plantão extra autorizado no surto da emergência". Se a mesma Regra pegar o mesmo Funcionário na Competência seguinte, o Achado novo nasce linkado: **Reincidência** à vista.
> **Dev:** A Maria do Espelho não casou com ninguém da Folha.
> **Auditor:** Ela casou no civil e o Domínio tem o nome novo. Confirmo o **Vínculo** uma vez e as próximas Competências casam sozinhas.
