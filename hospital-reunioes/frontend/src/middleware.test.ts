/**
 * O alcance do middleware do Next (issue #344).
 *
 * Este arquivo existe por causa de um quase-acidente: a fatia do painel da
 * Ouvidoria pôs `/ouvidoria/:path*` no matcher para "proteger a área", e com
 * isso levou junto `/ouvidoria/qr`, que é o rewrite do cartaz colado na parede
 * da Recepção (ADR 0034 decisão 9, ADR 0036). O middleware roda ANTES dos
 * rewrites do `next.config`, então o backend nunca veria a requisição: quem
 * apontasse a câmera para o cartaz receberia a tela de login do staff. Cartaz
 * na parede não se corrige com deploy.
 *
 * A regra que estes testes fixam: o que o matcher alcança é interceptado antes
 * de qualquer rewrite. Área pública fica FORA dele, e o que a Ouvidoria precisa
 * de guarda ela tem nos layouts de servidor (`app/ouvidoria/layout.tsx` para
 * sessão, `app/ouvidoria/painel/layout.tsx` para perfil).
 *
 * O molde é o `next.config.test.ts`, que já testa o mapa de rewrites nesta casa.
 */
import { describe, expect, it } from "vitest";

import { config, isProtectedPath } from "./middleware";
import nextConfig from "../next.config";

/**
 * O padrão do matcher como expressão regular. Aproximação deliberada da regra
 * do Next, o bastante para o que se quer provar aqui: `:param*` come zero ou
 * mais segmentos, `:param` come exatamente um.
 *
 * A aproximação não pode mentir para o lado permissivo sem ser notada, e é para
 * isso que existe o teste de controle positivo logo abaixo: se esta conversão
 * quebrar, ele cai junto, em vez de deixar tudo passar como "não interceptado".
 */
function alcanca(padrao: string, pathname: string): boolean {
  const regex = padrao
    .replace(/\/:[A-Za-z_][A-Za-z0-9_]*\*/g, "(?:/.*)?")
    .replace(/\/:[A-Za-z_][A-Za-z0-9_]*/g, "/[^/]+");
  return new RegExp(`^${regex}$`).test(pathname);
}

function interceptado(pathname: string): boolean {
  return config.matcher.some((padrao) => alcanca(padrao, pathname));
}

/** A URL do cartaz, lida de onde ela é declarada de verdade. */
async function urlDoCartaz(): Promise<string> {
  const rewrites = await nextConfig.rewrites!();
  if (!Array.isArray(rewrites)) throw new Error("rewrites deveria ser uma lista");
  const cartaz = rewrites.find((r) => r.source.startsWith("/ouvidoria"));
  if (!cartaz) throw new Error("o rewrite do cartaz da Ouvidoria sumiu do next.config");
  return cartaz.source;
}

describe("o que o middleware intercepta", () => {
  it("alcança as áreas do staff, que é para o que ele existe", () => {
    // Controle positivo: sem ele, uma conversão quebrada deixaria todos os
    // testes de baixo verdes por motivo errado.
    expect(interceptado("/dashboard")).toBe(true);
    expect(interceptado("/dashboard/qualquer/coisa")).toBe(true);
    expect(interceptado("/reunioes/123")).toBe(true);
    expect(interceptado("/admin")).toBe(true);
    expect(interceptado("/configuracoes")).toBe(true);
    expect(interceptado("/login")).toBe(true);
  });
});

describe("o que o middleware NÃO pode interceptar", () => {
  it("não alcança a URL impressa no cartaz de QR da Ouvidoria", async () => {
    // Lida do `next.config`, e não escrita à mão: se a URL do cartaz mudar, o
    // teste continua guardando a URL certa.
    const cartaz = await urlDoCartaz();

    expect(cartaz).toBe("/ouvidoria/qr");
    expect(interceptado(cartaz)).toBe(false);
  });

  it("não alcança o portal que o gestor de área abre pelo link do email", () => {
    // Entra por token, sem sessão: interceptar aqui derrubaria a cobrança de
    // prazo que o setor recebe por email.
    expect(interceptado("/ouvidoria-setor")).toBe(false);
    expect(interceptado("/ouvidoria-setor/um-token-qualquer")).toBe(false);
  });

  it("não alcança o formulário público de manifestação", () => {
    expect(interceptado("/manifestacao")).toBe(false);
  });

  it("deixa a área logada da Ouvidoria para os layouts de servidor", () => {
    // Não é esquecimento: `app/ouvidoria/layout.tsx` já exige sessão e
    // `app/ouvidoria/painel/layout.tsx` exige o perfil. Trazer a área para cá
    // não compra guarda nenhuma e traz junto a URL pública do cartaz.
    expect(interceptado("/ouvidoria")).toBe(false);
    expect(interceptado("/ouvidoria/painel")).toBe(false);
  });
});

/**
 * A segunda régua do middleware (issue #439). O matcher decide o que chega
 * até ele; `isProtectedPath` decide o que exige sessão depois de chegar.
 *
 * Antes, a régua era `pathname.startsWith(p)`, prefixo de texto puro: uma
 * rota futura chamada `/admin-publico` seria protegida sem ninguém pedir, só
 * porque o nome dela começa com o nome de uma área. Área não é prefixo de
 * texto, é segmento.
 */
describe("o que conta como área protegida", () => {
  it("protege a própria área e o que desce dentro dela", () => {
    // Controle positivo: sem ele, uma régua quebrada para o lado restritivo
    // deixaria os testes de baixo verdes por motivo errado.
    expect(isProtectedPath("/admin")).toBe(true);
    expect(isProtectedPath("/admin/x")).toBe(true);
    expect(isProtectedPath("/admin/usuarios/P10")).toBe(true);
    expect(isProtectedPath("/dashboard")).toBe(true);
    expect(isProtectedPath("/reunioes/123")).toBe(true);
    expect(isProtectedPath("/perfil")).toBe(true);
  });

  it("não protege rota vizinha que só começa com o nome da área", () => {
    // O caso do achado: nome parecido não é a mesma área.
    expect(isProtectedPath("/admin-publico")).toBe(false);
    expect(isProtectedPath("/admin-publico/qualquer")).toBe(false);
    expect(isProtectedPath("/perfil-do-hospital")).toBe(false);
    expect(isProtectedPath("/reunioes-abertas")).toBe(false);
  });

  it("deixa a área pública de fora, como o matcher já deixa", () => {
    expect(isProtectedPath("/ouvidoria/qr")).toBe(false);
    expect(isProtectedPath("/manifestacao")).toBe(false);
    expect(isProtectedPath("/login")).toBe(false);
  });

  it("o matcher também não alcança a rota vizinha", () => {
    // As duas réguas concordam: se um dia o matcher passar a alcançar
    // `/admin-publico`, este teste cai antes de a guarda decidir por ela.
    expect(interceptado("/admin-publico")).toBe(false);
  });
});
