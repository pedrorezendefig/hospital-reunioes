---
status: accepted
---

# POPs: segundo contexto de domínio no mesmo app, com eixo de permissão próprio

A Diretoria do HSM entregou um DRF pedindo um "Sistema de Gestão de POPs" — ciclo de vida de Procedimentos Operacionais Padrão (elaboração com IA → revisão → validação → assinatura ClickSign → Biblioteca → treinamentos), com 4 perfis novos que **logam** (Superadmin/Diretoria, Gestor de Qualidade, Gerente, Coordenador). O domínio não se mistura com o de Reuniões — só "Colaborador" coincide (e por sorte com o mesmo significado: quem não loga).

A decisão tem três partes:

1. **Mesmo app físico, contexto de domínio separado.** O POPs vive no mesmo repo, backend FastAPI, frontend Next.js e deploy Coolify do Hospital Reuniões — rotas e módulos com namespace próprio (`pops`). A separação é de **domínio e permissão**, não de infraestrutura: nasce o `CONTEXT-MAP.md` na raiz e o glossário próprio em `docs/pops/CONTEXT.md`; termos homônimos entre contextos (ex.: "Superadmin") não significam a mesma coisa.
2. **Pessoa única, eixo de permissão novo.** Não há tabela nova de gente: `participantes` segue sendo a entidade pessoa dos dois contextos. O acesso ao POPs vem de um eixo ortogonal `perfil_pop` (`superadmin | gestor_qualidade | gerente | coordenador | null`), independente do `access_profile` das Reuniões. Ganhar perfil POP implica ganhar login (Supabase Auth). Uma pessoa pode ter papel num contexto, no outro, em ambos ou em nenhum.
3. **Setor vira entidade.** Tabela própria com nome e sigla (base do código travado `HSM_[SIGLA]-[NNN]`, sequência por Setor), com vínculo N:N pessoa↔Setor (Gerente: vários; Coordenador: normalmente um, sem trava artificial). Não confundir com o campo livre `setor` que já existe em `participantes`.

## Por que é surpreendente

- O DRF pede um "**Sistema**" — quem o lê espera repo/app/deploy separados. A escolha foi módulo no app existente: a mesma diretoria usa os dois contextos, e a infraestrutura que o DRF exige **já existe aqui** (ClickSign com Envelope+webhook, email Resend+SMTP, PDF WeasyPrint, cron APScheduler, Supabase Storage, admin de usuários, chat-agente iterativo da Ata Guiada, extração de .pdf/.docx, voz).
- O cadastro atual **já tinha** `UserRole.GERENTE` e `UserRole.COORDENADOR` (cargo informativo) e um campo `setor` string — mas nada disso é o RBAC do POPs. O eixo novo é deliberadamente separado em vez de estender o `access_profile`: estender misturaria contextos (Secretária das Reuniões viraria "irmã" de Coordenador de POPs no mesmo enum) e impediria a mesma pessoa de ter papéis distintos nos dois contextos.
- "Superadmin (POPs)" ≠ `super_admin` das Reuniões (bypass de debug). Homônimos em colunas diferentes — o CONTEXT-MAP documenta a homonímia para ninguém fundir.

## Alternativas descartadas

- **App irmão com infra compartilhada** (repo/deploy separados, mesmo Supabase/ClickSign): contextos fisicamente isolados, mas 2 backends + 2 frontends + serviços duplicados ou lib comum extraída — caro demais para um dev solo, sem ganho de domínio (o CONTEXT-MAP já dá a separação que importa).
- **App separado com stack própria**: zero risco de vazamento entre contextos, mas duplica toda a infraestrutura pronta e dobra a operação que o ADR 0001 já coloca sob nossa responsabilidade (backup, upgrade, monitoramento).
- **Estender o `access_profile` existente**: menos colunas, acoplamento máximo — ver acima.
- **Tabela de usuários POP separada**: duplicaria a pessoa física (mesmo email em duas tabelas), quebraria o reuso do admin de usuários e complicaria o ClickSign (o signatário é a mesma pessoa nos dois contextos).

## Consequências

- **A disciplina do ADR 0002 fica mais exposta.** Coordenadores e Gerentes logam no mesmo app mas **não podem ver Reuniões, Notas ou Pendências** (e Facilitadores sem perfil POP não veem POPs). Sem RLS, cada endpoint e item de navegação aplica o gating na camada de app — todo endpoint novo do POPs e a navegação por perfil são candidatos permanentes de `/security-review`.
- O volume de usuários logados sai de 5 (Facilitadores) para potencialmente dezenas (Coordenadores/Gerentes de todos os setores) — o admin de usuários existente vira peça central e ganha o eixo `perfil_pop` + vínculos de Setor.
- O volume ClickSign cresce estruturalmente: cada Versão Publicada = 3 signatários, e **toda Revisão periódica re-assina** (mesmo sem mudança de conteúdo, por exigência do DRF). Custo por envelope do plano atual precisa ser confirmado antes da Leva 1 entrar em produção.
- Glossários por contexto via `CONTEXT-MAP.md`; ADRs seguem únicos e com numeração contínua em `docs/adr/`.
- Decisões de produto do grilling (espinha de entregas, agente sem RAG, fluxograma em CSS, OCR com confirmação humana, alertas por regra + redação IA) ficam no PRD — não são desta ADR.
