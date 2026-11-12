---
name: divulgar
description: Vídeo de percepção de valor (MP4 narrado, feito no Motion studio pela skill motion-studio) e página de divulgação na Vercel de um PRD entregue. Sintaxe `/divulgar <PRD> [--so-video | --so-pagina]`. Fonte em docs/comunicacao/<contexto>/, MP4 em ~/Videos/Hospital/.
---

# Divulgar

Fecha uma entrega para o diretor e para o usuário funcional em **dois passos, um comando**:

1. **Vídeo de Percepção de Valor** (MP4 narrado): o diretor assiste e **vê o sistema funcionando**, sem jargão. Um exemplo único, com dados de exemplo, seguido de ponta a ponta nas telas reais do app.
2. **Página de divulgação** (HTML na Vercel): uma explicada leve no que mudou, com o vídeo embutido. Um link compartilhável.

**Divisão de trabalho fixa:** o vídeo demonstra, a página explica. A página não tem passo a passo, stepper, réplica de tela nem simulação. Se a explicação precisar "mostrar", ela aponta para a aba do vídeo.

**O que isto NÃO é:** changelog, PRD, doc de arquitetura. Não existe "como foi implementado". Se sobrar migration, endpoint, PR, deploy ou RLS em texto visível ou falado, a skill falhou (gate anti-técnica).

## Entrada

`/divulgar <N> [--so-video | --so-pagina]`. N é uma issue entregue sem PRD (um bug, por exemplo) ou um PRD (issue mãe). PRD agrega as fatias filhas numa demonstração só: o caso de uso completo, não uma demonstração por fatia.

- Sem flag: os dois passos, com as duas paradas do Pedro no vídeo (lista de tomadas e folha de quadros).
- `--so-video`: só o passo 1 (para WhatsApp, e-mail, TV).
- `--so-pagina`: só o passo 2, quando o MP4 já está em `~/Videos/Hospital/`.

## Onde cada coisa mora

**Nenhum MP4 no repositório**, nem rascunho (regra 10 do CLAUDE.md global).

`docs/comunicacao/<contexto>/<PRD>-<slug>/` é a casa da fonte daquela entrega (ADR 0045):

- `video/`: a **fonte do vídeo**, versionada:
  - `roteiro.md`: o briefing da skill `copy`, os três ganchos e o escolhido, a narração final e a tabela de cenas (fala, tela capturada, transição de entrada, paradas planejadas em segundos).
  - `narracao.txt`: o texto que a voz B lê (um parágrafo por cena). A voz B aceita emoção por parágrafo: o parágrafo que começa com `[animada]` (ou outra marca da skill `narracao`) sai naquele tom.
  - `tempos.json`: o tempo de cada palavra, convertido do `narracao.json` do `narrar.py`. O filme lê este arquivo para prender cada evento a uma palavra.
  - `capturas/*.png`: as telas reais do app, capturadas pelo `playwright-cli`.
  - `cena/`: a cópia do filme do Motion studio (o `index.html` e a pasta `docs/` de `films/<pasta>/`, sem `assets/` nem `out/`). O estúdio não é versionado: esta cópia é a fonte que fica.
  - `meta.json`: o carimbo legível por máquina (abaixo), com o campo `filme` apontando para a pasta do filme no Motion studio.
- `index.html`: a página de divulgação. Versionada. Referencia `logo-hsm.png`, `HPSimplified_Rg.ttf` e `<PRD>-<slug>.mp4` relativos, que **não ficam na pasta**: o deploy copia os três.
- `.vercel/`: vínculo com o projeto da Vercel. Fora do git.

Fora do repositório:

- **Filme no Motion studio:** `~/PedroDev/Videos/motion-studio/films/<AAAA-MM-DD>-<PRD>-<slug>/`, criado do `modelo` do estúdio, com `assets/` (capturas, logo, fonte, `narracao.wav`) e `out/` (prévias, folha de quadros, render). Tudo que precisa voltar ao repositório fica em `video/`.
- **Vídeo final:** `~/Videos/Hospital/AAAA-MM-DD-<PRD>-<slug>.mp4` (regra 10). Nunca sobrescreva: refazer o vídeo gera `-v2`, `-v3`. O deploy usa o mais novo.

Regras da pasta mãe: uma subpasta por contexto de domínio (`reunioes/`, `pops/`, `ouvidoria/`), nome `<PRD>-<slug>` (número na frente ordena e garante unicidade; slug curto em kebab-case). **Sem data no nome e sem índice paralelo**: pasta, nome e `meta.json` são o índice.

**Entregas antigas** (a composição em `video/` é HyperFrames, com `hyperframes.json`, ou um componente `.tsx` em `video/cena/`): ficam como estão. Refazer o vídeo de uma delas é fazer de novo por esta receita.

**Página de módulo** (vários PRDs numa vitrine só, caso `ouvidoria/modulo/`): só `index.html`, embutindo os MP4 dos PRDs por nomes fixos (`fase-1.mp4`, `fase-2.mp4`). O deploy copia cada um do `~/Videos/Hospital/` com o nome que a página espera.

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **A issue no GitHub**: `gh issue view <N> --comments`. Para PRD, também as filhas. As user stories e os critérios de aceite viram os passos da demonstração, um a um. **Critério de aceite não coberto = vídeo incompleto.** Não inventar passo que a issue não aborda.
2. **O app rodando**, com o código do PRD: as telas do vídeo são capturas dele, não réplica de memória.
3. **`docs/spec/snapshots/`** (ROTAS.md, FLUXOGRAMAS.md): o caminho de navegação real até a tela.
4. **`CONTEXT.md` e o CONTEXT do contexto** (ex.: `docs/pops/CONTEXT.md`): vocabulário canônico. Sempre o termo do glossário, nunca sinônimo inventado, na tela e na fala.

## Passo 1: o vídeo

**Antes de tudo, carregue a skill `motion-studio`** (Skill tool) e leia o que ela manda: o `CLAUDE.md` do estúdio inteiro, `prompts/produto.md` e `prompts/critica.md`. Leia também as skills globais `narracao`, `copy`, `som` e `marca-hsm`. As rules do estúdio (contrato de render, molas, look, som, crítica) são o padrão; esta receita só diz o que muda no Hospital. O filme é o `index.html` do estúdio, renderizado pelo `render.mjs` dele, sem outro framework de vídeo.

**Especificação:** 1920x1080 (formato `16x9`), 60 fps constante no render final (`--final`), 45 a 90 s, narrado com a voz B e legível no mudo: a fala aparece na tela como texto cinético, palavra a palavra, quando é dita (presa ao `tempos.json`).

**Duas paradas do Pedro** (ADR 0018 do PedroOS), e só essas: a **lista de tomadas**, antes de escrever o código do filme, e a **folha de quadros** com o `phone.png` e as notas, antes do render final. Em cada uma, mostre e espere o "pode". Ajuste pedido = nova lista ou nova folha, novo "pode".

### 1. Copy e roteiro

1. **Briefing e ganchos pela skill `copy`:** quem vê é o diretor do módulo (e o usuário funcional), a única ideia é o que a entrega muda no dia dele, a prova são os critérios de aceite. Três ganchos de tipos diferentes, um escolhido.
2. **Roteiro fixo:**
   - **Gancho (2 a 4 s):** o momento do dia a dia que a entrega resolve, em uma frase falada e escrita. **Nada de tela de título com metadado** ("PRD #N", versão, data de geração): o vídeo abre no gancho.
   - **Antes e depois (condicional, 3 a 5 s):** só quando a issue descreve uma situação anterior real. **Nunca inventar dor fictícia.**
   - **Demonstração ponta a ponta (o vídeo é isso):** um exemplo único, do primeiro clique ao resultado, nas telas capturadas. Cobre **todos** os critérios de aceite, na ordem do caso de uso real. Uma frase por cena.
   - **Fecho:** uma virada curta (o que a pessoa ganha) e a assinatura com a logo do hospital **inteira e parada** (`marca-hsm`), a única parada planejada do vídeo.

   Issue sem PRD (bug, melhoria, design) tem roteiro próprio, do mesmo molde: o gancho é a situação que o bug causava ou que a melhoria resolve, e a demonstração segue os critérios de aceite dela.
3. **Gate anti-técnica (no texto falado e no escrito):** varrer procurando `migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt`. Cada ocorrência vira linguagem funcional ou sai. Varrer também travessão e meia-risca.
4. **Humanizer (ADR 0071):** a narração e todo texto de tela passam pela Skill tool com `humanizer` em modo embutido, depois da `copy`. A amostra de voz é o `video/roteiro.md` de uma entrega anterior em `docs/comunicacao/` (na falta de uma feita no Motion studio, a página de referência do Passo 2): ela manda no tom, o humanizer só tira os cacoetes. Nome de botão e de tela, igual ao app, não muda.
5. Grave tudo em `video/roteiro.md` e a narração final em `video/narracao.txt`.

### 2. Telas reais

Capture as telas com o **`playwright-cli`** contra o app local com o código do PRD, com **dados de exemplo** do hospital, verossímeis e fictícios (CME, Farmácia, UTI; nomes que não existem). Nunca dado real: o repositório é público. Antes de capturar: Supabase local no ar (`supabase start` em `hospital-reunioes/`; se o PostgREST não subir, `supabase stop` e `supabase start`), a stack com o código do PRD (`bash .claude/skills/atualizar-app/scripts/apply.sh`, conferindo que a tela nova está no build) e, para tela de dentro do app, login com a senha do `DEFAULT_USER_PASSWORD` do `.env` local, nunca a de produção.

```bash
playwright-cli open http://localhost:3000/<rota>
playwright-cli resize 1920 1080
playwright-cli snapshot                # refs para clicar e preencher
playwright-cli click <ref>             # ou fill <ref> "<texto>"
playwright-cli screenshot              # salve em video/capturas/NN-<passo>.png
```

Uma captura por estado que a demonstração mostra (antes do clique, campo preenchido, resultado). Tire o foco antes de capturar. Confira a versão no rodapé do app: captura de versão velha mostra a tela errada.

### 3. Filme novo no estúdio

```bash
M=~/PedroDev/Videos/motion-studio
F="$M/films/$(date +%F)-<PRD>-<slug>"
cp -R "$M/modelo" "$F" && mkdir -p "$F/assets" "$F/docs"
cp video/capturas/*.png "$F/assets/"
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$F/assets/"
```

**O pedido do estúdio já está respondido por esta receita** (não pergunte de novo): 16:9 só, sem música, narração na voz B, marca do hospital, tela real do app. Grave isso em `docs/brief.md` do filme, com a lista das capturas.

### 4. Narração e tempos

1. `python3 ~/.claude/voz/narrar.py --file video/narracao.txt --output "$F/assets/narracao.wav"` (voz B, padrão aprovado, skill `narracao`). Se o VoiceStudio falhar, pare e avise: nunca outra voz.
2. Converta o `narracao.json` (tempo de cada palavra) para o `tempos.json`: uma cena por parágrafo, com o `inicio_s` da primeira palavra da cena e a lista das palavras com início e fim em segundos. Corrija a grafia, não os tempos. Grave em `video/tempos.json` e copie para `$F/assets/`.
3. `FILM.duration` do filme é a duração do `narracao.wav` mais a assinatura.

### 5. Lista de tomadas (parada 1)

Grave `docs/shotlist.md` no filme: uma tomada por frase da narração, com o tempo (do `tempos.json`), a captura usada, a câmera, o texto na tela, a transição de entrada e o critério de aceite que ela cobre. Todo critério de aceite aparece em alguma tomada.

**PARADA 1:** mostre a lista ao Pedro e espere o "pode" antes de escrever código.

### 6. Código do filme

O `index.html` do filme, pelas rules do estúdio (`seek(t)` puro, molas de `lib/motion.js`, nada de transição CSS nem timer):

- **Identidade do Hospital:** **HP Simplified** em todo texto (`@font-face` apontando para `assets/HPSimplified_Rg.ttf`), peso 400, sem negrito falso. Paleta das cores do app (`globals.css` do frontend: `#2B2E7E`, `#3B6FB6`, `#1A1C4E`) e da `marca-hsm` (`#1E1D57`, `#1D3F98`, `#EEF2FA`): fundo azul-marinho escuro, um acento só (azul claro), texto claro, sem vermelho. Logo só na assinatura, inteira e parada (`marca-hsm`): nunca como transição, moldura ou motivo.
- **Cenas:** uma por frase. Cada captura entra recortada e animada dentro de uma câmera (push-in de 1 para 1,05 a 1,16, balanço leve), com cursor fantasma, destaque no elemento que a fala cita e campo que se preenche sozinho quando a fala diz. Nunca redesenhe a tela de memória. **Nada parado mais de 0,5 s**: câmera viva, cascata, luz correndo. Todo evento preso a uma palavra do `tempos.json`, nunca a um tempo fixo. **Uma transição diferente em cada corte.**
- **Som:** cliques, trocas de tela e a assinatura viram `window.CUES` (`click`, `whoosh`, `pop`, `notification`), sob a voz e nas pausas dela.

Prévia: `node render.mjs films/<pasta>` (30 fps, em `out/film.mp4`).

### 7. Crítica e folha de quadros (parada 2)

`prompts/critica.md` até toda nota chegar a 8, com cada rodada em `docs/review_log.md`: `node render.mjs films/<pasta> --sheet --every 0.5` e um `--strip <t>` em cada ação rápida. Além das notas do estúdio, confira: telas batem com o app, todos os critérios de aceite aparecem, texto legível no `phone.png`, zero jargão, zero travessão, nenhum nome de ferramenta na tela.

**PARADA 2:** mostre ao Pedro a folha de quadros (`out/sheet.png`), o `phone.png` e as notas, e espere o "pode" antes do render final.

### 8. Volta para o repo

Copie o `index.html` e a pasta `docs/` do filme para `video/cena/` e grave `video/meta.json`:

```json
{"prd": 210, "issues": [221, 222], "contexto": "pops", "titulo": "<texto puro>",
 "app_version": "0.43.0", "gerado_em": "<ISO-8601 com timezone>",
 "duracao_s": 62, "paradas": ["58.5-62"], "mp4": "2026-11-01-210-<slug>.mp4",
 "filme": "films/2026-11-01-210-<slug>"}
```

`app_version` vem de `hospital-reunioes/frontend/package.json`. O carimbo é só este arquivo: nada de versão, PRD ou data escritos no vídeo.

### 9. Render final, som e portão de entrega

```bash
node render.mjs films/<pasta> --final        # 60 fps com motion blur, mudo, em out/film.mp4
```

Depois, a skill `som` com o `out/cues.json` e o `out/film.mp4` mudo, com a narração no `base_audio` (`{"file":"<filme>/assets/narracao.wav","keep_level":true}`). Grave o MP4 com voz e efeitos, a -14 LUFS, como `out/<PRD>-<slug>.mp4`. Em seguida, o portão:

```bash
bash .claude/skills/divulgar/scripts/gate-video.sh "<filme>/out/<PRD>-<slug>.mp4" --parada <ini>-<fim>
```

O gate confere fps constante 60 (`ffprobe`), nenhum congelamento de 0,5 s ou mais fora das paradas declaradas (`ffmpeg -vf freezedetect=n=-60dB:d=0.5`) e o vídeo tocando no **Chrome real** (Playwright com `channel="chrome"`, servido por HTTP; o Chromium do Playwright não toca H.264). `--parada` é cada janela de `paradas` do `meta.json`. **Falhou, não entrega:** conserte a cena, renderize de novo, rode o gate de novo.

Passou: mova (nunca copie) para `~/Videos/Hospital/`, sem sobrescrever, e apague as prévias:

```bash
mkdir -p ~/Videos/Hospital
V=~/Videos/Hospital/$(date +%F)-<PRD>-<slug>.mp4   # existe? some -v2, -v3
mv -n "$F/out/<PRD>-<slug>.mp4" "$V" && rm -f "$F"/out/*.mp4
open "$V"
```

Confira que o arquivo chegou e sumiu da origem antes de dizer que entregou. Junto, diga ao Pedro o que você melhoraria na próxima versão (regra de entrega do estúdio).

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

O link compartilhável é o **alias de produção** (`https://<projeto>.vercel.app`, sem hash): URLs de deployment com hash caem no SSO da Vercel. Grave o link no corpo da issue N, que é o que leva a Demonstração ao card da aba Tecnologia (ADR 0084, decisão 9):

```bash
python3 .claude/skills/divulgar/scripts/marcar_demonstracao.py <N> https://<projeto>.vercel.app
```

O script põe `<!-- demonstracao: <url> -->` no fim do corpo, troca o marcador se ele já existe e só aceita `https`. Refazer o vídeo e republicar é rodar de novo com o mesmo link: o card não avisa o diretor duas vezes. Ajuste depois = editar no repo, recopiar, redeployar. A pasta temporária é apagada depois do deploy.

## Checklist de saída

1. Todos os critérios de aceite têm passo na demonstração; as telas são capturas do app real.
2. Roteiro pela `copy` e pelo `humanizer`; abre no gancho, sem tela de metadado; vocabulário do glossário, zero jargão, zero travessão, tudo em HP Simplified.
3. Narração na voz B; a fala aparece na tela quando é dita; uma transição diferente em cada corte; nada parado mais de 0,5 s fora da assinatura.
4. Filme feito no Motion studio; "pode" do Pedro na lista de tomadas e na folha de quadros; `gate-video.sh` passou no MP4 final (60 fps).
5. MP4 final em `~/Videos/Hospital/AAAA-MM-DD-<PRD>-<slug>.mp4`, nenhum MP4 no repositório nem no `out/` do filme; `video/` (roteiro, narração, tempos, capturas, cena, `meta.json`) e `index.html` commitados.
6. Página publicada e marcador da demonstração gravado na issue N. Se existe página de módulo do contexto, ela foi republicada com o MP4 novo.
