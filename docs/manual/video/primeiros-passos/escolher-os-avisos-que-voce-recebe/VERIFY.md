# VERIFY: Escolher os avisos que você recebe

- Draft: docs/manual/public/video/primeiros-passos/escolher-os-avisos-que-voce-recebe.mp4 em --quality draft, 35 s, conferido pelo anel, pelas strips e pelos quadros; o render final ocupou o mesmo caminho
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos (lint, runtime, layout, motion; contraste AA); gate do anel OK
- Strips: 9 cortes, gate OK; olhei corte-01 a corte-09. A placa da legenda fica parada na troca de passo; a janela do navegador entra com rastro a partir do branco da abertura; a troca de tela tem rastro (a que sai desfoca para a esquerda, a que entra vem da direita); o fecho corta para o cartão branco do carimbo, sem quadro preto.
- Quadros a cada 2 s no draft e a cada 5 s no final: anel em Configurações no menu, em PESSOAL, em Notificações já acesa, nas quatro chaves, na linha Novos comentários e no aviso verde Preferências salvas!; o dedo toca o nome, Configurações, Notificações e a chave de Novos comentários, que passa para cinza com a bolinha à esquerda. Conferido com NotificationsSection.tsx (títulos, ajudas e chaves) e com o print configuracoes-notificacoes.png.
- Texto da tela: legendas, lower-thirds, abertura e carimbo passaram pelo humanizer e pela varredura anti-técnica, sem achados.
- Ressalvas: o ícone girando ao lado de Notificações, que aparece enquanto a escolha é gravada, não entra. O vídeo não mostra que a chave ainda não silencia aviso nenhum; isso fica no Se der errado da página.
- Render final: docs/manual/public/video/primeiros-passos/escolher-os-avisos-que-voce-recebe.mp4 (--quality high), 35 s, sha256 5cac0f195d1f; strips refeitas no final, gate OK; master em local/manual-video-masters/primeiros-passos/escolher-os-avisos-que-voce-recebe.mp4
