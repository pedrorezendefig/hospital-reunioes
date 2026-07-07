---
status: accepted
---

# Observabilidade de custo de IA: registro por Chamada, custo real do OpenRouter, só metadados, acesso restrito

O OpenRouter é o gateway único de toda a IA do sistema (Reuniões, POPs e, quando plugada, Auditoria de Pessoal compartilham o mesmo Pipeline). Hoje a resposta de cada chamada traz tokens e custo, mas o código descarta tudo menos o texto. O dono (Engenheiro de IA) quer controlar o gasto de crédito: quanto custou cada ação, quem disparou, em que feature, com qual modelo, e onde o gasto se concentra. Nasce a área **Controle** em `/admin`, com a subaba **Custos**.

A decisão tem seis partes:

1. **Grão por Chamada de IA, em tabela nova e dedicada.** Uma linha por chamada LLM (não por Operação de negócio, não no `audit_log`). Operação e totais são agregação por cima. É o único grão em que o custo existe de fato e o único que permite ver qual etapa ou qual mensagem de chat pesou.
2. **Custo real do OpenRouter, em dólar, capturado junto na resposta** (usage incluído no corpo, sem segunda chamada de rede). Não se estima por tabela de preços. Exceção única: a transcrição de voz usa o endpoint de áudio, cobrado por duração; quando o custo real não vem pronto, a linha é estimada e marcada como `estimado`.
3. **Só metadados, zero conteúdo.** Nunca se persiste texto de prompt ou resposta, apenas números e referências (quando, responsável, contexto, feature, modelo, tokens, custo, latência, status, id da Reunião ou POP). Honra o ADR 0010 e protege o conteúdo sensível de Atas e POPs.
4. **Responsável é quem disparou** a ação (o usuário autenticado no request), não o dono do artefato, que fica derivável da referência.
5. **Instrumentação no cliente central** (`ai_processor`), **best-effort**: se o registro falhar, a geração da Ata ou do POP segue normal. Telemetria nunca derruba a feature.
6. **Acesso fixo a um único operador** (o Engenheiro de IA), configurado por variável de ambiente no Coolify, com `is_super_admin` como piso. É deliberadamente mais estreito que o conjunto de Super admin.

## Por que é surpreendente

- Um dev vai encontrar um gate que libera a aba para um único email e presumir gambiarra. É intencional: "Super admin" no domínio significa "permissões irrestritas", então restringir custo financeiro a um operador exige um corte explícito, mais estreito que super admin, fora da tela de concessão de perfis.
- Vai ver a tabela sem nenhum trecho de prompt e achar que faltou salvar. É privacidade deliberada (ADR 0010, mais o conteúdo sensível do hospital); o painel de custo não precisa do conteúdo.
- Vai perguntar por que capturar custo no app se o OpenRouter tem dashboard próprio. Porque o OpenRouter não sabe qual usuário, qual Reunião nem qual feature; o cruzamento por essas dimensões é o valor.

## Alternativas descartadas

- **Estimar por tabela de preços local**: divergiria do valor cobrado e exigiria manter preços à mão; o OpenRouter já devolve o real de graça.
- **Grão por Operação**: leitura direta mais simples, mas perde qual etapa custou e força definir quando uma sessão de chat "fecha".
- **Guardar amostra do prompt para debug**: ajudaria a otimizar, mas reintroduz dado sensível na tabela mais quente e no painel.
- **Reusar o `audit_log`**: schema e volume incompatíveis (telemetria de alta frequência com tokens e custo, não ação administrativa pontual).
- **Expor a todo Super admin**: são 6, incluindo diretoras médicas que não gerenciam gasto de IA.

## Consequências

- Nova migration com a tabela de uso de IA, RLS default-deny e policy de leitura restrita; instrumentação no `ai_processor`; escrita best-effort.
- Painel em `/admin` (Controle > Custos) com duas visões, Visão geral e Interações, sobre Recharts (já instalado).
- O painel soma o que foi instrumentado; o saldo do OpenRouter continua a fonte final para reconciliação. Tráfego de mock (dev) não entra na conta.
- Mudar quem enxerga a aba é editar a env var no Coolify e reiniciar, sem deploy de código.
- Retenção e expurgo ficam a definir se o volume crescer; hoje o volume é baixo.
