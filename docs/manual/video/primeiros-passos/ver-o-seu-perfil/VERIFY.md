# VERIFY: Ver o seu perfil

- Draft: docs/manual/public/video/primeiros-passos/ver-o-seu-perfil.mp4 em --quality draft, 35 s, conferido pelo anel, pelas strips e pelos quadros; o render final ocupou o mesmo caminho
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos (lint, runtime, layout, motion; contraste AA); gate do anel OK
- Strips: 9 cortes, gate OK; olhei corte-01 a corte-09. A placa da legenda fica parada na troca de passo; a janela do navegador entra com rastro a partir do branco da abertura; a troca de tela tem rastro (a que sai desfoca para a esquerda, a que entra vem da direita); o fecho corta para o cartão branco do carimbo, sem quadro preto.
- Quadros a cada 2 s no draft e a cada 5 s no final: anel no seu nome, no menu aberto, em Meu Perfil, na trilha Dashboard > Meu Perfil, no alto do cartão (PN, Paula Nogueira, Analista de Qualidade, Ativo), nos dados E-MAIL, SETOR, AREA e ID, e no Resumo de Atividade depois da rolagem; os rótulos sem acento (Area, Reunioes, Pendencias Ativas, Concluidas) são os do app. Conferido com app/perfil/page.tsx e com os prints menu-do-usuario-perfil.png e meu-perfil.png.
- Texto da tela: legendas, lower-thirds, abertura e carimbo passaram pelo humanizer e pela varredura anti-técnica, sem achados.
- Ressalvas: o atalho Perfil da barra de baixo do celular, citado no passo 2 da página, fica fora. Os números do resumo são de exemplo.
- Render final: docs/manual/public/video/primeiros-passos/ver-o-seu-perfil.mp4 (--quality high), 35 s, sha256 40e81eab1d55; strips refeitas no final, gate OK; master em local/manual-video-masters/primeiros-passos/ver-o-seu-perfil.mp4
