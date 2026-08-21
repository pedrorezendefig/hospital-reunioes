---
status: accepted
---

# Role é etiqueta interna: o próprio usuário nunca vê o seu role

Decisão do diretor (20/ago/2026, grilling): o campo `participantes.role` (`diretor`, `gerente`, `coordenador`, `presidente`) é uma etiqueta interna de administração. Ele nunca é exibido ao próprio Facilitador; só o Super admin o vê, no painel de usuários.

## Contexto

- Um profissional da ouvidoria foi cadastrado como Facilitador. O formulário de cadastro força a escolha de um role e o default é `coordenador`; nenhum valor do enum descreve a função dele.
- A página "Meu Perfil" exibia um badge com o role. Um Facilitador que não é coordenador de fato veria "Coordenador" na própria tela, poderia fotografar e usar como indício de desvio de função num processo trabalhista. O risco é jurídico, não técnico.
- O role tem poder de permissão quase nulo: a permissão real vive em `access_profile` (Reuniões) e `perfil_pop` (POPs). O role é lido em `require_role` em 7 pontos: invite (`auth.py:24`), soft delete (`participantes.py:289`), uma rota de reuniões (`reunioes.py:861`) e 4 rotas legadas de admin (`admin/legacy.py`, todas exigem `diretor`); há ainda uma policy RLS que o backend bypassa (service_role). O valor `coordenador` só é aceito explicitamente no invite; nos demais gates ele não dá acesso a nada.
- O role é derivado do cargo por mapa hardcoded (`cargo_mapping.py`); o texto público de identificação nas telas de reunião é o **cargo**, texto livre que pode dizer "Ouvidoria" sem risco.

## Decisões

1. **O badge de role sai da página "Meu Perfil" para todos os Facilitadores.** O cargo continua exibido e é o texto público de identificação.
2. **A coluna Role permanece no painel `/admin/usuarios`**, que já é restrito a super admins. Não há restrição adicional a um único admin.
3. **O contexto POPs fica inalterado.** O cabeçalho "seu perfil: Coordenador" reflete uma permissão real de elaboração. Aviso registrado: só conceder `perfil_pop = coordenador` a coordenadores de fato; conceder a outra pessoa recria o mesmo risco jurídico.
4. **O campo `role` permanece no banco e no cadastro** como faixa hierárquica interna, sem mudança de schema.

## Considered options

- **Criar um role novo (ex.: `ouvidoria`):** rejeitado. O role quase não controla nada; crescer o enum para cada função nova só espalha a etiqueta que se quer esconder.
- **Apagar a coluna/enum `role`:** rejeitado. Ainda alimenta os 7 gates de `require_role` (invite, soft delete, reuniões, rotas legadas de admin) e o mapa de cargos; a cirurgia é maior que o problema.
- **Esconder o badge só de quem "não é coordenador de verdade":** rejeitado. O sistema não tem como saber isso; exigiria um campo novo para alimentar uma exceção.

## Consequences

- Nenhuma tela futura voltada ao próprio Facilitador deve exibir o role dele. Quem precisar mostrar "quem é a pessoa" usa o **cargo**.
- O painel admin segue sendo o único lugar onde o role aparece, para o conjunto de super admins.
