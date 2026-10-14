# VERIFY: Validar o POP

- Draft: docs/manual/public/video/pops/validar-o-pop.mp4, 52 s, sha256 fcd560c2c592
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 13 cortes, gate OK; olhei corte-01 a corte-13. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em POPs, em Validar na linha do HSM_CC-001, em Validação final, na Identificação e no palco do fluxograma; o callout aparece antes de Aprovar validação, com a câmera longe do canto de cima; a confirmação Aprovar a Validação?; a lista com o HSM_CC-001 em Em Assinatura, sem Papéis nem lixeira, e o aviso verde; no passo 6, a devolução com o motivo escrito e Devolver aceso.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: o passo 6 volta à mesma Versão depois da aprovação para mostrar o outro caminho; no app a Versão aprovada não volta a ter os botões. O roteiro não tem devolução anterior neste POP, então a tarja não aparece.
- Render final: docs/manual/public/video/pops/validar-o-pop.mp4, 52 s, sha256 b74042b7eb56; master em local/manual-video-masters/pops/validar-o-pop.mp4
