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
