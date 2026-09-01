---
status: accepted
amends: 0039
---

> Revoga a regra do glossário "todo email que sai da Ouvidoria leva só texto escrito pela Ouvidoria" (verbete Extrato para o setor) e **emenda a decisão 2 do ADR 0039**: `resumo` e `relato_integral` entram na lista fechada `_CAMPOS_DO_EMAIL`, por decisão explícita da Diretoria (RN-78), exatamente pelo mecanismo que aquela decisão exige. As demais decisões do 0039 seguem intactas.

# O acionamento leva resumo, relato integral e nota da ouvidoria

Até aqui, o responsável de setor lia apenas o Extrato para o setor: o texto que o ouvidor escreve com as próprias palavras na validação. A regra existia para proteger a palavra do manifestante (nome, leito, detalhes) de viajar por email, superfície que encaminha e vaza.

O diagnóstico da Diretoria Executiva de 31/08/2026 (RN-78, RN-60) determinou o contrário, com fundamento operacional: quem lê só a interpretação da Ouvidoria responde à interpretação, não ao paciente. O resumo permite decidir em segundos se o caso é da área; o relato integral é o que permite responder ao manifestante; a nota separada evita que a área responda ao intermediário. A Diretoria conhece o risco do email e o aceitou; a decisão foi seguir a RN-78 integralmente.

## Decisões

1. **Três blocos, nos dois lugares.** O email de acionamento e a tela do responsável (`/ouvidoria-setor/{token}`) apresentam, nesta ordem e visualmente separados: RESUMO, RELATO INTEGRAL e NOTA DA OUVIDORIA (o Extrato para o setor). Os blocos nunca são fundidos nem formatados iguais (RN-60).

2. **O extrato continua obrigatório.** A validação segue recusada sem ele. O que muda é a companhia: ele deixa de ser o único conteúdo.

3. **Sigilo reforçado é a exceção (RN-79).** Caso sigiloso não leva identificação do manifestante em email nem na tela do token, e o relato integral é substituído pelo extrato. Vale nos dois lugares, sem exceção.

4. **O reenvio manda os mesmos três blocos** gravados no caso, para provar o que a área recebeu.

## Consequências

- O relato do manifestante, em caso não sigiloso, passa a viajar por email, e email do sistema é entregue por processador externo com infraestrutura fora do Brasil (ADR 0039). Risco conhecido e aceito pela Diretoria; a mitigação permanente é o sigilo reforçado subir sempre que o tipo ou o ouvidor pedirem, e o aviso de privacidade do hospital (que o 0039 alimenta) deve refletir a mudança.
- O verbete Extrato para o setor do CONTEXT.md foi reescrito nesta data.
- A tela do responsável é reorganizada na ordem da RN-59, com o relato integral aberto por padrão.
