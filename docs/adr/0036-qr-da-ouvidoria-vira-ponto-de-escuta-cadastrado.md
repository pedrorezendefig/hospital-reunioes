---
status: accepted
amends: 0034
---

# O QR da Ouvidoria vira Ponto de escuta cadastrado, com código curto no cartaz

Decisão do Pedro (26/ago/2026, grilling): o QR setorial da Ouvidoria deixa de ser uma URL montada à mão e passa a nascer de um cadastro no app. Nasce a entidade **Ponto de escuta**, e o que vai impresso no cartaz passa a ser um código curto, não o nome do setor por extenso. Este ADR emenda a decisão 9 do ADR 0034 na parte da URL do cartaz.

## Contexto

- O ADR 0034 (decisão 9) definiu a URL do cartaz como `/ouvidoria/qr?setor=X&ponto=Y`, e a issue #323 a implementou: o backend resolve o setor contra a taxonomia e redireciona ao formulário público.
- O que ficou de fora: **nada no app gera o QR**. Não há imagem, não há cadastro, não há lista. Quem quisesse um cartaz teria que montar a URL na mão e gerar o código num site qualquer.
- Consequência prática: **nenhum cartaz foi impresso até hoje**. O canal `qr` existe no banco e nunca foi usado de verdade. Aposentar o formato antigo não quebra nada que esteja na parede.
- O `ponto` é texto livre de até 80 caracteres, sem entidade por trás. O ouvidor não tem como saber quais cartazes existem, nem onde estão.
- A revisão da issue #375 registrou duas arestas do formato atual: o texto de origem na query string aparece na página com a marca do hospital (item 9, superfície de golpe), e `canal = 'qr'` não prova presença física (item 10).
- A spec da Diretoria (RN-14) pede pontos de instalação nomeados, cada um com código próprio, e observa que o cartaz converte muito mais com convite direto do que com a palavra "Ouvidoria" sozinha.

## Decisões

1. **Nasce o Ponto de escuta**: entidade própria (setor, rótulo do ponto, código, ativo). Cada linha é um cartaz. Fica sobre a taxonomia de Setores da casa, sem cadastro paralelo, como os [Responsáveis do setor].
2. **O cartaz leva código curto**: a URL impressa passa a ser `https://<app>/ouvidoria/qr?p=<codigo>`, e o servidor resolve o setor e o ponto. Três razões: QR com menos dados tem módulos maiores e a câmera lê melhor de longe; renomear o ponto não obriga reimprimir; e a origem deixa de ser texto que qualquer pessoa monta, o que fecha o item 9 da #375.
3. **Código aleatório de 6 caracteres**, sem os pares ambíguos (0/O, 1/I). Não sugere ordem e não depende de sigla de setor, que o contexto Reuniões não tem.
4. **O formato antigo é aposentado**: `/ouvidoria/qr` passa a aceitar somente `?p=`. Manter as duas portas anularia a decisão 2, porque a brecha do texto arbitrário continuaria aberta pela porta velha. Nenhum cartaz impresso é afetado, porque não existe nenhum.
5. **Lista fechada também para o ponto**: `canal_ponto` só é gravado quando o código resolve um Ponto de escuta ativo. É o mesmo tratamento que o setor já recebe hoje. O que não resolve entra sem origem, nunca com texto cru.
6. **Ponto desativa, nunca apaga**: o histórico de casos aponta para ele. QR de ponto inativo abre o formulário público normal, **sem origem**, e nunca uma página de erro: ninguém parado na frente de um cartaz pode ficar sem canal por causa de faxina no cadastro.
7. **Quem gere é o [Perfil da Ouvidoria]** (`ouvidor` e `diretoria_executiva`), e não só a Diretoria. Cartaz é operação do canal, não governança: não carrega dado de paciente e não muda prazo nem responsabilidade. O ouvidor é quem sabe qual cartaz caiu da parede.
8. **A tela entrega os dois artefatos**: o PNG do QR visível e baixável, e o **cartaz A5 em PDF** pronto para a gráfica, com logo, convite direto, o QR grande e o setor. A geração é no backend, com `segno` (Python puro, sem Pillow), porque o PDF é montado lá pelo weasyprint que já serve Ata e POP.

## Considered options

- **Gerador solto, sem cadastro:** rejeitado. "Gerir" pede lista: sem entidade ninguém sabe quantos cartazes existem nem onde, e o rótulo do ponto continuaria refém de erro de digitação.
- **Manter setor e ponto por extenso na URL:** rejeitado. URL legível não paga o preço de QR mais denso, cartaz que morre ao renomear o ponto, e a superfície de golpe do item 9 da #375.
- **Código legível (`REC-01`, `PS-03`):** rejeitado. Exigiria cadastro de siglas de setor, que só o contexto POPs tem, e a tela mostra setor e ponto ao lado do código de qualquer forma.
- **Manter as duas URLs por compatibilidade:** rejeitado. Não há o que compatibilizar: zero cartazes impressos.
- **Gerar o QR no navegador:** rejeitado. O PDF do cartaz precisa da imagem no backend, então o front duplicaria a lógica.
- **Só a Diretoria Executiva gere:** rejeitado. Poria a Diretoria no caminho de todo cartaz novo, sem ganho de proteção.

## Consequences

- O `canal_ponto` deixa de ser texto de canal aberto e passa a ser dado derivado de cadastro. O que o ouvidor lê no Dossiê passa a ter um cartaz de verdade por trás.
- Entra dependência nova no backend (`segno`), e nasce a primeira imagem gerada pelo app.
- O item 10 da #375 continua valendo em parte: quem passar na frente do cartaz lê o código e pode montar a URL depois, em casa. `qr` segue sendo sinal de origem, não prova de presença física, e a tela do Dossiê precisa dizer isso.
- A decisão 12 da #375 (não gravar `canal_ponto` em caso anônimo) continua de pé e vale sobre o ponto cadastrado do mesmo jeito.
- O dia em que a Ana entrar no WhatsApp oficial, o destino muda no servidor e o cartaz com código curto continua valendo, que é o mesmo ganho que o ADR 0034 já buscava.
