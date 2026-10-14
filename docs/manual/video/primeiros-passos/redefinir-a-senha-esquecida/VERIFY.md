# VERIFY: Redefinir a senha que você esqueceu

- Final: docs/manual/public/video/primeiros-passos/redefinir-a-senha-esquecida.mp4 (--quality high), 44 s, sha256 ceca11eed3a0
- Check (HyperFrames 0.8.41): 0 erros, 0 avisos (lint, runtime, layout, motion; contraste AA); gate do anel OK
- Strips: 14 cortes, gate OK; olhei corte-01 a corte-14. A placa da legenda fica parada na troca de passo; a janela do navegador entra com rastro a partir do branco da abertura; a troca de tela tem rastro (a que sai desfoca para a esquerda, a que entra vem da direita); o fecho corta para o cartão branco do carimbo, sem quadro preto.
- Quadros a cada 2 s: anel em Esqueci minha senha, no campo Email preenchido, em Verifique seu email, no botão Redefinir minha Senha do email e nos dois campos de senha; o dedo toca o link, o Email, Enviar link de redefinição (que passa a Enviando...), o botão do email, Nova senha, Confirmar nova senha e Redefinir senha (Redefinindo...); a tela termina em Senha redefinida com sucesso!. Conferido com app/reset-password/page.tsx, app/reset-password/update/page.tsx (o painel da marca dessas telas diz Gestão automatizada de atas e decisões com inteligência artificial) e com supabase/templates/recovery.html.
- Texto da tela: legendas, lower-thirds, abertura e carimbo passaram pelo humanizer e pela varredura anti-técnica, sem achados.
- Ressalvas: o email aparece aberto na janela do navegador, como um leitor de email genérico; o assunto real traz um travessão e ficou fora do quadro. O endereço do link do email é mostrado sem os parâmetros. A fonte do email é a do app (o modelo usa Segoe UI).
- OK humano: dispensado por decisão do Pedro em 14/10/2026 ("não quero mais checar draft, confio até o final"); render final direto, sem o OK por módulo da Folha de contato.
