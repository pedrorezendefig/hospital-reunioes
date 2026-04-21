# Blueprint — Hospital Reuniões

Pasta de documentação viva do projeto. Reflete o estado **atual** do sistema. Diagramas, fluxos, configurações. Orientada para quem precisa entender o sistema sem ler o código linha-a-linha.

---

## O que é o sistema, em 30 segundos

**Hospital Reuniões** automatiza o ciclo de vida de reuniões corporativas em hospital de alta complexidade: gravação → transcrição via IA → geração automática de ata → assinatura digital → acompanhamento de pendências.

**Quem usa:** 5 facilitadores ativos (1 diretor + 4 diretoras). Colaboradores não logam — recebem só e-mails da ClickSign quando viram responsáveis por pendências.

**Stack:** FastAPI (Python 3.12) + Next.js 15 + Supabase (self-hosted) + Coolify em VPS Hostinger. Integra OpenAI, ClickSign, Resend e Fireflies.

**Estado:** aguardando primeiro deploy em produção (`mala-ia.cloud`). Banco de teste ainda mocado.

---

## Como navegar este blueprint

| Documento | Serve para |
|---|---|
| [ARQUITETURA.md](./ARQUITETURA.md) | Ver o desenho de alto nível: stack, componentes, recursos externos, estrutura de pastas |
| [FLUXOS.md](./FLUXOS.md) | Entender como uma reunião é processada ponta a ponta — do áudio ao PDF assinado |
| [AMBIENTES.md](./AMBIENTES.md) | Ver o que difere entre LOCAL e PRODUÇÃO — env vars, serviços externos, Supabase |
| [DEPLOY.md](./DEPLOY.md) | Config de Coolify + status atual de produção + histórico de deploys |

Ordem sugerida para um leitor novo: **README → ARQUITETURA → FLUXOS → AMBIENTES → DEPLOY**.

---

## Slash commands relevantes

| Comando | O que faz |
|---|---|
| `/deploy` | Ship diário: pre-flight silencioso, commit assistido, push, monitora Coolify, aplica migrations, health check, auto-rollback se falhar |
| `/deploy setup` | Setup inicial do Coolify (1x por projeto): cria apps, Supabase, env vars, DNS guia |
| `/deploy status` | Reporta estado atual de produção (apps, SHA local vs prod, migrations pendentes) — não altera nada |
| `/deploy rollback` | Reverte para último SHA saudável via MCP Coolify |
| `/resetsupa` | Reseta o Supabase local (apaga dados, mantém schema) |
| `/migrar-atas` | Migração assistida de ATAs antigas (PDFs em `atas-migracao/`) em lote |

Todos os detalhes de cada comando vivem nas próprias skills — este doc só aponta para elas.

---

## Convenções do projeto

- **Deploy:** só via `/deploy` (nunca push manual direto). A skill lê `blueprint/DEPLOY.md` como fonte única de UUIDs, domínios e vars obrigatórias.
- **Idioma:** toda comunicação em pt-BR, código em inglês (convenção padrão).
- **Planos:** arquivos `.md` na raiz (ex: `plano-nova-feature.md`). Transitórios, gitignored.
- **Commits:** convencionais (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`).
- **Não criar:** pasta `implementacoes/` ou `deploy-history.md` — substituídos por `blueprint/DEPLOY.md` + `git log`.

---

## Manutenção deste blueprint

**Atualização automática após cada commit:** o hook `.githooks/post-commit` invoca a skill `/blueprint-sync`, que revisa o diff e atualiza as seções afetadas de `README.md`, `ARQUITETURA.md`, `FLUXOS.md` e `AMBIENTES.md`. Se algum destes arquivos mudou, o hook amenda o commit.

**Ativar o hook após clonar o repo:**

```bash
git config core.hooksPath .githooks
```

**Pular o hook em um commit específico:**
- `BLUEPRINT_SYNC=off git commit ...` — desliga só esta vez
- `git commit --no-verify` — mesmo efeito

**Invocação manual:** `/blueprint-sync` (sem argumento) revisa os últimos 5 commits + working tree.

**`DEPLOY.md` é gerenciado separadamente** pela skill `/deploy` após cada ship — `/blueprint-sync` não toca nele.
