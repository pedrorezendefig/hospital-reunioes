# Roteiro de prints

Print do manual é **tela real do app rodando em localhost**, capturada por
código versionado: quando a tela muda, o roteiro roda de novo e refaz as
imagens. Recorte feito à mão não entra.

- Roteiro: `docs/manual/prints/<modulo>.py` (um por módulo).
- Saída: `docs/manual/src/assets/<modulo>/<nome>.png`, versionada.
- A página aponta por caminho relativo:
  `![<o que mostra>](../../../assets/<modulo>/<nome>.png)`.

## Antes de rodar

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`). Se o
   PostgREST não subir, o backend fica `degraded` e a tela trava em
   "Carregando...": `supabase stop` e `supabase start` recriam o container.
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`. Confira depois que a
   tela nova está mesmo no build, senão o print sai da versão antiga.
3. Tela de dentro do app: login como ouvidor (`admin@hospital.com`), senha do
   `DEFAULT_USER_PASSWORD` do `.env` **local**, nunca de produção. Tela sem
   login (formulário público, portal do setor, aceite da Ata) não precisa de
   nada disso.
4. `python3 docs/manual/prints/<modulo>.py`.

## Como escrever o roteiro

Use `docs/manual/prints/ouvidoria.py` como molde. Um dicionário `PRINTS` mapeia
nome para função, e cada função recebe `(page, base, saida)`. Isso deixa
`--print <nome>` refazer uma imagem só quando só uma tela mudou.

- Celular primeiro (`viewport` 390x844) na tela que nasce do QR ou do celular;
  desktop no que a pessoa usa sentada. `device_scale_factor=2` sempre.
- **Dados de exemplo do hospital**, verossímeis e fictícios (CME, Farmácia,
  UTI; nomes que não existem). Nunca dado real de manifestante.
- **Tire o foco antes de capturar**: o anel de foco num campo vira instrução
  falsa ("clique aqui") na hora que a pessoa lê a página.
- Lista `<select>`: o menu nativo do sistema não sai na captura. Antes do
  screenshot, transforme o campo em lista visível (`el.size = <n>`) e recorte a
  área dele.
- Nada de enviar formulário que cria registro de verdade quando o print podia
  ser da tela preenchida: o banco local é compartilhado com o resto do trabalho.

## Print que envelhece

Print que existe mas mostra tela velha é responsabilidade de quem mexe na tela:
mudou o texto do botão, rode o roteiro do módulo e commite a imagem nova no
mesmo PR.

O inventário que acusa print referenciado e inexistente é da `/montar-manual`
(`python3 tools/inventario_manual.py --dir docs/manual`, lacuna
`print-faltando`). Ele diz qual página aponta para qual imagem que não existe,
e de que módulo é o roteiro que a refaz.

## O balão numerado (Print de passo)

O print que fica sob um passo leva **balões numerados** com o número do passo,
desenhados pelo roteiro por cima da tela real, antes da captura. É a única
marcação permitida: nada de seta, retângulo ou destaque à mão.

- O roteiro tem um helper `balao(page, seletor, numero, onde)` que injeta, no
  DOM da página, um círculo de 28 px (navy do app, número branco, HP
  Simplified) encostado no elemento, 6 px para fora dele, com
  `pointer-events: none` e `z-index` acima de tudo. Vários balões na mesma tela
  são várias chamadas antes de um `capturar`.
- `onde` é de que lado o balão encosta: `esquerda` (o padrão) para campo, botão
  e rótulo; `acima` para o ícone de uma fileira de ícones, onde a esquerda já é
  o ícone vizinho; `acima-inicio` para a célula larga com o texto à esquerda,
  como o cabeçalho de uma coluna. Sem espaço à esquerda na tela, o balão sobe
  sozinho: sobreposto ao canto ele comeria a primeira letra do rótulo.
- O balão nasce dentro do bloco que rola junto com o elemento. Num modal que
  rola por dentro, um balão preso à página escorrega do alvo assim que o balão
  seguinte rola o corpo, e o print sai apontando o campo de baixo.
- Formulário mais alto do que a tela: aumente a altura da JANELA antes de
  abrir o modal, em vez de escolher entre mostrar o alto e mostrar o fim. É a
  mesma tela num monitor maior, e nenhum balão fica de fora.
- O seletor aponta o elemento que o passo cita (o botão **Novo Usuário**, o
  campo **Email**). Balão em cima de elemento errado é o mesmo defeito do
  marcador errado no vídeo: olhe cada imagem depois de gerar.
- Um print por **mudança de tela**: se os passos 2, 3 e 4 preenchem o mesmo
  formulário, é um print com os balões 2, 3 e 4. O passo que abre uma janela
  ou muda de página ganha print novo.
- O nome do arquivo diz a tela, não o passo: `novo-usuario.png`, e não
  `passo-3.png`, porque a mesma imagem serve a mais de um passo.
- Tela de dentro do app sai em computador (1440x900, escala 2, como os roteiros já fazem); tela que nasce
  do QR ou do link no celular sai em celular (390x844), como já era.
