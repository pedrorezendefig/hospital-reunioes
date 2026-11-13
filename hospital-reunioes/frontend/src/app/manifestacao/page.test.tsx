/**
 * @vitest-environment jsdom
 */

/**
 * A Manifestação guiada, na tela (issue #1620, PRD #1527, ADR 0086 decisão 6).
 *
 * O formulário público virou os cinco passos da seção 4.2 da especificação da
 * Diretoria: identificação, sobre o quê, quando e onde, o que aconteceu e
 * contato. A régua de cada passo tem teste próprio em
 * `lib/ouvidoria/manifestacao-guiada.test.ts`; o que só existe nesta página é:
 *
 * * a ordem dos passos, com a identificação primeiro;
 * * o Continuar que só libera com o obrigatório, e o Voltar que não perde nada;
 * * o aviso de quem deixa só o telefone;
 * * o recibo e as recusas do servidor, que continuam como eram;
 * * o desenho de celular (375 px): cards empilhados e alvos de 44 px.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apareceComoFoiEscrito } from "@/lib/caixa-alta";
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

const LOCAIS = [
  { nome: "Emergência adulta", ala_internacao: false },
  { nome: "Internação · Ala 2A", ala_internacao: true },
];

let enviados: Record<string, unknown>[] = [];

function servidor({ status = 201 }: { status?: number } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/publico/locais")) {
        return { ok: true, status: 200, json: async () => ({ locais: LOCAIS }) } as Response;
      }
      const envio = JSON.parse(String(init?.body ?? "{}"));
      enviados.push(envio);
      // O código de acompanhamento só vem no recibo do anônimo (issue #1623).
      const recibo = envio.anonimo ? { ...RECIBO, codigo_acompanhamento: "K7M2P-Q9RX4" } : RECIBO;
      return { ok: status < 300, status, json: async () => (status < 300 ? recibo : {}) } as Response;
    })
  );
}

beforeEach(() => {
  enviados = [];
  servidor();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function botao(nome: string | RegExp) {
  return screen.getByRole("button", { name: nome }) as HTMLButtonElement;
}

function continuar() {
  fireEvent.click(botao("Continuar"));
}

function voltar() {
  fireEvent.click(botao("Voltar"));
}

function escrever(rotulo: string | RegExp, valor: string) {
  fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } });
}

async function escolherLocal(nome: string) {
  const onde = (await screen.findByLabelText("Onde foi?")) as HTMLSelectElement;
  await waitFor(() => expect(within(onde).getByRole("option", { name: nome })).toBeTruthy());
  fireEvent.change(onde, { target: { value: nome } });
}

/** Passos 1 a 4 respondidos com o mínimo, parando no passo 5. */
async function ateOContato({
  identificacao = "Com identificação",
  sobre = "Sobre mim",
  local = "Emergência adulta",
}: { identificacao?: string; sobre?: string; local?: string } = {}) {
  render(<ManifestacaoPage />);
  fireEvent.click(botao(new RegExp(identificacao)));
  continuar();
  fireEvent.click(botao(sobre));
  continuar();
  fireEvent.click(botao("Tarde"));
  await escolherLocal(local);
  continuar();
  escrever("Seu relato", "Esperei duas horas na emergência.");
  fireEvent.click(botao("Uma resposta"));
  continuar();
}

describe("o passo a passo começa pela identificação (critério 1)", () => {
  it("o primeiro passo é a escolha entre identificado e anônimo, e nada mais", () => {
    render(<ManifestacaoPage />);

    expect(screen.getByText("Passo 1 de 5")).toBeTruthy();
    expect(botao(/Com identificação/)).toBeTruthy();
    expect(botao(/Anônimo/)).toBeTruthy();
    expect(screen.queryByLabelText("Seu relato")).toBeNull();
    expect(screen.queryByRole("button", { name: "Voltar" })).toBeNull();
  });

  it("os dois cards dizem o que cada escolha significa, como foi escrito", () => {
    render(<ManifestacaoPage />);

    const identificado = screen.getByText("A Ouvidoria responde diretamente a você.");
    const anonimo = screen.getByText(
      "Você recebe um número de protocolo, sem se identificar. Não conseguimos responder diretamente a você."
    );
    // O card é botão, e a regra de caixa alta (ADR 0080) pegaria a frase.
    expect(apareceComoFoiEscrito(identificado)).toBe(true);
    expect(apareceComoFoiEscrito(anonimo)).toBe(true);
  });

  it("sem escolher, não segue", () => {
    render(<ManifestacaoPage />);

    expect(botao("Continuar").disabled).toBe(true);
    fireEvent.click(botao(/Anônimo/));
    expect(botao(/Anônimo/).getAttribute("aria-pressed")).toBe("true");
    expect(botao("Continuar").disabled).toBe(false);
  });
});

describe("os obrigatórios do anexo seguram o passo, e os opcionais não (critério 2)", () => {
  it("passo 2 só segue com a resposta de quem é o relato, sem precisar da natureza", () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();

    expect(screen.getByText("Passo 2 de 5")).toBeTruthy();
    expect(botao("Continuar").disabled).toBe(true);
    fireEvent.click(botao("Sobre mim"));
    expect(botao("Continuar").disabled).toBe(false);
  });

  it("as quatro naturezas seguem com o elogio na frente, e desmarcam com um toque", () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();

    const grupo = screen.getByRole("group", { name: /O que você quer registrar/ });
    expect(within(grupo).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Elogio",
      "Reclamação",
      "Sugestão",
      "Informação",
    ]);
    fireEvent.click(botao("Reclamação"));
    fireEvent.click(botao("Reclamação"));
    expect(botao("Reclamação").getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText("Não precisa escolher. A Ouvidoria confirma ao ler seu relato.")).toBeTruthy();
  });

  it("passo 3 vem com a data de hoje e pede o período e o lugar", async () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();
    fireEvent.click(botao("Sobre mim"));
    continuar();

    const data = screen.getByLabelText("Em que dia foi?") as HTMLInputElement;
    expect(data.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(botao("Continuar").disabled).toBe(true);
    fireEvent.click(botao("Noite"));
    expect(botao("Continuar").disabled).toBe(true);
    await escolherLocal("Emergência adulta");
    expect(botao("Continuar").disabled).toBe(false);
  });

  it("o quarto só aparece quando o lugar é ala de internação", async () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();
    fireEvent.click(botao("Sobre mim"));
    continuar();

    await escolherLocal("Emergência adulta");
    expect(screen.queryByLabelText(/Quarto ou leito/)).toBeNull();
    await escolherLocal("Internação · Ala 2A");
    expect(screen.getByLabelText(/Quarto ou leito/)).toBeTruthy();
  });

  it("quem não acha o lugar na lista escolhe Outro lugar do hospital", async () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();
    fireEvent.click(botao("Sobre mim"));
    continuar();
    fireEvent.click(botao("Manhã"));

    await escolherLocal("Outro lugar do hospital");

    expect(botao("Continuar").disabled).toBe(false);
  });

  it("passo 4 pede o relato e o que a pessoa espera", async () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();
    fireEvent.click(botao("Sobre mim"));
    continuar();
    fireEvent.click(botao("Tarde"));
    await escolherLocal("Emergência adulta");
    continuar();

    expect(screen.getByText("Quanto mais detalhes, mais rápido conseguimos apurar.")).toBeTruthy();
    expect(botao("Continuar").disabled).toBe(true);
    escrever("Seu relato", "Esperei duas horas.");
    expect(botao("Continuar").disabled).toBe(true);
    fireEvent.click(botao("Só registrar"));
    expect(botao("Continuar").disabled).toBe(false);
  });

  it("envia sem nenhum opcional preenchido", async () => {
    await ateOContato();
    escrever("Seu nome", "Maria Souza");
    escrever("E-mail", "maria@exemplo.com");

    fireEvent.click(botao(/Enviar manifestação/));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({
      anonimo: false,
      sobre: "mim",
      periodo: "tarde",
      local_informado: "Emergência adulta",
      expectativa: "resposta",
      nome: "Maria Souza",
      contato: "maria@exemplo.com",
    });
    for (const opcional of ["hora_aprox", "quarto", "profissionais", "paciente_nascimento", "natureza_informada"]) {
      expect(enviados[0]).not.toHaveProperty(opcional);
    }
    expect(await screen.findByText("2026-0042")).toBeTruthy();
  });
});

describe("o contato de quem se identifica (critério 3)", () => {
  it("sem telefone nem e-mail, o envio não sai", async () => {
    await ateOContato();
    escrever("Seu nome", "Maria Souza");

    expect(botao(/Enviar manifestação/).disabled).toBe(true);
    expect(screen.getByText("Para enviar, deixe seu nome e um telefone ou e-mail.")).toBeTruthy();
  });

  it("só com telefone passa e mostra o aviso de que as respostas saem por e-mail", async () => {
    await ateOContato();
    escrever("Seu nome", "Maria Souza");
    expect(screen.queryByText(/As respostas da Ouvidoria saem por e-mail/)).toBeNull();

    escrever("Telefone", "(21) 99999-0000");

    expect(
      screen.getByText(
        "As respostas da Ouvidoria saem por e-mail. Só com o telefone, você não recebe o aviso de que a manifestação chegou nem a resposta final."
      )
    ).toBeTruthy();
    fireEvent.click(botao(/Enviar manifestação/));
    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ telefone: "(21) 99999-0000" });
    expect(enviados[0]).not.toHaveProperty("contato");
  });

  it("o anônimo envia sem contato, sabendo que o protocolo é o que fica", async () => {
    await ateOContato({ identificacao: "Anônimo" });

    expect(screen.queryByLabelText("Seu nome")).toBeNull();
    expect(
      screen.getByText("Guarde o número do protocolo e o código que aparecerão na próxima tela.")
    ).toBeTruthy();
    fireEvent.click(botao(/Enviar manifestação/));
    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ anonimo: true });
    expect(enviados[0]).not.toHaveProperty("nome");
  });

  it("o último passo diz para que servem os dados", async () => {
    await ateOContato();

    expect(
      screen.getByText("Seus dados são usados apenas para tratar sua manifestação, conforme a LGPD.")
    ).toBeTruthy();
  });
});

describe("o paciente atendido no passo 4", () => {
  async function ateOPasso4(identificacao: string, sobre: string) {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(new RegExp(identificacao)));
    continuar();
    fireEvent.click(botao(sobre));
    continuar();
    fireEvent.click(botao("Tarde"));
    await escolherLocal("Emergência adulta");
    continuar();
  }

  it("sobre outra pessoa pede nome e nascimento do paciente, também no anônimo", async () => {
    await ateOPasso4("Anônimo", "Sobre outra pessoa");

    expect(screen.getByLabelText(/Nome do paciente/)).toBeTruthy();
    expect(screen.getByLabelText(/Data de nascimento do paciente/)).toBeTruthy();
    expect(
      screen.getByText(
        "Sem o nome do paciente, o hospital não consegue achar o atendimento. " +
          "O nome do paciente e a referência do atendimento podem indicar quem manifestou."
      )
    ).toBeTruthy();
  });

  it("quem se identifica e fala de si informa só a própria data de nascimento", async () => {
    await ateOPasso4("Com identificação", "Sobre mim");

    expect(screen.queryByLabelText(/Nome do paciente/)).toBeNull();
    expect(screen.getByLabelText(/Sua data de nascimento/)).toBeTruthy();
  });

  it("o anônimo que fala de si não vê campo de paciente nenhum", async () => {
    await ateOPasso4("Anônimo", "Sobre mim");

    expect(screen.queryByLabelText(/Nome do paciente/)).toBeNull();
    expect(screen.queryByLabelText(/data de nascimento/i)).toBeNull();
  });

  it("Não sei apaga e trava o campo dos profissionais", async () => {
    await ateOPasso4("Com identificação", "Sobre mim");
    escrever(/Profissionais envolvidos/, "Doutor Fulano");

    fireEvent.click(screen.getByRole("checkbox", { name: "Não sei" }));

    const campo = screen.getByLabelText(/Profissionais envolvidos/) as HTMLInputElement;
    expect(campo.disabled).toBe(true);
    expect(campo.value).toBe("");
  });
});

describe("Voltar não perde o que foi preenchido", () => {
  it("volta ao passo anterior com as respostas no lugar", async () => {
    render(<ManifestacaoPage />);
    fireEvent.click(botao(/Com identificação/));
    continuar();
    fireEvent.click(botao("Sobre outra pessoa"));
    fireEvent.click(botao("Elogio"));
    continuar();
    fireEvent.click(botao("Noite"));

    voltar();

    expect(screen.getByText("Passo 2 de 5")).toBeTruthy();
    expect(botao("Sobre outra pessoa").getAttribute("aria-pressed")).toBe("true");
    expect(botao("Elogio").getAttribute("aria-pressed")).toBe("true");
    continuar();
    expect(botao("Noite").getAttribute("aria-pressed")).toBe("true");
  });

  it("a barra de progresso acompanha o passo", () => {
    render(<ManifestacaoPage />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");

    fireEvent.click(botao(/Anônimo/));
    continuar();

    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("2");
  });
});

describe("funciona a 375 px (critério 7, regra T4)", () => {
  it("os dois cards ficam um embaixo do outro no celular e lado a lado da tela pequena para cima", () => {
    render(<ManifestacaoPage />);

    const grade = botao(/Com identificação/).parentElement!;
    expect(grade.className).toContain("grid-cols-1");
    expect(grade.className).toContain("sm:grid-cols-2");
    expect(grade.contains(botao(/Anônimo/))).toBe(true);
  });

  it("todo botão do passo a passo tem alvo de toque de 44 px", async () => {
    await ateOContato();

    for (const nome of ["Voltar", /Enviar manifestação/]) {
      expect(botao(nome).className).toContain("min-h-[44px]");
    }
    voltar();
    for (const nome of ["Uma resposta", "Uma providência", "Só registrar"]) {
      expect(botao(nome).className).toContain("min-h-[44px]");
    }
  });

  it("nada abre corredor lateral nem fixa largura maior que a tela", () => {
    const { container } = render(<ManifestacaoPage />);

    for (const no of container.querySelectorAll("*")) {
      const classe = no.className.toString();
      expect(classe).not.toContain("overflow-x-auto");
      expect(classe).not.toMatch(/\bw-\[\d+px\]/);
      expect(classe).not.toMatch(/\bmin-w-\[\d+px\]/);
    }
  });
});

describe("as recusas do servidor continuam sem culpar o relato (issue #666)", () => {
  it("o 422 pede para recarregar, e o relato continua no passo 4 para copiar", async () => {
    servidor({ status: 422 });
    await ateOContato();
    escrever("Seu nome", "Maria Souza");
    escrever("E-mail", "maria@exemplo.com");

    fireEvent.click(botao(/Enviar manifestação/));

    expect(
      await screen.findByText(
        "Não foi possível registrar sua manifestação com os dados desta página. " +
          "Copie o que você escreveu, recarregue a página e envie de novo."
      )
    ).toBeTruthy();
    voltar();
    expect((screen.getByLabelText("Seu relato") as HTMLTextAreaElement).value).toBe(
      "Esperei duas horas na emergência."
    );
  });

  it("o 400 tem mensagem própria", async () => {
    servidor({ status: 400 });
    await ateOContato({ identificacao: "Anônimo" });

    fireEvent.click(botao(/Enviar manifestação/));

    expect(
      await screen.findByText(
        "Não foi possível registrar sua manifestação. Recarregue a página e tente de novo."
      )
    ).toBeTruthy();
  });
});

describe("a confirmação do anônimo traz o código de acompanhamento (issue #1623)", () => {
  it("mostra o protocolo, o código, o Copiar e o link para a página de acompanhamento", async () => {
    const copiar = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: copiar } });
    await ateOContato({ identificacao: "Anônimo" });

    fireEvent.click(botao(/Enviar manifestação/));

    expect(await screen.findByText("2026-0042")).toBeTruthy();
    expect(screen.getByText("K7M2P-Q9RX4")).toBeTruthy();
    expect(screen.getByText(/aparece só agora/)).toBeTruthy();
    fireEvent.click(botao(/Copiar/));
    await waitFor(() => expect(copiar).toHaveBeenCalledWith("K7M2P-Q9RX4"));
    expect(screen.getByRole("link", { name: /Acompanhar/ }).getAttribute("href")).toBe("/acompanhar");
  });

  it("quem se identifica vê só o protocolo, sem código", async () => {
    await ateOContato();
    escrever("Seu nome", "Maria Souza");
    escrever("E-mail", "maria@exemplo.com");

    fireEvent.click(botao(/Enviar manifestação/));

    expect(await screen.findByText("2026-0042")).toBeTruthy();
    expect(screen.queryByText("K7M2P-Q9RX4")).toBeNull();
    expect(screen.queryByRole("button", { name: /Copiar/ })).toBeNull();
  });
});
