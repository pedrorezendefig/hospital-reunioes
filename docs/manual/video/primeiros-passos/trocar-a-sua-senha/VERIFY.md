# VERIFY: Trocar a sua senha

- Final: docs/manual/public/video/primeiros-passos/trocar-a-sua-senha.mp4 (--quality high), 41 s, sha256 336bab27f9c2
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos (lint, runtime, layout, motion; contraste AA); gate do anel OK
- Strips: 10 cortes, gate OK; olhei corte-01 a corte-10. A placa da legenda fica parada na troca de passo; a janela do navegador entra com rastro a partir do branco da abertura; a troca de tela tem rastro (a que sai desfoca para a esquerda, a que entra vem da direita); o fecho corta para o cartão branco do carimbo, sem quadro preto.
- Quadros a cada 2 s: o menu do seu nome abre com Meu Perfil, Configurações e Sair da conta; anel em Configurações, em PESSOAL e em Segurança (já aberta, a primeira da coluna); o dedo toca o nome, Configurações, Segurança, os dois campos e Alterar senha; o botão sai do apagado quando as duas senhas batem; depois do clique os campos se esvaziam, o botão volta a apagar e o aviso verde Senha alterada com sucesso! aparece no canto de baixo. Conferido com UserProfileDropdown.tsx, app/configuracoes/page.tsx, SecuritySection.tsx e Toast.tsx, e com os prints menu-do-usuario-configuracoes.png e configuracoes-seguranca.png.
- Texto da tela: legendas, lower-thirds, abertura e carimbo passaram pelo humanizer e pela varredura anti-técnica, sem achados.
- Ressalvas: o aviso verde fica na tela até o fim do trecho, um segundo além dos 5 s do app. A dica amarela de senha curta, que aparece enquanto a pessoa digita, não entra: a senha chega inteira.
- OK humano: dispensado por decisão do Pedro em 14/10/2026 ("não quero mais checar draft, confio até o final"); render final direto, sem o OK por módulo da Folha de contato.
