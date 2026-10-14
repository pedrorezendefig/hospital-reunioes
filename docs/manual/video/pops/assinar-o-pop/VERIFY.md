# VERIFY: Assinar o POP

- Draft: docs/manual/public/video/pops/assinar-o-pop.mp4, 48 s, sha256 50e9da105bce
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 11 cortes, gate OK; olhei corte-01 a corte-11. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel na mensagem da ClickSign, no link, no Código e na Versão do documento e em Assinar; o documento repete o topo do PDF do POP (pop_template.html: título, faixa de preliminar, 1. Identificação); na plataforma, o HSM_CC-002 em Em Assinatura e depois Publicado.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: a caixa de email e a página de assinatura são de fora da plataforma e foram desenhadas neutras; o texto da mensagem e a tela da ClickSign não são cópia do serviço.
- Render final: docs/manual/public/video/pops/assinar-o-pop.mp4, 48 s, sha256 075020322a75; master em local/manual-video-masters/pops/assinar-o-pop.mp4
