// Cacoetes de texto gerado que dao para pegar por regex (ADR 0071, decisao 1).
//
// Espelho do `tools/tells_texto.py`, a lista unica que o lint do Manual usa.
// Os dois leem os casos do `tools/tells_casos.json` nos testes: mudou um padrao
// aqui, mude la e acrescente o caso no JSON. As regexes sao as mesmas, escritas
// para valer igual nas duas linguagens (sem \b, que no JS nao ve letra
// acentuada; a classe de letras e explicita).
//
// A regra `hospital/sem-tells` olha string e texto de JSX, como a trava do
// travessao no eslint.config.mjs; comentario fica de fora.

import { relative, sep } from "node:path";

const L = "A-Za-zÀ-ÖØ-öø-ÿ";
const COPULA = "(?:é|são|foi|era)";

function porRegex(padrao) {
  return (texto) =>
    [...texto.matchAll(new RegExp(padrao, "gi"))].map((m) => [m.index, m[0]]);
}

const RE_TITULO = /^ {0,3}#{1,6}\s/;
const RE_NAO_LETRA = new RegExp(`[^${L}0-9 ]`, "g");

// Secoes seguidas que terminam num paragrafo de uma linha comecado igual ate a
// primeira pontuacao ("Simples assim.", "Pronto, ..."). Aponta o segundo fecho.
function fechosRepetidos(texto) {
  const secoes = [[]];
  let pos = 0;
  for (const linha of texto.split("\n")) {
    if (RE_TITULO.test(linha)) secoes.push([]);
    else secoes[secoes.length - 1].push([pos, linha]);
    pos += linha.length + 1;
  }
  const achados = [];
  let anterior = null;
  for (const secao of secoes) {
    const paragrafos = [];
    let novo = true;
    for (const [p, linha] of secao) {
      if (!linha.trim()) novo = true;
      else if (novo) {
        paragrafos.push([[p, linha]]);
        novo = false;
      } else paragrafos[paragrafos.length - 1].push([p, linha]);
    }
    let fecho = null;
    const ultimo = paragrafos[paragrafos.length - 1];
    if (paragrafos.length >= 2 && ultimo.length === 1) {
      const [p, linha] = ultimo[0];
      const limpa = linha.trim().replace(/^[*_]+|[*_]+$/g, "");
      // Linha com link e a estrutura das Novidades, nao fecho.
      if (new RegExp(`^[${L}]`).test(limpa) && !limpa.includes("[")) {
        const inicio = limpa.split(/[,.:;!?]/)[0];
        const chave = inicio.replace(RE_NAO_LETRA, " ").toLowerCase().trim().split(/\s+/).join(" ");
        fecho = [p + linha.indexOf(linha.trim()), linha.trim(), chave];
      }
    }
    if (fecho && anterior !== null && fecho[2] === anterior) achados.push([fecho[0], fecho[1]]);
    anterior = fecho ? fecho[2] : null;
  }
  return achados;
}

export const CACOETES = [
  {
    nome: "nao-e-x-e-y",
    achar: porRegex(
      `(?<![${L}])não\\s+${COPULA}\\s[^\\n.!?;:]{1,80}?[,;.]\\s+` +
        `(?:(?:mas\\s+)?${COPULA}|(?:mas|e)\\s+sim)(?![${L}])`,
    ),
  },
  {
    nome: "nao-so-x-mas-y",
    achar: porRegex(
      `(?<![${L}])não\\s+(?:só|apenas|somente)(?![${L}])[^\\n.!?;]{1,100}?` +
        `(?<![${L}])(?:mas|como)(?![${L}])`,
    ),
  },
  {
    nome: "nao-x-dois-pontos-y",
    // "Nao foi possivel X: <causa>" e "nao pode ser lido: ..." sao aviso de
    // falha, nao contraste.
    achar: porRegex(
      `(?<![${L}])não\\s+(?!foi\\s+possível|pôde|puderam)[^\\n.!?;:,]{1,40}:(?=\\s+[${L}])`,
    ),
  },
  {
    nome: "mais-do-que-x-y",
    // So no comeco da frase: "custa mais do que o previsto" e comparacao.
    achar: porRegex(
      `(?<![${L}0-9,;:])(?<![${L}0-9,;:]\\s)mais\\s+(?:do\\s+)?que\\s[^\\n.!?;:]{1,80}?,`,
    ),
  },
  {
    nome: "nao-se-trata-de",
    achar: porRegex(`(?<![${L}])não\\s+se\\s+trata\\s+de(?![${L}])`),
  },
  { nome: "fecho-repetido", achar: fechosRepetidos },
];

export function acharTells(texto, cacoetes = CACOETES) {
  return cacoetes
    .flatMap((c) => c.achar(texto).map(([posicao, trecho]) => ({ cacoete: c.nome, trecho, posicao })))
    .sort((a, b) => a.posicao - b.posicao || a.cacoete.localeCompare(b.cacoete));
}

// Opcao `conhecidos`: arquivo (relativo ao frontend) -> trechos que ja estavam
// no ar quando a regra nasceu (eslint-rules/tells_conhecidos.json). Eles passam;
// a varredura do texto do app (issue #1229) tira da tela e da lista.
const semTells = {
  meta: {
    type: "problem",
    schema: [
      {
        type: "object",
        properties: { conhecidos: { type: "object" } },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const arquivo = relative(context.cwd, context.filename).split(sep).join("/");
    const jaNoAr = new Set(context.options[0]?.conhecidos?.[arquivo] ?? []);
    const checar = (node, texto) => {
      for (const o of acharTells(texto)) {
        if (jaNoAr.has(o.trecho)) continue;
        context.report({
          node,
          message:
            `Cacoete de texto gerado (${o.cacoete}): "${o.trecho}". ` +
            "Reescreva com o fato direto (ADR 0071).",
        });
      }
    };
    return {
      Literal(node) {
        if (typeof node.value === "string") checar(node, node.value);
      },
      JSXText(node) {
        checar(node, node.value);
      },
    };
  },
};

export const pluginHospital = { rules: { "sem-tells": semTells } };
