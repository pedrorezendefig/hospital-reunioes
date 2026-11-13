/**
 * O roteiro dos prints da página de Tecnologia e o seed dele (issue #1727,
 * ADR 0094, decisão 5).
 *
 * O roteiro (`scripts/manual/tecnologia/roteiro.sh`) semeia o diretor de
 * exemplo, responde no lugar do backend em toda rota da aba Tecnologia com a
 * tabela do `respostas.py` e fotografa a tela pelo playwright-cli. Assim
 * nenhuma conversa chama a IA e nenhum card real do GitHub entra no print.
 * Rodar o roteiro de verdade pede o app no ar, o que o CI não tem; aqui se
 * prova o contrato dele: refaz todas as imagens que a página cita, recusa o
 * que não é o app local, a tabela cobre o que a tela pede e enche o Quadro de
 * hoje, e o seed e as respostas só têm gente e endereço de exemplo.
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { conversaValida } from "@/components/tecnologia/chat";
import { colunasDoQuadro, type Demanda } from "@/components/tecnologia/demandas";
import { carregarPaginasDoManual } from "./carregar";
import { imagensCitadas } from "./paginas";

const PASTA = join(process.cwd(), "scripts", "manual", "tecnologia");
const ROTEIRO = join(PASTA, "roteiro.sh");
const SEED_CRU = readFileSync(join(PASTA, "seed.json"), "utf8");
const SEED = JSON.parse(SEED_CRU);

/** Os PNGs que o roteiro grava: o último argumento de cada `print` e `print_tela`. */
function imagensDoRoteiro(texto: string): string[] {
  return Array.from(texto.matchAll(/^\s*print(?:_tela)?\s.*"([^"/]+\.png)"\s*$/gm), (m) => m[1]);
}

/** A tabela que o roteiro serve no lugar do backend: a rota (depois de `/api/admin/tecnologia/`) e o corpo. */
function tabela(): Record<string, unknown> {
  const rodada = spawnSync("python3", [join(PASTA, "respostas.py")], { encoding: "utf8" });
  if (rodada.status !== 0) throw new Error(rodada.stderr);
  return JSON.parse(rodada.stdout);
}

/** Todo texto de um valor JSON, folha por folha. */
function folhas(valor: unknown): string[] {
  if (typeof valor === "string") return [valor];
  if (valor && typeof valor === "object") return Object.values(valor).flatMap(folhas);
  return [];
}

const NUMERO_LONGO = /\d[\d .()-]{7,}\d/;
const EMAIL = /[\w.+-]+@[\w.-]+/g;
const ENDERECO = /https?:\/\/[^\s"']+/gi;
/** Gente de verdade que mexe nesta aba: o nome não pode ir para um print do repositório público. */
const NOMES_REAIS = ["pedro rezende", "pedro rib", "lucas sampaio", "hospitalsaomatheus", "são matheus", "sao matheus"];

/** E-mails, telefones, endereços e nomes que não são de exemplo, num texto. Compara em casefold. */
function dadoReal(texto: string): string[] {
  const dobrado = texto.toLocaleLowerCase("pt-BR");
  const emails = (dobrado.match(EMAIL) ?? []).filter((e) => !e.endsWith("@exemplo.local"));
  const enderecos = (dobrado.match(ENDERECO) ?? []).filter((u) => !/^https:\/\/[\w.-]*exemplo\.local(\/|$)/.test(u));
  // Data e hora (2026-11-12, 2026-11-12T12:00:00-03:00) são do calendário, não de gente.
  const semDatas = texto.replace(/\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?\b/g, "");
  const numeros = NUMERO_LONGO.test(semDatas) ? [texto] : [];
  const nomes = NOMES_REAIS.filter((nome) => dobrado.includes(nome));
  return [...emails, ...enderecos, ...numeros, ...nomes];
}

describe("o roteiro dos prints da página de Tecnologia", () => {
  it("refaz todas as imagens que a página cita, e só elas", () => {
    const pagina = carregarPaginasDoManual().find((p) => p.modulo === "tecnologia")!;
    const citadas = imagensCitadas(pagina.corpo);
    const doRoteiro = imagensDoRoteiro(readFileSync(ROTEIRO, "utf8"));

    expect(citadas.length).toBeGreaterThan(0);
    expect([...doRoteiro].sort()).toEqual([...citadas].sort());
  });

  it("recusa rodar contra um endereço que não é o app local", () => {
    const rodada = spawnSync("bash", [ROTEIRO], {
      env: { ...process.env, BASE: "https://app.hospitalsaomatheus.cloud", PATH: "/usr/bin:/bin" },
      encoding: "utf8",
    });

    expect(rodada.status).toBe(1);
    expect(rodada.stderr).toContain("não é o app local");
    expect(rodada.stdout).not.toContain("pronta");
  });

  it("serve a tabela no lugar do backend e não deixa pedido nenhum seguir para ele", () => {
    const texto = readFileSync(ROTEIRO, "utf8");
    expect(texto).toMatch(/page\.route\(/);
    // Fora da tabela e fora do GET, a resposta é do próprio roteiro, nunca do backend.
    expect(texto).not.toMatch(/route\.(continue|fallback)\(/);
  });
});

describe("a tabela de respostas da aba Tecnologia", () => {
  const T = tabela();
  const lista = T["chat"] as Demanda[];

  it("responde quem está logado como diretor, os Desenvolvedores, a lista e as Entregas", () => {
    expect(T["eu"]).toEqual({ desenvolvedor: false });
    expect(Array.isArray(T["desenvolvedores"])).toBe(true);
    expect(lista.length).toBeGreaterThan(0);
    expect(T["entregas"]).toMatchObject({ topo: expect.any(Object), semanas: expect.any(Array), grupos: expect.any(Array) });
  });

  it("enche todas as colunas do Quadro de hoje, inclusive Entregue", () => {
    for (const coluna of colunasDoQuadro(lista, false, new Date())) {
      expect(coluna.cards.length, `a coluna ${coluna.rotulo} sai vazia`).toBeGreaterThan(0);
    }
  });

  it("o filtro Projeto em Ana traz só os pedidos da Ana, e todos eles", () => {
    const daAna = T["chat?projeto=ana"] as Demanda[];
    expect(daAna.length).toBeGreaterThan(0);
    expect(daAna.every((d) => d.projeto === "ana")).toBe(true);
    expect(daAna.map((d) => d.id).sort()).toEqual(lista.filter((d) => d.projeto === "ana").map((d) => d.id).sort());
  });

  it("cada pedido do diretor abre com uma conversa que a tela aceita, e cada card com a Conversa da Demanda", () => {
    for (const demanda of lista) {
      if (demanda.origem !== "vitta") {
        expect(conversaValida(T[`chat/${demanda.id}`]), `a conversa de ${demanda.id} não serve`).toBe(true);
      }
      if (demanda.tem_vinculo) {
        expect(T[`chat/${demanda.id}/conversa`], `falta a Conversa da Demanda de ${demanda.id}`).toMatchObject({
          mensagens: expect.any(Array),
        });
      }
    }
  });

  it("as conversas que o roteiro fotografa estão no ponto do print: a pergunta da melhoria e o resumo do bug", () => {
    const melhoria = T[`chat/${SEED.abrir.melhoria}`] as { estado: string; planejamento: boolean; mensagens: { recomendada?: string }[] };
    expect(melhoria.estado).toBe("em_andamento");
    expect(melhoria.planejamento).toBe(true);
    // A última fala é a pergunta com a recomendada: a tela não pede o turno seguinte à IA.
    expect(melhoria.mensagens.at(-1)?.recomendada).toMatch(/^[AB]$/);
    const bug = T[`chat/${SEED.abrir.bug}`] as { estado: string; resumo: unknown };
    expect(bug.estado).toBe("resumido");
    expect(bug.resumo).toBeTruthy();
  });
});

describe("o seed e as respostas da página de Tecnologia", () => {
  it("o diretor de exemplo fica na faixa P17280 a P17289, longe das pessoas dos outros roteiros", () => {
    expect(SEED.admin.id).toMatch(/^P1728\d$/);
    for (const dev of SEED.desenvolvedores) expect(dev.id).toMatch(/^P1728\d$/);
  });

  it("o seed só tem e-mail de exemplo, e nenhum telefone, endereço ou nome de gente de verdade", () => {
    expect((SEED_CRU.match(EMAIL) ?? []).length).toBeGreaterThan(0);
    expect(folhas(SEED).flatMap(dadoReal)).toEqual([]);
  });

  it("a tabela de respostas não traz e-mail, telefone, endereço nem nome de gente de verdade", () => {
    expect(folhas(tabela()).flatMap(dadoReal)).toEqual([]);
  });
});

describe("os detectores do roteiro e do dado real", () => {
  it("o print de um pedaço e o da tela inteira contam como imagem do roteiro", () => {
    const texto = 'print "$(bloco x)" "bloco.png"\nprint_tela "tela.png"\n# print "velho.png"';
    expect(imagensDoRoteiro(texto)).toEqual(["bloco.png", "tela.png"]);
  });

  it("e-mail de verdade, telefone, endereço de fora e nome real são pegos, em maiúscula ou minúscula", () => {
    for (const real of [
      "diretoria@hospitalsaomatheus.com.br",
      "Fulano@Gmail.com",
      "(21) 99876-5432",
      "123.456.789-09",
      "HTTPS://github.com/exemplo/issues/1",
      "Responsável: PEDRO REZENDE",
      "Hospital São Matheus",
    ]) {
      expect(dadoReal(real), real).not.toEqual([]);
    }
    expect(dadoReal("HENRIQUE.BASTOS@EXEMPLO.LOCAL")).toEqual([]);
    expect(dadoReal("https://demonstracao.exemplo.local/selo")).toEqual([]);
    expect(dadoReal("2026-11-12T12:00:00-03:00")).toEqual([]);
  });
});
