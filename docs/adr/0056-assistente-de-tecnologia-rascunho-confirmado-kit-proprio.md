---
status: accepted
amended_by: 0057
---

# Assistente de Tecnologia: rascunho confirmado por gente, kit próprio embarcado, responde do kit ou registra

Decisão do Pedro (15/set/2026, grilling, na véspera de uma viagem em que os sócios e o diretor passam a usar a aba Tecnologia sozinhos). O Quadro de Demandas (ADR 0050) está em produção, mas abrir uma Demanda bem escrita exige que o diretor saiba de antemão o tipo, o produto e o que a Vitta vai perguntar depois. Esta ADR põe um agente de IA na porta de entrada, o **Assistente de Tecnologia**, e fixa três escolhas que seriam caras de desfazer: quem grava, de onde ele sabe o que sabe, e quando ele pode responder sem registrar.

## Contexto

- O app já replicou três vezes o mesmo molde de agente conversacional (Ata Guiada, correção de Ata, elaboração de POP): sem estado no servidor, resposta JSON `{reply, rascunho}`, prompts em `.md`, sanitizador de travessão (ADR 0013), modo mock sem chave. A Ata Guiada (ADR 0005 e 0006) tem tela dedicada com chat de um lado e rascunho vivo do outro, voz gravada no navegador e transcrita no backend, e Documento de apoio efêmero.
- A aba Tecnologia não toca o LLM em ponto nenhum: o "Copiar para IA" é texto para o humano colar fora do app.
- A Demanda não tem anexo; a descrição é texto puro sem limite. A criação exige título, tipo e produto, e o backend decide estado e responsável (ADR 0050, decisão 4).
- Todos os agentes usam a mesma `LLM_MODEL` (em produção o Gemini 3.7 Flash via OpenRouter, que lê imagem). Nenhuma chamada do app manda imagem ao modelo hoje; PDF e DOCX viram texto localmente, sem OCR.
- A imagem do backend leva só `backend/app/`. O glossário (`CONTEXT.md`) e os manuais (`docs/manual/`) ficam fora do build, o glossário fala de labels, issues e ADRs que o diretor não deve ver (ADR 0054, decisão 9), e os manuais são HTML com prints para gente ler.
- A Ana vive em outro repositório; o app não tem de onde ler o que ela faz.

## Decisões

1. **O agente monta, a pessoa grava.** O chat produz um Rascunho da Demanda com os campos do formulário, todos editáveis à mão, e a Demanda só nasce no botão "Criar Demanda", pela mesma rota e com as mesmas guardas de hoje. O botão nunca é segurado por falta de informação: o que faltou sai no roteiro como "não informado". Rejeitado: o agente criar por tool call ao fim da conversa (um clique a menos, e o erro do modelo virando Demanda sem ninguém olhar); só texto para colar no formulário (não resolve a usabilidade).

2. **O conhecimento é um kit próprio, escrito para o diretor, embarcado no prompt inteiro.** Um arquivo `.md` por Produto (Ana, Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site, Infra) mais um sobre a própria aba, em `backend/app/conhecimento/`, viajando no deploy. Sem número de issue, label, nome de tabela ou vocabulário do repositório. Curado por gente, com a regra do manual: mudou o comportamento de um módulo, o arquivo dele muda no mesmo PR. Rejeitado: RAG com embeddings (infraestrutura para cinco pessoas e oito documentos que cabem na janela do modelo); copiar `CONTEXT.md` e os manuais para a imagem (o leitor errado: vocabulário interno e HTML); gerar o kit por script a partir do glossário (um filtro em que ninguém confia). Custo aceito: uma terceira escrita do mesmo conhecimento, e kit desatualizado vira agente mentindo.

3. **Responde do kit ou registra.** Pergunta cuja resposta está no kit é respondida ali mesmo, dizendo de onde saiu, com a saída oferecida ("resolveu, ou quer registrar mesmo assim?"); se o diretor sai satisfeito, nada é gravado. Fora do kit o agente não responde de cabeça: diz que não sabe e monta a Demanda (Informação ou Consultoria). Rejeitado: sempre registrar (desperdiça o conhecimento e faz o diretor esperar um dia pelo que está escrito); responder e gravar uma Demanda já Concluída (enche o Histórico do que ninguém pediu).

4. **Tudo que entra é efêmero.** Texto, voz gravada, arquivo de texto, imagem e arquivo de áudio são lidos e viram descrição; nenhum é guardado, e a conversa também não (nem na Conversa da Demanda, nem em tabela própria). O produto é a Demanda. A imagem é a primeira chamada multimodal do app. Rejeitado nesta leva: Anexo da Demanda persistente (storage, tabela, card, e-mail), que pode entrar depois como PRD próprio sem desfazer nada.

5. **"Nova Demanda" abre o assistente**, em tela dedicada no molde da Ata Guiada, com o formulário antigo a um clique ("prefiro preencher à mão"). O agente enxerga as Demandas abertas do Quadro (título, tipo, produto, estado, Etapa; nunca a Conversa) e avisa quando já existe uma sobre o mesmo assunto. Sem nome próprio: persona compete com a Ana na cabeça do hospital. Mesma `LLM_MODEL` de todo mundo. Uma linha fixa avisa que o conteúdo é lido por uma IA, como o "Copiar para IA" já avisa.

## Consequências

- O glossário ganhou Assistente de Tecnologia, Kit de conhecimento e Roteiro por Tipo.
- Nasce uma pasta de conhecimento no backend que o `/to-prd` e o `/to-issues` precisam tratar como parte da entrega: fatia que muda comportamento visível de um módulo lista o arquivo do kit a atualizar, como já faz com o manual.
- A rota do chat é nova, atrás de `require_super_admin`, com o mesmo teto de taxa dos outros chats; a rota de voz existente serve como está (Super admin passa pelo gate de Reuniões). O arquivo de texto reaproveita o extrator dos outros módulos; imagem e áudio enviados por upload são caminhos novos, com teto de tamanho e sem persistência.
- Nada muda na criação, no Kanban, na Conversa, no Vínculo (ADR 0054) nem no e-mail: a Demanda que o assistente monta é indistinguível de uma digitada no formulário.
- Fora do escopo, de propósito: ajuda do agente dentro de uma Demanda existente (rascunhar resposta na Conversa) e Demandas fechadas no contexto.
