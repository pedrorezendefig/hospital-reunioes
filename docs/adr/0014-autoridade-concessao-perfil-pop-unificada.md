---
status: accepted
---

# Autoridade de concessão do perfil POP unificada no Super Admin de Reuniões

O ADR 0007 criou o eixo `perfil_pop` ortogonal ao `access_profile` das Reuniões e já previa que "o admin de usuários existente vira peça central e ganha o eixo `perfil_pop`". O que ele não definiu foi **quem concede** o perfil. A primeira implementação (issue #81) fechou a concessão no próprio contexto: o endpoint que grava `perfil_pop` exigia `require_perfil_pop("superadmin")` — só um Superadmin POP concede perfil POP.

Isso criou um ovo-e-galinha: não há como o **primeiro** Superadmin POP nascer pela aplicação, porque conceder o papel já exige tê-lo. Em produção a saída virou um UPDATE manual no banco (issue #128), repetível a cada ambiente novo.

A decisão: **a autoridade de administração da concessão é unificada no Super Admin de Reuniões.** O endpoint que grava `perfil_pop` passa a aceitar **Super Admin de Reuniões OU Superadmin POP**, e o controle de concessão ganha lugar na edição do usuário, na tela de Usuários, onde o Super Admin de Reuniões já administra o eixo das Reuniões. A concessão a quem ainda não loga continua provisionando o acesso automaticamente (comportamento herdado do contexto POPs).

## Por que é surpreendente

- O ADR 0007 enfatiza a ortogonalidade ("o Super admin das Reuniões **não** bypassa o `perfil_pop`"). À primeira vista, deixar o Super Admin de Reuniões conceder perfil POP parece furar essa regra. Não fura: o que o 0007 proíbe é o bypass de **acesso a dados** (ter `super_admin` não te deixa *ver* POPs). O que esta ADR unifica é a **autoridade de administração** da concessão, uma camada distinta. Administrar quem entra num contexto não é o mesmo que acessar o contexto.
- A ortogonalidade preservada é a de **acesso implícito**: nenhum acesso aos dados dos POPs vem de inferir `is_super_admin`. O guard `require_perfil_pop` **não** foi afrouxado, então um Super Admin de Reuniões sem `perfil_pop` continua recebendo 403 na área interna dos POPs (listagem do admin POPs, Setores, POPs). Acessar o contexto exige um `perfil_pop` gravado, sempre um ato explícito e auditado.

## Alternativas descartadas

- **Manter a concessão fechada no Superadmin POP (status quo).** Preserva a pureza do eixo, mas perpetua o ovo-e-galinha: todo ambiente novo exige UPDATE manual no banco para nascer o primeiro Superadmin POP. Frágil, não-autosserviço, e fora da UI auditável.
- **Bootstrap por migration/seed.** Seedar o primeiro Superadmin POP por migration. Mas o e-mail do responsável varia por ambiente, e seed hardcoded é frágil e fora do controle do administrador. Empurra a decisão de quem manda nos POPs pro código, não pra quem opera.
- **Híbrido: Super Admin de Reuniões concede apenas o perfil `superadmin` (o bootstrap), e daí o Superadmin POP distribui os demais.** Cruzamento mínimo entre contextos, mas regra mais difícil de explicar e auditar, sem ganho real: o admin raiz do app já é confiável para administrar o eixo inteiro.

## Consequências

- O endpoint de gravação de `perfil_pop` passa a ter dois caminhos de autorização (Super Admin de Reuniões e Superadmin POP) e segue candidato permanente de `/security-review`, como todo gate do POPs (ADR 0007).
- O Super Admin de Reuniões pode conceder e revogar qualquer perfil POP, inclusive promover/revogar outro Superadmin POP — coerente com o papel de admin raiz do app.
- O Super Admin de Reuniões pode conceder o perfil POP **a si mesmo**, e é assim que o bootstrap do primeiro Superadmin POP acontece (a Diretoria, já admin raiz das Reuniões, marca o próprio acesso pela tela de Usuários). Não é um bypass: grava o `perfil_pop` de forma explícita e auditável, não é acesso inferido de `is_super_admin`, e é reversível por qualquer administrador. Só a auto-**revogação** é barrada, para ninguém se trancar para fora por engano.
- A issue #128 (bootstrap manual do primeiro Superadmin POP) fica **aposentada**: o primeiro perfil POP nasce pela tela de Usuários, concedido pelo Super Admin de Reuniões, que já está seedado no banco (migração 017). Nenhum UPDATE manual é necessário.
- A auditoria (`POPS_PERFIL_POP`) registra o ator real da ação, seja ele Super Admin de Reuniões ou Superadmin POP.
- Os demais endpoints do admin POPs (listagem de pessoas, vínculos de Setor) permanecem restritos a `perfil_pop`: a área interna do contexto não é afetada por esta ADR.
