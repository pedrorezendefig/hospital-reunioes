/**
 * @vitest-environment jsdom
 */

/**
 * A salvaguarda da resposta no caso com o selo do Núcleo (issue #1627).
 *
 * No caso Em análise pelo NSP, o clique para enviar a resposta ao manifestante
 * pede antes ao agente que aponte as frases que admitem ou negam falha. O
 * ouvidor vê os trechos e decide enviar assim mesmo ou editar. Caso sem selo
 * não chama o agente, e falha do agente deixa enviar normalmente. A régua de
 * quem chama o agente também vive no backend
 * (`test_ouvidoria_salvaguarda_resposta.py`); aqui se prova a tela.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EncerrarModal } from "./EncerrarModal";

const RESPOSTA = "Verificamos que houve erro da enfermagem na grade do leito. Lamentamos o ocorrido.";
const TRECHO = "Verificamos que houve erro da enfermagem na grade do leito";
const MOTIVO = "Admite falha da equipe antes da conclusão do Núcleo.";

const fetchMock = vi.fn();

type Salvaguarda = { ok: boolean; corpo?: unknown } | "rede";

function montar(nspDecisao: string | null, salvaguarda: Salvaguarda) {
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).endsWith("/salvaguarda-da-resposta")) {
      if (salvaguarda === "rede") throw new TypeError("Failed to fetch");
      return { ok: salvaguarda.ok, json: async () => salvaguarda.corpo ?? {} } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  const onEncerrada = vi.fn();
  render(
    <EncerrarModal
      manifestacao={{ id: "uuid-7", protocolo: "2026-0007", nsp_decisao: nspDecisao }}
      token="t"
      onClose={vi.fn()}
      onEncerrada={onEncerrada}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: "Procedente" }));
  fireEvent.change(screen.getByLabelText(/Desfecho para o manifestante/), { target: { value: RESPOSTA } });
  return onEncerrada;
}

function chamadas(fim: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(fim));
}

function clicarEncerrar() {
  fireEvent.click(screen.getByRole("button", { name: /Encerrar caso/ }));
}

const COM_TRECHO = { ok: true, corpo: { analisada: true, trechos: [{ trecho: TRECHO, motivo: MOTIVO }] } };

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("caso com o selo do Núcleo", () => {
  it("mostra o trecho apontado antes do envio e não encerra ainda", async () => {
    montar("confirmado", COM_TRECHO);

    clicarEncerrar();

    expect(await screen.findByText(`"${TRECHO}"`)).toBeTruthy();
    expect(screen.getByText(MOTIVO)).toBeTruthy();
    const [[, init]] = chamadas("/salvaguarda-da-resposta");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ texto: RESPOSTA });
    expect(chamadas("/transicoes")).toHaveLength(0);
  });

  it("o ouvidor decide enviar assim mesmo", async () => {
    const onEncerrada = montar("confirmado", COM_TRECHO);
    clicarEncerrar();
    await screen.findByText(`"${TRECHO}"`);

    fireEvent.click(screen.getByRole("button", { name: /Enviar assim mesmo/ }));

    await waitFor(() => expect(onEncerrada).toHaveBeenCalled());
    const [[, init]] = chamadas("/transicoes");
    expect(JSON.parse((init as RequestInit).body as string).desfecho_descricao).toBe(RESPOSTA);
    expect(chamadas("/salvaguarda-da-resposta")).toHaveLength(1);
  });

  it("editar o texto tira o aviso e o próximo envio lê de novo", async () => {
    montar("confirmado", COM_TRECHO);
    clicarEncerrar();
    await screen.findByText(`"${TRECHO}"`);

    fireEvent.change(screen.getByLabelText(/Desfecho para o manifestante/), {
      target: { value: "O seu relato está em análise pelo Núcleo de Segurança do Paciente." },
    });

    expect(screen.queryByText(`"${TRECHO}"`)).toBeNull();
    clicarEncerrar();
    await waitFor(() => expect(chamadas("/salvaguarda-da-resposta")).toHaveLength(2));
  });

  it("sem trecho apontado, encerra direto", async () => {
    const onEncerrada = montar("confirmado", { ok: true, corpo: { analisada: true, trechos: [] } });

    clicarEncerrar();

    await waitFor(() => expect(onEncerrada).toHaveBeenCalled());
    expect(chamadas("/transicoes")).toHaveLength(1);
  });
});

describe("caso sem o selo do Núcleo", () => {
  it.each([null, "descartado"])("não chama o agente (nsp_decisao %s)", async (decisao) => {
    const onEncerrada = montar(decisao, COM_TRECHO);

    clicarEncerrar();

    await waitFor(() => expect(onEncerrada).toHaveBeenCalled());
    expect(chamadas("/salvaguarda-da-resposta")).toHaveLength(0);
  });
});

describe("falha do agente", () => {
  it.each<[string, Salvaguarda]>([
    ["sem leitura", { ok: true, corpo: { analisada: false, trechos: [] } }],
    ["erro do servidor", { ok: false }],
    ["rede", "rede"],
  ])("deixa enviar normalmente (%s)", async (_nome, salvaguarda) => {
    const onEncerrada = montar("confirmado", salvaguarda);

    clicarEncerrar();

    await waitFor(() => expect(onEncerrada).toHaveBeenCalled());
    expect(chamadas("/transicoes")).toHaveLength(1);
  });
});

describe("enquanto o agente lê", () => {
  // A leitura pode levar segundos. Se o ouvidor pudesse cancelar ou editar no
  // meio dela, o envio pendente sairia com o texto antigo (ou depois do
  // Cancelar), e o aviso atrasado cobriria um texto que não foi lido.
  function montarComLeituraPendente() {
    let responder: (trechos: unknown[]) => void = () => {};
    fetchMock.mockImplementation((url: string) => {
      if (String(url).endsWith("/salvaguarda-da-resposta")) {
        return new Promise((resolve) => {
          responder = (trechos) =>
            resolve({ ok: true, json: async () => ({ analisada: true, trechos }) } as Response);
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });
    vi.stubGlobal("fetch", fetchMock);
    const onClose = vi.fn();
    const onEncerrada = vi.fn();
    render(
      <EncerrarModal
        manifestacao={{ id: "uuid-7", protocolo: "2026-0007", nsp_decisao: "confirmado" }}
        token="t"
        onClose={onClose}
        onEncerrada={onEncerrada}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Procedente" }));
    fireEvent.change(screen.getByLabelText(/Desfecho para o manifestante/), { target: { value: RESPOSTA } });
    clicarEncerrar();
    return { onClose, onEncerrada, responder: (t: unknown[]) => responder(t) };
  }

  it("o texto e o desfecho ficam travados até a leitura voltar", async () => {
    const { responder } = montarComLeituraPendente();
    const campo = screen.getByLabelText(/Desfecho para o manifestante/) as HTMLTextAreaElement;

    await waitFor(() => expect(chamadas("/salvaguarda-da-resposta")).toHaveLength(1));
    expect(campo.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Improcedente" }) as HTMLButtonElement).disabled).toBe(true);

    responder([{ trecho: TRECHO, motivo: MOTIVO }]);
    await screen.findByText(`"${TRECHO}"`);
    expect(campo.disabled).toBe(false);
  });

  it("cancelar no meio da leitura não fecha nem deixa o caso encerrar escondido", async () => {
    const { onClose, onEncerrada, responder } = montarComLeituraPendente();
    await waitFor(() => expect(chamadas("/salvaguarda-da-resposta")).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();

    responder([]);
    await waitFor(() => expect(onEncerrada).toHaveBeenCalled());
    const [[, init]] = chamadas("/transicoes");
    expect(JSON.parse((init as RequestInit).body as string).desfecho_descricao).toBe(RESPOSTA);
  });
});
