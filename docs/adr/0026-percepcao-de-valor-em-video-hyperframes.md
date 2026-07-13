---
status: accepted
---

# Percepção de Valor passa a ser vídeo renderizado (HyperFrames); o HTML interativo com stepper é aposentado

O documento de Percepção de Valor (skill `/perceber`) nasceu como HTML autocontido com simulação animada interativa: stepper manual (quem apresenta controla o ritmo) mais play/pause por cima. Quatro percepções circularam nesse formato (panorama do ciclo de vida, #187, #210, #200).

A decisão: percepções novas são **vídeo MP4 renderizado com HyperFrames** (framework open-source da HeyGen que transforma HTML + CSS + animações em MP4 determinístico via Chrome headless + FFmpeg). A simulação continua sendo escrita em HTML no design system réplica do app, agora como composição HyperFrames com timeline determinística. Divisão de papéis:

- **Fonte**: a composição (HTML + assets) vive versionada em `docs/percepcao/<contexto>/<PRD>-<slug>/`. É editável e regerável.
- **Entregável**: o MP4 renderizado na mesma pasta, **fora do git** (`.gitignore`). Render determinístico: a mesma fonte reproduz o mesmo vídeo, então versionar o binário só duplicaria dezenas de MB no histórico a cada regeração.

Roteiro fixo do vídeo: abertura editorial (título + o que melhorou, cards tipográficos) → bloco "Antes" de 5 a 10s só quando a issue documenta dor real (nunca inventada) → demonstração atuada ponta a ponta cobrindo todos os critérios de aceite → fecho com carimbo (PRD, versão do app, data). Sem narração de voz na v1: comunicação 100% em tela, o vídeo funciona no mudo; voz sintetizada pode entrar depois sem retrabalho de formato. Especificação: 1920x1080, 30fps, 60 a 120s.

Gate de qualidade em duas camadas, no espírito dos gates do `/ship`: auto-revisão de frames extraídos do render draft (fidelidade ao design system, critérios cobertos, gate anti-técnica, zero travessão) e OK humano assistindo o draft antes do render final.

As ferramentas vivem fora do repo: skills HyperFrames instaladas globalmente em `~/.claude/skills/` (pacote completo via `npx skills add heygen-com/hyperframes`), com FFmpeg e Node 22+ na máquina.

## Por que é surpreendente

Um leitor futuro vai estranhar duas coisas. Primeiro, `docs/percepcao/` mistura `.html` soltos (formato antigo) com pastas de composição sem o vídeo dentro: os HTML antigos são retratos históricos válidos com links já circulados, ficam como estão e só migram sob demanda; os MP4 novos são regeráveis e por isso não são versionados. Segundo, o formato novo **abre mão do stepper interativo**, que era o trunfo do HTML (apresentador controla o ritmo passo a passo). A troca foi consciente: o vídeo circula sozinho por email, WhatsApp e TV, sem depender de navegador nem de apresentador, e esse alcance vale mais para a área de negócio do que o controle manual de ritmo.

## Alternativas descartadas

- **Manter os dois entregáveis (HTML interativo + MP4)**: preservaria o stepper, mas cada percepção exigiria manter duas versões da mesma simulação sincronizadas, o dobro de produção por PRD.
- **Narração TTS ou avatar HeyGen desde já**: mais "apresentação", porém adiciona chave de API, custo por vídeo e sincronização áudio-cena ao pipeline. Fica como evolução possível.
- **MP4 versionado (direto ou via Git LFS)**: histórico dos vídeos exatos que circularam, ao custo de inchar o repo ou configurar LFS em cada worktree/sessão paralela; o determinismo do render torna o binário redundante.
- **Gravar a tela do app real (screencast)**: fidelidade máxima, mas exige ambiente com dados encenados, não é determinístico nem regerável, e não comporta a camada editorial (abertura, antes, legendas) sem editor de vídeo.

## Consequências

- A skill `/perceber` foi reescrita para o pipeline de vídeo (fontes da verdade, gate anti-técnica, réplica do design system e carimbos permanecem).
- `docs/percepcao/**/*.mp4` e `node_modules` de composição entram no `.gitignore`.
- Quem precisa de um vídeo antigo regenera a partir da fonte (minutos de render) ou usa o arquivo que já circulou.
- Dependência de máquina (não de repo): FFmpeg, Node 22+ e as skills globais do HyperFrames.
