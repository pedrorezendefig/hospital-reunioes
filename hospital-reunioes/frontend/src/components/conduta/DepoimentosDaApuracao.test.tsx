/**
 * @vitest-environment jsdom
 */

/**
 * Os depoimentos da Apuração do Canal de Conduta (issue #1830; especificação,
 * seções 7.1 e 7.2).
 *
 * O servidor decide o que vale (a lista de conferência e o motivo do bloqueio
 * chegam prontos). O que se trava aqui é o que o cartão mostra e o que ele
 * pede ao servidor: cada arquivo pelo seu botão, o termo pela câmera, o áudio
 * tocado do que o backend entregou, sem URL do bucket.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Depoimento, ItemDaLista } from "@/lib/conduta/depoimentos";

import { DepoimentosDaApuracao } from "./DepoimentosDaApuracao";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }) },
  }),
}));

let chamadas: { url: string; method: string; body: unknown; headers: Record<string, string> }[];

beforeEach(() => {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({
        url,
        method: init?.method ?? "GET",
        body: init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : null,
        headers: (init?.headers ?? {}) as Record<string, string>,
      });
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
        blob: async () => new Blob(["som"], { type: "audio/mp4" }),
      } as Response;
    })
  );
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:http://localhost/audio-1", revokeObjectURL: () => {} }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const LISTA_PENDENTE: ItemDaLista[] = [
  { item: "transcricao", rotulo: "Transcrição anexada", automatico: true, estado: "pendente" },
  { item: "audio", rotulo: "Áudio anexado", automatico: true, estado: "pendente" },
  { item: "termo_assinado", rotulo: "Termo assinado anexado", automatico: true, estado: "pendente" },
  { item: "arquivos_corretos", rotulo: "Abri os arquivos na aplicação e estão corretos", automatico: false, estado: "pendente" },
  { item: "gravacao_apagada", rotulo: "Apaguei a gravação de áudio da plataforma de gravação", automatico: false, estado: "pendente" },
  { item: "arquivos_apagados", rotulo: "Apaguei os arquivos do computador e do celular", automatico: false, estado: "pendente" },
  { item: "original_no_envelope", rotulo: "Guardei o original assinado no envelope do caso", automatico: false, estado: "pendente" },
];

const DEPOIMENTO: Depoimento = {
  id: "d1",
  nome: "Fulano de Tal",
  cargo: "Supervisor do almoxarifado",
  papel: "acusado",
  situacao: "Aguardando assinatura",
  arquivos: { transcricao: [], audio: [], termo_assinado: [] },
  sem_gravacao: null,
  lista: LISTA_PENDENTE,
  bloqueio_da_conclusao: "Falta marcar: Transcrição anexada, Áudio anexado.",
  concluido_em: null,
  concluido_por: null,
};

function desenhar(depoimento: Partial<Depoimento> = {}, extra: Partial<Parameters<typeof DepoimentosDaApuracao>[0]> = {}) {
  const aoMudar = vi.fn();
  render(
    <DepoimentosDaApuracao
      casoId="c1"
      depoimentos={[{ ...DEPOIMENTO, ...depoimento }]}
      emApuracao
      bloqueioDoAvanco={null}
      adicionando={false}
      aoFecharAdicionar={() => {}}
      aoMudar={aoMudar}
      {...extra}
    />
  );
  return { aoMudar, cartao: screen.getByRole("article", { name: "Fulano de Tal" }) };
}

describe("o cartão recebe transcrição, áudio e termo assinado, cada um no seu botão", () => {
  it("tem os três botões e nenhum seletor de tipo", () => {
    const { cartao } = desenhar();

    for (const botao of ["ANEXAR TRANSCRIÇÃO DO DEPOIMENTO", "ANEXAR ÁUDIO DO DEPOIMENTO", "ANEXAR TERMO ASSINADO"]) {
      expect(within(cartao).getByRole("button", { name: botao })).toBeTruthy();
    }
    expect(within(cartao).queryByRole("combobox")).toBeNull();
    expect(within(cartao).getByText("Acusado, Supervisor do almoxarifado")).toBeTruthy();
    expect(within(cartao).getByText("Aguardando assinatura")).toBeTruthy();
  });

  it("o arquivo do botão do áudio vai ao endereço do áudio, com o login", async () => {
    const { aoMudar } = desenhar();
    const audio = new File(["som"], "gravacao.m4a", { type: "audio/mp4" });

    fireEvent.change(screen.getByLabelText("Arquivo do áudio do depoimento"), { target: { files: [audio] } });

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    const envio = chamadas.at(-1)!;
    expect(envio.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/audio");
    expect(envio.method).toBe("POST");
    expect(envio.headers.Authorization).toBe("Bearer token-de-teste");
    expect((envio.body as FormData).getAll("arquivo")).toEqual([audio]);
  });

  it("o botão da transcrição envia ao endereço da transcrição", async () => {
    const { aoMudar } = desenhar();

    fireEvent.change(screen.getByLabelText("Arquivo da transcrição do depoimento"), {
      target: { files: [new File(["texto"], "transcricao.txt")] },
    });

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/transcricao");
  });

  it("o áudio grande demais é recusado na tela antes de subir", async () => {
    desenhar();
    const grande = new File(["x"], "gravacao.m4a");
    Object.defineProperty(grande, "size", { value: 301 * 1024 * 1024 });

    fireEvent.change(screen.getByLabelText("Arquivo do áudio do depoimento"), { target: { files: [grande] } });

    expect(await screen.findByText("O áudio passa de 300 MB.")).toBeTruthy();
    expect(chamadas).toEqual([]);
  });
});

describe("o áudio toca do que o backend entregou", () => {
  it("OUVIR pede o arquivo ao backend e toca o endereço local, sem URL do bucket", async () => {
    desenhar({
      arquivos: {
        transcricao: [],
        audio: [{ versao: 1, enviado_em: "2026-11-20T13:00:00+00:00", enviado_por: "Bruno Membro", paginas: [{ id: "a1", content_type: "audio/mp4", tamanho_bytes: 250 * 1024 * 1024 }] }],
        termo_assinado: [],
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "OUVIR VERSÃO 1" }));

    const player = await screen.findByLabelText("Áudio do depoimento, versão 1");
    expect(player.getAttribute("src")).toBe("blob:http://localhost/audio-1");
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/arquivos/a1");
    expect(chamadas.at(-1)!.headers.Authorization).toBe("Bearer token-de-teste");
  });
});

describe("o termo assinado sobe pela câmera do celular, e a versão nova não apaga a anterior", () => {
  it("a câmera abre direto, e as fotos vão juntas como páginas do termo", async () => {
    const { aoMudar } = desenhar();
    const camera = screen.getByLabelText("Foto do termo assinado");
    expect(camera.getAttribute("capture")).toBe("environment");
    expect(camera.getAttribute("accept")).toBe("image/*");

    const pagina1 = new File(["p1"], "image.jpg", { type: "image/jpeg" });
    const pagina2 = new File(["p2"], "image.jpg", { type: "image/jpeg" });
    fireEvent.change(camera, { target: { files: [pagina1] } });
    fireEvent.change(screen.getByLabelText("Foto do termo assinado"), { target: { files: [pagina2] } });
    fireEvent.click(screen.getByRole("button", { name: "ENVIAR TERMO ASSINADO (2 PÁGINAS)" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    const envio = chamadas.at(-1)!;
    expect(envio.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/termo-assinado");
    expect((envio.body as FormData).getAll("arquivo")).toEqual([pagina1, pagina2]);
  });

  it("mostra todas as versões, da mais nova para a mais antiga", () => {
    const { cartao } = desenhar({
      arquivos: {
        transcricao: [],
        audio: [],
        termo_assinado: [
          { versao: 2, enviado_em: "2026-11-21T13:00:00+00:00", enviado_por: "Ana Coordenadora", paginas: [{ id: "t2", content_type: "image/jpeg", tamanho_bytes: 10 }] },
          { versao: 1, enviado_em: "2026-11-20T13:00:00+00:00", enviado_por: "Bruno Membro", paginas: [{ id: "t1", content_type: "image/jpeg", tamanho_bytes: 10 }] },
        ],
      },
    });

    const termo = within(cartao).getByRole("list", { name: "Versões do termo assinado" });
    expect(within(termo).getAllByRole("listitem").map((l) => l.textContent)).toEqual([
      expect.stringContaining("Versão 2, por Ana Coordenadora"),
      expect.stringContaining("Versão 1, por Bruno Membro"),
    ]);
  });
});

describe("CONCLUIR DEPOIMENTO e a lista de conferência", () => {
  it("fica bloqueado, com o motivo, até os sete itens", () => {
    const { cartao } = desenhar();

    const concluir = within(cartao).getByRole("button", { name: "CONCLUIR DEPOIMENTO" }) as HTMLButtonElement;
    expect(concluir.disabled).toBe(true);
    expect(within(cartao).getByText("Falta marcar: Transcrição anexada, Áudio anexado.")).toBeTruthy();
  });

  it("liberado, conclui no servidor", async () => {
    const { cartao, aoMudar } = desenhar({ bloqueio_da_conclusao: null });

    fireEvent.click(within(cartao).getByRole("button", { name: "CONCLUIR DEPOIMENTO" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/conclusao");
  });

  it("a declaração marcada diz quem marcou e quando, e não se desmarca", () => {
    const lista = LISTA_PENDENTE.map((i) =>
      i.item === "gravacao_apagada"
        ? { ...i, estado: "feito" as const, marcado_por: "Ana Coordenadora", marcado_em: "2026-11-20T13:05:00+00:00" }
        : i
    );
    const { cartao } = desenhar({ lista });

    const marcada = within(cartao).getByRole("checkbox", { name: "Apaguei a gravação de áudio da plataforma de gravação" }) as HTMLInputElement;
    expect(marcada.checked).toBe(true);
    expect(marcada.disabled).toBe(true);
    expect(within(cartao).getByText("Marcado por Ana Coordenadora em 20/11/2026, 10:05")).toBeTruthy();
  });

  it("marcar uma declaração grava no servidor", async () => {
    const { cartao, aoMudar } = desenhar();

    fireEvent.click(within(cartao).getByRole("checkbox", { name: "Guardei o original assinado no envelope do caso" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/conferencia");
    expect(chamadas.at(-1)!.body).toEqual({ item: "original_no_envelope" });
  });

  it("os itens automáticos não são caixas de marcar", () => {
    const { cartao } = desenhar();

    expect(within(cartao).getAllByRole("checkbox")).toHaveLength(4);
  });
});

describe("sem gravação", () => {
  it("os pontos aparecem no lugar da transcrição e os dois itens ficam Não se aplica, com o motivo", () => {
    const motivo = "A pessoa não aceitou ser gravada.";
    const lista = LISTA_PENDENTE.map((i) =>
      i.item === "transcricao" || i.item === "audio" ? { ...i, estado: "nao_se_aplica" as const, motivo } : i
    );
    const { cartao } = desenhar({
      sem_gravacao: { motivo, pontos: "Confirmou que levantou a voz.", registrado_por: "Bruno Membro" },
      lista,
    });

    expect(within(cartao).getByText("Confirmou que levantou a voz.")).toBeTruthy();
    const conferencia = within(cartao).getByRole("region", { name: "Lista de conferência" });
    expect(within(conferencia).getAllByText(`Não se aplica: ${motivo}`)).toHaveLength(2);
    expect(within(cartao).queryByRole("button", { name: "ANEXAR ÁUDIO DO DEPOIMENTO" })).toBeNull();
    expect(within(cartao).queryByRole("button", { name: "ANEXAR TRANSCRIÇÃO DO DEPOIMENTO" })).toBeNull();
    expect(within(cartao).getByRole("button", { name: "ANEXAR TERMO ASSINADO" })).toBeTruthy();
  });

  it("registrar sem gravação envia o motivo e os pontos", async () => {
    const { cartao, aoMudar } = desenhar();

    fireEvent.click(within(cartao).getByRole("button", { name: "A PESSOA NÃO ACEITOU GRAVAÇÃO" }));
    fireEvent.change(within(cartao).getByLabelText("Motivo"), { target: { value: "Recusou a gravação." } });
    fireEvent.change(within(cartao).getByLabelText("Pontos da conversa"), { target: { value: "Negou os fatos." } });
    fireEvent.click(within(cartao).getByRole("button", { name: "REGISTRAR SEM GRAVAÇÃO" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos/d1/sem-gravacao");
    expect(chamadas.at(-1)!.body).toEqual({ motivo: "Recusou a gravação.", pontos: "Negou os fatos." });
  });
});

describe("adicionar pessoa a ouvir e o avanço da Apuração", () => {
  it("o formulário cria o cartão com nome, cargo e papel", async () => {
    const aoMudar = vi.fn();
    render(
      <DepoimentosDaApuracao
        casoId="c1"
        depoimentos={[]}
        emApuracao
        bloqueioDoAvanco={null}
        adicionando
        aoFecharAdicionar={() => {}}
        aoMudar={aoMudar}
      />
    );

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Beltrana" } });
    fireEvent.change(screen.getByLabelText("Cargo"), { target: { value: "Técnica de enfermagem" } });
    fireEvent.click(screen.getByLabelText("Testemunha"));
    fireEvent.click(screen.getByRole("button", { name: "ADICIONAR" }));

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(chamadas.at(-1)!.url).toBe("/api/comite-de-conduta/casos/c1/depoimentos");
    expect(chamadas.at(-1)!.body).toEqual({ nome: "Beltrana", cargo: "Técnica de enfermagem", papel: "testemunha" });
  });

  it("diz que a Apuração não avança com depoimento em aberto", () => {
    desenhar({}, { bloqueioDoAvanco: "A Apuração só avança com todos os depoimentos concluídos. Falta 1." });

    expect(screen.getByText("A Apuração só avança com todos os depoimentos concluídos. Falta 1.")).toBeTruthy();
  });
});
