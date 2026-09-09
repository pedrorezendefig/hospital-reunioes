---
status: accepted
---

> Nasceu como 0049 no grilling de 08/09/2026, na árvore local. O número 0049 já tinha sido tomado no `origin/main` pela ADR da wayfinder, então esta cedeu o número e virou 0050 em 09/09/2026. O PRD #634 e a issue #636 citam 0050.

# Demandas de tecnologia moram no app do hospital, só para Super admin, apartadas das Pendências

Decisão do Pedro (08/set/2026, grilling): a conversa entre a Vitta e o diretor sobre as aplicações (hoje no WhatsApp, onde se perdia) vira a aba **Tecnologia** da área admin do app, com uma entidade própria, a **Demanda**, um Kanban de cinco estados e uma Conversa por card. Só quem é Super admin vê a aba. Nada disso encosta nas Pendências de Ata.

## Contexto

O Pedro e o diretor trocam dezenas de pedidos por WhatsApp: perguntas de decisão sobre a Ana, cobranças a terceiros (Global Health, analista de TI), defeitos, testes, pedidos de mudança. O diretor não consegue responder algumas, pede outras, e as duas pontas se perdem. O pedido inicial era um site próprio na Vercel com banco próprio, no visual do Ana OS em azul claro.

Fatos que pesaram:

- O app do hospital roda em Coolify na VPS, com Supabase self-hosted e login pelo Supabase Auth. Não está na Vercel.
- Na Vercel, o plano Hobby é só para uso pessoal; um site da Vitta para o hospital exigiria o plano Pro. O banco seria Neon pelo Marketplace (Vercel Postgres acabou em dez/2024).
- "Pendência" é termo reservado do glossário (ação de Ata com responsável e prazo). "TI", no programa Ana, é o analista de TI do hospital, um terceiro.
- O perfil da Ouvidoria (`perfil_ouvidoria` em `participantes`) é o molde de eixo de permissão à parte, concedido pelo Super admin.

## Decisões

1. **Dentro do app, não num site próprio.** Um login só para o diretor, o banco e o e-mail (Resend) já existem, e o deploy é o mesmo. Rejeitado: site próprio na Vercel com Neon (segundo link e segunda senha para o diretor, plano Pro para uso comercial, mais uma infraestrutura para a Vitta manter). Custo aceito: cada sócio da Vitta que for usar precisa de conta no app do hospital, e cada mudança segue o pipeline do repo.

2. **Só `is_super_admin` vê a aba.** Rejeitado: eixo próprio de permissão no molde da Ouvidoria (`perfil_tecnologia` com papéis hospital e vitta). Consequência assumida: sócio da Vitta que usar a aba é Super admin do app, com poder irrestrito. O lado de cada pessoa (hospital ou Vitta) não é dado do sistema: aparece pelo autor e pelo responsável de cada Demanda.

3. **Entidade "Demanda", aba "Tecnologia".** Tipo em lista fechada de sete (Decisão, Informação, Terceiro, Ajuste, Novo, Defeito, Consultoria), cada um com símbolo desenhado. Rejeitado: "Pedido" (fraco para o que a Vitta pede ao diretor) e "Demandas TI" (colide com o analista de TI).

4. **Produto com dono.** Cada Demanda pertence a um Produto (Ana, Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site, Infra; lista editável pelo Super admin) e nasce atribuída ao dono do Produto, do lado da Vitta, que pode repassar.

5. **Kanban de cinco estados** (Nova, Em andamento, Aguardando, Concluída, Cancelada), com Responsável, Prioridade em três níveis e Prazo opcional. Sem prazo o card não atrasa, só envelhece (idade em dias, vermelha a partir de 14). Rejeitado: três estados com o campo "com quem está" virando sozinho a cada resposta (mais fiel ao WhatsApp, mas o Pedro preferiu colunas).

6. **Conversa por card, com @menção, e "Copiar para IA".** O botão copia a Demanda inteira (título, tipo, produto, descrição e a Conversa) em texto simples, para o diretor colar na IA dele e voltar com a resposta. E-mail em três gatilhos: atribuição (inclui a criação), @menção e resposta nova numa Demanda de que a pessoa é responsável. Rejeitado: e-mail por mudança de coluna e resumo diário.

7. **Três abas:** Quadro (as colunas, Concluída e Cancelada recolhidas, filtros por tipo, produto e responsável), Minha vez (o que espera por quem está logado) e Histórico (concluídas e canceladas, com busca).

8. **Visual do próprio app** (Tailwind e lucide). Rejeitado: o Ledger do Ana OS recolorido de azul-piscina, que era o pedido inicial; o Pedro preferiu uma cara só no sistema.

9. **Atualização por consulta periódica** (a cada 30 segundos e ao voltar o foco). Rejeitado: Supabase Realtime, peça a mais para 5 pessoas.

10. **Sem integração com o Ana OS.** As Demandas nascem à mão; as primeiras são as seis perguntas ao diretor sobre o encerramento de conversas da Ana (Decisão, produto Ana). Rejeitado: importar os itens "aguardando" do `roadmap.json`.

11. **Todos iguais dentro da aba.** Quem entra cria, edita, move, atribui e responde. Nada se apaga: a saída é Cancelada. Cada movimento vira linha automática na Conversa, com quem e quando. Rejeitado: só a Vitta move e atribui.

## Consequências

- Tabelas novas por migration no Supabase do app (Demanda, Produto, Conversa), separadas das tabelas de Pendência. Nenhum relatório, painel ou e-mail das Pendências lê essas tabelas.
- O glossário ganhou a seção "Tecnologia" com Demanda, Tipo da Demanda, Produto, Estado da Demanda e Conversa da Demanda.
- A tela de Usuários não muda: o acesso é o `is_super_admin` que já existe.
