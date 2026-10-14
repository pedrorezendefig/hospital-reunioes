# VERIFY: Criar um POP

- Draft: docs/manual/public/video/pops/criar-um-pop.mp4, 52 s, sha256 84764d85cda5
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 10 cortes, gate OK; olhei corte-01 a corte-10. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em POPs no menu e em Criar novo POP; a janela Criar novo POP igual ao CriarPopModal e ao print criar-novo-pop.png (rótulos, texto de exemplo, prazos 15 e 30, Criar POP com o degradê); as listas de Setor, Criticidade, das três pessoas e da Periodicidade abrem embaixo do campo e o valor entra no lugar do texto de exemplo; o Nome vem sugerido do Setor (POP Farmácia); a linha HSM_FARM-003 entra no fim da lista com os botões de quem não é o Elaborador (Papéis e lixeira) e o aviso verde do app.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: a lista da Periodicidade passa da borda de baixo da janela e é cortada por ela, como no app, que rola a janela; o vídeo não mostra a troca do Nome sugerido.
- Render final: docs/manual/public/video/pops/criar-um-pop.mp4, 52 s, sha256 818e11825c5d; master em local/manual-video-masters/pops/criar-um-pop.mp4
