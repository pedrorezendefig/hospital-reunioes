/**
 * Helpers de ambiente do frontend.
 *
 * Le NEXT_PUBLIC_ENVIRONMENT que e injetada em build time
 * (Dockerfile + docker-compose.yml + .env).
 *
 * Em producao (Coolify), garantir que NEXT_PUBLIC_ENVIRONMENT=production
 * esta configurada nas env vars do projeto antes do build.
 */

export const environment = (process.env.NEXT_PUBLIC_ENVIRONMENT ?? "development") as
  | "development"
  | "production";

export const isDev = environment === "development";
export const isProd = environment === "production";
