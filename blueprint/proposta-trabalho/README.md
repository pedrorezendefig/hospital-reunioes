# Proposta PJ · Flowtech Soluções × Hospital São Mateus

Pasta com a proposta comercial em formato HTML (single-page, single-file), suas cláusulas em markdown e este guia.

## Arquivos

- **`proposta.html`** · documento principal. Single-page, vanilla, sem build, sem dependências além do Google Fonts (Inter). Estrutura: header → hero → rampa por entrega com 5 degraus (Início R$ 8,4k → Reuniões R$ 10,4k → Site R$ 11,4k → Ana R$ 16,4k → Retell.AI futuro/referência ~R$ 22,4k). Cada degrau decompõe o total em salários (Pedro+Lucas em destaque), Claude Code Max (+R$ 2.200) e Servidor com daily backup (+R$ 200), seguido da lista de tarefas/responsabilidades daquela fase. O 5º degrau (Retell) tem visual "futuro" tracejado e nota explicativa: pagamento proporcional à economia gerada, com parte da compensação posterior. Inclusos → cláusulas → footer.
- **`CLAUSULAS-COMUNS.md`** · espelho textual das 4 cláusulas centrais (Saída livre · Condicionamento da rampa · Propriedade intelectual · LGPD), com anexos de rampa e fase futura. Referência para o advogado redigir o contrato real.
- **`proposta-old.html`** · versão anterior com 3 cenários A/B/C (backup; descartar quando a versão atual for aprovada).
- **`README.md`** · este guia.

## Como abrir

```sh
open blueprint/proposta-trabalho/proposta.html
```

Funciona em Chrome, Safari, Firefox e Edge. Abre offline; só requer internet para carregar a fonte Inter (Google Fonts CDN). Se offline, o fallback é a fonte do sistema.

## Como exportar PDF

1. Abrir `proposta.html` no Chrome (recomendado para melhor render do CSS print)
2. `Cmd+P` (Mac) ou `Ctrl+P` (Windows/Linux)
3. Destination: "Save as PDF"
4. Mais opções → desmarcar "Headers and footers", marcar "Background graphics"
5. Salvar

O CSS de impressão desliga animações, força quebra de página entre seções, preserva a brand mark e mantém cards (inclusos, cláusulas, fase futura) sem cortes no meio.

## Trocar antes de enviar

Localizar e substituir os 4 placeholders no `proposta.html`:

| Placeholder | Onde | Substituir por |
|---|---|---|
| `[Lucas SOBRENOME]` | Header (subtítulo do brand) | Nome completo do Lucas |
| `Maio · 2026` | Header (data da proposta) | Data exata do envio (ex: `28 · Mai · 2026`) |
| `pmrdef@gmail.com` | Footer (contato) | Email de domínio próprio, se houver |
| `Rio de Janeiro, maio de 2026` | Footer (cidade + data) | Cidade e mês de envio |

Comentários HTML `<!-- TROCAR ANTES DE ENVIAR: ... -->` sinalizam os pontos no código.

Lembre também de atualizar `CLAUSULAS-COMUNS.md` se o contrato definitivo precisar refletir o nome completo do Lucas como sócio da Flowtech Soluções LTDA.

## Como ajustar valores da rampa

Os valores estão em 2 lugares no HTML, ambos óbvios:

1. **Atributo `data-counter="6000"` (etc.)** controla o número que anima o counter.
2. **Texto `R$ 6.000` dentro do `<span class="num">`** é o fallback estático antes da animação rodar.

Ao trocar um valor, atualize **ambos** para o mesmo número. Os incrementos individuais de Pedro e Lucas (`<b>Pedro</b> 6.000 · <b>Lucas</b> 0`) também ficam na mesma área.

A paleta e tipografia ficam centralizadas em variáveis CSS no `:root` (linhas 11-32 do HTML).

## Como enviar para o cliente

Três opções:

1. **PDF** · exportar conforme acima, anexar ao email para o presidente do Hospital São Mateus.
2. **HTML standalone** · enviar `proposta.html` direto; abre offline no browser do cliente.
3. **Hospedagem temporária** · subir o HTML em qualquer estático (Netlify, Vercel, Cloudflare Pages) e enviar link com data de expiração.

Recomendação: PDF para apresentação institucional ao presidente; HTML/link se for mais conveniente para o diretor revisar no celular ou tablet.

## Identidade visual

- **Estilo:** Editorial Bold. Paleta restrita preto (`#0c0a09`) + creme (`#fafaf7`) + laranja queimado (`#ea580c`) como acento único.
- **Tipografia:** Inter (400-900) via Google Fonts CDN. Abandona Figtree/Noto Sans do app por escolha editorial.
- **Princípios:** light mode default, tipografia grande, animações sutis e cinematográficas, cards densos, sem gradientes, sem glassmorphism, sem emojis decorativos.
- **Brand mark "FT"** em quadrado preto 46×46 com letras brancas Inter 900. Sem logo do hospital (proposta neutra; CNPJ é Flowtech Soluções).
- **Animações:** scroll-reveal por seção, counter dos totais da rampa, linha da timeline desenhando, hover sutil em cards. Tudo desligado em `prefers-reduced-motion: reduce` e em print/PDF.

## Próximos passos sugeridos

1. **Pedro revisa o HTML** no browser (abrir + scroll) e no PDF (exportar + abrir)
2. Substituir placeholders (Lucas, email, data, cidade)
3. **Apresentação para o irmão (diretor-geral)** primeiro, para alinhamento
4. **Apresentação para o presidente** com foco no hero + rampa + cláusula 01 (saída livre)
5. Após aceite verbal, **advogado redige contrato** com base em `CLAUSULAS-COMUNS.md`
6. Em paralelo, **abertura da PJ Flowtech Soluções LTDA** com contador digital
7. Vigência inicia no primeiro dia do mês seguinte à assinatura
