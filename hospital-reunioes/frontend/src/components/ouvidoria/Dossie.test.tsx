/**
 * @vitest-environment jsdom
 */

/**
 * A natureza informada pelo manifestante, na tela do Dossiê (issue #474).
 *
 * A régua de o que dizer já tem teste próprio em `lib/ouvidoria/
 * natureza-informada.ts`. O que só existe aqui dentro é a fiação: o bloco
 * aparecer quando o caso trouxe a sugestão, e não aparecer quando não trouxe.
 * Sem este arquivo, remover o bloco do JSX deixaria a suíte inteira verde.
 *
 * O `fetch` entra dublado por URL: a página carrega anexos, notificações,
 * prorrogações, respostas e tentativas junto do Dossiê, e nenhum deles importa
 * para o que se quer provar.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SUGESTAO_NAO_E_CLASSIFICACAO } from "@/lib/ouvidoria/natureza-informada";
import { Dossie } from "./Dossie";

function dossie(overrides: Record<string, unknown> = {}) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "em_classificacao",
    tipo_manifestacao: null,
    categoria: "A classificar",
    setor: "A definir",
    resumo: "Paciente elogia a equipe da recepção.",
    relato_integral: "A moça da recepção foi muito atenciosa comigo.",
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
    natureza_informada: null,
    ...overrides,
  };
}

function montarComDossie(caso: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      return respostaJson(caso);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

describe("o Dossiê e a natureza informada pelo manifestante (issue #474)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra a sugestão do manifestante, com a origem escrita na linha", async () => {
    montarComDossie(dossie({ natureza_informada: "elogio" }));

    expect(await screen.findByText(/O manifestante informou: Elogio/)).toBeTruthy();
    expect(screen.getByText(SUGESTAO_NAO_E_CLASSIFICACAO)).toBeTruthy();
  });

  it("caso sem natureza informada não mostra o bloco", async () => {
    montarComDossie(dossie({ natureza_informada: null }));

    // Espera o Dossiê chegar antes de afirmar a ausência: sem isto o teste
    // passaria só porque a tela ainda estava carregando. O marco é o relato, e
    // não o protocolo: o cabeçalho mostra o protocolo PEDIDO na URL enquanto o
    // caso não chega, então ele apareceria sem o caso ter chegado.
    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(screen.queryByText(/O manifestante informou/)).toBeNull();
    expect(screen.queryByText(SUGESTAO_NAO_E_CLASSIFICACAO)).toBeNull();
  });

  it("a sugestão não vira a classificação do caso na tela", async () => {
    // O caso do canal aberto nasce sem tipo (ADR 0037): mesmo dizendo "elogio",
    // ele continua se apresentando como não classificado, e quem classifica é
    // o ouvidor no bloco de classificação (ADR 0040, decisão 3).
    montarComDossie(dossie({ natureza_informada: "elogio", tipo_manifestacao: null }));

    await screen.findByText(/O manifestante informou: Elogio/);
    await waitFor(() => {
      expect(screen.getByText("Não classificada")).toBeTruthy();
    });
  });
});

/**
 * O Paciente do caso na tela do ouvidor (issue #666, PRD #659, ADR 0052).
 *
 * As duas linhas ficam ao lado de "Quem manifestou", "Contato" e "Vínculo": é
 * o bloco onde o ouvidor lê o caso inteiro antes de acionar. O teste asserta o
 * VALOR na linha certa, e não a presença do texto na página: "Maria Souza"
 * solto passaria com o nome caindo em qualquer outro lugar, e "Não informado"
 * solto casaria com a linha do contato.
 */
describe("o Dossiê e o Paciente do caso (issue #666)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function valorDaLinha(rotulo: string): string {
    return screen.getByText(rotulo).nextElementSibling?.textContent ?? "";
  }

  it("mostra o nome do paciente e a referência do atendimento", async () => {
    montarComDossie(
      dossie({
        manifestante_vinculo: "acompanhante",
        paciente_nome: "Maria Souza",
        paciente_referencia: "Leito 12, dia 9",
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Maria Souza");
    expect(valorDaLinha("Referência do atendimento")).toBe("Leito 12, dia 9");
  });

  it("caso sem paciente informado desenha as duas linhas com Não informado", async () => {
    // A linha existe sempre: o ouvidor precisa saber que o campo está vazio,
    // e não que ele não existe.
    montarComDossie(dossie({ paciente_nome: null, paciente_referencia: null }));

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Não informado");
    expect(valorDaLinha("Referência do atendimento")).toBe("Não informado");
  });

  it("o caso anônimo mostra o paciente e segue sem identificar quem manifestou", async () => {
    // A decisão 3 do ADR 0052 desenhada: são duas pessoas, e o anonimato é de
    // uma só.
    montarComDossie(
      dossie({
        anonimo: true,
        manifestante_nome: null,
        manifestante_vinculo: "acompanhante",
        paciente_nome: "Maria Souza",
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(valorDaLinha("Paciente")).toBe("Maria Souza");
    expect(valorDaLinha("Quem manifestou")).toBe("Manifestação anônima");
  });
});

/**
 * O aviso do relato em nome de outra pessoa sem o nome do paciente
 * (issue #662, PRD #659, ADR 0052 decisão 5).
 *
 * É o ponto mais barato de pegar o caso: antes de o ouvidor acionar e a área
 * devolver por "não achei o atendimento". Sinalização pura, sem bloqueio.
 *
 * A frase é escrita AQUI por extenso, e não importada do componente: um teste
 * que compara a tela com a própria constante do componente segue verde quando
 * alguém derruba o "não" da frase ou a reescreve inteira.
 */
const AVISO_DO_ACOMPANHANTE_SEM_PACIENTE =
  "Relato em nome de outra pessoa sem o nome do paciente. Confirme com o manifestante antes de acionar.";

describe("o Dossiê e o aviso do acompanhante sem nome do paciente (issue #662)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("acende o aviso quando o relato é sobre outra pessoa e ninguém disse o nome do paciente", async () => {
    montarComDossie(
      dossie({
        manifestante_vinculo: "acompanhante",
        paciente_nome: null,
        paciente_referencia: "Leito 12, dia 9",
      })
    );

    expect(await screen.findByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeTruthy();
  });

  it("acompanhante que disse o nome do paciente não acende o aviso", async () => {
    montarComDossie(dossie({ manifestante_vinculo: "acompanhante", paciente_nome: "Maria Souza" }));

    // Espera o caso chegar antes de afirmar a ausência: sem isto o teste
    // passaria só porque a tela ainda estava carregando.
    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(screen.queryByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeNull();
  });

  it("relato sobre o próprio manifestante não acende o aviso", async () => {
    // "Sobre mim" grava o vínculo `paciente` e descarta o paciente do caso:
    // não ter nome ali é o normal, e não uma falta.
    montarComDossie(dossie({ manifestante_vinculo: "paciente", paciente_nome: null }));

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(screen.queryByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeNull();
  });

  // O vínculo nulo é o caso do QR enviado por uma aba aberta antes da versão
  // que pergunta "sobre quem" (issue #666): silêncio não é "outra pessoa".
  it.each(["colaborador", "terceiro", "outro", null])(
    "o vínculo %s não acende o aviso",
    async (vinculo) => {
      montarComDossie(dossie({ manifestante_vinculo: vinculo, paciente_nome: null }));

      expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
      expect(screen.queryByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeNull();
    }
  );

  // Nome em branco é nome nenhum. Nenhum dos três estados é produzível hoje
  // além do nulo (o canal público apara e converte vazio em nulo), mas sem a
  // string vazia aqui o mutante que troca `!paciente_nome` por
  // `paciente_nome == null` sobrevive, e sem os espaços sobrevive o que come
  // o `.trim()`.
  it.each([null, "", "   "])(
    "nome do paciente %o é nome nenhum, e o aviso acende",
    async (nome) => {
      montarComDossie(dossie({ manifestante_vinculo: "acompanhante", paciente_nome: nome }));

      expect(await screen.findByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeTruthy();
    }
  );

  it("canal que não pergunta o paciente fica em silêncio", async () => {
    // O Registro manual do ouvidor grava o vínculo `acompanhante` e não tem
    // campo de paciente (a issue #663 é que dá). Aceso ali, o aviso não teria
    // onde ser apagado, e mandaria o ouvidor confirmar com o manifestante a
    // ligação que ele mesmo acabou de atender.
    montarComDossie(
      dossie({
        canal: "telefone",
        canal_setor: null,
        manifestante_vinculo: "acompanhante",
        paciente_nome: null,
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(screen.queryByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeNull();
  });

  it("caso encerrado fica em silêncio: não há mais o que acionar", async () => {
    // "Confirme antes de acionar" num caso encerrado manda fazer o que não
    // existe mais. O fato continua legível na linha "Paciente: Não informado".
    montarComDossie(
      dossie({
        status: "encerrado",
        manifestante_vinculo: "acompanhante",
        paciente_nome: null,
      })
    );

    expect(await screen.findByText(/A moça da recepção foi muito atenciosa/)).toBeTruthy();
    expect(screen.queryByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE)).toBeNull();
  });

  it("CONTRAPROVA: o aviso não trava nada, o ouvidor aciona a área mesmo assim", async () => {
    // Sem esta, um mutante que trocasse o aviso por um bloqueio passaria: a
    // frase estaria na tela e o ato estaria indisponível. A prova é o clique
    // que abre a modal do acionamento, e não o atributo `disabled`: o botão
    // nunca o recebe, então afirmar `disabled === false` seria verdade até no
    // mundo em que o botão inteiro sumiu.
    montarComDossie(
      dossie({
        status: "em_classificacao",
        manifestante_vinculo: "acompanhante",
        paciente_nome: null,
      })
    );

    await screen.findByText(AVISO_DO_ACOMPANHANTE_SEM_PACIENTE);

    fireEvent.click(screen.getByText("Validar e acionar"));

    await waitFor(() => expect(screen.getByText(/Validar e acionar 2026-0012/)).toBeTruthy());
  });
});
