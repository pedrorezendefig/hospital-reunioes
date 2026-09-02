import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";
import pkg from "./package.json";

const APP_VERSION = pkg.version;

// `cacheOnNavigation` fica DESLIGADO de propósito (issue #508).
//
// Ele não é uma regra do service worker: liga um segundo worker, que roda na
// PÁGINA, embrulha `history.pushState`/`replaceState` e escuta o evento
// `online`. A cada navegação esse worker faz `caches.open("pages").put(url)`
// com a mão dele, escrita imperativa que não passa por matcher nenhum do
// `sw.ts`. A regra `NetworkOnly` do `lib/pwa/cache-runtime.ts` não teria voto
// ali, e a URL de `/aceite/{token}` e `/ouvidoria-setor/{token}`, que é a
// credencial inteira dessas rotas, iria para o disco do aparelho assim mesmo.
//
// Com `false` o `@serwist/next` nem emite o worker de navegação
// (`shouldBuildSWEntryWorker = cacheOnNavigation`), então não sobra caminho.
// O custo é a tela alcançada por navegação client-side não ter mais a casca
// HTML pré-gravada: o offline dela passa a depender do que o service worker
// guardou pelo caminho normal, pelas regras "pages"/"pages-rsc"/"others" do
// `defaultCache`. Nenhuma tela deixa de funcionar online.
const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  cacheOnNavigation: false,
  reloadOnOnline: true,
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_APP_VERSION: APP_VERSION,
  },
  generateBuildId: async () => `v${APP_VERSION}-${Date.now()}`,
  async rewrites() {
    // O rewrite roda no servidor do Next. API_PROXY_URL é o caminho interno
    // até o backend (rede do Docker): sem a volta pela URL pública, o Traefik
    // não reescreve o X-Forwarded-For e o IP real do visitante chega vivo ao
    // rate limit do backend (issue #349). Sem a variável, vale a URL pública.
    const api = process.env.API_PROXY_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    return [
      {
        source: "/api/:path*",
        destination: `${api}/:path*`,
      },
      // URL do cartaz de QR da Ouvidoria (ADR 0034, decisão 9). É a única coisa
      // impressa e colada na parede, então ela mora no domínio do app e sem o
      // prefixo /api: quem decide o destino é o backend, do outro lado deste
      // rewrite. Reescrita, e não redirect, para o cartaz continuar valendo com
      // uma volta só.
      {
        source: "/ouvidoria/qr",
        destination: `${api}/ouvidoria/qr`,
      },
    ];
  },
  async redirects() {
    return [
      { source: "/signup", destination: "/login", permanent: false },
      { source: "/signup/:path*", destination: "/login", permanent: false },
    ];
  },
};

export default withSerwist(nextConfig);
