/**
 * A régua do destino de retorno pós-login (issue #477, RN-54, PRD #468).
 *
 * A funcionalidade é conveniência: quem clica no link do caso estando deslogado
 * faz o login e cai no caso, não na tela inicial. A régua, no entanto, é
 * segurança: o valor chega pela query string, ou seja, quem escolhe o que vem
 * ali é quem monta o link, e link montado por terceiro é open redirect
 * esperando acontecer (a pessoa vê o domínio do hospital, autentica, e sai
 * cuspida num site parecido pedindo a senha de novo).
 *
 * Por isso os casos de fora do site vêm em variedade: não basta recusar
 * `https://evil.com`, é preciso recusar as formas que começam com `/` e mesmo
 * assim saem daqui.
 */
import { describe, expect, it } from "vitest";

import {
  DESTINO_PADRAO,
  caminhoInternoOuNulo,
  destinoAposLogin,
  urlDeLoginCom,
} from "./destino";

describe("destino interno é aceito", () => {
  it("aceita a rota do caso da Ouvidoria", () => {
    expect(caminhoInternoOuNulo("/ouvidoria/m/2026-0012")).toBe("/ouvidoria/m/2026-0012");
  });

  it("preserva a query string e a âncora do destino", () => {
    expect(caminhoInternoOuNulo("/ouvidoria?status=em_classificacao")).toBe(
      "/ouvidoria?status=em_classificacao"
    );
    expect(caminhoInternoOuNulo("/ouvidoria/painel#fila")).toBe("/ouvidoria/painel#fila");
  });

  it("aceita a raiz", () => {
    expect(caminhoInternoOuNulo("/")).toBe("/");
  });

  it("devolve a forma já resolvida, e não o texto cru", () => {
    // O que sai daqui vira navegação. Devolver o texto cru deixaria a
    // navegação acontecer numa forma que ninguém mediu, ainda que neste caso
    // as duas cheguem ao mesmo lugar.
    expect(caminhoInternoOuNulo("/ouvidoria/../admin")).toBe("/admin");
  });
});

describe("destino de fora do site é recusado", () => {
  it("recusa URL absoluta", () => {
    expect(caminhoInternoOuNulo("https://evil.com/roubo")).toBeNull();
    expect(caminhoInternoOuNulo("http://evil.com")).toBeNull();
  });

  it("recusa a URL de protocolo relativo, que começa com barra e sai daqui", () => {
    // O caso clássico: `//evil.com` passa por qualquer teste de `startsWith("/")`
    // e o navegador o lê como `https://evil.com`.
    expect(caminhoInternoOuNulo("//evil.com")).toBeNull();
    expect(caminhoInternoOuNulo("//evil.com/roubo")).toBeNull();
  });

  it("recusa a variante de barra invertida, que o navegador normaliza para barra", () => {
    expect(caminhoInternoOuNulo("/\\evil.com")).toBeNull();
    expect(caminhoInternoOuNulo("\\\\evil.com")).toBeNull();
    expect(caminhoInternoOuNulo("/ouvidoria\\..\\evil")).toBeNull();
  });

  it("recusa esquema que não é caminho nenhum", () => {
    expect(caminhoInternoOuNulo("javascript:alert(1)")).toBeNull();
    expect(caminhoInternoOuNulo("data:text/html,<h1>oi</h1>")).toBeNull();
    expect(caminhoInternoOuNulo("mailto:alguem@exemplo.com")).toBeNull();
  });

  it("recusa caminho relativo, que não começa na raiz", () => {
    expect(caminhoInternoOuNulo("ouvidoria/painel")).toBeNull();
    expect(caminhoInternoOuNulo("../admin")).toBeNull();
  });

  it("recusa espaço em branco e caractere de controle", () => {
    expect(caminhoInternoOuNulo(" /ouvidoria")).toBeNull();
    expect(caminhoInternoOuNulo("/ouvi doria")).toBeNull();
    expect(caminhoInternoOuNulo("/ouvidoria\nSet-Cookie: x=1")).toBeNull();
    expect(caminhoInternoOuNulo("/\tevil")).toBeNull();
  });
});

describe("destino ausente ou malformado", () => {
  it("recusa vazio, nulo e o que não é texto", () => {
    expect(caminhoInternoOuNulo("")).toBeNull();
    expect(caminhoInternoOuNulo(null)).toBeNull();
    expect(caminhoInternoOuNulo(undefined)).toBeNull();
    expect(caminhoInternoOuNulo(42)).toBeNull();
    expect(caminhoInternoOuNulo(["/ouvidoria"])).toBeNull();
  });
});

describe("para onde o login manda", () => {
  it("manda para o destino quando ele é interno", () => {
    expect(destinoAposLogin("/ouvidoria/m/2026-0012")).toBe("/ouvidoria/m/2026-0012");
  });

  it("manda para o padrão quando não há destino", () => {
    expect(destinoAposLogin(null)).toBe(DESTINO_PADRAO);
    expect(destinoAposLogin("")).toBe(DESTINO_PADRAO);
    expect(DESTINO_PADRAO).toBe("/dashboard");
  });

  it("manda para o padrão quando o destino sai daqui", () => {
    expect(destinoAposLogin("https://evil.com")).toBe(DESTINO_PADRAO);
    expect(destinoAposLogin("//evil.com")).toBe(DESTINO_PADRAO);
  });
});

describe("a URL de login que carrega o destino", () => {
  it("codifica o destino na query string", () => {
    expect(urlDeLoginCom("/ouvidoria/m/2026-0012")).toBe(
      "/login?redirect=%2Fouvidoria%2Fm%2F2026-0012"
    );
  });

  it("codifica destino que já tem query própria, sem vazar os parâmetros dele", () => {
    // Sem codificar, o `&` do destino viraria parâmetro do próprio /login.
    expect(urlDeLoginCom("/ouvidoria?status=novo&setor=UTI")).toBe(
      "/login?redirect=%2Fouvidoria%3Fstatus%3Dnovo%26setor%3DUTI"
    );
  });

  it("não carrega destino nenhum quando ele sai daqui ou não existe", () => {
    expect(urlDeLoginCom("https://evil.com")).toBe("/login");
    expect(urlDeLoginCom("//evil.com")).toBe("/login");
    expect(urlDeLoginCom(null)).toBe("/login");
  });
});
