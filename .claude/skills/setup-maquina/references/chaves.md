# Chaves: de onde vem cada uma

Cofre compartilhado do 1Password: **VITTA TECH**. Quem clona precisa de acesso a ele. Item marcado com "(criar)" ainda não existe no cofre: o Pedro cria na primeira vez.

## tokens/.env (tokens da máquina)

| Chave | Nível | Tipo | Origem |
|---|---|---|---|
| `COOLIFY_ACCESS_TOKEN` | 2 | por pessoa | Painel do Coolify, Keys & Tokens, API tokens, com permissão de deploy. A conta no Coolify quem cria é o Pedro. |
| `COOLIFY_BASE_URL` | 2 | config | Já vem no `.env.example`. |
| `ANA_API_KEY` | 2 | compartilhada | 1Password, VITTA TECH, item "Ana API key" (criar). É a mesma chave de produção. Só para smoke test. |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | opcional | por pessoa | Conta GitHub própria, PAT clássico com escopo `repo`. Nenhuma skill lê; o `gh` usa o próprio login. |

## hospital-reunioes/.env (nível 2: só o mínimo para o snapshot)

| Chave | Valor | Motivo |
|---|---|---|
| `ENVIRONMENT` | `development` | O default é `production` e recusa subir sem tudo. |
| `SUPABASE_URL` | `http://localhost:54321` | Fictício, igual ao CI. Só precisa existir. |
| `SUPABASE_SERVICE_ROLE_KEY` | `dummy-local` | Fictício, igual ao CI. São as 2 únicas chaves sem default. |

Todo o resto copia do `.env.example` como está. Chave vazia liga o mock (LLM, email, ClickSign).

## hospital-reunioes/.env (nível 3: rodar o app local, opcional)

| Chave | Tipo | Origem |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | por pessoa | Saída de `supabase status` depois de `supabase start` em `hospital-reunioes/`. |
| `OPENROUTER_API_KEY` | por pessoa ou compartilhada | 1Password, VITTA TECH, item "OpenRouter" (criar). Vazia liga o mock de IA. |
| `CLICKSIGN_API_KEY` (sandbox) | compartilhada | 1Password, VITTA TECH, item "ClickSign sandbox" (criar). |
| `SMTP_USER`, `SMTP_PASSWORD` | por pessoa | Senha de app do Gmail de quem roda. Vazio imprime o email no log. |
| `RESEND_API_KEY` | só produção | 1Password, VITTA TECH, item "Resend". Não entra no local. |
| `GH_TOKEN_HOMOLOG` | só produção | 1Password, HOSPITAL SÃO MATHEUS, item "Global Health". É a agenda de homologação, não é GitHub. Não entra no local. |
| `FIREFLIES_*`, `DIRETOR_EMAIL`, `DEFAULT_USER_PASSWORD` | só produção | Vivem no Coolify. |

## Fora de arquivo

| O quê | Quem faz |
|---|---|
| Conta no Coolify do hospital | Pedro cria; o token cada um gera o seu. |
| Login em `REVIEWER_LOGINS` | `gh variable set REVIEWER_LOGINS --body "pedrorezendefig,<login>"`. Sem isso o comentário da pessoa não dispara o loop do revisor. |
| Acesso ao cofre VITTA TECH | Pedro compartilha no 1Password. |
| Migration em produção | Humano, no SQL Editor do Supabase Studio de produção. Só o Pedro tem acesso hoje. |
| Vercel (`/divulgar`) | Membro do time na Vercel. Fora disso a CLI recusa com `TEAM_ACCESS_REQUIRED`. |
