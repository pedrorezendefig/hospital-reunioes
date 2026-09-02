/**
 * @vitest-environment jsdom
 */

/**
 * A identidade da aplicação (issue #491, PRD #471, D-17).
 *
 * O sistema nasceu como "Hospital Reuniões: Gestão de Atas" e hoje abriga
 * Reuniões, POPs e Ouvidoria. Quem se apresenta pelo nome de um dos módulos
 * mente sobre o que é, e o manifestante que chega pela Ouvidoria lê "Gestão de
 * Atas" na aba do navegador.
 *
 * A identidade mora em dois arquivos que o Next nunca cruza sozinho: o
 * `metadata` do layout raiz (aba, descrição, atalho do iOS) e o
 * `manifest.webmanifest` estático (instalação em tela inicial). Os dois dizem a
 * mesma coisa em lugares diferentes, então o teste que importa é o de
 * coerência: se um for trocado sem o outro, o app instalado passa a ter nome
 * diferente do site. Por isso as asserções comparam manifesto com metadata, em
 * vez de repetir a mesma string literal nos dois lados.
 *
 * O título da aba vale "em todas as páginas" porque nenhuma outra rota exporta
 * `metadata.title`: no App Router, o que o layout raiz declara é herdado por
 * quem não declara nada.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { metadata } from "./layout";
import Home from "./page";

const IDENTIDADE_VELHA = /Gestão de Atas|gestão de reuniões|Hospital Reuniões/i;

const manifesto = JSON.parse(
  readFileSync(resolve(process.cwd(), "public/manifest.webmanifest"), "utf8"),
) as {
  name: string;
  short_name: string;
  description: string;
};

describe("a identidade da aplicação", () => {
  it("põe a plataforma de gestão na aba do navegador", () => {
    expect(metadata.title).toBe("Hospital São Matheus · Plataforma de Gestão");
  });

  it("descreve a plataforma inteira, não um módulo só", () => {
    expect(metadata.description).toBe(
      "Plataforma de gestão do Hospital São Matheus: reuniões, POPs e Ouvidoria.",
    );
  });

  it("instala com o mesmo nome que o site exibe", () => {
    expect(manifesto.name).toBe(metadata.applicationName);
    const atalhoDoIOS = metadata.appleWebApp as { title?: string };
    expect(manifesto.short_name).toBe(atalhoDoIOS.title);
    expect(manifesto.description).toBe(metadata.description);
  });

  it("não sobra menção à identidade velha em lugar nenhum", () => {
    expect(JSON.stringify(metadata)).not.toMatch(IDENTIDADE_VELHA);
    expect(JSON.stringify(manifesto)).not.toMatch(IDENTIDADE_VELHA);
  });
});

describe("a porta de entrada", () => {
  it("se apresenta como a plataforma, não como o módulo de reuniões", () => {
    const texto = render(<Home />).container.textContent ?? "";

    expect(texto).toContain("Hospital São Matheus · Plataforma de Gestão");
    expect(texto).toContain(
      "A plataforma de gestão do hospital: reuniões, POPs e Ouvidoria.",
    );
    expect(texto).not.toMatch(IDENTIDADE_VELHA);
  });
});
