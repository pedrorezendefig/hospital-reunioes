/**
 * Lê as páginas do manual do disco, no servidor (issue #1718).
 *
 * Elas moram em `public/manual/`, e não em `src/`, por dois motivos: os prints
 * ao lado do Markdown já saem servidos pelo próprio Next, e a pasta `public`
 * vai inteira para a imagem de produção (o `Dockerfile` a copia), onde o
 * servidor roda com `public/` ao lado do `server.js`.
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { lerPagina, type PaginaDoManual } from "./paginas";

export const PASTA_DO_MANUAL = join(process.cwd(), "public", "manual");

export function carregarPaginasDoManual(raiz: string = PASTA_DO_MANUAL): PaginaDoManual[] {
  if (!existsSync(raiz)) return [];
  return readdirSync(raiz, { withFileTypes: true })
    .filter((entrada) => entrada.isDirectory())
    .map((entrada) => join(raiz, entrada.name, "pagina.md"))
    .filter((arquivo) => existsSync(arquivo))
    .map((arquivo) => {
      const pasta = arquivo.split(/[\\/]/).at(-2)!;
      return lerPagina(pasta, readFileSync(arquivo, "utf8"));
    });
}
