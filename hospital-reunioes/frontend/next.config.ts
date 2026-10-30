import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";
import pkg from "./package.json";

// Versão do rodapé (issue #967): a subida grava APP_VERSION no Coolify antes do
// merge e o Dockerfile a entrega ao build. Sem ela (build local, CI) ou vazia
// (ARG sem valor), vale o package.json, que fica congelado: a versão não é
// mais commitada.
const APP_VERSION = process.env.APP_VERSION || pkg.version;

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
  // Cabeçalhos de segurança (issue #1283). A CSP leva só o `frame-ancestors`
  // por ora: a política completa pede o inventário de scripts e fica para
  // outra fatia.
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
  experimental: {
    // Envio de Contas médicas (issue #1213). Com o `src/middleware.ts` no app,
    // o Next clona o corpo de toda requisição e corta em 10 MB por padrão: o
    // backend recebia só o começo do prontuário e devolvia 400. O teto cabe o
    // maior arquivo da tela de envio (100 MB) mais o envelope do multipart.
    middlewareClientMaxBodySize: 120 * 1024 * 1024,
    // O repasse ao backend cortava em 30 s, menos do que um prontuário de
    // dezenas de MB leva numa conexão residencial.
    proxyTimeout: 10 * 60 * 1000,
  },
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
