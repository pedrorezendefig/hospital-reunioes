# Chaves: de onde vem cada uma

O que cada chave faz está no comentário do `hospital-reunioes/.env.example` e no campo `purpose` do `docs/spec/deploy/project.json`. Esta tabela só acrescenta o que não mora lá: nível, se é por pessoa ou compartilhada, e o item do 1Password.

Cofre compartilhado do 1Password: **VITTA TECH**. Quem clona precisa de acesso a ele. Item marcado com "(criar)" ainda não existe no cofre: o Pedro cria na primeira vez.

## tokens/.env (tokens da máquina)

| Chave | Nível | Tipo | Origem |
|---|---|---|---|
| `COOLIFY_ACCESS_TOKEN` | 2 | por pessoa | Painel do Coolify, Keys & Tokens, API tokens, com permissão de deploy. A conta no Coolify quem cria é o Pedro. |
| `COOLIFY_BASE_URL` | 2 | config | Já vem no `.env.example`. |
| `ANA_API_KEY` | opcional | compartilhada | 1Password, VITTA TECH, item "Ana API key" (criar). É a mesma chave de produção. Só para smoke test. |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | opcional | por pessoa | Conta GitHub própria, PAT clássico com escopo `repo`. Só para rodar Actions localmente; o `gh` das skills usa o `gh auth login`. |

## hospital-reunioes/.env (nível 2: três valores fictícios)

Só para o snapshot do `/deploy ship` conseguir importar o app. O script do `/setup-maquina` cria o arquivo com `ENVIRONMENT=development`, `SUPABASE_URL=http://127.0.0.1:54351` e `SUPABASE_SERVICE_ROLE_KEY=dummy-local` (o mesmo endereço do `.env.example`; o valor só precisa existir). Nada real, nada do 1Password. Chave vazia liga o mock de LLM e de email.

Chaves de produção: só no Coolify. A lista e o "quem mexe" estão no `README.md` da raiz, seção "Variáveis de ambiente".

## hospital-reunioes/.env (nível 3: rodar o app local, opcional)

| Chave | Tipo | Origem |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | por pessoa | Saída de `supabase status` depois de `supabase start` em `hospital-reunioes/`. |
| `OPENROUTER_API_KEY` | por pessoa ou compartilhada | 1Password, VITTA TECH, item "OpenRouter" (criar). Vazia liga o mock de IA. |
| `CLICKSIGN_API_KEY` (sandbox) | compartilhada | 1Password, VITTA TECH, item "ClickSign sandbox" (criar). |
| `SMTP_USER`, `SMTP_PASSWORD` | por pessoa | Senha de app do Gmail de quem roda. Vazio imprime o email no log. O Supabase local lê os mesmos nomes de `hospital-reunioes/supabase/.env` (molde em `supabase/.env.example`). |
| `GA4_PROPERTY_ID` | compartilhada | 1Password, VITTA TECH, item "Central de Comando Google" (criar). Peça ao Pedro: `GA4_PROPERTY_ID`, serve para a Central de Comando saber qual propriedade do Google Analytics é o Site. |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | compartilhada | 1Password, VITTA TECH, item "Central de Comando Google" (criar), o mesmo da linha de cima. Peça ao Pedro: `GOOGLE_APPLICATION_CREDENTIALS_JSON`, serve para a Central de Comando entrar no Google Analytics com a service account. |
| `INSTAGRAM_ACCESS_TOKEN` | compartilhada | 1Password, VITTA TECH, item "Central de Comando Instagram" (criar). Peça ao Pedro: `INSTAGRAM_ACCESS_TOKEN`, serve para a Central de Comando ler o Instagram do hospital. |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | compartilhada | 1Password, VITTA TECH, item "Central de Comando Instagram" (criar), o mesmo da linha de cima. Peça ao Pedro: `INSTAGRAM_BUSINESS_ACCOUNT_ID`, serve para a Central de Comando saber qual conta profissional do Instagram ler. |
| `GA4_EVENTO_WHATSAPP`, `GA4_EVENTO_FALE_CONOSCO` | config | Vazias usam `wa_click` e `generate_lead`, os mesmos da produção. Não precisa pedir. |
| `RESEND_API_KEY` | só produção | 1Password, VITTA TECH, item "Resend". Não entra no local. |
| `GH_TOKEN_HOMOLOG` | só produção | 1Password, HOSPITAL SÃO MATHEUS, item "Global Health". É a agenda de homologação, não é GitHub. Não entra no local. |
| `FIREFLIES_*`, `DIRETOR_EMAIL`, `DEFAULT_USER_PASSWORD` | só produção | Vivem no Coolify. |

**Credencial do Google, armadilha de formato:** no app antigo da Central (`CentraldeComando`) a chave se chama `GOOGLE_APPLICATION_CREDENTIALS` e guarda o caminho de um arquivo JSON; aqui a variável é `GOOGLE_APPLICATION_CREDENTIALS_JSON` e guarda o JSON inteiro da service account, numa linha só, entre aspas simples. Copiar o nome ou o valor de um para o outro não funciona: a tela mostra "Sem ligação com o Google Analytics" e, abaixo, o motivo. Com o nome antigo, diz que falta configurar `GOOGLE_APPLICATION_CREDENTIALS_JSON`; com o caminho no lugar do JSON, diz que a chave não é de uma service account e pede o conteúdo inteiro do arquivo. Leia essa linha, ela diz o que corrigir.

**Origem das chaves da Central:** hoje o valor real mora no Coolify de produção (backend, #826) e no app antigo. O Pedro cria os dois itens "Central de Comando" no cofre uma vez, e o mesmo item serve ao `.env` local e ao Coolify. Sem as chaves, a Central local fica desligada e diz que falta configurar, nunca mostra zero.

## Onde cada variável mora

| Arquivo | Quem lê | O que vai nele |
|---|---|---|
| `tokens/.env` | `/deploy`, `/ship`, `/onda` (CLI do Coolify) | `COOLIFY_ACCESS_TOKEN` (seu), `COOLIFY_BASE_URL`, `ANA_API_KEY` (opcional) |
| `hospital-reunioes/.env` | backend local e o snapshot do `/deploy ship` | Os três valores fictícios do nível 2; o resto só no nível 3 |
| `hospital-reunioes/frontend/.env.local` | `pnpm dev` (opcional) | `NEXT_PUBLIC_*` do Supabase local |
| Coolify (produção) | os containers | Todas as chaves reais (`env_keys` em `docs/spec/deploy/project.json`; `/deploy setup` confere). Nunca no clone |
| GitHub Actions | CI | Nenhum secret: valores fictícios no próprio `ci.yml` |

## Serviços: o que o sócio precisa e como conseguir

| Serviço | Para quê | O que você precisa | Como conseguir |
|---|---|---|---|
| **GitHub** (`pedrorezendefig/hospital-reunioes`) | Issues, PRs, CI, merge | Permissão WRITE e `gh auth login` | O Pedro adiciona você como colaborador; depois `gh auth login` |
| **Coolify** (`https://coolify.hospitalsaomatheus.cloud`) | Deploy, status, rollback, env de produção | Conta na instância e um token seu | O Pedro cria a conta. Você gera o token em Keys & Tokens, grava em `tokens/.env` e cria o contexto `hsm` (`claude-setup.md` seção 4.1) |
| **Supabase de produção** (`https://studio.hospitalsaomatheus.cloud`) | Aplicar migration, conferir tabela | Acesso ao Studio | Hoje só o Pedro. O `/ship` entrega o SQL e espera o humano aplicar |
| **App em produção** (`https://app.hospitalsaomatheus.cloud`; API em `api.hospitalsaomatheus.cloud/api/health`) | Testar o que subiu | Um usuário no app | O Pedro cria pelo admin |
| **Resend** | Email transacional | Nada na sua máquina | Chave só no Coolify (1Password, VITTA TECH, item "Resend"). Logs de envio: peça acesso ao painel |
| **ClickSign** | Assinatura de Ata e POP | Nada para o fluxo normal | Produção no Coolify; sandbox só no nível 3 |
| **OpenRouter** | LLM das Atas, POPs e Ouvidoria | Nada para o fluxo normal | Chave só no Coolify; local usa mock com chave vazia |
| **Global Health** | Espelho da agenda | Nada | Token de homologação só no Coolify (1Password, HOSPITAL SÃO MATHEUS, item "Global Health") |
| **Ana** (agente de IA externa) | Consome a API da Ouvidoria | `ANA_API_KEY` só para smoke test | 1Password, VITTA TECH, item "Ana API key" (criar) |
| **Vercel** | Publicar divulgação e manual | Membro do time | O Pedro convida. Sem isso a CLI recusa com `TEAM_ACCESS_REQUIRED` |
| **1Password** (cofre VITTA TECH) | Onde as chaves compartilhadas moram | Acesso ao cofre | O Pedro compartilha. Você copia à mão; nenhuma skill acessa o cofre |
| `REVIEWER_LOGINS` (variável do repo) | Papel de revisor humano (hoje o Pedro) | Nada | Dev não entra: faria o próprio agente disparar o loop `revisor-comentou` |
| Migration em produção | Schema | Acesso ao Studio | Humano, no SQL Editor. Só o Pedro hoje |
