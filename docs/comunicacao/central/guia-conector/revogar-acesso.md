# Tirar o acesso de alguém à Central pelo Claude

Guia do Super admin, complemento do [guia do conector](index.html). Vale para quem usa a Central de Comando dentro do Claude (claude.ai no navegador, no Desktop ou no celular).

## Quem consegue entrar

O conector só abre a Central quando as três coisas valem ao mesmo tempo:

1. A pessoa entrou com o e-mail do cadastro dela no app do hospital, com o e-mail confirmado.
2. No cadastro, ela é **Super admin** e está **ativa**.
3. O pedido veio do **claude.ai**. Outros apps de IA, inclusive o Claude Code, são recusados, mesmo com o login de um Super admin (issue #1448).

O conector confere o cadastro a **cada pergunta**, não só no login.

## Para tirar o acesso de alguém agora

No app do hospital, em **Administração, Usuários**, abra a pessoa e faça uma das duas:

- tire o perfil **Super admin**; ou
- marque a pessoa como **inativa**.

A partir da próxima pergunta, o Claude dela recebe "acesso negado" e pede um novo login, que também não passa. Não é preciso mexer no WorkOS nem no Claude da pessoa.

## Se você desconfiar que entrou por um app que não era o Claude

Por exemplo, se alguém pediu para você "conectar a Central" num site ou app desconhecido e você fez o login:

1. Esse app não consegue ler a Central: o conector só aceita o claude.ai, e recusa os outros a cada pergunta.
2. Mesmo assim, avise quem cuida do sistema, para conferir no log do backend qual app tentou o acesso (a linha `[ConectorMCP] acesso negado: cliente fora da lista`).

**Nunca copie e mande para ninguém o endereço que aparece no navegador depois do login** (o que começa com `https://claude.ai/api/mcp/auth_callback`). Com ele, outra pessoa pode terminar a conexão no Claude dela, usando o seu acesso, e essa conexão o conector não distingue da sua, porque vem do mesmo claude.ai. Se isso aconteceu:

1. Peça a outro Super admin para tirar o seu perfil Super admin no app: o acesso cai na próxima pergunta, o seu e o de quem recebeu o endereço.
2. Avise quem cuida do sistema. **Recolocar o seu Super admin devolve o acesso também para a outra pessoa**, então só volte depois que a sessão dada por engano for derrubada no WorkOS.

## Para a própria pessoa desligar

No claude.ai, em **Settings, Connectors**, ela remove o conector da Central. Para voltar, basta adicionar de novo pelo guia do conector.
