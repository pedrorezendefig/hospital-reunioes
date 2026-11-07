/**
 * @vitest-environment jsdom
 */

/**
 * A regra base da Caixa alta (ADR 0080, issue #1454).
 *
 * O jsdom não lê `@layer` nem calcula herança de `text-transform`, e por isso
 * o teste tira o bloco `@layer base` do `globals.css` real, injeta o miolo como
 * folha comum e resolve a herança à mão (`caixaEfetiva`): sobe do elemento até
 * o primeiro ancestral que alguma regra do bloco alcança. Assim o que se prova
 * é o CSS que vai para produção, e não uma cópia dele.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SELETOR_DO_TEXTO_CURTO, apareceComoFoiEscrito } from "@/lib/caixa-alta";

const CSS = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

/** O miolo de cada `@layer base { ... }` do arquivo, pelas chaves casadas. */
function blocosDaCamadaBase(css: string): string {
  const miolos: string[] = [];
  let inicio = css.indexOf("@layer base");
  while (inicio !== -1) {
    const abre = css.indexOf("{", inicio);
    let profundidade = 1;
    let i = abre + 1;
    for (; i < css.length && profundidade > 0; i++) {
      if (css[i] === "{") profundidade++;
      if (css[i] === "}") profundidade--;
    }
    miolos.push(css.slice(abre + 1, i - 1));
    inicio = css.indexOf("@layer base", i);
  }
  return miolos.join("\n");
}

const CAMADA_BASE = blocosDaCamadaBase(CSS);

let regras: CSSStyleRule[] = [];

beforeAll(() => {
  const estilo = document.createElement("style");
  estilo.textContent = CAMADA_BASE;
  document.head.appendChild(estilo);
  regras = Array.from(estilo.sheet!.cssRules).filter(
    (regra): regra is CSSStyleRule => "selectorText" in regra
  );
});

afterEach(() => {
  document.body.innerHTML = "";
});

/** A caixa com que o elemento sai: a própria, se uma regra o alcança, ou a herdada. */
function caixaEfetiva(elemento: Element): string {
  for (let atual: Element | null = elemento; atual; atual = atual.parentElement) {
    const alcancado = regras.some(
      (regra) => regra.style.getPropertyValue("text-transform") !== "" && atual!.matches(regra.selectorText)
    );
    if (alcancado) return getComputedStyle(atual).textTransform;
  }
  return "none";
}

function montar(html: string): HTMLElement {
  document.body.innerHTML = html;
  return document.body;
}

describe("a regra base existe no globals.css", () => {
  it("o bloco @layer base tem regras (piso de sanidade do extrator)", () => {
    // Sem este piso, um extrator que devolvesse vazio deixaria todo teste de
    // "fica em caixa mista" verde sem ter olhado para nada.
    expect(regras.length).toBeGreaterThanOrEqual(3);
  });

  it("o seletor da regra é o mesmo que os testes de componente usam", () => {
    // `lib/caixa-alta` guarda a lista para o teste de componente saber o que
    // grita. Se o CSS ganhar ou perder um elemento sem ela, o teste do dado
    // passa a olhar para a regra errada.
    const normalizar = (seletor: string) =>
      seletor.split(",").map((parte) => parte.trim().replace(/'/g, '"')).sort();
    const daRegra = regras.find((regra) => regra.style.getPropertyValue("text-transform") === "uppercase");
    expect(normalizar(daRegra!.selectorText)).toEqual(normalizar(SELETOR_DO_TEXTO_CURTO));
  });

  it("não muda o tamanho da fonte", () => {
    expect(CAMADA_BASE).not.toMatch(/font-size/);
  });
});

describe("o Texto curto sai em caixa alta", () => {
  it.each([
    ["título h1", "<h1 id='alvo'>Reuniões</h1>"],
    ["subtítulo h2", "<h2 id='alvo'>Próximas reuniões</h2>"],
    ["subtítulo h3", "<h3 id='alvo'>Notificações</h3>"],
    ["botão", "<button id='alvo'>Salvar</button>"],
    ["nome de campo", "<label id='alvo'>Nome</label>"],
    ["cabeçalho de coluna", "<table><thead><tr><th id='alvo'>Prazo</th></tr></thead></table>"],
    ["aba", "<div role='tablist'><button role='tab' id='alvo'>Lista</button></div>"],
    ["aba que não é botão", "<div role='tablist'><a role='tab' id='alvo'>Kanban</a></div>"],
    ["item de menu", "<nav><a href='/pops' id='alvo'>POPs</a></nav>"],
    ["etiqueta de situação", "<span class='etiqueta' id='alvo'>Atrasada</span>"],
    ["ícone e texto dentro do botão", "<button><span id='alvo'>Entrar</span></button>"],
  ])("%s", (_nome, html) => {
    montar(html);
    expect(caixaEfetiva(document.getElementById("alvo")!)).toBe("uppercase");
  });

  it("com espaçamento leve entre as letras", () => {
    montar("<button id='alvo'>Salvar</button>");
    // O jsdom devolve em pixels (0,02em sobre 16px). Leve: mais de zero, menos de 1px.
    const espaco = parseFloat(getComputedStyle(document.getElementById("alvo")!).letterSpacing);
    expect(espaco).toBeGreaterThan(0);
    expect(espaco).toBeLessThan(1);
  });
});

describe("o Texto corrido fica com maiúscula e minúscula", () => {
  it.each([
    ["parágrafo", "<p id='alvo'>A reunião foi marcada.</p>"],
    ["aviso (toast)", "<div role='status' id='alvo'>Salvo com sucesso.</div>"],
    ["mensagem de erro", "<div role='alert' id='alvo'>Não foi possível salvar.</div>"],
    ["texto de ajuda", "<span id='alvo'>Use o nome completo.</span>"],
    ["link solto, fora do menu", "<a href='/x' id='alvo'>abrir a ata</a>"],
    ["célula da tabela", "<table><tbody><tr><td id='alvo'>Maria</td></tr></tbody></table>"],
    ["subtítulo h4", "<h4 id='alvo'>Detalhe</h4>"],
  ])("%s", (_nome, html) => {
    montar(html);
    expect(caixaEfetiva(document.getElementById("alvo")!)).toBe("none");
  });

  it("o parágrafo dentro de um cartão clicável", () => {
    montar("<button><span>Reunião</span><p id='alvo'>A pauta ficou para terça.</p></button>");
    expect(caixaEfetiva(document.getElementById("alvo")!)).toBe("none");
  });

  it("o parágrafo dentro do rótulo de uma opção", () => {
    montar("<label><input type='radio' /><p id='alvo'>Quero ser identificado.</p></label>");
    expect(caixaEfetiva(document.getElementById("alvo")!)).toBe("none");
  });

  it.each(["input", "textarea", "select"])("o que se digita no %s dentro do rótulo", (campo) => {
    montar(`<label>Nome <${campo} id='alvo'></${campo}></label>`);
    expect(caixaEfetiva(document.getElementById("alvo")!)).toBe("none");
  });
});

describe("apareceComoFoiEscrito, a régua dos testes de componente", () => {
  it.each([
    ["dado com normal-case dentro do título", "<h1>Reunião <span class='normal-case' id='alvo'>Comitê de Ética</span></h1>", true],
    ["dado solto dentro do título", "<h1>Reunião <span id='alvo'>Comitê de Ética</span></h1>", false],
    ["dado no botão inteiro com normal-case", "<button class='normal-case'><span id='alvo'>Maria Souza</span></button>", true],
    ["dado no parágrafo do cartão clicável", "<button><p id='alvo'>Maria Souza</p></button>", true],
    ["dado sob a classe uppercase", "<p class='uppercase'><span id='alvo'>Maria Souza</span></p>", false],
    ["dado em texto corrido", "<div><span id='alvo'>Maria Souza</span></div>", true],
    ["etiqueta dentro de um botão com normal-case", "<button class='normal-case'><span class='etiqueta' id='alvo'>Novo</span></button>", false],
  ])("%s", (_nome, html, esperado) => {
    montar(html);
    expect(apareceComoFoiEscrito(document.getElementById("alvo")!)).toBe(esperado);
  });
});
