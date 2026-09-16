// Traz a logo e a fonte HP Simplified de docs/comunicacao/_assets para o site,
// e gera o favicon a partir da logo.
//
// A cópia única dos dois vive lá (ADR 0044, decisão 4) e nenhuma delas entra no
// git desta pasta: o `prebuild` roda antes de todo `astro build` e de todo
// `astro dev`, então quem clona o repositório publica sem passo manual. Sem a
// fonte o manual sai em Arial e deixa de parecer o app, então a falta trava
// aqui em vez de virar um site errado publicado.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
// O `sharp` já é dependência do site (o Astro usa para as imagens das
// páginas); aqui ele recorta o símbolo da marca para o favicon.
import sharp from "sharp";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assets = resolve(raiz, "../comunicacao/_assets");

const copias = [
  [resolve(assets, "logo-hsm.png"), resolve(raiz, "src/assets/logo-hsm.png")],
  [
    resolve(assets, "fonts/HPSimplified_Rg.ttf"),
    resolve(raiz, "public/fonts/HPSimplified_Rg.ttf"),
  ],
];

for (const [origem, destino] of copias) {
  if (!existsSync(origem)) {
    console.error(`asset não encontrado: ${origem}`);
    process.exit(1);
  }
  mkdirSync(dirname(destino), { recursive: true });
  copyFileSync(origem, destino);
}

// O favicon é o símbolo da marca, as duas arcadas, recortado da logo.
//
// A logo inteira não serve de ícone de aba: é um lockup deitado (926x522) com
// o wordmark embaixo, que a 32 pixels vira borrão. O recorte abaixo foi medido
// no próprio arquivo, não chutado: as arcadas ocupam x 40..651, y 30..224, e o
// wordmark só começa em y 268, então o corte não encosta nele.
//
// O quadrado sobra em cima e embaixo porque o símbolo é deitado (3,1 para 1).
// Esse preenchimento é o branco da própria logo, que não tem canal alfa: nada
// de cor inventada aqui.
const SIMBOLO = { left: 40, top: 30, width: 612, height: 195 };
const MARGEM = 30;
const LADO = 256;

const origemDaLogo = resolve(assets, "logo-hsm.png");
const favicon = resolve(raiz, "public/favicon.png");
mkdirSync(dirname(favicon), { recursive: true });

await sharp(origemDaLogo)
  .extract({
    left: SIMBOLO.left - MARGEM,
    top: SIMBOLO.top - MARGEM,
    width: SIMBOLO.width + 2 * MARGEM,
    height: SIMBOLO.height + 2 * MARGEM,
  })
  .resize(LADO, LADO, {
    fit: "contain",
    background: { r: 255, g: 255, b: 255, alpha: 1 },
  })
  .png({ compressionLevel: 9 })
  .toFile(favicon);

console.log("assets do manual prontos (logo, HP Simplified e favicon).");
