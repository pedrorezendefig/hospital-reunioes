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
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/:path*`,
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
