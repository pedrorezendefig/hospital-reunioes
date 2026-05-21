# skills-setup

Documento HTML interativo de onboarding do setup de skills do Claude Code que o Pedro usa.

## Como rodar local

```sh
cd docs/skills-setup
python3 -m http.server 8765
# abra http://localhost:8765
```

Ou abra `index.html` direto no browser (`file://`). GSAP e Lenis vêm de CDN ESM, então precisa de internet.

## Estrutura

```
docs/skills-setup/
├── index.html        # marcação semântica
├── styles.css        # tokens + layout + motion states
├── main.js           # GSAP, Lenis, render dinâmico, copy-to-clipboard
├── data/
│   └── skills.json   # 16 itens (5 skills + 11 plugins) em 5 categorias
└── README.md
```

## Como editar conteúdo

Cards e categorias são populados a partir de `data/skills.json`. Pra mudar copy, ajustar tagline ou adicionar item novo, edite o JSON. O HTML não precisa ser tocado.

## Stack

- HTML semântico vanilla
- CSS custom properties + grid + flex (tema dark neo-tech, paleta Vercel/Linear)
- ES modules via CDN: GSAP 3.12 + ScrollTrigger, Lenis 1.1
- Tipografia: Geist Sans + Geist Mono

Zero build step. Zero dependência local.

## Acessibilidade

- `prefers-reduced-motion`: desativa GSAP/Lenis e mostra tudo estático com fade simples.
- Contraste AA: `#ededee` sobre `#0a0a0b` → 16.4:1.
- Navegação por teclado funcional nos cards, links e botões. Focus visible com outline cyan.
