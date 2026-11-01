---
name: divulgar
description: Vídeo de percepção de valor (MP4 narrado, feito com a skill motion) e página de divulgação na Vercel de um PRD entregue. Sintaxe `/divulgar <PRD> [--so-video | --so-pagina]`. Fonte em docs/comunicacao/<contexto>/, MP4 em ~/Videos/Hospital/.
---

# Divulgar

Fecha uma entrega para o diretor e para o usuário funcional em **dois passos, um comando**:

1. **Vídeo de Percepção de Valor** (MP4 narrado): o diretor assiste e **vê o sistema funcionando**, sem jargão. Um exemplo único, com dados de exemplo, seguido de ponta a ponta nas telas reais do app.
2. **Página de divulgação** (HTML na Vercel): uma explicada leve no que mudou, com o vídeo embutido. Um link compartilhável.

**Divisão de trabalho fixa:** o vídeo demonstra, a página explica. A página não tem passo a passo, stepper, réplica de tela nem simulação. Se a explicação precisar "mostrar", ela aponta para a aba do vídeo.

**O que isto NÃO é:** changelog, PRD, doc de arquitetura. Não existe "como foi implementado". Se sobrar migration, endpoint, PR, deploy ou RLS em texto visível ou falado, a skill falhou (gate anti-técnica).

## Entrada

`/divulgar <N> [--so-video | --so-pagina]`. N é uma issue entregue ou um PRD (issue mãe). PRD agrega as fatias filhas numa demonstração só: o caso de uso completo, não uma demonstração por fatia.

- Sem flag: os dois passos, com o gate humano do vídeo entre eles.
- `--so-video`: só o passo 1 (para WhatsApp, e-mail, TV).
- `--so-pagina`: só o passo 2, quando o MP4 já está em `~/Videos/Hospital/`.

## Onde cada coisa mora

**Nenhum MP4 no repositório**, nem rascunho (regra 10 do CLAUDE.md global).

`docs/comunicacao/<contexto>/<PRD>-<slug>/` é a casa da fonte daquela entrega (ADR 0045):

- `video/`: a **fonte do vídeo**, versionada:
  - `roteiro.md`: o briefing da skill `copy`, os três ganchos e o escolhido, a narração final e a tabela de cenas (fala, tela capturada, transição de entrada, paradas planejadas em segundos).
  - `narracao.txt`: o texto que a voz A lê (um parágrafo por cena).
  - `tempos.json`: o tempo de cada palavra no formato da skill `motion` (`references/tempos.md`), convertido do `narracao.json` do `narrar.py`.
  - `capturas/*.png`: as telas reais do app, capturadas pelo `playwright-cli`.
  - `cena/`: a composição Remotion (`src/videos/<Nome>/` do projeto de trabalho: `<Nome>.tsx` e o que mais a cena usar).
  - `meta.json`: o carimbo legível por máquina (abaixo).
- `index.html`: a página de divulgação. Versionada. Referencia `logo-hsm.png`, `HPSimplified_Rg.ttf` e `<PRD>-<slug>.mp4` relativos, que **não ficam na pasta**: o deploy copia os três.
- `.vercel/`: vínculo com o projeto da Vercel. Fora do git.

Fora do repositório:

- **Projeto de trabalho do Remotion:** `${TMPDIR}divulgar/<PRD>-<slug>/`, uma cópia do projeto modelo da skill `motion` com `node_modules`, `public/narracao.wav` e `out/`. É descartável: tudo que precisa voltar fica em `video/`.
- **Vídeo final:** `~/Videos/Hospital/AAAA-MM-DD-<PRD>-<slug>.mp4` (regra 10). Nunca sobrescreva: refazer o vídeo gera `-v2`, `-v3`. O deploy usa o mais novo.

Regras da pasta mãe: uma subpasta por contexto de domínio (`reunioes/`, `pops/`, `ouvidoria/`), nome `<PRD>-<slug>` (número na frente ordena e garante unicidade; slug curto em kebab-case). **Sem data no nome e sem índice paralelo**: pasta, nome e `meta.json` são o índice.

**Entregas antigas** (a composição em `video/` é HyperFrames, com `hyperframes.json`): ficam como estão. Refazer o vídeo de uma delas é fazer de novo por esta receita.

**Página de módulo** (vários PRDs numa vitrine só, caso `ouvidoria/modulo/`): só `index.html`, embutindo os MP4 dos PRDs por nomes fixos (`fase-1.mp4`, `fase-2.mp4`). O deploy copia cada um do `~/Videos/Hospital/` com o nome que a página espera.

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **A issue no GitHub**: `gh issue view <N> --comments`. Para PRD, também as filhas. As user stories e os critérios de aceite viram os passos da demonstração, um a um. **Critério de aceite não coberto = vídeo incompleto.** Não inventar passo que a issue não aborda.
2. **O app rodando**, com o código do PRD: as telas do vídeo são capturas dele, não réplica de memória.
3. **`docs/spec/snapshots/`** (ROTAS.md, FLUXOGRAMAS.md): o caminho de navegação real até a tela.
4. **`CONTEXT.md` e o CONTEXT do contexto** (ex.: `docs/pops/CONTEXT.md`): vocabulário canônico. Sempre o termo do glossário, nunca sinônimo inventado, na tela e na fala.

## Passo 1: o vídeo

**Antes de tudo, leia as skills globais:** `motion` (o `SKILL.md` e, inteiros, `references/guia-motion.md`, `references/catalogo.md` e `references/tempos.md`), `narracao`, `copy` e `marca-hsm`. Os valores do guia (ritmo, easing, transições, checklist) são o padrão; esta receita só diz o que muda no Hospital.

**Especificação:** 1920x1080, 30 fps constante, 45 a 90 s, narrado com a voz A e legível no mudo: a fala aparece na tela como texto cinético, palavra a palavra, quando é dita (`<Fala>` da skill motion).

### 1. Copy e roteiro

1. **Briefing e ganchos pela skill `copy`:** quem vê é o diretor do módulo (e o usuário funcional), a única ideia é o que a entrega muda no dia dele, a prova são os critérios de aceite. Três ganchos de tipos diferentes, um escolhido.
2. **Roteiro fixo:**
   - **Gancho (2 a 4 s):** o momento do dia a dia que a entrega resolve, em uma frase falada e escrita. **Nada de tela de título com metadado** ("PRD #N", versão, data de geração): o vídeo abre no gancho.
   - **Antes e depois (condicional, 3 a 5 s):** só quando a issue descreve uma situação anterior real. **Nunca inventar dor fictícia.**
   - **Demonstração ponta a ponta (o vídeo é isso):** um exemplo único, do primeiro clique ao resultado, nas telas capturadas. Cobre **todos** os critérios de aceite, na ordem do caso de uso real. Uma frase por cena.
   - **Fecho:** uma virada curta (o que a pessoa ganha) e a assinatura com a logo do hospital **inteira e parada** (`marca-hsm`), a única parada planejada do vídeo.
3. **Gate anti-técnica (no texto falado e no escrito):** varrer procurando `migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt`. Cada ocorrência vira linguagem funcional ou sai. Varrer também travessão e meia-risca.
4. **Humanizer (ADR 0071):** a narração e todo texto de tela passam pela Skill tool com `humanizer` em modo embutido, depois da `copy`. A amostra de voz é o `video/roteiro.md` de uma entrega anterior em `docs/comunicacao/` (na falta de uma em motion, a página de referência do Passo 2): ela manda no tom, o humanizer só tira os cacoetes. Nome de botão e de tela, igual ao app, não muda.
5. Grave tudo em `video/roteiro.md` e a narração final em `video/narracao.txt`.

### 2. Telas reais

Capture as telas com o **`playwright-cli`** contra o app local com o código do PRD, com **dados de exemplo** do hospital, verossímeis e fictícios (CME, Farmácia, UTI; nomes que não existem). Nunca dado real: o repositório é público. O preparo do app local (Supabase, `/atualizar-app`, login, seed) é o da `/manual`: `.claude/skills/manual/references/prints.md`.

```bash
playwright-cli open http://localhost:3000/<rota>
playwright-cli resize 1920 1080
playwright-cli snapshot                # refs para clicar e preencher
playwright-cli click <ref>             # ou fill <ref> "<texto>"
playwright-cli screenshot              # salve em video/capturas/NN-<passo>.png
```

Uma captura por estado que a demonstração mostra (antes do clique, campo preenchido, resultado). Tire o foco antes de capturar. Confira a versão no rodapé do app: captura de versão velha mostra a tela errada.

### 3. Narração e tempos

1. `python3 ~/.claude/voz/narrar.py --file video/narracao.txt --output "$W/public/narracao.wav"` (voz A, padrão aprovado, skill `narracao`). Se o VoiceStudio falhar, pare e avise: nunca outra voz.
2. Converta o `narracao.json` (tempo de cada palavra) para o `tempos.json` da skill motion: uma cena por parágrafo, `inicio_s` na primeira palavra da cena. Corrija a grafia, não os tempos. Grave em `video/tempos.json`.

### 4. Composição em Remotion

1. **Projeto de trabalho**, fora do repo:

   ```bash
   W="${TMPDIR}divulgar/<PRD>-<slug>"
   mkdir -p "$W" && cp -R ~/.claude/skills/motion/projeto/. "$W"/ && rm -rf "$W/node_modules"
   cp docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$W/public/fonts/"
   cp docs/comunicacao/_assets/logo-hsm.png "$W/public/"
   cp video/capturas/*.png "$W/public/"
   (cd "$W" && npm install)
   ```

   No `remotion.config.ts` do projeto de trabalho, `Config.setChromiumOpenGlRenderer('swangle')` (skill `narracao`: sem isso o texto treme).
2. **Identidade do Hospital no projeto de trabalho** (nunca no modelo da skill):
   - Fonte: **HP Simplified** em todo texto (`Fontes.tsx` e `FONTEM` apontando para `fonts/HPSimplified_Rg.ttf`), peso 400, sem negrito falso.
   - `PALETA` em `src/tema.ts` com as cores do app (`globals.css` do frontend: `#2B2E7E`, `#3B6FB6`, `#1A1C4E`) e da `marca-hsm` (`#1E1D57`, `#1D3F98`, `#EEF2FA`): fundo azul-marinho escuro, um acento só (azul claro), texto claro. Sem verde do modelo, sem vermelho (`alerta` não é usado).
   - Logo só na assinatura, inteira e parada (`marca-hsm`): nunca como transição, moldura ou motivo.
3. **Cenas:** copie `src/videos/demo/` para `src/videos/<Nome>/` e monte uma cena por frase. Cada captura entra como imagem dentro da `<Camera>` (push-in de 1 para 1,05 a 1,16, balanço leve), com cursor fantasma, destaque no elemento que a fala cita e campo que se preenche sozinho quando a fala diz. **Nada parado mais de 0,5 s**: câmera viva, cascata, luz correndo. Todo evento preso a uma palavra (`c.local(fala[i].s)`), nunca a quadro fixo. Easing do guia (`sai`, `corte`, `suave`, molas), nunca linear em coisa visível. **Uma transição diferente do catálogo em cada corte**, com áudio `audio="narracao.wav"` no `<VideoMontado>`.
4. **Conferir:** `npx tsc --noEmit` e stills (`node scripts/stills.mjs <Comp> out/stills 0.5 <quadros>`) no meio de cada cena, no pico de cada transição e 2 quadros depois de uma palavra-chave. Abra e passe o checklist da seção 9 do guia: telas batem com o app, todos os critérios de aceite aparecem, texto legível, zero jargão, zero travessão.
5. **Draft:** `npx remotion render src/index.ts <Comp> out/draft.mp4 --scale=0.5` e **OK humano** no draft. Ajuste pedido = novo draft, novo OK.
6. **Volta para o repo:** copie `src/videos/<Nome>/` para `video/cena/` e grave `video/meta.json`:

   ```json
   {"prd": 210, "issues": [221, 222], "contexto": "pops", "titulo": "<texto puro>",
    "app_version": "0.43.0", "gerado_em": "<ISO-8601 com timezone>",
    "duracao_s": 62, "paradas": ["58.5-62"], "mp4": "2026-11-01-210-<slug>.mp4"}
   ```

   `app_version` vem de `hospital-reunioes/frontend/package.json`. O carimbo é só este arquivo: nada de versão, PRD ou data escritos no vídeo.

### 5. Render final e gate anti-travamento

```bash
npx remotion render src/index.ts <Comp> out/<PRD>-<slug>.mp4
bash .claude/skills/divulgar/scripts/gate-video.sh "$W/out/<PRD>-<slug>.mp4" --parada <ini>-<fim>
```

O gate confere fps constante 30 (`ffprobe`), nenhum congelamento de 0,5 s ou mais fora das paradas declaradas (`ffmpeg -vf freezedetect=n=-60dB:d=0.5`) e o vídeo tocando no **Chrome real** (Playwright com `channel="chrome"`, servido por HTTP; o Chromium do Playwright não toca H.264). `--parada` é cada janela de `paradas` do `meta.json`. **Falhou, não entrega:** conserte a cena, renderize de novo, rode o gate de novo.

Passou: mova (nunca copie) para `~/Videos/Hospital/`, sem sobrescrever, e apague o draft:

```bash
mkdir -p ~/Videos/Hospital
F=~/Videos/Hospital/$(date +%F)-<PRD>-<slug>.mp4   # existe? some -v2, -v3
mv -n "$W/out/<PRD>-<slug>.mp4" "$F" && rm -f "$W/out/draft.mp4"
open "$F"
```

Confira que o arquivo chegou e sumiu da origem antes de dizer que entregou.

## Passo 2: a página

**Referência de implementação:** `docs/comunicacao/reunioes/272-pendencia-nasce-na-assinatura/index.html`. Página nova = copiar essa como base e trocar o conteúdo, mantendo estrutura e design.

**Design system: o do app, sempre.** A página replica o `globals.css` do frontend, não inventa identidade:
- Fonte **HP Simplified** em tudo (fallback `system-ui, -apple-system, sans-serif`), `html { font-size: 17px }`.
- Tokens copiados do `globals.css`: `--color-primary #2B2E7E`, `--color-primary-light #3B6FB6`, `--color-primary-dark #1A1C4E`, texto `#1E293B`, secundário `#64748B`, borda `#E2E8F0`, fundo branco, `--shadow-premium`, radius corporativo (xl 6px, 2xl 8px, 3xl 12px; pill 9999px).
- Antes de compor, conferir o `globals.css` atual: se os tokens mudaram no app, a página segue o app.

**Estrutura fixa:**
1. **Cabeçalho:** logo real do hospital + nome do contexto + selo "em produção".
2. **Hero:** uma frase de título com o valor da entrega + um parágrafo de resumo.
3. **Abas em barra flutuante no rodapé (liquid glass):** `Funcionalidade` e `Demonstração por Vídeo` numa barra pill fixa na parte de baixo da viewport, centralizada (`position: fixed; bottom: ~22px; left: 50%`). Receita do `.glass-card` do app: `background: rgba(255,255,255,.8)`, `backdrop-filter: blur(12px) saturate(160%)`, borda `rgba(255,255,255,.5)`, `--shadow-premium-strong`. Aba ativa = pill navy com texto branco. `padding-bottom` no body; aba ativa no hash da URL (`#funcionalidade` / `#video`). **Nunca** como linha de tabs no topo.
4. **Aba Funcionalidade** (a explicação leve, nada além): *O problema* em um parágrafo; *O que mudou* em cards compactos (título + 1 a 2 frases), um por mudança; *Na prática*, checklist de até 5 itens; CTA para a aba do vídeo.
5. **Aba Demonstração por Vídeo:** um parágrafo de contexto (o exemplo seguido; o vídeo tem narração e legenda na tela, então funciona com ou sem som) + `<video controls>` com `<PRD>-<slug>.mp4` + linha de carimbo (`duração · PRD #N · retrata o app em vX.Y.Z · gerado em DD/MM/AAAA`, dados do `video/meta.json`).
6. **Rodapé:** contexto, mês/ano e versão do app.

**Regras de conteúdo:** linguagem de negócio, vocabulário do `CONTEXT.md`, mesmo gate anti-técnica do vídeo. Enxuto de verdade: seção da aba Funcionalidade que passa de uma tela de leitura, cortar. pt-BR, sem travessão nem meia-risca (`grep -Pn "\x{2013}|\x{2014}" index.html`). Verificar com o `playwright-cli` (screenshot das duas abas) antes de publicar.

**Humanizer no texto da página (antes de publicar, ADR 0071):** hero, cards de *O que mudou*, checklist e parágrafo da aba do vídeo passam pela Skill tool com `humanizer` em modo embutido. A amostra de voz é a página de referência (`272-pendencia-nasce-na-assinatura/index.html`): ela manda no tom, o humanizer só tira os cacoetes. HTML, classes e carimbo ficam iguais.

**Publicação (pela CLI, sem pedir ao humano).** Deploy de dentro do repo é BLOQUEADO pela Vercel (`TEAM_ACCESS_REQUIRED`: a CLI anexa o autor git, que não é membro do time). Sempre de uma cópia FORA do repo, só com o que a página precisa. O MP4 vem do `~/Videos/Hospital/` (o mais novo daquele PRD) com o nome que a página embute:

```bash
P=docs/comunicacao/<contexto>/<PRD>-<slug>; D=$(mktemp -d)
V=$(ls -t ~/Videos/Hospital/*-<PRD>-<slug>*.mp4 | head -1)
cp "$P"/index.html "$D"/ && cp "$V" "$D/<PRD>-<slug>.mp4" && cp -R "$P"/.vercel "$D"/ 2>/dev/null
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$D"/
cd "$D" && npx vercel@latest deploy --prod --yes
```

O link compartilhável é o **alias de produção** (`https://<projeto>.vercel.app`, sem hash): URLs de deployment com hash caem no SSO da Vercel. Entregar o link e registrá-lo em comentário no PRD. Ajuste depois = editar no repo, recopiar, redeployar. A pasta temporária é apagada depois do deploy.

## Checklist de saída

1. Todos os critérios de aceite têm passo na demonstração; as telas são capturas do app real.
2. Roteiro pela `copy` e pelo `humanizer`; abre no gancho, sem tela de metadado; vocabulário do glossário, zero jargão, zero travessão, tudo em HP Simplified.
3. Narração na voz A; a fala aparece na tela quando é dita; uma transição diferente em cada corte; nada parado mais de 0,5 s fora da assinatura.
4. `gate-video.sh` passou no MP4 final; OK humano no draft.
5. MP4 final em `~/Videos/Hospital/AAAA-MM-DD-<PRD>-<slug>.mp4`, nenhum MP4 no repositório nem em `out/`; `video/` (roteiro, narração, tempos, capturas, cena, `meta.json`) e `index.html` commitados.
6. Página publicada, link no PRD. Se existe página de módulo do contexto, ela foi republicada com o MP4 novo.
