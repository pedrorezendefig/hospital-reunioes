import { describe, expect, it } from "vitest";
import {
  avisoDoTetoDaResposta,
  blocosDoCaso,
  cartaoDeProrrogacaoTemConteudo,
  classeDoBloco,
  CHAVE_NOTA,
  CHAVE_RELATO,
  CHAVE_RESUMO,
  MAXIMO_DA_RESPOSTA,
  mensagemDoPortal,
  MINIMO_DA_RESPOSTA,
  tamanhoBrutoDaResposta,
  tamanhoDaResposta,
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

describe("os três blocos de leitura na tela do responsável (issue #483, ADR 0041)", () => {
  const CASO = {
    protocolo: "OUV-2026-0001",
    setor: "Recepcao",
    categoria: "Demora",
    gravidade: "alto",
    extrato: "Confirmar a escala da recepção no turno da manhã.",
    identificacao: "Joana da Silva",
    sigiloso: false,
    destinatario_nome: "Carlos Titular",
    aceita_resposta: true,
    rotulo_prazo: "vence amanhã às 17h",
    prazo_estourado: false,
    minutos_uteis_restantes: 1080,
    degradado: [],
  } as CasoDoPortal;

  it("entrega os blocos que o servidor montou, na ordem em que ele mandou", () => {
    const blocos = blocosDoCaso({
      ...CASO,
      blocos: [
        { chave: CHAVE_RESUMO, rotulo: "RESUMO", texto: "Espera acima de duas horas." },
        { chave: CHAVE_RELATO, rotulo: "RELATO INTEGRAL", texto: "Cheguei às 8h e só fui atendida às 10h30." },
        { chave: CHAVE_NOTA, rotulo: "NOTA DA OUVIDORIA", texto: CASO.extrato },
      ],
    });

    expect(blocos.map((bloco) => bloco.chave)).toEqual([CHAVE_RESUMO, CHAVE_RELATO, CHAVE_NOTA]);
  });

  it("caso protegido chega com um bloco só, e a tela mostra exatamente esse", () => {
    // A tela reflete o que a API mandou: quem corta resumo e relato é o
    // servidor (RN-79 e a emenda de 01/09/2026 do ADR 0041), nunca o cliente.
    const blocos = blocosDoCaso({
      ...CASO,
      sigiloso: true,
      identificacao: null,
      blocos: [{ chave: CHAVE_NOTA, rotulo: "NOTA DA OUVIDORIA", texto: CASO.extrato }],
    });

    expect(blocos.map((bloco) => bloco.chave)).toEqual([CHAVE_NOTA]);
  });

  it("backend uma versão atrás não deixa a tela sem o caso: o extrato vira a nota", () => {
    expect(blocosDoCaso(CASO)).toEqual([
      { chave: CHAVE_NOTA, rotulo: "NOTA DA OUVIDORIA", texto: CASO.extrato },
    ]);
  });

  it("lista vazia é o mesmo que ausente: a tela não pode ficar sem o caso", () => {
    expect(blocosDoCaso({ ...CASO, blocos: [] })).toHaveLength(1);
  });

  it("cada bloco tem formatação própria: fundir dois deles é o que a RN-60 proíbe", () => {
    const classes = [CHAVE_RESUMO, CHAVE_RELATO, CHAVE_NOTA].map(classeDoBloco);

    expect(new Set(classes).size).toBe(3);
  });

  it("bloco de chave desconhecida cai na formatação da nota, e não some da tela", () => {
    expect(classeDoBloco("chave-que-ainda-nao-existe")).toBe(classeDoBloco(CHAVE_NOTA));
  });
});

describe("o mínimo que habilita o envio (issue #483, RN-61)", () => {
  it("o botão só libera a partir de 20 caracteres, o mesmo piso do servidor", () => {
    expect(MINIMO_DA_RESPOSTA).toBe(20);
    expect(respostaDoSetorValida("Trocamos a escala.")).toBe(false);
    expect(respostaDoSetorValida("Trocamos a escala!!")).toBe(false);
    expect(respostaDoSetorValida("Trocamos a escala!!!")).toBe(true);
  });

  it("espaço nas pontas não conta para o piso", () => {
    expect(respostaDoSetorValida(`   ${"a".repeat(19)}   `)).toBe(false);
    expect(respostaDoSetorValida(`   ${"a".repeat(20)}   `)).toBe(true);
  });

  it("conta como o servidor conta: emoji é um caractere, não dois", () => {
    // O servidor conta code points; `String.length` conta unidades UTF-16, e
    // cada emoji vale duas. Esta frase tem 19 code points e 21 unidades: o
    // botão habilitava, o responsável apertava e levava 422 com o campo cheio.
    const dezenoveComEmoji = "Ok, ja resolvido 👍👍";

    expect(dezenoveComEmoji.trim().length).toBe(21);
    expect(tamanhoDaResposta(dezenoveComEmoji)).toBe(19);
    expect(respostaDoSetorValida(dezenoveComEmoji)).toBe(false);
    expect(respostaDoSetorValida(`${dezenoveComEmoji}👍`)).toBe(true);
  });

  it("caractere de largura zero não empurra o texto por cima do piso", () => {
    // O servidor descarta a categoria Cf antes de medir. Sem o mesmo descarte
    // aqui, quatro caracteres invisíveis colados no fim liberavam o botão.
    const dezoitoMaisInvisiveis = `Resolvido, tudo ok${"​".repeat(4)}`;

    expect(dezoitoMaisInvisiveis.trim().length).toBe(22);
    expect(tamanhoDaResposta(dezoitoMaisInvisiveis)).toBe(18);
    expect(respostaDoSetorValida(dezoitoMaisInvisiveis)).toBe(false);
  });
});

describe("o teto que o botão espelha (issue #512)", () => {
  it("é o mesmo número do servidor", () => {
    // `ouvidoria_respostas.MAXIMO_DE_CARACTERES`. Divergir aqui é o mesmo bug
    // que o PR #507 fechou no piso, só que com o sinal trocado.
    expect(MAXIMO_DA_RESPOSTA).toBe(10_000);
  });

  it("a fronteira é até o teto, não abaixo dele", () => {
    expect(respostaDoSetorValida("a".repeat(10_000))).toBe(true);
    expect(respostaDoSetorValida("a".repeat(10_001))).toBe(false);
  });

  it("o teto conta o texto cru: invisível não conta para o piso, mas conta para o teto", () => {
    // O servidor mede o teto ANTES de normalizar (`len(texto)`), e só o piso
    // depois. Usar aqui a contagem do piso, que descarta a categoria Cf,
    // liberaria o botão para um texto que o servidor recusa com 422.
    const noTetoMaisInvisivel = `${"a".repeat(10_000)}${"​".repeat(1)}`;

    expect(tamanhoDaResposta(noTetoMaisInvisivel)).toBe(10_000);
    expect(tamanhoBrutoDaResposta(noTetoMaisInvisivel)).toBe(10_001);
    expect(respostaDoSetorValida(noTetoMaisInvisivel)).toBe(false);
  });

  it("conta code points, não unidades UTF-16: emoji é um caractere", () => {
    // `String.length` daria 10.010 e barraria um texto que o servidor aceita.
    const comEmoji = `${"a".repeat(9_990)}${"👍".repeat(10)}`;

    expect(comEmoji.length).toBe(10_010);
    expect(tamanhoBrutoDaResposta(comEmoji)).toBe(10_000);
    expect(respostaDoSetorValida(comEmoji)).toBe(true);
  });

  it("conta exatamente a string que o formulário envia", () => {
    // A tela apara antes de mandar (`montarFormularioDeResposta`), então o
    // servidor mede o texto já aparado. Contar o não aparado barraria um envio
    // que passa: dez mil caracteres com uma quebra de linha no fim.
    const comEspacoNasPontas = `\n  ${"a".repeat(10_000)}  \n`;
    const enviado = montarFormularioDeResposta(comEspacoNasPontas, []).get("resposta") as string;

    expect([...enviado].length).toBe(tamanhoBrutoDaResposta(comEspacoNasPontas));
    expect(respostaDoSetorValida(comEspacoNasPontas)).toBe(true);
  });

  it("o piso continua valendo: o teto não abriu a porta para a resposta curta", () => {
    expect(respostaDoSetorValida("Resolvido.")).toBe(false);
  });
});

describe("o aviso do teto na tela (issue #512)", () => {
  it("não polui a tela na resposta de tamanho normal", () => {
    expect(avisoDoTetoDaResposta("Trocamos a escala da recepção nesta segunda.")).toBeNull();
  });

  it("aparece quando o texto chega perto do limite, ainda dentro dele", () => {
    const aviso = avisoDoTetoDaResposta("a".repeat(9_500));

    expect(aviso).toContain("500");
    expect(aviso).toContain("10.000");
  });

  it("diz que passou quando passou, com o mesmo teto do servidor", () => {
    const aviso = avisoDoTetoDaResposta("a".repeat(10_001));

    expect(aviso).toContain("passou");
    expect(aviso).toContain("10.000");
  });

  it("o aviso e o botão concordam: sempre que o botão barra pelo teto, há aviso", () => {
    const acimaDoTeto = "a".repeat(10_050);

    expect(respostaDoSetorValida(acimaDoTeto)).toBe(false);
    expect(avisoDoTetoDaResposta(acimaDoTeto)).not.toBeNull();
  });
});
