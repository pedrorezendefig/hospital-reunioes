// Traz a logo e a fonte HP Simplified de docs/comunicacao/_assets para o site.
//
// A cópia única dos dois vive lá (ADR 0044, decisão 4) e nenhuma delas entra no
// git desta pasta: o `prebuild` roda antes de todo `astro build` e de todo
// `astro dev`, então quem clona o repositório publica sem passo manual. Sem a
// fonte o manual sai em Arial e deixa de parecer o app, então a falta trava
// aqui em vez de virar um site errado publicado.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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

console.log("assets do manual prontos (logo e HP Simplified).");
