# VERIFY: Ver o fluxograma do POP

- Draft: docs/manual/public/video/pops/ver-o-fluxograma-do-pop.mp4, 49 s, sha256 791e31302be5
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 11 cortes, gate OK; olhei corte-01 a corte-11. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em Revisar na linha do HSM_CTI-001; o título 6. Fluxograma e o palco com o desenho inteiro (89%); o mais leva a 109% e 129%, o arraste anda pelo caminho, Ajustar à tela volta a 89%; PNG e SVG com o aviso de download do navegador (HSM_CTI-001_fluxograma.png e .svg), como o FluxogramaPalco nomeia.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: o palco tem 70% da altura da janela do vídeo, menor que a do print, e por isso o enquadramento inicial é 89% e não 100%; o vídeo mostra o botão de mais e o arraste, sem o zoom pela rolagem.
- Render final: docs/manual/public/video/pops/ver-o-fluxograma-do-pop.mp4, 49 s, sha256 7cb71b32e877; master em local/manual-video-masters/pops/ver-o-fluxograma-do-pop.mp4
