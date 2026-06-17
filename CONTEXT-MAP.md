# Mapa de Contextos — HSM

Este repositório abriga **um app físico** (`hospital-reunioes/`: FastAPI + Next.js + Supabase self-hosted) com **três contextos de domínio**. Cada contexto tem o seu glossário; termos homônimos entre contextos **não** significam a mesma coisa — confira o glossário do contexto antes de usar um termo.

| Contexto | Glossário | O que cobre |
|---|---|---|
| **Reuniões** | [CONTEXT.md](CONTEXT.md) | Reunião → Transcrição → Ata → assinatura/aprovação → Pendências |
| **POPs** | [docs/pops/CONTEXT.md](docs/pops/CONTEXT.md) | Ciclo de vida dos Procedimentos Operacionais Padrão: elaboração assistida por IA → revisão → validação → assinatura → Biblioteca → treinamentos |
| **Auditoria de Pessoal** | [docs/auditoria-pessoal/CONTEXT.md](docs/auditoria-pessoal/CONTEXT.md) | Auditoria mensal ponto × folha: ingestão do Espelho (RH iD) e da Folha (Domínio) por Competência → Conciliação → Achados monitorados com Reincidência; acesso exclusivo do Auditor (diretor) |

Os contextos compartilham o mesmo deploy, o mesmo login (Supabase Auth) e os mesmos serviços de integração (ClickSign, email, PDF, cron). A separação é **de domínio e permissão**, não de infraestrutura.

## Termos compartilhados e homônimos

- **Pessoa física é uma só nos contextos Reuniões e POPs**: a tabela `participantes` é a entidade pessoa de ambos. Os eixos de permissão são separados — `access_profile` (Reuniões) e perfil POP (POPs); uma pessoa pode ter um, outro, ambos ou nenhum. **Exceção: o Funcionário (Auditoria de Pessoal) é população própria**, vinda da Folha/Espelho, sem vínculo com `participantes` nem com Colaborador (ADR 0009).
- **Colaborador** significa o mesmo em Reuniões e POPs: pessoa que **não loga** no sistema. No contexto Auditoria de Pessoal o termo é **evitado** — lá a entidade é Funcionário.
- **"Folha de ponto" não existe como termo**: o documento do ponto (RH iD) é o **Espelho**; **Folha** é só a de pagamento (Domínio). A homonímia popular é a principal fonte de confusão do contexto Auditoria de Pessoal.
- **Vínculo (Auditoria de Pessoal)** ≠ **Resolução (Reuniões)**: ambos casam identidades, mas Resolução casa nome citado → Colaborador numa Reunião/Nota; Vínculo casa Funcionário ↔ matrículas dos dois sistemas de RH. Análogos, não intercambiáveis.
- **Superadmin (POPs)** ≠ **Super admin (Reuniões)**: no contexto POPs é o papel funcional da Diretoria Executiva (gere usuários, vê tudo); nas Reuniões é o Facilitador com bypass de debug (`is_super_admin`). Homônimos, conceitos distintos — não fundir.
- **Setor (POPs)** ≠ **setor (Reuniões)** ≠ **departamento/centro de custo (Auditoria de Pessoal)**: em Reuniões é atributo da pessoa — o campo livre `participantes.setor` com a taxonomia canônica `setores` (nome, **sem sigla**) por cima; em POPs é entidade própria (`pops_setores`) com **sigla**, que trava o Código imutável `HSM_[SIGLA]-NNN`; na Auditoria de Pessoal é texto extraído da Folha/Espelho, sem lista canônica. Ao criar um Setor de POP o sistema **sugere** os nomes que Reuniões já conhece (autocomplete sobre `/api/participantes/setores`) e propõe a sigla pelas iniciais — mas **não funde as entidades nem cria FK**: direção única (POPs consome; renomear ou arquivar um setor em Reuniões nunca pode tocar um Código já emitido).
- **Assinatura digital / Envelope / Signatário**: mesma mecânica ClickSign nos dois contextos.

As decisões arquiteturais continuam únicas em [docs/adr/](docs/adr/) (numeração contínua, sistema todo).
