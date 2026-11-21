/**
 * @vitest-environment jsdom
 */

/**
 * A tela da Pendência mostra o histórico e pede anotação em toda ação
 * (issue #1862, ADR 0098, decisão 5).
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AcoesDaPendencia } from "./AcoesDaPendencia";

const HISTORICO = {
  eventos: [
    {
      id: 1,
      comando: "iniciar",
      anotacao: "Comecei a cotação",
      autor_nome: "Rita Souza",
      criado_em: "2026-11-10T13:05:00+00:00",
      conta_atraso: false,
    },
    {
      id: 2,
      comando: "repactuar",
      anotacao: "Fornecedor atrasou",
      autor_nome: "Fábio Lima",
      prazo_antes: "2026-11-12",
      prazo_depois: "2026-11-30",
      criado_em: "2026-11-14T18:40:00+00:00",
      conta_atraso: true,
    },
  ],
  acoes_permitidas: ["anotar", "concluir", "repactuar"],
};

let chamadas: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ id_acao: "A001", status: "CONCLUIDO" }), { status: 200 });
      }
      return new Response(JSON.stringify(HISTORICO), { status: 200 });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function montar(onAtualizada = vi.fn()) {
  render(<AcoesDaPendencia idAcao="A001" token="tk" onAtualizada={onAtualizada} />);
  return onAtualizada;
}

describe("histórico da pendência", () => {
  it("mostra cada evento em ordem, com quem, quando e a anotação", async () => {
    montar();

    const lista = await screen.findByRole("list", { name: "Histórico da pendência" });
    const itens = within(lista).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0].textContent).toContain("Iniciou");
    expect(itens[0].textContent).toContain("Rita Souza");
    expect(itens[0].textContent).toContain("10/11/2026");
    expect(itens[0].textContent).toContain("Comecei a cotação");
    expect(itens[1].textContent).toContain("Repactuou");
    expect(itens[1].textContent).toContain("30/11/2026");
    expect(itens[1].textContent).toContain("Depois do vencimento");
  });

  it("mostra só as ações que quem olha pode fazer", async () => {
    montar();

    await screen.findByRole("button", { name: "Concluir" });
    expect(screen.queryByRole("button", { name: "Cancelar pendência" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reabrir" })).toBeNull();
  });
});

describe("toda ação pede anotação", () => {
  it.each(["Anotar", "Concluir", "Repactuar"])("%s só confirma com anotação escrita", async (rotulo) => {
    montar();

    fireEvent.click(await screen.findByRole("button", { name: rotulo }));
    const confirmar = screen.getByRole("button", { name: "Confirmar" });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    // Com o prazo preenchido (quando a ação pede), ainda falta a anotação.
    const prazo = screen.queryByLabelText("Prazo novo");
    if (prazo) fireEvent.change(prazo, { target: { value: "2026-12-20" } });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "   " } });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
  });

  it("concluir manda a anotação e devolve a pendência atualizada", async () => {
    const onAtualizada = montar();

    fireEvent.click(await screen.findByRole("button", { name: "Concluir" }));
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Entregue ao setor" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(onAtualizada).toHaveBeenCalledWith({ id_acao: "A001", status: "CONCLUIDO" }));
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(post?.url).toBe("/api/pendencias/A001/acoes");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ comando: "concluir", anotacao: "Entregue ao setor" });
  });

  it("repactuar pede o prazo novo além da anotação", async () => {
    montar();

    fireEvent.click(await screen.findByRole("button", { name: "Repactuar" }));
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Fornecedor" } });
    const confirmar = screen.getByRole("button", { name: "Confirmar" }) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Prazo novo"), { target: { value: "2026-12-20" } });
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);

    await waitFor(() => expect(chamadas.some((c) => c.init?.method === "POST")).toBe(true));
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      comando: "repactuar",
      anotacao: "Fornecedor",
      prazo: "2026-12-20",
    });
  });
});

describe("anexo na conclusão (issue #1865)", () => {
  function arquivo(nome: string, tipo: string, bytes = 2048): File {
    const f = new File(["x"], nome, { type: tipo });
    Object.defineProperty(f, "size", { value: bytes });
    return f;
  }

  async function abrirConclusao() {
    montar();
    fireEvent.click(await screen.findByRole("button", { name: "Concluir" }));
  }

  it("a recomendação sobre fotos aparece junto do campo de anexo", async () => {
    await abrirConclusao();

    const campo = screen.getByLabelText("Anexo (opcional)");
    const bloco = campo.closest("label");
    expect(bloco?.textContent).toContain("Não anexe foto com paciente nem documento interno sensível");
  });

  it("o campo de anexo só aparece na conclusão", async () => {
    montar();
    fireEvent.click(await screen.findByRole("button", { name: "Anotar" }));
    expect(screen.queryByLabelText("Anexo (opcional)")).toBeNull();
  });

  it("concluir com foto manda anotação e arquivo para a rota de conclusão", async () => {
    await abrirConclusao();
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Entregue" } });
    const foto = arquivo("almoxarifado.jpg", "image/jpeg");
    fireEvent.change(screen.getByLabelText("Anexo (opcional)"), { target: { files: [foto] } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(chamadas.some((c) => c.init?.method === "POST")).toBe(true));
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(post?.url).toBe("/api/pendencias/A001/conclusao");
    const corpo = post?.init?.body as FormData;
    expect(corpo.get("anotacao")).toBe("Entregue");
    expect(corpo.get("arquivo")).toBe(foto);
  });

  it.each([
    ["video.mp4", "video/mp4", 2048, "foto"],
    ["foto.jpg", "image/jpeg", 10 * 1024 * 1024 + 1, "10 MB"],
  ])("%s é recusado na tela com mensagem clara", async (nome, tipo, bytes, trecho) => {
    await abrirConclusao();
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Entregue" } });
    fireEvent.change(screen.getByLabelText("Anexo (opcional)"), { target: { files: [arquivo(nome, tipo, bytes)] } });

    expect(screen.getByRole("alert").textContent).toContain(trecho);
    expect((screen.getByRole("button", { name: "Confirmar" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("anexo no histórico (issue #1865)", () => {
  const COM_ANEXO = (pode: boolean) => ({
    eventos: [
      {
        id: 7,
        comando: "concluir",
        anotacao: "Entregue ao setor",
        autor_nome: "Rita Souza",
        criado_em: "2026-11-19T13:05:00+00:00",
        conta_atraso: false,
        anexo: { id: 3, nome: "nota fiscal.pdf", tipo: "application/pdf", tamanho_bytes: 4096 },
      },
    ],
    acoes_permitidas: [],
    pode_abrir_anexos: pode,
  });

  function servir(historico: unknown) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url, init });
        if (url.endsWith("/link")) {
          return new Response(JSON.stringify({ url: "https://storage.exemplo/assinado" }), { status: 200 });
        }
        return new Response(JSON.stringify(historico), { status: 200 });
      })
    );
  }

  it("o anexo aparece no evento de conclusão e abre pelo link assinado", async () => {
    servir(COM_ANEXO(true));
    const aba = { opener: {}, location: { href: "" }, close: vi.fn() };
    vi.stubGlobal("open", vi.fn(() => aba));
    montar();

    const lista = await screen.findByRole("list", { name: "Histórico da pendência" });
    const [conclusao] = within(lista).getAllByRole("listitem");
    expect(conclusao.textContent).toContain("nota fiscal.pdf");
    fireEvent.click(within(conclusao).getByRole("button", { name: "Abrir anexo" }));

    await waitFor(() => expect(aba.location.href).toBe("https://storage.exemplo/assinado"));
    expect(chamadas.some((c) => c.url === "/api/pendencias/A001/anexos/3/link")).toBe(true);
  });

  it("quem não abre vê que há anexo, sem o botão", async () => {
    servir(COM_ANEXO(false));
    montar();

    const lista = await screen.findByRole("list", { name: "Histórico da pendência" });
    const [conclusao] = within(lista).getAllByRole("listitem");
    expect(conclusao.textContent).toContain("nota fiscal.pdf");
    expect(within(conclusao).queryByRole("button", { name: "Abrir anexo" })).toBeNull();
  });
});

describe("contestação do item da Ata (issue #1870)", () => {
  function comHistorico(historico: unknown) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url, init });
        if (init?.method === "POST") return new Response(JSON.stringify({ id_acao: "A001" }), { status: 200 });
        return new Response(JSON.stringify(historico), { status: 200 });
      })
    );
  }

  it("o responsável contesta com anotação, sem prazo", async () => {
    comHistorico({ eventos: [], acoes_permitidas: ["anotar", "contestar"] });
    montar();

    fireEvent.click(await screen.findByRole("button", { name: "Contestar" }));
    expect(screen.queryByLabelText("Prazo novo")).toBeNull();
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "O prazo era março" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(chamadas.some((c) => c.init?.method === "POST")).toBe(true));
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ comando: "contestar", anotacao: "O prazo era março" });
  });

  it("o facilitador ajusta com anotação e, se quiser, o prazo novo", async () => {
    comHistorico({ eventos: [], acoes_permitidas: ["ajustar", "recusar"] });
    montar();

    fireEvent.click(await screen.findByRole("button", { name: "Ajustar" }));
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "Combinado em março" } });
    const confirmar = screen.getByRole("button", { name: "Confirmar" }) as HTMLButtonElement;
    // O prazo novo é opcional no ajuste: a anotação basta.
    expect(confirmar.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Prazo novo (opcional)"), { target: { value: "2027-03-31" } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(chamadas.some((c) => c.init?.method === "POST")).toBe(true));
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      comando: "ajustar",
      anotacao: "Combinado em março",
      prazo: "2027-03-31",
    });
  });

  it("o facilitador ajusta o responsável errado escolhendo a pessoa certa no cadastro", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url, init });
        if (init?.method === "POST") return new Response(JSON.stringify({ id_acao: "A001" }), { status: 200 });
        if (url.startsWith("/api/participantes")) {
          return new Response(JSON.stringify([{ id: "P_CERTO", nome_completo: "Carla Certa", cargo: "Enfermeira" }]), {
            status: 200,
          });
        }
        return new Response(JSON.stringify({ eventos: [], acoes_permitidas: ["ajustar", "recusar"] }), { status: 200 });
      })
    );
    montar();

    fireEvent.click(await screen.findByRole("button", { name: "Ajustar" }));
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "A luva é com a Carla" } });
    fireEvent.change(screen.getByLabelText("Responsável novo (opcional)"), { target: { value: "Carla" } });
    fireEvent.click(await screen.findByRole("button", { name: /Carla Certa/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(chamadas.some((c) => c.init?.method === "POST")).toBe(true));
    expect(chamadas.some((c) => c.url.startsWith("/api/participantes?nome=Carla"))).toBe(true);
    const post = chamadas.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      comando: "ajustar",
      anotacao: "A luva é com a Carla",
      responsavel_id: "P_CERTO",
    });
  });

  it("o histórico mostra a troca de responsável do ajuste", async () => {
    comHistorico({
      eventos: [
        {
          id: 3,
          comando: "ajustar",
          anotacao: "Era a Carla",
          autor_nome: "Fábio",
          responsavel_antes: "Edu Errado",
          responsavel_depois: "Carla Certa",
          criado_em: "2026-11-19T14:00:00+00:00",
          conta_atraso: false,
        },
      ],
      acoes_permitidas: [],
    });
    montar();

    const itens = within(await screen.findByRole("list", { name: "Histórico da pendência" })).getAllByRole("listitem");
    expect(itens[0].textContent).toContain("Responsável novo: Carla Certa (era Edu Errado)");
  });

  it("recusar só confirma com anotação", async () => {
    comHistorico({ eventos: [], acoes_permitidas: ["ajustar", "recusar"] });
    montar();

    fireEvent.click(await screen.findByRole("button", { name: "Recusar contestação" }));
    const confirmar = screen.getByRole("button", { name: "Confirmar" }) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Anotação (obrigatória)"), { target: { value: "O prazo foi esse" } });
    expect(confirmar.disabled).toBe(false);
  });

  it("o histórico mostra a contestação e a resposta", async () => {
    comHistorico({
      eventos: [
        { id: 1, comando: "contestar", anotacao: "Prazo errado", autor_nome: "Rita", criado_em: "2026-11-19T12:00:00+00:00", conta_atraso: false },
        { id: 2, comando: "recusar", anotacao: "Está certo", autor_nome: "Fábio", criado_em: "2026-11-19T13:00:00+00:00", conta_atraso: false },
      ],
      acoes_permitidas: [],
    });
    montar();

    const itens = within(await screen.findByRole("list", { name: "Histórico da pendência" })).getAllByRole("listitem");
    expect(itens[0].textContent).toContain("Contestou");
    expect(itens[1].textContent).toContain("Recusou a contestação");
  });
});

describe("arrasto no kanban", () => {
  it("arrastar para Repactuada abre o formulário uma vez só: depois de confirmar ele não volta preenchido", async () => {
    const onAtualizada = vi.fn();
    render(<AcoesDaPendencia idAcao="A001" token="tk" acaoInicial="repactuar" onAtualizada={onAtualizada} />);

    fireEvent.change(await screen.findByLabelText("Anotação (obrigatória)"), { target: { value: "Fornecedor" } });
    fireEvent.change(screen.getByLabelText("Prazo novo"), { target: { value: "2026-12-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(onAtualizada).toHaveBeenCalled());
    // O histórico recarregado depois da ação não reabre o formulário.
    await waitFor(() => expect(chamadas.filter((c) => !c.init?.method).length).toBe(2));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull());
    expect(screen.queryByLabelText("Anotação (obrigatória)")).toBeNull();

    // Abrir de novo pelo botão começa em branco.
    fireEvent.click(screen.getByRole("button", { name: "Repactuar" }));
    expect((screen.getByLabelText("Anotação (obrigatória)") as HTMLTextAreaElement).value).toBe("");
    expect(chamadas.filter((c) => c.init?.method === "POST")).toHaveLength(1);
  });
});
