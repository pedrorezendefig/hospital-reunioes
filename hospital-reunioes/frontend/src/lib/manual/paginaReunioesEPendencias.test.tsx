/**
 * @vitest-environment jsdom
 */

/**
 * A página de Reuniões e Pendências do manual (issue #1721, ADR 0094).
 *
 * Os testes leem o Markdown de verdade, do disco, e não uma cópia: a página que
 * a pessoa abre é a mesma que eles conferem. As tarefas esperadas vêm da
 * issue (marcar a reunião, anexar a transcrição, revisar a Ata, mandar para
 * assinatura e acompanhar as Pendências).
 */

import { existsSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MarkdownDoManual } from "@/components/manual/MarkdownDoManual";
import { lerFluxograma, type Fluxo } from "@/components/manual/fluxograma/fluxo";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";
import { carregarPaginasDoManual } from "./carregar";
import { enderecoDaImagem, imagensCitadas, paginasVisiveis } from "./paginas";

afterEach(() => {
  cleanup();
});

const PAGINAS = carregarPaginasDoManual();
const PAGINA = PAGINAS.find((p) => p.pasta === "reunioes-e-pendencias")!;

function pessoa(papeis: Partial<CurrentParticipante>): CurrentParticipante {
  return { id: "p1", nome_completo: "Fulana de Tal", email: "fulana@hsm", ...papeis };
}

/** As seções `##` da página: o título e o texto até a próxima. */
function secoes(corpo: string): { titulo: string; texto: string }[] {
  return corpo
    .split(/^## /m)
    .slice(1)
    .map((parte) => {
      const [titulo, ...resto] = parte.split("\n");
      return { titulo: titulo.trim(), texto: resto.join("\n") };
    });
}

const FONTE_DO_FLUXOGRAMA = /```fluxograma\n([\s\S]*?)```/;

/** Os passos que se alcançam a partir de `de`, seguindo as ligações. */
function alcancaveis(fluxo: Fluxo, de: string): Set<string> {
  const achados = new Set([de]);
  const fila = [de];
  while (fila.length) {
    const atual = fila.shift()!;
    for (const l of fluxo.ligacoes) {
      if (l.de === atual && !achados.has(l.para)) {
        achados.add(l.para);
        fila.push(l.para);
      }
    }
  }
  return achados;
}

describe("quem vê a página de Reuniões e Pendências", () => {
  it("o Facilitador vê a página, e quem só tem POPs não vê", () => {
    const facilitador = paginasVisiveis(PAGINAS, pessoa({ access_profile: "regular" }));
    const soPops = paginasVisiveis(PAGINAS, pessoa({ access_profile: null, perfil_pop: "coordenador" }));

    expect(facilitador.map((p) => p.pasta)).toContain("reunioes-e-pendencias");
    expect(soPops.map((p) => p.pasta)).not.toContain("reunioes-e-pendencias");
  });
});

describe("as tarefas da página", () => {
  const tarefas = secoes(PAGINA.corpo).filter((s) => !FONTE_DO_FLUXOGRAMA.test(s.texto));

  it("tem as tarefas da issue, da reunião às Pendências", () => {
    const titulos = tarefas.map((t) => t.titulo);
    for (const tarefa of [
      /^Marcar uma reunião$/,
      /^Anexar a transcrição/,
      /^Revisar a Ata$/,
      /^Mandar a Ata para assinatura$/,
      /^Acompanhar as Pendências$/,
    ]) {
      expect(titulos.some((t) => tarefa.test(t)), String(tarefa)).toBe(true);
    }
  });

  it("cada tarefa tem passos numerados e pelo menos um print que existe", () => {
    const semPasso = tarefas.filter((t) => !/^1\. /m.test(t.texto) || !/^2\. /m.test(t.texto));
    const semPrint = tarefas.filter((t) => imagensCitadas(t.texto).length === 0);
    const printsQueFaltam = tarefas
      .flatMap((t) => imagensCitadas(t.texto))
      .map((src) => enderecoDaImagem(PAGINA.pasta, src))
      .filter((endereco) => !existsSync(join(process.cwd(), "public", endereco)));

    expect(tarefas.length).toBeGreaterThanOrEqual(5);
    expect(semPasso.map((t) => t.titulo)).toEqual([]);
    expect(semPrint.map((t) => t.titulo)).toEqual([]);
    expect(printsQueFaltam).toEqual([]);
  });
});

describe("o fluxograma da página", () => {
  const fonte = FONTE_DO_FLUXOGRAMA.exec(PAGINA.corpo)?.[1] ?? "";

  it("vai da reunião até a Ata assinada e às Pendências que nascem dela", () => {
    const leitura = lerFluxograma(fonte);
    if (!leitura.ok) throw new Error(leitura.erros.join("\n"));
    const { fluxo } = leitura;
    const porRotulo = (rotulo: RegExp) => fluxo.passos.find((p) => rotulo.test(p.rotulo))?.id ?? "";

    const inicio = fluxo.passos.find((p) => p.forma === "inicio");
    const assinada = porRotulo(/^Ata assinada$/);
    const pendencias = porRotulo(/^Pendências/);

    expect(inicio?.rotulo).toMatch(/reunião/i);
    expect(alcancaveis(fluxo, inicio!.id)).toContain(assinada);
    expect(alcancaveis(fluxo, assinada)).toContain(pendencias);
  });

  it("a página desenha o fluxograma, sem erro de bloco", () => {
    const { container } = render(<MarkdownDoManual pasta={PAGINA.pasta}>{PAGINA.corpo}</MarkdownDoManual>);

    expect(container.querySelector("[data-fluxograma]")).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});
