# VERIFY: Dar acesso à Gestão de POPs

- Draft: docs/manual/public/video/pops/dar-acesso-a-gestao-de-pops.mp4, 50 s, sha256 7c143afee95a
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK (tools/anel_video_manual.py)
- Strips: 8 cortes, gate OK; olhei corte-01 a corte-08. A placa da legenda fica parada na troca de passo, as trocas de tela têm rastro e não há quadro preto entre a abertura, a tarefa e o carimbo.
- Quadros a cada 3 s: anel em POPs, em Conceder perfil, na pessoa encontrada pela busca e no Perfil; a janela igual ao print conceder-perfil.png, com o aviso de quem não loga; Login provisionado com a senha, que aparece uma vez (callout antes); a linha de Bruno Tavares entra no alto da tabela; Setores da pessoa com as caixas marcadas e o aviso do app; o ícone de pessoa com o sinal de menos e o confirm do navegador.
- Texto da tela: legendas, lower-thirds, callout, abertura e carimbo pelo humanizer e pela varredura anti-técnica (todo nó de texto da réplica e todo slot), sem achados.
- Fonte da réplica: código do frontend (componentes de POPs, AppShell, Select, DataTable) e prints do roteiro docs/manual/prints/pops.py, com a página em 1440 px como nos prints e a base de 17 px do globals.css.
- Ressalvas: a senha é de exemplo; o confirm do navegador foi desenhado no alto da janela, como o Chrome mostra, e o vídeo não clica em OK.
- Render final: docs/manual/public/video/pops/dar-acesso-a-gestao-de-pops.mp4, 50 s, sha256 43e897771b2c; master em local/manual-video-masters/pops/dar-acesso-a-gestao-de-pops.mp4
