---
status: accepted
---

# Dados do atendimento da Ana migram para o app: módulo admin, painel de ouvidoria e API de serviço

Decisão do Pedro (14/ago/2026, grilling conduzido no repo da Ana, ADR-0015 de lá): o Hospital Reuniões vira a casa dos dados que alimentam a **Ana**, a agente de IA de atendimento via WhatsApp do mesmo hospital (produto irmão, repo `~/PedroDev/Ana`). As 5 tabelas que hoje vivem num NocoDB na mesma VPS migram para o Postgres deste app; o app ganha um módulo de edição na área admin, um painel de ouvidoria e uma API de serviço para a Ana; o NocoDB se aposenta.

## Contexto

- A Ana lê 4 tabelas de referência (preços de consultas particulares, exames, estimativas de cirurgias, convênios por especialidade) e escreve 1 tabela operacional (protocolos de ouvidoria) num NocoDB no Coolify desta mesma VPS. O hospital não visita o NocoDB; quem loga todo dia é neste app.
- A API deste app só autentica usuário logado (JWT do Supabase Auth); não existe caminho máquina-a-máquina. As regras de negócio vivem no Python (ADR 0002), então escrita externa direta no banco furaria invariantes.
- As variáveis `ANA_READONLY_*` do `.env` (usuário Postgres read-only provisionado para a Ana, nunca usado por código) ficam obsoletas: o caminho decidido é API, não banco direto.
- Pesquisa em fonte primária (14/ago/2026, docs e código do NocoDB) descartou mantê-lo no meio: webhooks sem retry, escrita externa não dispara webhook, data source externo com sync manual de schema.

## Decisões

1. **Cinco tabelas novas no Postgres**, com as colunas equivalentes às atuais (sem remodelagem nesta passada): consultas particulares, exames, estimativas de cirurgias, convênios por especialidade e protocolos de ouvidoria.
2. **Módulo "Dados do Atendimento" na área admin**: super admins e secretárias editam as tabelas de valores; facilitadores enxergam em leitura. Edição vale imediatamente para a Ana (leitura direta, sem cache).
3. **Painel de ouvidoria**: facilitadores e secretárias veem os protocolos (categoria, setor, resumo, prazo) e mudam o status (aberto/respondido). Invariante herdada: **índice, não dossiê**. Nenhum dado pessoal do manifestante entra neste app; nome, CPF e relato vivem na conversa do Chatwoot da Ana, ligados pelo campo `conversa_id`.
4. **API de serviço `/api/ana/*`**: endpoints de leitura das 4 tabelas de valores, POST de registro de protocolo e GET de consulta de protocolo, autenticados por **API key de serviço** dedicada (header), fora do fluxo JWT. A chave vive no vault da plataforma da Ana; escopo restrito a esses endpoints.
5. **Protocolo de ouvidoria**: formato `ANO-NNNN`, gerado pelo banco (sequence), nunca pela aplicação cliente nem por IA. A migração importa os protocolos existentes e a sequence continua do último número usado: números já informados a pacientes seguem consultáveis. O NNNN é contínuo, não reinicia por ano.
6. **Fases**: fase 1 entrega valores (tabelas, CRUD admin, GETs); fase 2 entrega ouvidoria (migração com continuidade, POST/GET, painel). O NocoDB só desliga após a fase 2 validada do lado da Ana.
7. **Defesa contra escrita vazia**: nos endpoints de escrita, campos críticos são NOT NULL no banco e validados na API (a plataforma da Ana tem falha silenciosa conhecida de interpolação que grava vazio com HTTP 200; o banco deve recusar).

## Considered options

- **Expor o Postgres à Ana (usuário read-only já provisionado):** rejeitado. Furaria as regras que vivem no Python e acoplaria o produto irmão ao schema interno.
- **Manter o NocoDB como camada de edição sobre este Postgres:** rejeitado pela pesquisa citada (sync manual, webhooks sem garantia); dois sistemas para sempre.
- **Usuário técnico no Supabase Auth para a Ana:** rejeitado; o executor HTTP da plataforma da Ana não renova JWT.
- **Leitura pública sem auth (como as shared views atuais):** rejeitado; endpoints anônimos na API de produção por economia de um header não compensa.

## Consequences

- Primeira integração de serviço do app com outro sistema: nasce o conceito de API key de serviço ao lado do JWT (uma dependência de auth nova, pequena e isolada).
- O app passa a guardar dado operacional de ouvidoria (anonimizado). O painel dá à diretoria visibilidade que o NocoDB nunca deu.
- A disponibilidade da API deste app passa a afetar as respostas da Ana sobre preços e o registro de protocolos: o comportamento de indisponibilidade do lado dela já existe (Regra Híbrida, sem número inventado).
- O detalhamento de produto (histórias, critérios) vive no PRD desta feature no GitHub; o lado Ana (troca de URLs das tools, credencial, desligamento do NocoDB) vive no repo da Ana (ADR-0015 e proposta P9 de lá).
