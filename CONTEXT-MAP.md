# Mapa de Contextos — HSM

Este repositório abriga **um app físico** (`hospital-reunioes/`: FastAPI + Next.js + Supabase self-hosted) com **três contextos de domínio**. Cada contexto tem o seu glossário; termos homônimos entre contextos **não** significam a mesma coisa — confira o glossário do contexto antes de usar um termo.

| Contexto | Glossário | O que cobre |
|---|---|---|
| **Reuniões** | [CONTEXT.md](CONTEXT.md) | Reunião → Transcrição → Ata → assinatura/aprovação → Pendências |
| **POPs** | [docs/pops/CONTEXT.md](docs/pops/CONTEXT.md) | Ciclo de vida dos Procedimentos Operacionais Padrão: elaboração assistida por IA → revisão → validação → assinatura → Biblioteca → treinamentos |
| **Contas médicas** | [docs/contas-medicas/CONTEXT.md](docs/contas-medicas/CONTEXT.md) | Conferência da conta de internação antes do envio à operadora: Conta + Prontuário do MV → Motor (código e IA) × Memória da operadora → Guia da faturista → indicadores (ADR 0070) |

Os contextos compartilham o mesmo deploy, o mesmo login (Supabase Auth) e os mesmos serviços de integração (ClickSign, email, PDF, cron). A separação é **de domínio e permissão**, não de infraestrutura.

## Termos compartilhados e homônimos

- **Pessoa física é uma só nos contextos Reuniões e POPs**: a tabela `participantes` é a entidade pessoa de ambos. Os eixos de permissão são separados — `access_profile` (Reuniões) e perfil POP (POPs); uma pessoa pode ter um, outro, ambos ou nenhum.
- **Colaborador** significa o mesmo em Reuniões e POPs: pessoa que **não loga** no sistema.
- **Superadmin (POPs)** ≠ **Super admin (Reuniões)**: no contexto POPs é o papel funcional da Diretoria Executiva (gere usuários, vê tudo); nas Reuniões é o Facilitador com bypass de debug (`is_super_admin`). Homônimos, conceitos distintos — não fundir.
- **Setor (POPs)** ≠ **setor (Reuniões)**: em Reuniões é atributo da pessoa — o campo livre `participantes.setor` com a taxonomia canônica `setores` (nome, **sem sigla**) por cima; em POPs é entidade própria (`pops_setores`) com **sigla**, que trava o Código imutável `HSM_[SIGLA]-NNN`. Ao criar um Setor de POP o sistema **sugere** os nomes que Reuniões já conhece (autocomplete sobre `/api/participantes/setores`) e propõe a sigla pelas iniciais — mas **não funde as entidades nem cria FK**: direção única (POPs consome; renomear ou arquivar um setor em Reuniões nunca pode tocar um Código já emitido).
- **Assinatura digital / Envelope / Signatário**: mesma mecânica ClickSign nos dois contextos.
- **Atendimento (Contas médicas)** ≠ **Dados do Atendimento (Reuniões / Ana)**: em Contas médicas é o número da internação no MV, chave de tudo no módulo; em Reuniões é o módulo das tabelas que alimentam a Ana. Homônimos, sem relação.
- **Setor (Contas médicas)** é o nome do setor como o MV imprime, ligado a uma acomodação (`cm_setor`); não é o Setor dos POPs nem o setor das Reuniões. Sem FK entre os três.
- **Perfil de Contas médicas** vive no eixo `perfil_contas_medicas` de `participantes`, ortogonal a `access_profile`, `perfil_pop` e `perfil_ouvidoria`.

As decisões arquiteturais continuam únicas em [docs/adr/](docs/adr/) (numeração contínua, sistema todo).
