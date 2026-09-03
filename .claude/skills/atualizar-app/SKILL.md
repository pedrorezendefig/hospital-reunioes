---
name: atualizar-app
description: Rebuilda a stack docker-compose local (frontend + backend) com o código da working copy, com preview antes de aplicar. Use para subir, atualizar ou reiniciar o app em localhost.
---

# Atualizar stack local do Hospital Reuniões

Esta skill derruba e reconstrói a stack `docker-compose.yml` do projeto (`hr-frontend` em :3000 + `hr-backend` em :8000) usando o código atual da working copy. Antes de qualquer mudança, mostra um **preview** do que vai acontecer — estado atual, o que mudou desde o último build, o que vai ser derrubado/construído, quais portas são afetadas e o que NÃO vai ser tocado. O usuário confirma, aí executa.

O valor é **previsibilidade**: toda subida local passa pelo mesmo caminho, com o mesmo diagnóstico, nas mesmas portas canônicas (3000 e 8000). Acaba a confusão de "por que a 3000 tá com versão velha" ou "qual porta o Next subiu dessa vez".

## Objetivo da skill

Você terminou quando:
- O usuário viu o preview e confirmou (ou pediu `--preview`/`--dry-run` e você só mostrou).
- A stack subiu, o healthcheck do backend respondeu e o frontend retornou 200.
- Você devolveu as URLs finais (http://localhost:3000 e http://localhost:8000/api).

Se algo falhar no meio (build quebra, healthcheck não responde), pare, mostre as últimas ~30 linhas do log do serviço afetado, e diga ao usuário o que você acha que é — sem tentar "consertar sozinho" a stack rodando `docker system prune`, `rm -rf node_modules`, ou coisa agressiva. Problemas de build são do código, não da skill.

## Flags

O usuário pode indicar modo explicitamente; inferir da frase dele:

- **(sem flag)** → preview + confirmação + executa. Caminho padrão.
- **`--yes` / `-y` / "sem perguntar" / "direto"** → pula confirmação. Usa quando o usuário deixou claro que já sabe o que quer ("sobe direto", "manda bala", "sem preview").
- **`--preview` / `--dry-run` / "só preview" / "só me mostra o que vai acontecer"** → mostra o preview e PARA. Não executa. Serve pra debuggar a stack sem mudar nada.

Se o usuário não foi explícito, use o modo padrão (preview + confirmação).

## Pré-requisitos

Antes de rodar qualquer coisa, cheque em uma única rodada paralela:

1. **Docker Desktop ativo** — `/Applications/Docker.app/Contents/Resources/bin/docker ps` tem que responder sem erro. Se não, avise o usuário pra abrir o Docker Desktop e pare.
2. **Arquivo `.env` existe** em `hospital-reunioes/.env`. Se não existir, `docker compose` quebra com erro de variável — avise antes.
3. **`docker-compose.yml` existe** em `hospital-reunioes/docker-compose.yml`. Sanidade básica.

Se qualquer pré-req faltar, pare e informe. Não improvise.

## Workflow

### Fase 1 — Preview

Rode o script de preview:

```bash
bash .claude/skills/atualizar-app/scripts/preview.sh
```

O script imprime um bloco formatado com:
- Estado atual dos containers `hr-frontend` e `hr-backend` (rodando/parado + idade da imagem)
- Quem ocupa :3000 e :8000 agora (Docker nosso, Docker alheio, processo não-Docker, ou livre)
- Git diff resumido em `hospital-reunioes/frontend/` e `hospital-reunioes/backend/`
- Passos que serão executados, com estimativas de tempo
- URLs que vão ficar disponíveis no final
- O que NÃO é tocado (Supabase CLI, outros projetos)

Se o script detectar **conflito não-Docker** em :3000 ou :8000 (ex: `next dev` órfão de outra sessão, outro projeto ocupando a porta), ele inclui essa linha no preview com destaque. Nesse caso, você precisa **pedir confirmação explícita** antes de matar esse processo — pode ser algo do usuário que ele esqueceu que estava rodando.

Mostre o output do script integralmente para o usuário. Não resuma.

### Fase 2 — Confirmação

Se o modo for `--preview`/`--dry-run`: pare aqui. Skill concluída.

Se o modo for `--yes`: pule direto pra Fase 3.

Modo padrão: pergunte "Prosseguir? [s/N]" e aguarde resposta. Só avance com "s", "sim", "y", "yes" ou equivalente. Qualquer outra coisa = aborta, skill termina.

### Fase 3 — Executar

Rode:

```bash
bash .claude/skills/atualizar-app/scripts/apply.sh
```

O script:
1. Mata processos não-Docker em :3000/:8000 se o preview detectou (e o usuário confirmou na Fase 2).
2. `docker compose down` no `hospital-reunioes/`.
3. `docker compose up -d --build` — aproveita cache de layers.
4. Aguarda healthcheck do backend (`GET /api/health` → 200) por até 60s.
5. Aguarda frontend responder 200 em `http://localhost:3000` por até 60s.
6. Se tudo ok, imprime as URLs finais e sai com código 0.
7. Se algo falhar, imprime as últimas 30 linhas de `docker compose logs` do serviço problemático e sai com código != 0.

**Enquanto roda**, o script imprime marcos ("derrubando stack", "buildando frontend", "aguardando backend", "ok"). Repasse esses marcos pro usuário conforme chegam, pra ele saber onde está.

### Fase 4 — Confirmar sucesso

Quando `apply.sh` termina com sucesso, confirme ao usuário:

> Stack no ar. Frontend: http://localhost:3000 · Backend: http://localhost:8000/api
> (build demorou Xs — rebuild de Y / cache de Z)

Se falhou, confirme a falha citando o serviço e as linhas de log mais relevantes. Sugira o que o usuário pode olhar (ex: "o build do frontend quebrou em `pnpm install`, provável mudança de deps — rode `pnpm install` local pra ver o erro").

## O que NÃO fazer

- **Nunca mate** processos em portas que não sejam :3000 ou :8000. O preview detecta; o usuário decide.
- **Nunca rode** `docker system prune`, `docker volume rm`, `docker image rm`, `rm -rf node_modules` ou qualquer limpeza agressiva "pra tentar resolver". Quebra de build se resolve lendo o erro.
- **Nunca toque** nos containers do Supabase CLI (nomes começam com `supabase_`). Eles são de outro stack.
- **Nunca toque** em containers fora do compose do hospital (sem prefixo `hr-`).
- **Nunca improvise** `npm run dev` solto fora do compose. A stack é via docker — é a premissa da skill.

## Limitação conhecida

Essa skill rebuilda a imagem Docker do frontend a cada invocação (modo produção `next build` + `node server.js`). Isso significa **sem hot-reload no frontend** — cada mudança no código exige rodar a skill de novo. O cache de layers do Docker torna isso rápido (~5-15s quando só o src muda), mas não é instantâneo.

Se o usuário pedir hot-reload de frontend, explique que isso requer mudar o `Dockerfile` do frontend pra usar `pnpm dev` + volume funcional (o volume atual em `docker-compose.yml` é ilusório porque o Dockerfile serve o bundle pré-compilado). Isso é mudança no projeto, não na skill — ofereça fazer separado.
