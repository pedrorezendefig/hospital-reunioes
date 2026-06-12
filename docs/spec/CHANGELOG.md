# Changelog Hospital Reuniões

Cronologia de deploys e mudanças importantes em ordem reversa (mais recente no topo).
Prepended pelo `/deploy ship` ao final do ciclo (ou manualmente quando o PR é meta — só skills/docs).

A partir de **v0.2.0** as entradas seguem o formato `## v0.X.Y — DATA — tipo(escopo): descrição`, com bump automático decidido pelo `/ship` (BREAKING > feat > fix/chore). Entradas mais antigas usam o formato `## YYYY-MM-DD HH:MM - tipo(escopo): descrição` — preservadas como histórico, sem retrofit de versão. Esquema completo descrito em [VERSIONING.md](VERSIONING.md).

---

## 2026-06-11 21:41 — Vínculo do responsável honrado fim a fim: dropdown da validação grava, liberação respeita
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `43bc069`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (163s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/43bc069

## 2026-06-11 17:57 — Calendário: verde consistente de concluído + lixeira discreta no hover
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `9adfa62`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (176s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/9adfa62

## 2026-06-11 17:38 — Ata Guiada conclui e gera pendências num clique
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `2e84450`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (210s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/2e84450

## 2026-06-11 14:56 — documento de apoio na Ata Guiada (contexto sob demanda)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `21906cb`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (206s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/21906cb

## 2026-06-11 14:31 — correção por apontar seção (⌖) na Ata Guiada
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4b42056`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (269s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4b42056

## v0.16.0 — 2026-06-11 — feat(reunioes): Ata Guiada em tela dedicada (ata viva + chat texto/voz)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `9bb9dd3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (174s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/9bb9dd3
- PR: https://github.com/pedrorezendefig/hospital-reunioes/pull/60 (Closes #57)

## 2026-06-11 03:30 — Ata Guiada F4 - distincao visual (badge metodo_geracao) + esconder acoes por Transcricao
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `d078493`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (152s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/d078493

## 2026-06-11 02:59 — Ata Guiada F3 - ditar o relato por voz (hook useGravacaoVoz)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a99319c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (177s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a99319c

## 2026-06-11 01:46 — Ata Guiada F2 - IA hibrida real do agente (OpenRouter)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `f11ce59`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (136s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/f11ce59

## 2026-06-11 01:00 — Ata Guiada — esqueleto + persistência (IA mock)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `18c3454`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (159s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/18c3454

## v0.11.0 — 2026-06-10 — feat(notas): multi-select estilizado de participantes

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#46](https://github.com/pedrorezendefig/hospital-reunioes/pull/46) · Issue: [#43](https://github.com/pedrorezendefig/hospital-reunioes/issues/43)
- Commit: `25a670b`
- Resultado: 🟢 healthy (backend 42s, frontend 214s)

**Resumo:** Segunda fatia das correções da **Nota** (PRD #42) — troca o `<select>` nativo de "Adicionar do cadastro…" (dropdown preto do SO) por um **dropdown estilizado com busca + multi-seleção**, alinhado ao design. Novo componente `RosterCadastroSelect` (picker controlado: reusa o vocabulário visual do `MultiSelect`, **não** guarda chips — a fonte da verdade segue sendo o roster acima; marca vários com ✓ e o dropdown fica aberto; fecha por clique-fora/Escape). No `notas/page.tsx` o `<select>` vira o componente, com `toggleRosterCadastro` reusando `adicionarRosterCadastro`/`removerRoster`; o fetch de participantes sobe pra `limit=200` (antes cortava em 50, escondendo parte do cadastro da busca). Campo "Ou nome avulso (externo)…" e chips âmbar **intactos**. Só **frontend** (backend rebuildou no-op por `watch_paths=null`). **Gates:** code-review high (sem achados — `tsc --noEmit` + `next build` verdes; sem `overflow-hidden` no card → dropdown não clipa), security-review N/A (não toca auth/permissões/schema/env), CI 3/3. `APP_VERSION` 0.10.1→0.11.0. Health pós: backend 200 `version:0.11.0` (`db:healthy`, 120ms), frontend 200 (100ms). **Verificação visual manual pendente** (fatia visual — conferir logado no app).

## v0.10.1 — 2026-06-10 — fix(backend): transcrição da Nota via OpenRouter + OpenRouter-only

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#45](https://github.com/pedrorezendefig/hospital-reunioes/pull/45) · Issue: [#44](https://github.com/pedrorezendefig/hospital-reunioes/issues/44)
- Commit: `c6896bf`
- Resultado: 🟢 healthy (backend 127s, frontend 181s)

**Resumo:** Conserta o **"Gravar voz"** da Nota (#35), que falhava 100% com **502** — a transcrição era enviada como multipart do SDK OpenAI, mas o OpenRouter espera um corpo **JSON com o áudio em base64**. Agora `transcricao_service.transcrever` chama `POST {OPENROUTER_BASE_URL}/audio/transcriptions` via **httpx** com `{model, input_audio:{data:<base64>, format}, language:"pt"}`, autenticado com a `OPENROUTER_API_KEY`, e lê o texto do campo `text` (áudio segue **não persistido**; interface `transcrever(audio, formato) → texto` inalterada; falha real → `TranscricaoIndisponivelError` → 502 com aviso de digitação). De quebra, torna o projeto **100% OpenRouter**: remove a chave e o **fallback automático da OpenAI** dos serviços de IA (ata, chat de correção, extração, transcrição) — `_llm_provider` vira `openrouter`/`mock` e `chat_correcao`/`_chamar_llm` perdem o failover (erro claro, sem fallback); no painel admin a integração "OpenAI" vira **"OpenRouter"** (status pela chave + teste de conexão no endpoint autenticado `/key`); `OPENAI_API_KEY`/`LLM_FALLBACK_MODEL` saem de `config.py`, `.env.example`, `supabase/config.toml`, `project.json` e do **Coolify** (deletadas via MCP — 2 ocorrências cada). O **pacote pip `openai` permanece** (é o cliente usado pra falar com o OpenRouter em chat). **Testes:** `test_transcricao_voz_nota` reescrito p/ o contrato base64 (mock de `httpx.post`, valida endpoint/payload/headers/erros); testes de IA ajustados (sem chave/fallback OpenAI) — **315 passam**. **Gates:** code-review high (1 achado refutado — `parsed` só é lido após o `return` do `except`), security-review (sem vulnerabilidade; PR reduz superfície de ataque), CI 3/3. `APP_VERSION` 0.10.0→0.10.1. Health pós: backend 200 `version:0.10.1` (`db:healthy`, 126ms), frontend 200 (185ms).

## v0.10.0 — 2026-06-09 — feat(notas): comando por voz na Nota

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#41](https://github.com/pedrorezendefig/hospital-reunioes/pull/41) · Issue: [#35](https://github.com/pedrorezendefig/hospital-reunioes/issues/35)
- Commit: `71c7325`
- Resultado: 🟢 healthy (backend 50s, frontend 170s)

**Resumo:** Quarta fatia da **Nota** (#31) — ditar a Nota por **voz**, o uso-canônico. No editor, o Facilitador grava um áudio (MediaRecorder), ele é transcrito e o **texto cai editável no corpo** para revisar antes de salvar (não cria a Nota sozinho). **Backend:** módulo profundo `transcricao_service.transcrever(audio, formato) → texto` reusa a chave/billing do Pipeline (`_get_llm`) chamando `/audio/transcriptions` do OpenRouter com `gpt-4o-mini-transcribe` (default `openai/gpt-4o-mini-transcribe`, `language=pt`); endpoint `POST /notas/transcrever` (UploadFile, autenticado) — áudio **não é persistido** (bytes em memória → texto), teto de 25 MB (413), `anyio.to_thread` pra não bloquear o event loop, falha → 502 com aviso de fallback. **Frontend:** botão "Gravar voz" no editor (estados gravando/transcrevendo, microfone liberado no cancelar, `AbortController` cancela transcrição em voo ao fechar). **Testes:** 11 novos com OpenRouter 100% mockado (299 total). **Gates:** code-review (6 achados corrigidos pré-merge — MIME `;codecs`, prefixo do modelo, vazamento de microfone, limite/anyio, race), security-review (sem achados), CI 3/3. `APP_VERSION` 0.9.0→0.10.0. Health pós: backend 200 `version:0.10.0` (`db:healthy`), frontend 200 (1.2s).

## v0.9.0 — 2026-06-09 — feat(notas): Extração de Pendências por IA (propõe-confirma) + roster

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#40](https://github.com/pedrorezendefig/hospital-reunioes/pull/40) · Issue: [#34](https://github.com/pedrorezendefig/hospital-reunioes/issues/34)
- Commit: `60d6fc9`
- Resultado: 🟢 healthy (backend 187s, frontend 340s)

**Resumo:** Terceira fatia da **Nota** (ADR 0004) — a mágica central: a partir do corpo, a **IA propõe** Pendências que o Facilitador revisa e **confirma** antes de criar (a confirmação é a guarda contra alucinação). **Backend:** migration `043` cria `nota_participantes` (roster: Colaborador do cadastro **ou** nome avulso, CHECK de origem única + unique por Nota) — aplicada manualmente no Studio **antes do merge**; endpoints `GET/PUT /notas/{id}/participantes` (acesso herda a Nota) e `POST /notas/{id}/extrair-pendencias` (propõe sem persistir; Secretária 403, alheia/arquivada 404, IA fora → 502); módulo profundo `extracao_pendencias_service` reusa o passo de estruturação JSON do Pipeline (OpenRouter + fallback OpenAI), casa responsável **roster-first** → cadastro (externo fica só como nome) e converte prazo de linguagem natural ("sexta", "semana que vem") com DATA BASE injetada + parse determinístico; 2 prompts novos; `_find_participante` passa a devolver `nome_completo` (aditivo). **Frontend:** editor da Nota com "Quem participou" (chips cadastro/avulso), botão ✨ de extrair e painel de propostas editáveis (descartar individual, confirmar em lote via endpoint da fatia #33). **Testes:** 16 novos com LLM 100% mockado (288 total). **Gates:** code-review (1 achado corrigido — docstring desatualizada, reincidência do PR #37), security-review (nenhuma vulnerabilidade), CI 3/3. `APP_VERSION` 0.8.0→0.9.0. Este deploy substituiu o `a105587` (PR #39, conversor PDF/DOCX, sessão paralela) minutos depois — leva as duas features. Health pós: backend 200 `version:0.9.0` (`db:healthy`, 104ms), frontend 200 (122ms).

## 2026-06-09 18:12 — Conversor PDF/DOCX → Markdown para Super Admins (sem tokens de IA)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a105587`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (231s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a105587

## v0.8.0 — 2026-06-09 — feat(pendencias): Pendência com origem Nota (add manual)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#37](https://github.com/pedrorezendefig/hospital-reunioes/pull/37) · Issue: [#33](https://github.com/pedrorezendefig/hospital-reunioes/issues/33)
- Commit: `28a6347`
- Resultado: 🟢 healthy (backend ~48s, frontend ~221s)

**Resumo:** Segunda fatia da **Nota** (ADR 0004) — a **Pendência** passa oficialmente a ter **duas origens**: Reunião terminal (ASSINADA/APROVADA) ou **Nota**, via add manual do Facilitador (descrição, responsável escolhido do cadastro, prazo). **Backend:** migration `042` adiciona `pendencias.id_nota` (FK → notas, ON DELETE CASCADE) + CHECK de origem única `(id_reuniao IS NOT NULL) <> (id_nota IS NOT NULL)` + índice do FK — aplicada manualmente no Studio de produção **antes do merge**. `pendencia_service` refatorado: núcleo compartilhado `_inserir_pendencias` (IDs `A###` na sequência global) usado por `liberar_pendencias` e pelo novo `criar_pendencias_de_nota` (idempotente por conteúdo; responsável resolvido da fonte canônica). Endpoint `POST /notas/{id}/pendencias` (autor ou Super admin; Secretária 403; 404 anti-enumeration; Nota arquivada não aceita). Visibilidade origem Nota nos pontos que assumiam `id_reuniao`: GET/PATCH/list/stats de pendências e os 3 endpoints de comentários (helper `nota_pertence_ao_participante`); contador `acoes_concluidas` só com Reunião de origem. **Frontend:** form de add manual na página de Notas (descrição + responsável do cadastro + prazo); painel, kanban e modal exibem a origem Nota graciosamente. **Testes:** 15 novos (272 total). **Gates:** code-review (1 achado corrigido — docstring desatualizada), security-review (1 MEDIUM corrigido — gate uniforme da Secretária no add manual), CI 3/3. `APP_VERSION` 0.7.0→0.8.0. Health pós: backend 200 `version:0.8.0` (`db:healthy`, 168ms), frontend 200 (1.9s).

## v0.7.0 — 2026-06-09 — feat(notas): CRUD, histórico e acesso da Nota

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#36](https://github.com/pedrorezendefig/hospital-reunioes/pull/36) · Issue: [#32](https://github.com/pedrorezendefig/hospital-reunioes/issues/32)
- Commit: `b96b57a`
- Resultado: 🟢 healthy (backend ~179s, frontend ~249s)

**Resumo:** Fatia fundadora da **Nota** (ADR 0004) — entidade leve e **paralela** à Reunião, para registrar conversas, feedbacks e eventos sem a cerimônia Reunião → Transcrição → Ata → ClickSign. Esta fatia entrega o núcleo: **CRUD + histórico + acesso** (sem roster de Participantes, Pendências ou voz — fatias seguintes). **Backend:** migration `041` cria a tabela `notas` (`id` UUID, `corpo`, `autor_id` → participantes, `created_at`/`updated_at`, `deleted_at`; índice parcial das vivas; RLS default-deny) — aplicada manualmente no SQL Editor do Supabase Studio de produção **antes do merge** (Postgres self-hosted não exposto; gate de migration agora nas skills). Router `/notas` (`POST`, `GET` histórico ordenado por mais recente, `GET/PATCH/DELETE {id}`) com acesso **espelhando a Reunião**: autor vê só as suas, Secretária e Super admin veem todas; editar/arquivar por autor ou Super admin; `404` anti-enumeration para quem não pode ver; arquivar é **soft-delete** (`deleted_at`), sem hard-delete. **Frontend:** rota `/notas` (histórico + editor de corpo + arquivar) + link na Sidebar. **Testes:** 8 cobrindo os 6 critérios de aceite (257 total). **Gates:** code-review (5 finders + verificação; 2 fixes aplicados — fecha janela de race no `UPDATE` e cobre `DELETE` da Secretária), security-review (limpo — sem SQL injection, authz/IDOR correto, RLS ok, sem XSS), CI 3/3. `APP_VERSION` 0.6.2→0.7.0. Auto-deploy via webhook no merge (`watch_paths=null` rebuilda os dois). Health pós: backend 200 `version:0.7.0` (`db:healthy`), `/api/notas` 401 sem auth (rota viva), frontend 200 e `/notas` 307 (redirect login).

## 2026-06-05 20:11 — Email editado pelo admin agora vale para o login (sincroniza Supabase Auth)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `94b2288`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (144s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/94b2288

## v0.6.1 — 2026-06-05 — fix(frontend): crash na busca de participante com cargo nulo

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#28](https://github.com/pedrorezendefig/hospital-reunioes/pull/28)
- Commit: `b0ec2bf`
- Resultado: 🟢 healthy (frontend ~181s, backend ~151s)

**Resumo:** Correção de crash client-side ao adicionar participante. Ao abrir **"Adicionar participante"** numa reunião existente e começar a digitar no campo "Buscar por nome ou cargo...", o app quebrava com *"Application error: a client-side exception has occurred"*. Causa: o filtro de busca em `reunioes/[id]/page.tsx` chamava `.toLowerCase()` direto em `cargo`, que é nullable no backend desde a migration `037` (secretárias não têm cargo hospitalar). Com o campo vazio o short-circuit do `||` (`nome_completo.includes("")` é sempre `true`) escondia o problema; ao digitar um termo que **não casava o nome** de um colaborador com `cargo` nulo, o JS avaliava `null.toLowerCase()` → `TypeError`. Fix mínimo (2 linhas): null-coalescing `(p.cargo ?? "")` no filtro + tipo da interface `ParticipanteCadastrado` alinhado ao backend (`cargo: string | null`), que com `strict:true` passa a exigir o null-check — fechando a defasagem aberta desde a `037`. Sem migration. Gates: code-review (4 revisores independentes, sem issues), CI 3/3 (backend tests, frontend lint+tsc, docker build), security-review N/A (diff só `.tsx`, não-sensível). `APP_VERSION` 0.6.0→0.6.1. Auto-deploy via webhook no merge (`watch_paths=null` rebuilda os dois): frontend ~181s, backend ~151s (rebuild sem mudança de código). Health pós: backend 200 em 117ms (`status:healthy`, `db:healthy`, `version:0.6.1` → version match ok), frontend 200 em 142ms.

## v0.6.0 — 2026-06-02 — feat(aprovacao): finalizar Ata sem assinatura (estado APROVADA)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#27](https://github.com/pedrorezendefig/hospital-reunioes/pull/27) · Issue: [#26](https://github.com/pedrorezendefig/hospital-reunioes/issues/26)
- Commit: `2e9652c`
- Resultado: 🟢 healthy (backend ~215s, frontend ~288s, migration 040 aplicada via Studio)

**Resumo:** Novo caminho terminal na validação da Ata. Além de **"Enviar para assinatura"** (fluxo ClickSign inalterado), o Facilitador agora tem **"Finalizar sem assinatura"**: as Pendências nascem na hora e a Reunião vai direto para o estado terminal **`APROVADA`**, sem Envelope e sem aguardar assinaturas — pensado para reuniões operacionais, onde o valor está em registrar a Ata e disparar as tarefas. Endpoint `POST /reunioes/{id}/aprovar-sem-assinatura` (irmão do `/aprovar`, mesmas guardas: Secretária 403, status 400, 404), **síncrono** (retorna `total_pendencias`), reusando `liberar_pendencias` (idempotente) e gravando auditoria `APROVACAO_SEM_ASSINATURA`. Schema: `StatusAta.APROVADA` no enum + migration `040` (CHECK) + tipo `StatusAta` no frontend (2 locais). UX: `ConfirmDialog` com contagem e aviso de ausência de assinatura, timeline no ramo "Aprovada", banner próprio (distinto do verde "Assinada") com link para Pendências, sem card de Signatários. Glossário e máquina de estados em `CONTEXT.md` + decisão em `ADR 0003` (gatilho da Pendência = `ASSINADA` **ou** `APROVADA`). 8 testes novos (suíte backend 241 verde); 3 gates verdes (code-review com 2 correções aplicadas, security-review sem achados, CI 3/3). `APP_VERSION` 0.5.1→0.6.0. Health pós: backend 200 em 83ms (`db:healthy`, `version:0.6.0`), frontend 200 em 123ms. A migration 040 foi aplicada manualmente no Supabase Studio (SSH temporariamente no fail2ban) e confirmada (`'APROVADA'` no CHECK).

## 2026-05-28 11:12 — Status real de assinatura: card passa a refletir quem realmente assinou no ClickSign
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `b471893`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (212s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/b471893

## 2026-05-27 19:05 — Fallback de assinatura: aviso humano + link pro painel ClickSign quando o Envelope não é recuperável
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `655a5a6`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (224s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/655a5a6

## v0.4.0 — 2026-05-27 — feat(backend): self-heal do Envelope ClickSign (status real pré-039)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#22](https://github.com/pedrorezendefig/hospital-reunioes/pull/22) · Issue: [#20](https://github.com/pedrorezendefig/hospital-reunioes/issues/20)
- Commit: `ed87233`
- Resultado: 🟢 healthy (backend auto-deploy ~140s + redeploy 109s p/ aplicar APP_VERSION, frontend ~182s)

**Resumo:** Recuperação automática do `envelope_id` ClickSign + status real por signatário em Atas **pré-039** (criadas antes da migration `039_add_envelope_id_clicksign`, que não tinham `envelope_id_clicksign` gravado). Quando o card de signatários consulta uma Ata legada, o backend agora faz self-heal: descobre o envelope a partir dos dados disponíveis, persiste o `envelope_id` e passa a exibir o status live (assinou / pendente) em vez da faixa amarela "legacy". Mudança em `routers/reunioes.py` (+45) e `services/clicksign_service.py` (+74), com 356 linhas novas de teste em `test_signatarios_status.py`. **Efetivação da v0.4.0 em prod:** a entrada v0.4.0 de 22/05 (bc2f8ab) era um bump aspiracional — o `package.json` do frontend já estava em 0.4.0, mas o `APP_VERSION` do backend no Coolify ficou em `0.3.1`, então o `/api/health` mentia a versão. Este deploy fecha isso: o auto-deploy via webhook rodou no merge (ainda com 0.3.1, pois o sync do `/ship` falhou na sessão anterior por MCP Coolify em 403 — restrição de IP no token), e nesta sessão, com token/IP liberados no `coolify.mala-ia.cloud`, o `APP_VERSION` foi setado `0.3.1 → 0.4.0` (runtime) + redeploy do backend (`f5tqsd2`, force, 109s, sem OOM). Agora `/api/health` retorna `version:0.4.0`, batendo com o rodapé do frontend. Sem migration nova (039 já aplicada no PR #16). Health pós-deploy: backend 200 em 78ms (`status:healthy`, `db:healthy`), frontend 200 em 155ms.

---

## v0.4.0 — 2026-05-22 — feat(clicksign): card de signatários com status + lembrete; remove modo sandbox

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#16](https://github.com/pedrorezendefig/hospital-reunioes/pull/16) · Issue: —
- Commit: `bc2f8ab`
- Resultado: 🟢 healthy (backend 29s, frontend 120s, migration 039 aplicada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Substitui o card "Aguardando Assinatura Digital" (parágrafo genérico + bloco DEV laranja "Simular Sandbox" — dead-code em prod por causa de `ENABLE_BYPASS_ENDPOINTS=false`) pelo novo **`SignatariosCard`** com lista live de signatários. Cada linha mostra avatar + nome + email + badge verde com timestamp ("Assinou em DD/MM HH:MM") ou amarelo com botão "✉ Lembrar" pra signatários pendentes. Contador "X de Y assinaram", botão "⟳ Atualizar" (refresh manual com spin) e auto-poll a cada 30s via `usePolling`. Botão "Lembrar" envia POST que chama ClickSign pra reenviar email de assinatura com template PT-BR custom (cooldown visual de 60s pós-click). **Backend:** 2 endpoints novos — `GET /reunioes/{id}/signatarios/status` (rate-limit 60/min, consulta ClickSign v3 + enriquece com nome local + modo degradado pra reuniões pré-migration) e `POST /reunioes/{id}/signatarios/{signer_id}/lembrar` (rate-limit 10/min, template em PT-BR via mensagem custom no notification do ClickSign). 2 métodos novos em `clicksign_service`: `list_signers(envelope_id)` (`GET /api/v3/envelopes/{id}/signers` com normalização) e `remind_signer(envelope_id, signer_id, message)`. `start_signature_flow` agora grava `envelope_id_clicksign` no banco (separado de `envelope_key_clicksign` que continua sendo o `document_id` usado pelo webhook — nomes legados v1). **Sandbox eliminado:** 4 endpoints removidos (`/aprovar-bypass`, `/aprovar-bypass-todas`, `/simular-assinatura`, helper `_executar_simulacao`), flag `enable_bypass_endpoints` + validator `validate_bypass_prod` em `config.py`, teste `test_secretaria_403_em_aprovar_bypass`, linha `ENABLE_BYPASS_ENDPOINTS=false` em `.env.example`, entrada em `runtime_required` + `prod_only_assertions` em `docs/spec/deploy/project.json`. **Migration 039:** `ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS envelope_id_clicksign TEXT` — aditiva, idempotente, executada como `supabase_admin` (user `postgres` não era owner da tabela; documentado no chronicle). Reuniões pré-deploy ficam com coluna NULL e a UI exibe faixa amarela "legacy" + desabilita botão Lembrar. **Cobertura:** `test_signatarios_status.py` novo com 19 testes (7 endpoint status, 6 endpoint lembrar, 3 service list_signers, 3 service remind_signer) cobrindo paths felizes + 4xx/5xx + cenários legacy. 203/203 testes verdes (incluindo o hotfix do PR1). CI 3/3 SUCCESS (Backend Lint 26s, Frontend Lint+TSC 41s, Docker 2m24s). Self-approval/merge direto via `gh pr merge 16 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend 29s + frontend 120s. Health backend 97ms, frontend 115ms. **APP_VERSION mantido em 0.3.1 no Coolify** — bump aspiracional pra v0.4.0 registrado neste CHANGELOG mas o `/api/health` e o rodapé do frontend continuam exibindo `0.3.1` até o próximo deploy real que rebuilde frontend com `NEXT_PUBLIC_APP_VERSION` atualizado.

---

## v0.3.2 — 2026-05-22 — fix(matcher): sincronizar reuniao_participantes na correção de ata (bug 7→4 ClickSign)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#15](https://github.com/pedrorezendefig/hospital-reunioes/pull/15) · Issue: —
- Commit: `385d9c7`
- Resultado: 🟢 healthy (backend 37s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Hotfix do bug "7→4" relatado pelo diretor: quando ele corrigia o número de participantes via Chat de Correção (ex: IA extraía 7 nomes, ele removia 3 → 4), o ClickSign recebia o envelope com **os 7 emails originais** (incluindo os 3 removidos), em vez dos 4 corrigidos. Causa raiz em `backend/app/services/participant_matcher.py:292-411` — `match_participants()` fazia apenas UPSERT em `reuniao_participantes`, nunca DELETE. Era correto pro fluxo de extração inicial (pré-vinculados que a IA não cita continuam válidos como "convidados que não falaram"), mas no fluxo de correção a tabela junção ficava corrompida. Fix cirúrgico: kwarg novo `prune_missing: bool = False` (default = comportamento legado preservado). `run_correction_pipeline:411` opta-in com `prune_missing=True` (modo SYNC: delete + upsert). Adicionado `all_matched_this_pass: set[str]` que coleta TODOS os matches (inclusive pré-vinculados re-confirmados), permitindo distinguir "pré-vinculado confirmado" de "pré-vinculado removido pelo diretor". Mock `_Query` em `test_participant_matcher.py` estendido com `.delete().eq().in_().execute()`. 7 testes novos em `TestSyncPruneMissing` (canônico 7→4, regressão off, idempotente, lista vazia, renomeação, `link_on_match=False`, isolamento por id_reuniao) + arquivo novo `test_correction_pipeline_sync.py` com 2 testes de integração (run_correction_pipeline → 4 rows persistem; start_signature_flow → add_signer chamado 4× com emails corretos). 203/203 testes verdes. CI 3/3 SUCCESS (Backend Lint+Tests 24s, Docker 41s, Frontend Lint+TSC 32s). Self-approval/merge direto via `gh pr merge 15 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend em 37s. Health `https://api.hospitalsaomatheus.cloud/api/health` 200 em 1.15s. **APP_VERSION mantido em 0.3.1** (sem bump no Coolify; PR2 sequencial bump pra 0.4.0). **Pendência manual pós-deploy:** reuniões hoje em `AGUARDANDO_ASSINATURA` com envelope errado precisam tratamento caso a caso (cancel ClickSign + force-status + reaprovar).

---

## v0.3.1 — 2026-05-22 — fix(secretaria): habilitar edição de participantes na tela Editar reunião

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#11](https://github.com/pedrorezendefig/hospital-reunioes/pull/11) · Issue: —
- Commit: `2e745ab`
- Resultado: 🟢 healthy (backend 36s, frontend 169s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Bug reportado pelo Pedro — a tela "Editar reunião" (rota `/secretaria/nova?edit=`) escondia o `<MultiSelect />` de participantes em modo edição. A secretária ficava sem visão pra adicionar/remover quem participa de uma reunião futura. Fix em 1 arquivo TSX (`hospital-reunioes/frontend/src/app/secretaria/nova/page.tsx`, +101 −18): MultiSelect agora aparece também em edição, populado com snapshot inicial de `participantes_programada`. `handleSubmit` calcula diff (`toAdd = atual − iniciais`, `toRemove = iniciais − atual − [facilitadorId]`) e chama `POST/DELETE /api/reunioes/:id/participantes` em paralelo via `Promise.allSettled` (originalmente `Promise.all`, ajustado pelo `/code-review` pra não mascarar o sucesso do PATCH em erro de rede). `useEffect` re-injeta o facilitador automaticamente caso seja desmarcado. Backend já aceitava a operação pela secretária — endpoints sem gate de role, só exigem `status_ata == PROGRAMADA`. 5 camadas de gate verdes (`/code-review`, `/security-review` sem findings, `superpowers:requesting-code-review` aprovou com follow-ups arquiteturais registrados, CI 3/3 SUCCESS, `verification-before-completion` com tsc+lint+build local exit=0). Bump patch automático 0.3.0 → 0.3.1. Self-approval bloqueado pelo GitHub free; merge segue direto via `--admin`. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`).

---

## v0.3.0 — 2026-05-22 — feat(reunioes,secretaria): dropdown responsável + visão global da secretária com gate em ata/pendência

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#10](https://github.com/pedrorezendefig/hospital-reunioes/pull/10) · Issue: —
- Commit: `805daa0`
- Resultado: 🟢 healthy (backend 2m42s, frontend 3m43s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Mescla dois escopos numa única release. **(1) Dropdown responsável na correção da ATA** — substitui edição implícita via chat por combobox inline de participantes na coluna RESPONSÁVEL do quadro de atribuições; resolve bug "Josiane" (nome trocava mas cargo continuava stale). Endpoint novo `PATCH /reunioes/{id}/quadro-atribuicoes/{index}`, helper `_canonicalize_cargos_quadro` no orchestrator pós-IA, `pendencias.cargo` agora populado em `liberar_pendencias` (era NULL antes), componente `ResponsavelInlineCombobox.tsx`. **(2) Expansão do papel secretária** — antes só via PROGRAMADAS futuras, agora vê o calendário do hospital inteiro (qualquer status, qualquer data) e gerencia participantes em reuniões PROGRAMADAS (inclusive alheias). Defense-in-depth: **20 gates 403 explícitos** nos endpoints de ata/pendência/comentário (12 reuniões + 5 pendências + 3 comentários), `get_allowed_reuniao_ids` retorna `None` pra secretária, `_redact_ata_fields` redacta `json_ata`/`url_pdf_*` nos endpoints de leitura, gate de visibilidade adicionado em `PATCH /quadro-atribuicoes/{index}`. Frontend: flag `hideAtaSections` em 14 pontos do detalhe da reunião + esconde botão "Desmarcar" e "Anexar Transcrição" pra secretária. Bump 0.2.1 → 0.3.0 (feat=minor). 3 reviewers automatizados (code-review + security-review + superpowers:requesting-code-review) detectaram 3 must-fix em iteração — todos resolvidos antes do merge: critical de `json_ata` leak em `GET /reunioes/{id}`, must-fix de visibilidade no PATCH quadro e ausência de teste de gates. Novo arquivo `tests/test_secretaria_gates.py` com 9 testes cobrindo os 3 routers + edge case `me=None`. Suite final: 186/186 passa. CI 3/3 verde. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.1 — 2026-05-22 — fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#9](https://github.com/pedrorezendefig/hospital-reunioes/pull/9) · Issue: —
- Commit: `d3cc4a1`
- Resultado: 🟢 healthy (build frontend 169s; backend não redeployado, só env APP_VERSION sincronizada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Footer.tsx perde o wrapper `<a target=_blank>` que apontava pro CHANGELOG no GitHub e muda de `text-center` pra `text-right pr-4`. Versão agora é texto puro alinhado ao canto inferior direito (padrão visual de apps profissionais — não compete com conteúdo). Aria-label mantido pra screen readers. Bump patch automático `0.2.0 → 0.2.1` (tipo dominante: fix). APP_VERSION sincronizada no backend Coolify (`mcp__coolify__env_vars update`, runtime-only) pré-merge — backend NÃO foi redeployado, só o env mudou e o `/api/health` já reflete `version:0.2.1`. Frontend rebuild Docker em 169s (cache quente). Gates: code-review max-effort (3 agents, 1 nit aplicado `px-4` → `pr-4`), security e requesting-code-review pulados (mudança cosmética de 4 linhas em 1 arquivo de UI), CI verde, verification verde (tsc + lint). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.0 — 2026-05-22 — feat(app): acrescentar versionamento visível na aplicação

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#8](https://github.com/pedrorezendefig/hospital-reunioes/pull/8) · Issue: —
- Commit: `1efd175`
- Resultado: 🟢 healthy (build backend 198s, frontend 255s, health ok com version match)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** primeiro PR de versionamento. Rodapé `v0.2.0` clicável em todas as páginas do AppShell (link → CHANGELOG.md no GitHub). Backend `/api/health` retorna `version` lido de env `APP_VERSION` (default `0.1.0`). Footer.tsx novo lê `NEXT_PUBLIC_APP_VERSION` inlined em build-time pelo `next.config.ts` a partir de `package.json` (bumpado 0.1.0 → 0.2.0 manualmente neste PR; nos próximos é automático via /ship Passo 5.5). Skill `/ship` ganha bump automático de semver por tipo de commit (BREAKING > feat > fix/chore) + Passo 8.5 que sincroniza APP_VERSION no Coolify pré-merge (evita race com webhook). Skill `/deploy` ganha Passo 3.5 defensivo idempotente + Passo 7.2 version match check (rollback automático se /api/health não retorna versão esperada). Docs novos: `VERSIONING.md` (esquema completo) + header explicativo no CHANGELOG.md. 5 camadas de gate verdes antes do merge — 4 issues do code-review e 2 do requesting-code-review corrigidos em-band nos commits 3136a5c e 4a5fc8d.

---

## 2026-05-21 20:39 - feat(skills): automatizar /snapshot via script Python

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `70bac46`
- PR: [#7](https://github.com/pedrorezendefig/hospital-reunioes/pull/7) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** implementa o gerador real do `/snapshot` que estava só documentado no PR #6. Script Python self-contained (993 linhas, stdlib only) em `.claude/skills/snapshot/scripts/snapshot.py` com parser AST de routers FastAPI (78 endpoints em 13 routers), parser SQL cumulativo de migrations (13 tabelas das 36 migrations), 5 geradores de MD, idempotência via comparação de buffer e flags CLI (`--check`, `--force`, `--only`, `--diff`, `--no-commit`). Code-review pegou 1 bug score 100 (JSONB DEFAULT corrompendo parser de colunas) + 3 issues score 75, todas corrigidas antes do merge.

---

## 2026-05-21 18:58 - feat(workflow): integrar Superpowers + /snapshot vivo + 5 camadas de gate

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e9f64ee`
- PR: [#6](https://github.com/pedrorezendefig/hospital-reunioes/pull/6) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — PR só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** integra plugin Superpowers v5.1.0 no workflow do time. Cria skill `/snapshot` (gera 7 MDs vivos em `docs/spec/snapshots/` regenerados a cada deploy via `/deploy ship`). `/start` ganha Modo D (retomar trabalho parado de outra sessão) + invocação de `brainstorming` por default no Modo A. `/ship` ganha 5 camadas independentes de gate antes do self-approval (code-review, security-review, requesting-code-review, CI Actions, verification-before-completion). `CLAUDE.md` reescrito com 5 seções novas. CI Actions ganha job `build` (docker sanity). Cleanup de 150+ skills `reversa-*` absorvido no mesmo PR (-26338 linhas).
