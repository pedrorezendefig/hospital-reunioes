/**
 * @vitest-environment jsdom
 */

/**
 * O sexto tipo nas duas portas da tela (issue #490, ADR 0040 decisão 1).
 *
 * A lista fechada já tem teste próprio em `lib/ouvidoria/taxonomia.ts`. O que
 * só existe aqui dentro é a fiação: os dois seletores que classificam um caso
 * lerem essa lista em vez de trazerem as opções escritas à mão. Sem este
 * arquivo, alguém que fixasse os cinco tipos antigos no JSX de uma das telas
 * deixaria a suíte inteira verde, e o ouvidor continuaria sem conseguir
 * classificar como informação exatamente onde ele classifica.
 *
 * O `fetch` entra dublado por URL: as duas telas carregam setores,
 * responsáveis, anexos e notificações, e nada disso importa para o que se quer
 * provar.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dossie } from "./Dossie";
import { NovaManifestacaoModal } from "./NovaManifestacaoModal";
import { ValidarModal } from "./ValidarModal";

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

const CASO_DO_CANAL_ABERTO = {
  id: "uuid-12",
  protocolo: "2026-0012",
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-08-21",
  status: "em_classificacao",
  tipo_manifestacao: null,
  categoria: "A classificar",
  setor: "A definir",
  resumo: "Paciente quer saber como pedir a segunda via do laudo.",
  relato_integral: "Perdi o laudo do exame e nao sei a quem pedir a segunda via.",
  manifestante_nome: null,
  manifestante_contato: null,
  manifestante_vinculo: null,
  anonimo: true,
  sigilo_reforcado: false,
  dados_incompletos: false,
  desfecho: null,
  desfecho_descricao: null,
  gravidade: null,
  prazo_area_em: null,
  validada_em: null,
  respondida_em: null,
  resposta_da_area: null,
  respondida_por_nome: null,
  encerrada_em: null,
  pausada_em: null,
  minutos_pausados: 0,
  reincidencia: false,
  reaberta_em: null,
  canal: "qr",
  canal_setor: "Recepção",
  canal_ponto: null,
  natureza_informada: "informacao",
};

function dublarFetch(caso: Record<string, unknown> = CASO_DO_CANAL_ABERTO) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      if (url.includes("/setores")) return respostaJson({ setores: [] });
      if (url.includes("/responsaveis")) return respostaJson({ responsaveis: [] });
      return respostaJson(caso);
    })
  );
}

describe("informação como opção nas duas portas de classificação (issue #490)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("a Validação e acionamento oferece informação, junto dos outros cinco tipos", async () => {
    dublarFetch();
    render(
      <ValidarModal
        manifestacao={{
          id: "uuid-12",
          protocolo: "2026-0012",
          tipo_manifestacao: null,
          categoria: "A classificar",
          setor: "A definir",
          sigilo_reforcado: false,
        }}
        token="token-de-teste"
        onClose={() => {}}
        onAcionada={() => {}}
      />
    );

    const opcao = (await screen.findAllByRole("option", { name: "Informação" }))[0];
    expect((opcao as HTMLOptionElement).value).toBe("informacao");
    // Os cinco antigos continuam lá: o tipo novo entra na lista, não no lugar
    // de ninguém.
    expect(screen.getAllByRole("option", { name: "Relato de conduta" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "Denúncia" }).length).toBeGreaterThan(0);
  });

  it("a Classificação do Dossiê oferece informação, junto dos outros cinco tipos", async () => {
    dublarFetch();
    render(<Dossie protocolo="2026-0012" token="token-de-teste" />);

    const opcao = (await screen.findAllByRole("option", { name: "Informação" }))[0];
    expect((opcao as HTMLOptionElement).value).toBe("informacao");
    expect(screen.getAllByRole("option", { name: "Relato de conduta" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "Denúncia" }).length).toBeGreaterThan(0);
  });

  it("o Registro manual também oferece informação", async () => {
    // A terceira porta que grava o tipo. Ela não classifica um caso que já
    // existe: nasce um caso já com o tipo, e o ouvidor que atende o telefone
    // precisa poder registrar um pedido de informação como o que ele é.
    dublarFetch();
    render(
      <NovaManifestacaoModal aberto token="token-de-teste" onClose={() => {}} onRegistrada={() => {}} />
    );

    const opcao = (await screen.findAllByRole("option", { name: "Informação" }))[0];
    expect((opcao as HTMLOptionElement).value).toBe("informacao");
    expect(screen.getAllByRole("option", { name: "Relato de conduta" }).length).toBeGreaterThan(0);
  });
});
