# VERIFY: Revisar o POP

- Draft: docs/manual/public/video/pops/revisar-o-pop.mp4, 51 s, sha256 e78e6b519b71
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 10 cortes, gate OK; olhei corte-01 a corte-10. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em POPs, em Revisar na linha do HSM_CTI-001, em Revisão técnica, na Identificação inteira e no palco do fluxograma; a tela da Versão bate com o print versao-em-revisao.png e com a page.tsx de versao (pílula v1.0 · Em Revisão, os dois botões); a confirmação Aprovar a Revisão? e a devolução com Motivo (obrigatorio), contador 0/1000 e Devolver apagado até o motivo; de volta à lista, o HSM_CTI-001 em Em Elaboração e o aviso verde.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: no passo 4 o dedo abre a confirmação e sai por Cancelar, para mostrar a devolução na mesma Versão; o fluxograma é o desenho do roteiro, feito pelo renderer do app (svg.ts) com as cores trocadas pelos tokens.
- Render final: docs/manual/public/video/pops/revisar-o-pop.mp4, 51 s, sha256 5849e637b9b9; master em local/manual-video-masters/pops/revisar-o-pop.mp4
