import { describe, expect, it } from "vitest";
import {
  cartaoDeProrrogacaoTemConteudo,
  mensagemDoPortal,
  montarFormularioDeResposta,
  pedidoDeProrrogacaoValido,
  respostaDoSetorValida,
  rotuloDePrazoDoPortal,
  SEM_CONFIRMACAO_DO_CALENDARIO,
  situacaoDoPedido,
  type CasoDoPortal,
  type PedidoDeProrrogacao,
  type ProrrogacaoNoPortal,
} from "./setor";

describe("portal do setor (issue #326)", () => {
  it("a resposta precisa dizer o que foi feito: espaco em branco nao vale", () => {
    expect(respostaDoSetorValida("Conversamos com a equipe e corrigimos o fluxo.")).toBe(true);
    expect(respostaDoSetorValida("   ")).toBe(false);
    expect(respostaDoSetorValida("")).toBe(false);
  });

  it("token invalido ou expirado vira mensagem clara, sem vazar o caso", () => {
    expect(mensagemDoPortal(404, undefined)).toBe(
      "Este link não é válido. Confira se o endereço veio completo no email da Ouvidoria."
    );
    expect(mensagemDoPortal(410, "Este link expirou")).toBe("Este link expirou");
    expect(mensagemDoPortal(500, undefined)).toBe("Não foi possível carregar este link agora. Tente novamente.");
  });

  it("o formulario multipart leva a resposta e os anexos escolhidos", () => {
    const arquivo = new File(["conteudo"], "evidencia.pdf", { type: "application/pdf" });
    const form = montarFormularioDeResposta("  Fizemos a correção.  ", [arquivo]);

    expect(form.get("resposta")).toBe("Fizemos a correção.");
    expect(form.getAll("arquivos")).toHaveLength(1);
  });
});

describe("prorrogação pelo portal (issue #333)", () => {
  it("o pedido exige justificativa e um número de dias dentro do limite", () => {
    expect(pedidoDeProrrogacaoValido("A auditoria só devolve o laudo na semana que vem.", 5, 30)).toBe(
      true
    );
    expect(pedidoDeProrrogacaoValido("   ", 5, 30)).toBe(false);
    expect(pedidoDeProrrogacaoValido("Motivo válido.", 0, 30)).toBe(false);
    expect(pedidoDeProrrogacaoValido("Motivo válido.", 31, 30)).toBe(false);
    expect(pedidoDeProrrogacaoValido("Motivo válido.", 2.5, 30)).toBe(false);
  });

  it("cada situação do pedido tem um texto que diz qual prazo vale", () => {
    const base = {
      id: "p1",
      justificativa: "Motivo",
      dias_uteis_pedidos: 5,
      prazo_anterior: null,
      prazo_novo: null,
      solicitada_em: "2026-08-25T17:00:00+00:00",
      solicitante_nome: "Carlos Titular",
      decidida_em: null,
      decidida_por_nome: null,
      decisao_justificativa: null,
    };

    expect(situacaoDoPedido({ ...base, status: "pendente" })).toContain("ainda não decidiu");
    expect(situacaoDoPedido({ ...base, status: "aprovada" })).toContain("já é o prazo novo");
    expect(situacaoDoPedido({ ...base, status: "negada" })).toContain("continua valendo");
  });
});

describe("o cartão de prorrogação só aparece quando tem o que dizer (issue #375, item 21)", () => {
  const CHEIO: ProrrogacaoNoPortal = {
    regras: ["Um pedido por manifestação."],
    max_dias_uteis: 10,
    permitida: true,
    motivo: null,
    pedido: null,
  };

  it("não desenha o cartão quando o backend não mandou o bloco", () => {
    // Backend uma versão atrás, ou resposta em cache: o cartão saía com
    // título, ícone e uma lista vazia embaixo, dizendo nada ao titular.
    expect(cartaoDeProrrogacaoTemConteudo(undefined)).toBe(false);
  });

  it("não desenha o cartão quando o bloco veio sem regra, sem pedido e sem motivo", () => {
    expect(
      cartaoDeProrrogacaoTemConteudo({
        ...CHEIO,
        regras: [],
        permitida: false,
        motivo: null,
      })
    ).toBe(false);
  });

  it("desenha quando há regras a mostrar", () => {
    expect(cartaoDeProrrogacaoTemConteudo(CHEIO)).toBe(true);
  });

  it("desenha quando a porta está aberta, mesmo sem regra cadastrada", () => {
    expect(cartaoDeProrrogacaoTemConteudo({ ...CHEIO, regras: [] })).toBe(true);
  });

  it("desenha quando a porta está fechada mas há motivo para explicar", () => {
    // Contar com um recurso que não existe é pior do que não ter o recurso:
    // o motivo é conteúdo, e o cartão fica.
    expect(
      cartaoDeProrrogacaoTemConteudo({
        ...CHEIO,
        regras: [],
        permitida: false,
        motivo: "Este caso já teve um pedido.",
      })
    ).toBe(true);
  });

  it("desenha quando já existe pedido para mostrar", () => {
    expect(
      cartaoDeProrrogacaoTemConteudo({
        ...CHEIO,
        regras: [],
        permitida: false,
        motivo: null,
        pedido: {
          id: "p1",
          dias_uteis_pedidos: 3,
          solicitante_nome: "Carlos",
          status: "pendente",
          decisao_justificativa: null,
        } as PedidoDeProrrogacao,
      })
    ).toBe(true);
  });
});

describe("o prazo que o portal pode afirmar (issue #449)", () => {
  const CASO = {
    protocolo: "OUV-2026-0001",
    setor: "Recepcao",
    categoria: "Demora",
    gravidade: "medio",
    extrato: "Paciente relata espera.",
    identificacao: "Joana da Silva",
    sigiloso: false,
    destinatario_nome: "Carlos Titular",
    aceita_resposta: true,
    rotulo_prazo: "vence em 2 dias úteis",
    prazo_estourado: false,
    minutos_uteis_restantes: 1080,
  } as CasoDoPortal;

  it("afirma o prazo quando o servidor diz que leu o calendário", () => {
    expect(rotuloDePrazoDoPortal({ ...CASO, degradado: [] })).toBe("vence em 2 dias úteis");
  });

  it("tira a frase da tela quando o calendário não pôde ser lido", () => {
    // Sem os feriados, o servidor conta feriado como dia útil e o prazo sai
    // mais curto do que é. Quem lê esta tela é quem tem que cumprir.
    expect(rotuloDePrazoDoPortal({ ...CASO, degradado: ["feriados"] })).toBe(SEM_CONFIRMACAO_DO_CALENDARIO);
  });

  it("outra leitura degradada não tira o prazo: a que conta dia útil é a dos feriados", () => {
    expect(rotuloDePrazoDoPortal({ ...CASO, degradado: ["responsaveis"] })).toBe("vence em 2 dias úteis");
  });

  it("marca ausente é não saber, e não saber não vira prazo afirmado", () => {
    // Backend uma versão atrás: ele não tem como dizer se leu o calendário.
    expect(rotuloDePrazoDoPortal(CASO)).toBe(SEM_CONFIRMACAO_DO_CALENDARIO);
  });
});
