# VERIFY: Gerir os Setores de POP

- Draft: docs/manual/public/video/pops/gerir-os-setores-de-pop.mp4, 48 s, sha256 e289dea5417e
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 9 cortes, gate OK; olhei corte-01 a corte-09. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em POPs, no bloco Setores e em Novo Setor; a janela Novo Setor igual ao print novo-setor.png (Nome com a lista de sugestões, Sigla e a ajuda HSM_SIGLA-NNN, Salvar apagado até o Nome); a Sigla PA sugerida do nome; a linha Pronto Atendimento entra no fim da tabela, que o app ordena por nome, e o aviso Setor criado; o lápis abre Editar Setor e Salvar avisa Setor atualizado.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: os nomes da lista de sugestões vêm dos setores das Reuniões e aqui são de exemplo.
- Render final: docs/manual/public/video/pops/gerir-os-setores-de-pop.mp4, 48 s, sha256 0e5f91691b16; master em local/manual-video-masters/pops/gerir-os-setores-de-pop.mp4
