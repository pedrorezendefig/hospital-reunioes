/**
 * A página de Dados do Atendimento do manual (issue #1726, ADR 0094, decisões
 * 4 e 5).
 *
 * Lê a página de verdade, em `public/manual/dados-do-atendimento/pagina.md`, e
 * o roteiro que refaz os prints dela, em `scripts/manual/dados-do-atendimento/`.
 * Quem vê a página, o que cada tarefa traz, o fluxograma e a origem dos prints
 * são promessas desta página; as que valem para toda página (módulo no menu,
 * imagem existente) moram em `paginas.test.ts`.
 */

import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { lerFluxograma, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import { fluxogramasCitados, imagensCitadas, paginasVisiveis } from "./paginas";

function pessoa(campos: Partial<CurrentParticipante>): CurrentParticipante {
  return {
    id: "p1",
    nome_completo: "Fulana de Tal",
    email: "fulana@hsm",
    access_profile: "regular",
    ...campos,
  };
}

/** Cada `## ` do corpo é uma tarefa: o título e o texto até o próximo `## `. */
function tarefas(corpo: string): { titulo: string; texto: string }[] {
  return corpo
    .split(/^## /m)
    .slice(1)
    .map((bloco) => {
      const [titulo, ...resto] = bloco.split("\n");
      return { titulo: titulo.trim(), texto: resto.join("\n") };
    });
}

/** As tarefas que faltam passo numerado ou print. */
function tarefasIncompletas(corpo: string): string[] {
  return tarefas(corpo)
    .filter(({ texto }) => !/^1\. /m.test(texto) || imagensCitadas(texto).length === 0)
    .map(({ titulo }) => titulo);
}

const PAGINAS = carregarPaginasDoManual();
const PAGINA = PAGINAS.find((pagina) => pagina.pasta === "dados-do-atendimento");

describe("a página de Dados do Atendimento", () => {
  it("existe e declara o módulo Dados do Atendimento", () => {
    expect(PAGINA?.modulo).toBe("dados-do-atendimento");
    expect(PAGINA?.titulo).toBe("Dados do Atendimento");
  });

  it("aparece para quem acessa Dados do Atendimento e some para quem não acessa", () => {
    const pastas = (p: CurrentParticipante) => paginasVisiveis(PAGINAS, p).map((x) => x.pasta);

    expect(pastas(pessoa({ access_profile: "secretaria" }))).toContain("dados-do-atendimento");
    expect(pastas(pessoa({ access_profile: "regular" }))).toContain("dados-do-atendimento");
    expect(pastas(pessoa({ access_profile: null, perfil_pop: "coordenador" }))).not.toContain(
      "dados-do-atendimento"
    );
  });
});

describe("as tarefas da página de Dados do Atendimento", () => {
  it("são o preço da consulta particular, o preparo do exame e a estimativa de cirurgia", () => {
    expect(tarefas(PAGINA!.corpo).map((t) => t.titulo)).toEqual([
      "Mudar o preço de uma consulta particular",
      "Mudar o preparo de um exame",
      "Mudar a estimativa de uma cirurgia",
    ]);
  });

  it("cada tarefa tem passos numerados e pelo menos um print", () => {
    expect(tarefasIncompletas(PAGINA!.corpo)).toEqual([]);
  });

  it("o detector pega a tarefa sem print e a tarefa sem passo numerado", () => {
    const corpo = [
      "## Sem print",
      "1. Clique em **Admin**.",
      "## Sem passo",
      "Abra a tabela.",
      "![A tabela](tabela.png)",
      "## Completa",
      "1. Clique em **Admin**.",
      "![A tabela](tabela.png)",
    ].join("\n\n");
    expect(tarefasIncompletas(corpo)).toEqual(["Sem print", "Sem passo"]);
  });
});

/** Os passos que se alcançam a partir de `de`, seguindo as ligações. */
function alcancaveis(fluxo: Fluxo, de: string): Set<string> {
  const vistos = new Set([de]);
  const fila = [de];
  while (fila.length) {
    const atual = fila.shift()!;
    for (const l of fluxo.ligacoes) {
      if (l.de === atual && !vistos.has(l.para)) {
        vistos.add(l.para);
        fila.push(l.para);
      }
    }
  }
  return vistos;
}

describe("o fluxograma da página de Dados do Atendimento", () => {
  const blocos = fluxogramasCitados(PAGINA?.corpo ?? "");

  it("desenha da edição na tabela até a próxima resposta da Ana, sem erro de bloco", () => {
    expect(blocos).toHaveLength(1);
    const leitura = lerFluxograma(blocos[0]);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));

    const inicio = leitura.fluxo.passos.filter((p) => p.forma === "inicio");
    const fim = leitura.fluxo.passos.filter((p) => p.forma === "fim");
    expect(inicio).toHaveLength(1);
    expect(fim).toHaveLength(1);
    expect(inicio[0].rotulo).toMatch(/editar na tabela/i);
    expect(fim[0].rotulo).toMatch(/ana responde/i);
    expect(alcancaveis(leitura.fluxo, inicio[0].id).has(fim[0].id)).toBe(true);
  });

  it("o registro desativado não chega à resposta da Ana", () => {
    const leitura = lerFluxograma(blocos[0]);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const [decisao] = leitura.fluxo.passos.filter((p) => p.forma === "decisao");
    const nao = leitura.fluxo.ligacoes.find((l) => l.de === decisao?.id && l.rotulo === "não");
    const fim = leitura.fluxo.passos.find((p) => p.forma === "fim")!;

    expect(decisao?.rotulo).toMatch(/ativo/i);
    expect(nao).toBeTruthy();
    expect(alcancaveis(leitura.fluxo, nao!.para).has(fim.id)).toBe(false);
  });
});

const ROTEIRO = join(process.cwd(), "scripts", "manual", "dados-do-atendimento");
const lerDoRoteiro = (arquivo: string) => readFileSync(join(ROTEIRO, arquivo), "utf8");

/** Os PNGs que o roteiro grava: cada `foto("<arquivo>.png")` do prints.js. */
function printsDoRoteiro(codigo: string): string[] {
  return Array.from(codigo.matchAll(/\bfoto\(\s*"([^"]+\.png)"/g), (m) => m[1]);
}

describe("o roteiro dos prints da página de Dados do Atendimento", () => {
  it("refaz todas as imagens da página, e só elas", () => {
    const daPagina = [...new Set(imagensCitadas(PAGINA!.corpo))].sort();
    const doRoteiro = printsDoRoteiro(lerDoRoteiro("prints.js")).sort();

    expect(daPagina.length).toBeGreaterThan(0);
    expect(doRoteiro).toEqual(daPagina);
  });

  it("a pasta da página não guarda PNG que nenhum passo cita", () => {
    const pasta = join(process.cwd(), "public", "manual", "dados-do-atendimento");
    const pngs = readdirSync(pasta).filter((arquivo) => arquivo.endsWith(".png")).sort();
    expect(pngs).toEqual([...new Set(imagensCitadas(PAGINA!.corpo))].sort());
  });

  it("o detector lê o nome de cada print do roteiro", () => {
    const codigo = 'await foto("lista.png");\nawait foto( "ficha.png", { fullPage: true });\nfoto(arquivo);';
    expect(printsDoRoteiro(codigo)).toEqual(["lista.png", "ficha.png"]);
  });

  it("recusa rodar contra um banco que não é o da máquina", () => {
    const pasta = mkdtempSync(join(tmpdir(), "roteiro-dados-atendimento-"));
    const env = join(pasta, ".env");
    writeFileSync(env, "SUPABASE_URL=https://banco.de-producao.exemplo\nSUPABASE_SERVICE_ROLE_KEY=x\n");

    const rodada = spawnSync("bash", [join(ROTEIRO, "roteiro.sh")], {
      env: { ...process.env, ENV_LOCAL: env },
      encoding: "utf8",
    });

    expect(rodada.status).toBe(1);
    expect(rodada.stderr).toContain("recusado");
  });
});

/**
 * Os nomes que as migrations 061 e 062 trazem para as tabelas da Ana: são os
 * preços de verdade do hospital, importados da planilha antiga. Nenhum deles
 * pode aparecer num print.
 */
function nomesReais(): string[] {
  const migrations = join(process.cwd(), "..", "supabase", "migrations");
  const sql = ["061_consultas_particulares_ana.sql", "062_exames_cirurgias_convenios_ana.sql"]
    .map((arquivo) => readFileSync(join(migrations, arquivo), "utf8"))
    .join("\n");
  return Array.from(sql.matchAll(/^\s*\('([^']+)'/gm), (m) => m[1]);
}

/** Os nomes que o seed põe nas três tabelas: a primeira coluna de cada linha. */
function nomesDoSeed(seed: string): string[] {
  return Array.from(seed.matchAll(/^\s*\('([^']+)',/gm), (m) => m[1]).filter(
    (nome) => !/^P\d+$/.test(nome)
  );
}

/** Os nomes do seed que repetem um nome real, sem ligar para maiúscula. */
function nomesReaisNoSeed(seed: string, reais: string[]): string[] {
  const proibidos = new Set(reais.map((nome) => nome.trim().toLocaleLowerCase("pt-BR")));
  return nomesDoSeed(seed).filter((nome) => proibidos.has(nome.trim().toLocaleLowerCase("pt-BR")));
}

describe("os dados de exemplo dos prints", () => {
  const roteiro = lerDoRoteiro("roteiro.sh");
  // O SQL vive dentro do roteiro.sh (heredoc 'SQL'): .sql fora das pastas
  // liberadas trava o CI, porque o repositório é público.
  const seed = roteiro.match(/<<'SQL'\n([\s\S]*?)\nSQL\n/)?.[1] ?? "";

  it("o SQL de exemplo está dentro do roteiro e semeia as três tabelas", () => {
    expect(seed).toContain("insert into participantes");
    expect(seed).toContain("insert into consultas_particulares");
    expect(seed).toContain("insert into exames");
    expect(seed).toContain("insert into cirurgias_estimativas");
  });

  it("nenhum nome do seed repete o nome de um preço real do hospital", () => {
    const reais = nomesReais();
    expect(reais).toContain("Cardiologia");
    expect(nomesDoSeed(seed).length).toBeGreaterThanOrEqual(6);
    expect(nomesReaisNoSeed(seed, reais)).toEqual([]);
  });

  it("o detector pega o nome real mesmo com outra caixa", () => {
    const falso = "  ('CARDIOLOGIA', 300.00, 'x'),\n  ('Endocrinologia', 310.00, 'y'),";
    expect(nomesReaisNoSeed(falso, ["Cardiologia"])).toEqual(["CARDIOLOGIA"]);
  });

  it("os prints mostram só as linhas do seed", () => {
    const prints = lerDoRoteiro("prints.js");
    const doFiltro = prints.match(/const EXEMPLOS = (\[[\s\S]*?\]);/)?.[1] ?? "[]";
    expect((JSON.parse(doFiltro) as string[]).sort()).toEqual(nomesDoSeed(seed).sort());
  });

  it("só usam e-mails do domínio de exemplo, inclusive o de quem entra nos prints", () => {
    const emails = [...`${seed}\n${roteiro}`.matchAll(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g)].map((m) => m[0]);

    expect(emails.length).toBeGreaterThan(0);
    expect(emails.filter((email) => !email.endsWith("@exemplo.local"))).toEqual([]);
  });

  it("só criam pessoas na faixa própria do módulo, P17260 a P17269", () => {
    const ids = [...new Set([...seed.matchAll(/'(P\d{3,})'/g)].map((m) => m[1]))];

    expect(ids.length).toBeGreaterThan(0);
    expect(ids.filter((id) => !/^P1726\d$/.test(id))).toEqual([]);
  });
});
