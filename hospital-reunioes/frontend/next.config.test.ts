/**
 * Caminho do rewrite /api (issue #349).
 *
 * O rewrite roda no servidor do Next. Quando ele dá a volta pela URL pública,
 * o Traefik reescreve o X-Forwarded-For e o IP do visitante se perde, e todo
 * rate limit por IP do backend vira um balde único. Com API_PROXY_URL, o Next
 * fala com o backend pela rede interna do Docker e o IP chega vivo.
 */
import { afterEach, describe, expect, it } from "vitest";

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
