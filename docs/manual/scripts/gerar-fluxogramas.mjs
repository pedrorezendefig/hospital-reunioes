#!/usr/bin/env node
/**
 * Gera os Fluxogramas de caminho do Manual (ADR 0057, emenda de 17/09/2026,
 * decisão 13).
 *
 * Lê cada `docs/manual/fluxogramas/<modulo>/<slug>.mmd` (sintaxe Mermaid,
 * flowchart) e escreve `docs/manual/src/assets/<modulo>/fluxo-<slug>.svg` com
 * as cores do app (`fluxogramas/tema.json`, cópia do `globals.css`). O SVG
 * commitado é sempre o que este script produz: nunca editado à mão.
 *
 * Uso:
 *   node docs/manual/scripts/gerar-fluxogramas.mjs
 *   node docs/manual/scripts/gerar-fluxogramas.mjs --so ouvidoria/caminho-de-um-caso
 *
 * O mermaid-cli não entra no `package.json` de propósito: ele traz um navegador
 * inteiro junto e pesaria em todo build do site. Vem por `npx` com a versão
 * fixa, como o HyperFrames faz, e só na máquina de quem regera um desenho. A
 * primeira execução baixa o pacote e o navegador dele, e demora.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, mkdirSync, readdirSync, rmSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FONTES = join(SITE, "fluxogramas");
const DESTINO = join(SITE, "src", "assets");
const TEMA = join(FONTES, "tema.json");
// Versão fixa: o desenho de hoje tem que sair igual daqui a um ano. Subir de
// versão é decisão de quem regera todos os SVG e olha cada um.
const MERMAID_CLI = "@mermaid-js/mermaid-cli@11.17.0";

const TRAVESSAO = "—";
const MEIA_RISCA = "–";

/** Todos os `<modulo>/<slug>.mmd` da pasta de fontes. */
function desenhos() {
  const achados = [];
  for (const modulo of readdirSync(FONTES, { withFileTypes: true })) {
    if (!modulo.isDirectory()) continue;
    for (const arquivo of readdirSync(join(FONTES, modulo.name))) {
      if (!arquivo.endsWith(".mmd")) continue;
      achados.push({ modulo: modulo.name, slug: arquivo.slice(0, -4) });
    }
  }
  return achados.sort((a, b) =>
    `${a.modulo}/${a.slug}`.localeCompare(`${b.modulo}/${b.slug}`),
  );
}

function gerar({ modulo, slug }) {
  const entrada = join(FONTES, modulo, `${slug}.mmd`);
  const saida = join(DESTINO, modulo, `fluxo-${slug}.svg`);
  mkdirSync(dirname(saida), { recursive: true });
  execFileSync(
    "npx",
    ["--yes", MERMAID_CLI, "-i", entrada, "-o", saida, "-c", TEMA, "-b", "white"],
    { stdio: "inherit" },
  );

  // O CI do Manual varre travessão e meia-risca, e o texto de um SVG é texto
  // que o usuário vê. Rótulo com esse traço sai daqui travando, e não meia hora
  // depois, num lint que ninguém liga ao desenho.
  const svg = readFileSync(saida, "utf8");
  if (svg.includes(TRAVESSAO) || svg.includes(MEIA_RISCA)) {
    rmSync(saida);
    throw new Error(
      `${modulo}/${slug}.mmd: travessão ou meia-risca no texto do desenho. ` +
        "Use vírgula, dois-pontos ou hífen (ADR 0013).",
    );
  }
  console.log(`fluxo-${slug}.svg  (${modulo})`);
}

function main() {
  const argumentos = process.argv.slice(2);
  let alvo = null;
  for (let i = 0; i < argumentos.length; i += 1) {
    if (argumentos[i] === "--so") {
      alvo = argumentos[i + 1];
      i += 1;
    } else {
      throw new Error(`opção desconhecida: ${argumentos[i]}`);
    }
  }

  let lista = desenhos();
  if (alvo) {
    const [modulo, slug] = alvo.split("/");
    if (!modulo || !slug || !existsSync(join(FONTES, modulo, `${slug}.mmd`))) {
      throw new Error(
        `--so espera <modulo>/<slug> de um arquivo que existe em docs/manual/fluxogramas/. Recebi: ${alvo}`,
      );
    }
    lista = lista.filter((d) => d.modulo === modulo && d.slug === slug);
  }

  if (lista.length === 0) {
    console.log("nenhum desenho em docs/manual/fluxogramas/.");
    return;
  }
  for (const desenho of lista) gerar(desenho);
}

try {
  main();
} catch (erro) {
  console.error(erro.message);
  process.exit(1);
}
