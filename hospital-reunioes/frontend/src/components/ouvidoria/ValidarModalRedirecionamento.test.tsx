/**
 * @vitest-environment jsdom
 */

/**
 * A modal em modo redirecionamento (issue #710, PRD #706, ADR 0055).
 *
 * O Redirecionamento É a Validação e acionamento pré-preenchida, com a área em
 * branco e um motivo obrigatório. O que estes testes seguram é o que o ouvidor
 * LÊ em cada resposta da rota nova: cada recusa dela diz uma causa diferente e
 * um próximo passo diferente, e uma frase fixa da tela apagaria justamente isso.
 *
 * A lição que gerou este arquivo é da fatia anterior desta mesma leva: carimbo
 * do servidor sem par na tela some em silêncio, e a tela acaba afirmando duas
 * coisas que não aconteceram.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValidarModal } from "./ValidarModal";

const EXTRATO = "Conduta da equipe de enfermagem no plantao noturno. Apurar e responder a Ouvidoria.";
const MOTIVO = "O caso é de conduta médica, e a Recepção não tem como apurar.";

/** O caso que já está com uma área, que é de onde o redirecionamento parte. */
function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    tipo_manifestacao: "reclamacao" as const,
    categoria: "Demora no atendimento",
    setor: "Recepcao",
    sigilo_reforcado: false,
    gravidade: "medio",
    extrato_para_o_setor: EXTRATO,
    ...overrides,
  };
}

/**
 * O envio, quando ele acontece. `resposta` é o que a rota de redirecionamentos
 * devolve: `null` significa que nenhum envio é esperado neste teste.
 */
function montar(resposta: { ok: boolean; status: number; corpo?: unknown } | null = null) {
  const envios: { url: string; body: unknown }[] = [];
  const onClose = vi.fn();
  const onAcionada = vi.fn();

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/setores")) {
        return { ok: true, json: async () => ["Recepcao", "Centro Medico"] } as Response;
      }
      if (url.includes("/responsaveis")) {
        return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
      }
      envios.push({ url, body: JSON.parse(String(init?.body)) });
      return {
        ok: resposta?.ok ?? true,
        status: resposta?.status ?? 201,
        json: async () => resposta?.corpo ?? {},
      } as Response;
    })
  );

  render(
    <ValidarModal
      manifestacao={caso() as never}
      token="token-de-teste"
      modo="redirecionamento"
      onClose={onClose}
      onAcionada={onAcionada}
    />
  );

  return { envios, onClose, onAcionada };
}

/**
 * O que o ouvidor preenche antes de confirmar: a área nova e o motivo.
 *
 * A espera pela opção não é zelo: a taxonomia chega por fetch, e escolher uma
 * área antes de a lista existir deixaria o seletor em branco com o teste
 * achando que escolheu.
 */
async function preencher({ setor = "Centro Medico", motivo = MOTIVO } = {}) {
  await screen.findByRole("option", { name: setor });
  fireEvent.change(screen.getByLabelText(/Área responsável/), { target: { value: setor } });
  fireEvent.change(screen.getByLabelText(/Motivo do redirecionamento/), {
    target: { value: motivo },
  });
}

function botaoDeConfirmar(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Redirecionar para a área nova/ }) as HTMLButtonElement;
}

describe("a modal se apresenta como o ato do redirecionamento (issue #710)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("tem título e botão próprios", () => {
    // Uma tela intitulada "Validar e acionar" faria o ouvidor achar que clicou
    // na coisa errada, como já aconteceu com o reacionamento (issue #601).
    montar();

    expect(screen.getByText(/Redirecionar 2026-0012 para outra área/)).toBeTruthy();
    expect(botaoDeConfirmar()).toBeTruthy();
  });

  it("traz tipo, gravidade e extrato do acionamento anterior, editáveis", async () => {
    montar();

    expect((screen.getByLabelText(/Extrato para o setor/) as HTMLTextAreaElement).value).toBe(EXTRATO);
    expect(screen.getByRole("button", { name: /Médio/ }).getAttribute("aria-pressed")).toBe("true");
    expect((screen.getByLabelText(/Tipo da manifestação/) as HTMLSelectElement).value).toBe(
      "reclamacao"
    );
  });

  it("a área nasce em branco, e não na área que já tem o caso", async () => {
    // Pré-selecionada, o ato viraria um clique de confirmar que manda o caso de
    // volta para a mesma área errada. O servidor recusa isso com 409, mas a
    // tela não pode oferecer o caminho (ADR 0055, decisão 1).
    montar();

    await waitFor(() => {
      expect(screen.getByLabelText(/Área responsável/)).toBeTruthy();
    });
    expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("");
  });
});

describe("o motivo é obrigatório, e quem tem o que dizer passa", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("sem motivo o botão não confirma", async () => {
    // A espera pela opção é o que faz este teste falar do MOTIVO: sem ela, a
    // área ficaria em branco por causa do fetch em voo e o botão estaria
    // desabilitado pelo outro campo, com o teste passando por engano (o
    // mutante que tira a obrigatoriedade do motivo sobreviveu assim).
    montar();
    await screen.findByRole("option", { name: "Centro Medico" });
    fireEvent.change(screen.getByLabelText(/Área responsável/), {
      target: { value: "Centro Medico" },
    });

    expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe(
      "Centro Medico"
    );
    expect(botaoDeConfirmar().disabled).toBe(true);
  });

  it("motivo só de espaço também não confirma", async () => {
    montar();
    await preencher({ motivo: "   " });

    expect(botaoDeConfirmar().disabled).toBe(true);
  });

  it("sem área escolhida não confirma, nem com motivo escrito", () => {
    montar();
    fireEvent.change(screen.getByLabelText(/Motivo do redirecionamento/), {
      target: { value: MOTIVO },
    });

    expect(botaoDeConfirmar().disabled).toBe(true);
  });

  it("CONTRAPROVA: com área e motivo o ouvidor confirma e o pedido sai", async () => {
    // Sem esta, o mutante que desabilita o botão sempre passaria: a trava do
    // motivo viraria indisponibilidade do ato inteiro, sem ninguém notar.
    const { envios, onClose, onAcionada } = montar();
    await preencher();

    expect(botaoDeConfirmar().disabled).toBe(false);
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(envios.length).toBe(1));
    expect(envios[0].url).toBe("/api/ouvidoria/manifestacoes/uuid-12/redirecionamentos");
    expect(envios[0].body).toEqual({
      tipo_manifestacao: "reclamacao",
      categoria: "Demora no atendimento",
      sigilo_reforcado: false,
      setor: "Centro Medico",
      gravidade: "medio",
      extrato_para_o_setor: EXTRATO,
      observacao: null,
      motivo: MOTIVO,
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onAcionada).toHaveBeenCalledWith(
      "Caso redirecionado para Centro Medico. A área anterior foi avisada."
    );
  });

  it("o ato NÃO vai para a rota de validar", async () => {
    // A rota de validar recusa a chegada de "aguardando área" com a frase de
    // hoje: mandar o redirecionamento para lá daria uma recusa em cima de um
    // pedido correto.
    const { envios } = montar();
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(envios.length).toBe(1));
    expect(envios[0].url.endsWith("/validar")).toBe(false);
  });
});

/**
 * Uma recusa por linha, com a frase que o backend realmente devolve
 * (`app/routers/ouvidoria.py` e `app/services/ouvidoria_redirecionamento.py`).
 * O que se garante é sempre o mesmo: a frase do SERVIDOR na tela, a modal
 * aberta e nenhum sucesso anunciado.
 */
const RECUSAS = [
  {
    nome: "409 do caso pausado, mandando retomar antes",
    status: 409,
    detail:
      "Este caso está pausado à espera do manifestante. Retome o caso antes de redirecionar: " +
      "o relógio parado da pausa e o prazo cheio da área nova não se misturam na mesma ação.",
  },
  {
    nome: "409 da área sem titular nem gestor vigente",
    status: 409,
    detail:
      "O setor Centro Medico não tem titular nem gestor vigente cadastrado. " +
      "Cadastre o responsável antes de acionar.",
  },
  {
    nome: "409 de redirecionar para a mesma área",
    status: 409,
    detail:
      "Este caso já está com essa área, então não há para onde redirecioná-lo. " +
      "Escolha outra área, ou use a devolução por insuficiência para cobrar de novo a mesma, " +
      "que recalcula o prazo em vez de dar um novo por inteiro.",
  },
  {
    nome: "409 do caso que saiu da área durante o envio",
    status: 409,
    detail:
      "Este caso saiu da fila da área durante o envio, então o redirecionamento não valeu por ele. " +
      "Confira a manifestação no painel antes de tentar de novo.",
  },
  {
    nome: "422 do motivo vazio",
    status: 422,
    detail:
      "Diga por que este caso vai para outra área: sem o motivo, a trilha não conta por que ele saiu de onde estava.",
  },
  {
    nome: "422 do motivo acima do teto",
    status: 422,
    detail: "O motivo passou de 10.000 caracteres. Resuma por que o caso vai para outra área.",
  },
  {
    nome: "403 de quem não tem Perfil da Ouvidoria",
    status: 403,
    detail: "Acesso restrito ao Perfil da Ouvidoria",
  },
];

describe("cada recusa da rota aparece com a frase do servidor", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  for (const recusa of RECUSAS) {
    it(recusa.nome, async () => {
      const { onClose, onAcionada } = montar({
        ok: false,
        status: recusa.status,
        corpo: { detail: recusa.detail },
      });
      await preencher();
      fireEvent.click(botaoDeConfirmar());

      // O marcador é a frase do servidor, inteira. Asserir a AUSÊNCIA de uma
      // frase genérica seria cego a maiúscula, corte e aspas.
      await waitFor(() => expect(screen.getByText(recusa.detail)).toBeTruthy());
      // A modal fica aberta COM O TEXTO que o ouvidor escreveu, e o que se
      // assere é o VALOR do campo, não a presença dele: um `setMotivo("")` no
      // ramo de erro deixaria o campo na tela, vazio, e o ouvidor perderia até
      // 10.000 caracteres por causa de uma recusa que ele resolve ali mesmo
      // trocando a área.
      expect((screen.getByLabelText(/Motivo do redirecionamento/) as HTMLTextAreaElement).value).toBe(
        MOTIVO
      );
      expect(onClose).not.toHaveBeenCalled();
      expect(onAcionada).not.toHaveBeenCalled();
    });
  }

  it("a recusa que não tem texto legível não vira sucesso nem tela vazia", async () => {
    // O 422 do pydantic responde uma LISTA de erros de schema em vez de texto:
    // jogada no JSX, ela quebraria a tela em cima de uma recusa.
    const { onAcionada } = montar({
      ok: false,
      status: 422,
      corpo: { detail: [{ loc: ["body", "motivo"], msg: "Field required" }] },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() =>
      expect(screen.getByText(/Não foi possível redirecionar o caso agora/)).toBeTruthy()
    );
    expect(onAcionada).not.toHaveBeenCalled();
  });
});

describe("a falha DEPOIS da saída não é sucesso nem erro genérico", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  const FALHA_DEPOIS_DA_SAIDA =
    "O caso saiu da área anterior e está em classificação, mas a área nova não foi acionada. " +
    "Use Validar e acionar para despachá-lo, sem redirecionar de novo.";

  it("mostra a frase do servidor e não anuncia redirecionamento nenhum", async () => {
    const { onAcionada } = montar({
      ok: false,
      status: 500,
      corpo: { detail: `${FALHA_DEPOIS_DA_SAIDA} O acionamento respondeu: falha no email.` },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(new RegExp(FALHA_DEPOIS_DA_SAIDA))).toBeTruthy());
    // Nenhuma frase de confirmação: o caso NÃO chegou à área nova.
    expect(screen.queryByText(/Caso redirecionado para/)).toBeNull();
    expect(onAcionada).not.toHaveBeenCalled();
  });

  it("ao fechar, o que está embaixo recarrega, sem frase de sucesso", async () => {
    // O caso se moveu no servidor. Sem a recarga, o ouvidor fecharia a modal e
    // continuaria olhando um Dossiê que afirma o estado de antes, com o botão
    // Redirecionar ainda oferecido sobre um caso que já saiu da área.
    const { onAcionada, onClose } = montar({
      ok: false,
      status: 500,
      corpo: {
        detail:
          "O redirecionamento não terminou. Confira a manifestação no painel antes de agir: " +
          "o caso pode já estar com a área nova.",
      },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(/Confira a manifestação no painel/)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));

    expect(onAcionada).toHaveBeenCalledWith();
    expect(onClose).toHaveBeenCalled();
  });

  it("o 409 do relógio que parou e não voltou também recarrega ao fechar", async () => {
    // Caminho (a) do backend: o `parar` JÁ GRAVOU (o prazo e o marco T2 da área
    // foram limpos), a RPC de saída falhou e o `restaurar` não casou linha. O
    // status é 409, não 5xx. Derivar "o caso se moveu" da faixa do status
    // deixava este caso de fora, e a linha da fila seguia mostrando um prazo
    // que já não existe até alguém apertar F5.
    const { onAcionada, onClose } = montar({
      ok: false,
      status: 409,
      corpo: {
        detail:
          "Este caso saiu da fila da área durante o envio, então o redirecionamento não valeu por ele. " +
          "Confira a manifestação no painel antes de tentar de novo.",
      },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(/saiu da fila da área durante o envio/)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));

    expect(onAcionada).toHaveBeenCalledWith();
    expect(onClose).toHaveBeenCalled();
  });

  it("o 409 com o prefixo da falha depois da saída recarrega e trava o botão", async () => {
    // Caminho (b): o 23514 da transição de ENTRADA, que no redirecionamento só
    // roda depois do ponto sem volta, sobe com o status PRESERVADO. Existe,
    // portanto, um 409 cujo texto começa com a frase da falha depois da saída,
    // e essa frase manda literalmente não redirecionar de novo.
    const { onAcionada } = montar({
      ok: false,
      status: 409,
      corpo: { detail: `${FALHA_DEPOIS_DA_SAIDA} O acionamento respondeu: Transição recusada` },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(new RegExp(FALHA_DEPOIS_DA_SAIDA))).toBeTruthy());
    // O botão não pode convidar a repetir um ato que a própria resposta
    // desaconselha.
    expect(botaoDeConfirmar().disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onAcionada).toHaveBeenCalledWith();
  });

  it("CONTRAPROVA: a recusa da mesma área fecha sem recarregar, com o motivo intacto e o botão vivo", async () => {
    // Escolher a área que já tem o caso é recusado ANTES de qualquer escrita, e
    // o ouvidor resolve trocando a área ali mesmo. Recarregar seria pedir uma
    // leitura ao servidor por causa de um campo mal escolhido, e travar o botão
    // deixaria o ato indisponível para quem tem direito a ele.
    const { onAcionada } = montar({
      ok: false,
      status: 409,
      corpo: { detail: "Este caso já está com essa área, então não há para onde redirecioná-lo." },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(/já está com essa área/)).toBeTruthy());
    expect(botaoDeConfirmar().disabled).toBe(false);
    expect((screen.getByLabelText(/Motivo do redirecionamento/) as HTMLTextAreaElement).value).toBe(
      MOTIVO
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onAcionada).not.toHaveBeenCalled();
  });

  it("CONTRAPROVA: o 422 do motivo fecha sem recarregar e o ouvidor pode corrigir e reenviar", async () => {
    const { onAcionada } = montar({
      ok: false,
      status: 422,
      corpo: { detail: "O motivo passou de 10.000 caracteres. Resuma por que o caso vai para outra área." },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() => expect(screen.getByText(/passou de 10.000 caracteres/)).toBeTruthy());
    expect(botaoDeConfirmar().disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onAcionada).not.toHaveBeenCalled();
  });

  it("a marca é PEGAJOSA: uma recusa limpa depois de um 5xx não apaga a releitura", async () => {
    // Sem isso, o ouvidor que leva um 500 e tenta de novo levando um 409 de
    // estado fecharia a modal sem reler justamente o caso que pode ter se
    // movido no primeiro envio.
    const respostas = [
      { status: 500, detail: "O caso não saiu da área anterior e nada foi redirecionado." },
      { status: 409, detail: "Este caso já está com essa área, então não há para onde redirecioná-lo." },
    ];
    let envio = 0;
    const onAcionada = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/setores")) {
          return { ok: true, json: async () => ["Recepcao", "Centro Medico"] } as Response;
        }
        if (url.includes("/responsaveis")) {
          return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
        }
        const r = respostas[Math.min(envio++, respostas.length - 1)];
        return { ok: false, status: r.status, json: async () => ({ detail: r.detail }) } as Response;
      })
    );
    render(
      <ValidarModal
        manifestacao={caso() as never}
        token="token-de-teste"
        modo="redirecionamento"
        onClose={vi.fn()}
        onAcionada={onAcionada}
      />
    );
    await preencher();

    fireEvent.click(botaoDeConfirmar());
    await waitFor(() => expect(screen.getByText(/nada foi redirecionado/)).toBeTruthy());
    fireEvent.click(botaoDeConfirmar());
    await waitFor(() => expect(screen.getByText(/já está com essa área/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onAcionada).toHaveBeenCalledWith();
  });
});

describe("o limite de taxa não manda ninguém conferir o painel (429)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("tem frase própria, e não a que manda conferir a manifestação", async () => {
    // O handler do slowapi responde `{"error": ...}`, SEM `detail`, e nada
    // aconteceu no servidor: o fallback geral mandaria o ouvidor ao painel por
    // causa de um limite de taxa.
    const { onAcionada } = montar({
      ok: false,
      status: 429,
      corpo: { error: "Rate limit exceeded: 30 per 1 minute" },
    });
    await preencher();
    fireEvent.click(botaoDeConfirmar());

    await waitFor(() =>
      expect(
        screen.getByText("O painel recebeu pedidos demais em pouco tempo. Espere um minuto e tente de novo.")
      ).toBeTruthy()
    );
    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onAcionada).not.toHaveBeenCalled();
  });
});

describe("o modo acionamento não mudou (issue #325, #601)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("sem o modo, a tela continua sendo a validação, com a área gravada e sem motivo", async () => {
    const envios: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes("/setores")) {
          return { ok: true, json: async () => ["Recepcao", "Centro Medico"] } as Response;
        }
        if (url.includes("/responsaveis")) {
          return { ok: true, json: async () => ({ responsaveis: [] }) } as Response;
        }
        envios.push({ url, body: JSON.parse(String(init?.body)) });
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      })
    );
    const onAcionada = vi.fn();
    render(
      <ValidarModal
        manifestacao={caso() as never}
        token="token-de-teste"
        onClose={vi.fn()}
        onAcionada={onAcionada}
      />
    );

    await waitFor(() => {
      expect((screen.getByLabelText(/Área responsável/) as HTMLSelectElement).value).toBe("Recepcao");
    });
    expect(screen.queryByLabelText(/Motivo do redirecionamento/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Validar e acionar a área/ }));
    await waitFor(() => expect(envios.length).toBe(1));
    expect(envios[0].url).toBe("/api/ouvidoria/manifestacoes/uuid-12/validar");
    // O corpo da validação não ganhou o motivo: a rota dela não o conhece.
    expect(envios[0].body).not.toHaveProperty("motivo");
    // E o sucesso da validação continua sem frase de confirmação nenhuma.
    expect(onAcionada).toHaveBeenCalledWith(undefined);
  });
});
