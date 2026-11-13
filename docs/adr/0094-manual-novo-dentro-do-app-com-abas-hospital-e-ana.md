---
status: accepted
amends: 0078, 0068
---

# Manual novo dentro do app, com as abas Aplicativo do Hospital e Ana

Decisão do Pedro (13/11/2026, grill no terminal, rodadas 4 e 6, todas as recomendações aceitas). A ADR 0078 aposentou o manual antigo (site na Vercel, com vídeo por módulo e fatia de manual em todo PRD) e deixou o manual novo para uma decisão própria. Esta é ela. O Pedro quer um manual que qualquer pessoa abra pelo canto inferior esquerdo, com uma aba para o app e outra para a Ana, no molde do Retrato da Ana: bem explicado, desenhado com fluxogramas. Sem vídeo; print de tela pode.

## Decisões

1. **O manual mora dentro do app, atrás do login.** Um item "Manual", com ícone de livro, no rodapé das duas barras laterais (a do app e a do Admin), acima do botão de recolher, abre o manual na largura toda com duas abas: Aplicativo do Hospital e Ana. Rejeitado: site separado na Vercel (o prompt da Ana não pode ficar público, e o endereço do manual antigo ficou livre); o manual no menu do usuário.

2. **Quem vê o quê.** A aba Aplicativo do Hospital é de todo usuário logado, e cada pessoa vê só as páginas dos módulos que já acessa no menu. A aba Ana é só de Super admin, porque mostra o prompt, as chamadas e as ferramentas. Rejeitado: todos veem tudo; o manual inteiro só para Super admin.

3. **A aba Ana é o Retrato da Ana.** O backend serve a página do Retrato, como ela é, direto do repositório privado da Ana, pelo token da integração (ADR 0093), só para Super admin logado. O Retrato é regenerado no repositório da Ana sempre que o prompt muda. Rejeitado: refazer as abas e os fluxogramas do Retrato em componentes do app; publicar o Retrato na Vercel com senha; copiar o Retrato para o repositório do Hospital, que é público.

4. **A aba Aplicativo do Hospital é uma página por módulo.** Reuniões e Pendências, POPs, Ouvidoria, Contas médicas, Central de Comando, Dados do Atendimento e Tecnologia. Cada página tem as tarefas em passo a passo, prints de tela e fluxogramas. A fonte é um Markdown por módulo dentro do frontend, com Mermaid para os fluxogramas e PNG para os prints, desenhado pelo próprio app e revisado em PR. Rejeitado: texto no banco editado numa tela; uma página única e longa; perguntas e respostas.

5. **Print só com dado fictício.** Tirado pelo `playwright-cli` contra o app local, com dados de seed. Nenhum nome, dado de saúde ou contrato real, porque o repositório é público. Rejeitado: print de produção borrado à mão.

6. **A fatia de manual volta ao fluxo, sem vídeo.** Todo PRD com tela ganha uma fatia de manual com texto, prints e fluxograma. O `/to-prd` e o `/to-issues` voltam a criá-la, no repositório do OS e na cópia do Hospital. Emenda a decisão 3 da ADR 0078 e a ADR 0068 (a fatia de manual volta à lista do que sobe sem parada humana). O que fez a 0078 tirar a fatia era o peso do vídeo, que não volta. Rejeitado: um card de manual por mês; atualizar à mão.

## Consequências

- Continua valendo da 0078: o site antigo, as skills `/manual` e `/montar-manual`, a pasta `docs/manual/` e os vídeos do manual não voltam.
- As páginas nascem numa onda só, uma fatia por módulo, depois da fatia que monta o manual. A da Tecnologia espera as fatias das Entregas novas (ADR 0092).
- O Kit de conhecimento continua sendo o que o Assistente de Tecnologia lê; o manual é para a pessoa.
