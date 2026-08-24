import type { NextConfig } from "next";
import withSerwistInit from "@serwist/next";
import pkg from "./package.json";

const APP_VERSION = pkg.version;

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  cacheOnNavigation: true,
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
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
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
