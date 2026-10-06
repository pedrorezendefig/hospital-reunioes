/**
 * Caminho do rewrite /api (issue #349).
 *
 * O rewrite roda no servidor do Next. Quando ele dá a volta pela URL pública,
 * o Traefik reescreve o X-Forwarded-For e o IP do visitante se perde, e todo
 * rate limit por IP do backend vira um balde único. Com API_PROXY_URL, o Next
 * fala com o backend pela rede interna do Docker e o IP chega vivo.
 */
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "./next.config";

const API_PUBLICA = process.env.NEXT_PUBLIC_API_URL;

async function destinos(): Promise<Map<string, string>> {
  const rewrites = await nextConfig.rewrites!();
  if (!Array.isArray(rewrites)) throw new Error("rewrites deveria ser uma lista");
  return new Map(rewrites.map((r) => [r.source, r.destination]));
}

afterEach(() => {
  delete process.env.API_PROXY_URL;
  if (API_PUBLICA === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = API_PUBLICA;
});

describe("rewrite do /api", () => {
  it("com API_PROXY_URL, o Next fala com o backend pela rede interna", async () => {
    process.env.API_PROXY_URL = "http://backend-interno:8000/api";

    const mapa = await destinos();

    expect(mapa.get("/api/:path*")).toBe("http://backend-interno:8000/api/:path*");
    expect(mapa.get("/ouvidoria/qr")).toBe("http://backend-interno:8000/api/ouvidoria/qr");
  });

  it("sem API_PROXY_URL, cai na URL publica de sempre", async () => {
    delete process.env.API_PROXY_URL;
    process.env.NEXT_PUBLIC_API_URL = "https://api.exemplo.cloud/api";

    const mapa = await destinos();

    expect(mapa.get("/api/:path*")).toBe("https://api.exemplo.cloud/api/:path*");
    expect(mapa.get("/ouvidoria/qr")).toBe("https://api.exemplo.cloud/api/ouvidoria/qr");
  });
});

/**
 * Versão do app no rodapé (issue #967).
 *
 * A versão não é mais commitada: o rabo grava APP_VERSION no Coolify antes do
 * merge, o Dockerfile a passa ao build e o next.config a grava no bundle. Sem
 * ela (build local, CI), vale o package.json, que fica congelado.
 */
const VERSAO_DO_PACKAGE_JSON: string = JSON.parse(readFileSync("package.json", "utf-8")).version;

async function rodapeDoBuild(): Promise<{ rodape: string; buildId: string | null }> {
  vi.resetModules();
  const { default: config } = await import("./next.config");
  // O Next troca process.env.NEXT_PUBLIC_* pelo valor de config.env no bundle:
  // é o que o Footer lê.
  process.env.NEXT_PUBLIC_APP_VERSION = config.env?.NEXT_PUBLIC_APP_VERSION;
  const { Footer } = await import("@/components/layout/Footer");
  return {
    rodape: renderToStaticMarkup(createElement(Footer)),
    buildId: (await config.generateBuildId?.()) ?? null,
  };
}

describe("versão do rodapé", () => {
  afterEach(() => {
    delete process.env.APP_VERSION;
    delete process.env.NEXT_PUBLIC_APP_VERSION;
  });

  it("build com APP_VERSION=9.9.9 mostra 9.9.9 no rodapé", async () => {
    process.env.APP_VERSION = "9.9.9";

    const { rodape, buildId } = await rodapeDoBuild();

    expect(rodape).toContain(">v9.9.9<");
    expect(buildId).toMatch(/^v9\.9\.9-/);
  });

  it("sem APP_VERSION, cai no package.json", async () => {
    delete process.env.APP_VERSION;

    const { rodape } = await rodapeDoBuild();

    expect(VERSAO_DO_PACKAGE_JSON).toMatch(/^\d+\.\d+\.\d+$/);
    expect(rodape).toContain(`>v${VERSAO_DO_PACKAGE_JSON}<`);
  });

  it("APP_VERSION vazia, o ARG do Dockerfile sem valor, também cai no package.json", async () => {
    process.env.APP_VERSION = "";

    const { rodape } = await rodapeDoBuild();

    expect(rodape).toContain(`>v${VERSAO_DO_PACKAGE_JSON}<`);
  });

  it("o Dockerfile entrega APP_VERSION ao build do Next", () => {
    const dockerfile = readFileSync("Dockerfile", "utf-8");
    const builder = dockerfile.split(/^FROM /m).find((estagio) => /AS builder\b/.test(estagio)) ?? "";
    const linhas = builder.split("\n").map((l) => l.trim());
    const arg = linhas.indexOf("ARG APP_VERSION");
    const env = linhas.indexOf("ENV APP_VERSION=$APP_VERSION");
    const build = linhas.indexOf("RUN pnpm build");

    expect(build).toBeGreaterThan(-1);
    expect(arg).toBeGreaterThan(-1);
    expect(env).toBeGreaterThan(arg);
    expect(build).toBeGreaterThan(env);
  });
});
