/**
 * @vitest-environment jsdom
 */

/**
 * O formulário público da Ouvidoria, na tela (issue #473, PRD #467).
 *
 * O que o cartaz do ponto de escuta promete só existe se estiver DESENHADO
 * aqui: as quatro naturezas, o elogio na frente e a escolha que não prende
 * ninguém (RN-88). A régua do envio já tem teste próprio em
 * `lib/ouvidoria/publico.ts`; o que só existe nesta página, e que hoje só um
 * humano olhando a tela pegaria se sumisse, é:
 *
 * * a ordem dos quatro botões, que é a promessa do papel;
 * * a escolha ser opcional E desmarcável, para quem clicou por engano não ficar
 *   preso a uma natureza que não é a dele;
 * * o protocolo continuar aparecendo na tela depois do envio, que é o recibo de
 *   quem manifestou.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A constante entra só na asserção de AUSÊNCIA (procurar um literal que não
// está na tela não prova que a frase certa sumiu, prova que aquele literal não
// está lá). Toda asserção de PRESENÇA usa o texto exato que a pessoa lê.
import { FALTA_DIZER_SOBRE_QUEM } from "@/lib/ouvidoria/publico";
import ManifestacaoPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

const RECIBO = {
  protocolo: "2026-0042",
  data_abertura: "2026-09-01",
  prazo_resposta: "2026-09-08",
  status: "em_classificacao",
};

let enviados: unknown[] = [];

beforeEach(() => {
  enviados = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      enviados.push(JSON.parse(String(init?.body ?? "{}")));
      return { ok: true, status: 201, json: async () => RECIBO } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function escrever(texto: string) {
  fireEvent.change(screen.getByLabelText("O que aconteceu?"), { target: { value: texto } });
}

/** Os botões de natureza, e só eles: o grupo da pergunta "sobre quem" também
 *  é alternável, e filtrar por `aria-pressed` na página inteira passaria a
 *  pegar os dois. */
function botoesDeNatureza() {
  return within(screen.getByRole("group", { name: /O que você quer registrar/ })).getAllByRole(
    "button"
  );
}

/** A resposta obrigatória de quem é o relato (issue #666). */
function responderSobreQuem(rotulo: string) {
  fireEvent.click(screen.getByRole("button", { name: rotulo }));
}

function botaoDeEnviar() {
  return screen.getByRole("button", { name: /enviar manifestação/i }) as HTMLButtonElement;
}

describe("o seletor de natureza do formulário público", () => {
  it("mostra as quatro naturezas do cartaz, com o elogio primeiro", () => {
    render(<ManifestacaoPage />);

    expect(botoesDeNatureza().map((b) => b.textContent)).toEqual([
      "Elogio",
      "Reclamação",
      "Sugestão",
      "Informação",
    ]);
  });

  it("deixa enviar sem escolher natureza nenhuma", async () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");
    responderSobreQuem("Sobre mim");

    const enviar = botaoDeEnviar();
    expect(enviar.disabled).toBe(false);

    fireEvent.click(enviar);

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).not.toHaveProperty("natureza_informada");
  });

  it("leva a natureza escolhida no envio", async () => {
    render(<ManifestacaoPage />);
    escrever("Fui muito bem atendida na recepção.");
    responderSobreQuem("Sobre mim");

    fireEvent.click(screen.getByRole("button", { name: "Elogio" }));
    expect(screen.getByRole("button", { name: "Elogio" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ natureza_informada: "elogio" });
  });

  it("desmarca a natureza quando a pessoa clica de novo na mesma", async () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");
    responderSobreQuem("Sobre mim");

    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));
    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));

    expect(screen.getByRole("button", { name: "Reclamação" }).getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).not.toHaveProperty("natureza_informada");
  });

  it("troca a escolha quando a pessoa clica em outra natureza", async () => {
    render(<ManifestacaoPage />);
    escrever("Sugiro senhas por ordem de chegada.");
    responderSobreQuem("Sobre mim");

    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));
    fireEvent.click(screen.getByRole("button", { name: "Sugestão" }));

    expect(screen.getByRole("button", { name: "Reclamação" }).getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ natureza_informada: "sugestao" });
  });

  it("continua mostrando o protocolo na tela depois do envio", async () => {
    render(<ManifestacaoPage />);
    escrever("Fui muito bem atendida na recepção.");
    responderSobreQuem("Sobre mim");

    fireEvent.click(screen.getByRole("button", { name: "Elogio" }));
    fireEvent.click(botaoDeEnviar());

    expect(await screen.findByText("2026-0042")).toBeTruthy();
  });
});

/**
 * A pergunta de quem é o relato, na tela (issue #666, PRD #659, ADR 0052).
 *
 * A régua do envio tem teste próprio em `lib/ouvidoria/publico.ts`. O que só
 * existe nesta página é a fiação de três estados que um humano olhando a tela
 * pegaria e a suíte não: sem resposta o envio nem sai; "Sobre mim" não pede
 * paciente nenhum; "Sobre outra pessoa" abre os dois campos, e eles CONTINUAM
 * abertos com "anônimo" marcado, que é a decisão 3 do ADR desenhada.
 */
describe("a pergunta de quem é o relato (issue #666)", () => {
  function campoDoPaciente() {
    return screen.queryByLabelText(/Nome do paciente/);
  }

  function campoDaReferencia() {
    return screen.queryByLabelText(/Quando ou onde foi o atendimento/);
  }

  it("oferece as duas respostas, com Sobre mim primeiro", () => {
    render(<ManifestacaoPage />);

    const botoes = within(
      screen.getByRole("group", { name: /Este relato é sobre quem/ })
    ).getAllByRole("button");

    expect(botoes.map((b) => b.textContent)).toEqual(["Sobre mim", "Sobre outra pessoa"]);
  });

  it("sem resposta, o envio fica desabilitado e a tela diz o que falta", () => {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");

    expect(botaoDeEnviar().disabled).toBe(true);
    // O literal que a pessoa lê, e não a constante: procurar pela constante é
    // procurar exatamente o que a página acabou de renderizar, e qualquer
    // reescrita da frase passaria batido.
    expect(screen.getByText('Responda "Este relato é sobre quem?" para enviar.')).toBeTruthy();
  });

  it("respondida a pergunta, o aviso some e o envio libera", () => {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");

    responderSobreQuem("Sobre mim");

    expect(botaoDeEnviar().disabled).toBe(false);
    expect(screen.queryByText(FALTA_DIZER_SOBRE_QUEM)).toBeNull();
  });

  it("Sobre mim não mostra campo de paciente nenhum", () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");

    responderSobreQuem("Sobre mim");

    expect(campoDoPaciente()).toBeNull();
    expect(campoDaReferencia()).toBeNull();
  });

  it("Sobre outra pessoa mostra os dois campos e o aviso de por que preencher", () => {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");

    responderSobreQuem("Sobre outra pessoa");

    expect(campoDoPaciente()).toBeTruthy();
    expect(campoDaReferencia()).toBeTruthy();
    expect(
      screen.getByText("Sem o nome do paciente, o hospital não consegue achar o atendimento.")
    ).toBeTruthy();
  });

  it("os campos do paciente continuam na tela com anônimo marcado, e o aviso cresce", () => {
    // O anonimato protege quem fala; o paciente é outra pessoa (decisão 3). E
    // quem se protege lê que o nome do paciente pode entregá-lo.
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");
    responderSobreQuem("Sobre outra pessoa");

    fireEvent.click(screen.getByRole("checkbox"));

    expect(campoDoPaciente()).toBeTruthy();
    expect(campoDaReferencia()).toBeTruthy();
    expect(
      screen.getByText(
        "Sem o nome do paciente, o hospital não consegue achar o atendimento. " +
          "O nome do paciente e a referência do atendimento podem indicar quem manifestou."
      )
    ).toBeTruthy();
    // A identificação de quem fala, essa some: são duas pessoas diferentes.
    expect(screen.queryByLabelText(/Seu nome/)).toBeNull();
  });

  it("leva a resposta e os dois campos do paciente no envio", async () => {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");
    responderSobreQuem("Sobre outra pessoa");

    fireEvent.change(screen.getByLabelText(/Nome do paciente/), {
      target: { value: "Maria Souza" },
    });
    fireEvent.change(screen.getByLabelText(/Quando ou onde foi o atendimento/), {
      target: { value: "Leito 12, dia 9" },
    });
    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({
      sobre: "outra_pessoa",
      paciente_nome: "Maria Souza",
      paciente_referencia: "Leito 12, dia 9",
    });
  });

  it("o envio anônimo leva o paciente e não leva quem falou", async () => {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");
    responderSobreQuem("Sobre outra pessoa");
    fireEvent.change(screen.getByLabelText(/Nome do paciente/), {
      target: { value: "Maria Souza" },
    });
    fireEvent.click(screen.getByRole("checkbox"));

    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ anonimo: true, paciente_nome: "Maria Souza" });
    expect(enviados[0]).not.toHaveProperty("nome");
  });

  it("trocar a resposta para Sobre mim não leva o paciente que já tinha sido digitado", async () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");
    responderSobreQuem("Sobre outra pessoa");
    fireEvent.change(screen.getByLabelText(/Nome do paciente/), {
      target: { value: "Maria Souza" },
    });

    responderSobreQuem("Sobre mim");
    fireEvent.click(botaoDeEnviar());

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ sobre: "mim" });
    expect(enviados[0]).not.toHaveProperty("paciente_nome");
  });

  it("clicar de novo na resposta já marcada não desfaz a escolha", () => {
    // Ao contrário da natureza, que é opcional e desmarcável: esta resposta é
    // obrigatória, e voltar ao nada só travaria o envio sem a pessoa entender.
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");

    responderSobreQuem("Sobre mim");
    responderSobreQuem("Sobre mim");

    expect(screen.getByRole("button", { name: "Sobre mim" }).getAttribute("aria-pressed")).toBe(
      "true"
    );
    expect(botaoDeEnviar().disabled).toBe(false);
  });
});

/**
 * O que a tela diz quando o servidor recusa o envio (issue #666).
 *
 * `sobre` é obrigatório no backend, então uma aba aberta antes do deploy manda
 * um payload que o servidor novo recusa com 422. O bundle do Next é hasheado e
 * a aba segue no código velho até recarregar, e o caso de uso desta página é
 * alguém parado na frente do cartaz escrevendo devagar. A mensagem não pode
 * culpar o relato: num canal sem login e sem segunda porta, mandar reescrever é
 * mandar repetir o que nunca vai passar.
 */
describe("a recusa do envio na tela do formulário (issue #666)", () => {
  function responderCom(status: number) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status, json: async () => ({}) }) as Response)
    );
  }

  async function enviar() {
    render(<ManifestacaoPage />);
    escrever("Minha mãe esperou duas horas na recepção.");
    responderSobreQuem("Sobre mim");
    fireEvent.click(botaoDeEnviar());
  }

  it("o 422 pede para recarregar, e nunca para reescrever o relato", async () => {
    responderCom(422);

    await enviar();

    expect(
      await screen.findByText(
        "Não foi possível registrar sua manifestação com os dados desta página. " +
          "Copie o que você escreveu, recarregue a página e envie de novo."
      )
    ).toBeTruthy();
    expect(screen.queryByText(/Reescreva o relato/)).toBeNull();
  });

  it("o 400 tem mensagem própria, e também não culpa o relato", async () => {
    responderCom(400);

    await enviar();

    expect(
      await screen.findByText(
        "Não foi possível registrar sua manifestação. Recarregue a página e tente de novo."
      )
    ).toBeTruthy();
    expect(screen.queryByText(/Reescreva o relato/)).toBeNull();
  });

  it("o texto do relato continua na tela depois da recusa", async () => {
    // A pessoa precisa conseguir copiar o que escreveu antes de recarregar, que
    // é o que a mensagem manda fazer.
    responderCom(422);

    await enviar();

    await screen.findByText(/Copie o que você escreveu/);
    expect((screen.getByLabelText("O que aconteceu?") as HTMLTextAreaElement).value).toBe(
      "Minha mãe esperou duas horas na recepção."
    );
  });
});
