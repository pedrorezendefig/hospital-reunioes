// Rótulo bonito para os grupos que o `autogenerate` cria a partir de subpastas.
//
// O Starlight rotula um grupo autogerado com o nome cru da pasta (`label:
// dirName`), então `como-funciona/` aparecia assim mesmo no menu, em minúsculas
// e com hífen. Não existe opção de rótulo por pasta no `autogenerate`.
//
// Trocar `autogenerate` por uma lista explícita de páginas resolveria e criaria
// um problema pior: as seções do manual ganham página quase toda semana e a
// lista ficaria desatualizada no mesmo dia. O route middleware é o ponto de
// extensão do próprio Starlight para mexer no menu já montado: a geração
// automática continua inteira e só o rótulo é reescrito.
import { defineRouteMiddleware } from "@astrojs/starlight/route-data";
import type { StarlightRouteData } from "@astrojs/starlight/route-data";

// Nome da pasta => rótulo no menu. Vale para qualquer módulo que tenha a
// subpasta (hoje `ouvidoria` e `pops`).
const rotulos: Record<string, string> = {
  "como-funciona": "Como funciona",
};

type Entrada = StarlightRouteData["sidebar"][number];

function renomearGrupos(entradas: Entrada[]): void {
  for (const entrada of entradas) {
    if (entrada.type !== "group") continue;
    const rotulo = rotulos[entrada.label];
    if (rotulo) entrada.label = rotulo;
    renomearGrupos(entrada.entries);
  }
}

export const onRequest = defineRouteMiddleware((context) => {
  renomearGrupos(context.locals.starlightRoute.sidebar);
});
