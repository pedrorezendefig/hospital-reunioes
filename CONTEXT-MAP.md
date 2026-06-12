# Mapa de Contextos — HSM

Este repositório abriga **um app físico** (`hospital-reunioes/`: FastAPI + Next.js + Supabase self-hosted) com **dois contextos de domínio**. Cada contexto tem o seu glossário; termos homônimos entre contextos **não** significam a mesma coisa — confira o glossário do contexto antes de usar um termo.

| Contexto | Glossário | O que cobre |
|---|---|---|
| **Reuniões** | [CONTEXT.md](CONTEXT.md) | Reunião → Transcrição → Ata → assinatura/aprovação → Pendências; Notas |
| **POPs** | [docs/pops/CONTEXT.md](docs/pops/CONTEXT.md) | Ciclo de vida dos Procedimentos Operacionais Padrão: elaboração assistida por IA → revisão → validação → assinatura → Biblioteca → treinamentos |

Os dois contextos compartilham o mesmo deploy, o mesmo login (Supabase Auth) e os mesmos serviços de integração (ClickSign, email, PDF, cron). A separação é **de domínio e permissão**, não de infraestrutura.

## Termos compartilhados e homônimos

- **Pessoa física é uma só**: a tabela `participantes` é a entidade pessoa dos dois contextos. Os eixos de permissão são separados — `access_profile` (Reuniões) e perfil POP (POPs); uma pessoa pode ter um, outro, ambos ou nenhum.
- **Colaborador** significa o mesmo nos dois contextos: pessoa que **não loga** no sistema.
- **Superadmin (POPs)** ≠ **Super admin (Reuniões)**: no contexto POPs é o papel funcional da Diretoria Executiva (gere usuários, vê tudo); nas Reuniões é o Facilitador com bypass de debug (`is_super_admin`). Homônimos, conceitos distintos — não fundir.
- **Assinatura digital / Envelope / Signatário**: mesma mecânica ClickSign nos dois contextos.

As decisões arquiteturais continuam únicas em [docs/adr/](docs/adr/) (numeração contínua, sistema todo).
