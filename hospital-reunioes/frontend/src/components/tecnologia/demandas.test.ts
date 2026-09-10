/**
 * As contas puras da Conversa (issue #638, PRD #634, ADR 0050).
 *
 * A janela de 10 minutos e a @menção são regras que a tela precisa saber para
 * desenhar (o botão "Corrigir", o autocomplete e o destaque da menção). Quem
 * recusa de verdade continua sendo o backend; o que se prova aqui é que a tela
 * não oferece um caminho que ela já sabe recusado, nem esconde um que vale.
 */

import { describe, expect, it } from "vitest";

import {
  aplicarMencao,
  blocosDoTextoSimples,
  demandaIdDaUrl,
  fraseDaMinhaVezVazia,
  fraseDoHistoricoVazio,
  linkDaDemanda,
  mencoesNoTexto,
  momentoLegivel,
  pedacosDoTexto,
  pessoasDoAutocomplete,
  podeCorrigirAgora,
  queryDeFiltros,
  queryDoHistorico,
  SEM_FILTRO,
  SEM_REGISTRO_DE_QUANDO,
  SEM_REGISTRO_DE_QUEM,
  temFiltroAtivo,
  termoDaMencao,
  textoDoDesfecho,
} from "./demandas";

const PESSOAS = [
  { id: "P1", nome_completo: "Pedro Vitta" },
  { id: "P2", nome_completo: "Sócia Vitta" },
];

const AGORA = new Date("2026-09-09T12:00:00Z");

describe("A janela de correção, do lado da tela", () => {
  it("o botão vale enquanto o limite não passou", () => {
    expect(podeCorrigirAgora("2026-09-09T12:00:30Z", AGORA)).toBe(true);
  });

  it("no instante exato do limite ainda vale", () => {
    // O backend usa limite inclusivo ("por até 10 minutos"): uma tela mais
    // rígida esconderia o botão de um clique que a API aceitaria.
    expect(podeCorrigirAgora("2026-09-09T12:00:00Z", AGORA)).toBe(true);
  });

  it("um segundo depois do limite o botão some", () => {
    expect(podeCorrigirAgora("2026-09-09T11:59:59Z", AGORA)).toBe(false);
  });

  it("sem limite não há botão", () => {
    // É o que o backend manda na linha de movimento e na resposta de outra
    // pessoa: `editavel_ate` nulo.
    expect(podeCorrigirAgora(null, AGORA)).toBe(false);
  });

  it("limite ilegível não vira botão eterno", () => {
    expect(podeCorrigirAgora("depois do almoço", AGORA)).toBe(false);
  });
});

describe("O autocomplete do @", () => {
  it("o termo é o que veio depois do último @", () => {
    expect(termoDaMencao("Oi @Só")).toBe("Só");
  });

  it("sem @ não há menção em aberto", () => {
    expect(termoDaMencao("Oi, tudo bem")).toBeNull();
  });

  it("o @ digitado sozinho abre a lista inteira", () => {
    expect(termoDaMencao("Oi @")).toBe("");
    expect(pessoasDoAutocomplete("", PESSOAS)).toHaveLength(2);
  });

  it("o @ de um parágrafo anterior não segue aberto", () => {
    expect(termoDaMencao("Falei com @Pedro Vitta\nE também isso")).toBeNull();
  });

  it("lista quem começa pelo termo, sem distinguir maiúsculas", () => {
    expect(pessoasDoAutocomplete("só", PESSOAS).map((p) => p.id)).toEqual(["P2"]);
    expect(pessoasDoAutocomplete("SÓ", PESSOAS).map((p) => p.id)).toEqual(["P2"]);
  });

  it("some quando a frase seguiu e ninguém mais casa", () => {
    // O par de presença está acima: com "só" a lista tem gente. Aqui a pessoa
    // continuou escrevendo, e o autocomplete sai da frente.
    expect(pessoasDoAutocomplete("Sócia Vitta consegue olhar?", PESSOAS)).toEqual([]);
  });

  it("escolher troca o termo em aberto pelo nome inteiro", () => {
    expect(aplicarMencao("Oi @Só", "Sócia Vitta")).toBe("Oi @Sócia Vitta ");
  });

  it("escolher sem @ nenhum ainda escreve a menção no fim", () => {
    expect(aplicarMencao("Oi", "Sócia Vitta")).toBe("Oi@Sócia Vitta ");
  });
});

describe("Da escolha à lista de menções", () => {
  it("manda só quem o texto ainda chama", () => {
    const texto = "@Sócia Vitta consegue olhar?";
    expect(mencoesNoTexto(texto, PESSOAS)).toEqual(["P2"]);
  });

  it("apagar o @Fulano do texto tira a menção", () => {
    // Senão a linha continuaria dizendo que chamou alguém que o texto não
    // chama mais, e o e-mail da fatia seguinte avisaria essa pessoa à toa.
    expect(mencoesNoTexto("Deixa comigo", PESSOAS)).toEqual([]);
  });

  it("as duas menções cabem na mesma resposta", () => {
    expect(mencoesNoTexto("@Pedro Vitta e @Sócia Vitta, olhem", PESSOAS)).toEqual(["P1", "P2"]);
  });

  it("nome que é começo de outro não entra de carona", () => {
    // A pessoa digita "@Ana", clica em "Ana Souza" por engano, apaga, digita de
    // novo e escolhe "Ana Souza Lima": as duas ficam na lista de escolhidas, e o
    // texto chama uma só. Com um `includes` por nome, a curta entrava junto, e o
    // erro era MUDO, porque o destaque marca só a longa. Na fatia do e-mail
    // viraria aviso para quem o texto não chamou.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];

    expect(mencoesNoTexto("@Ana Souza Lima decide", homonimas)).toEqual(["PB"]);
  });

  it("as duas homônimas entram quando o texto chama as duas", () => {
    // Par de presença do teste acima: uma regra que sempre ficasse com o nome
    // mais longo perderia a menção legítima à curta.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];

    expect(mencoesNoTexto("@Ana Souza e @Ana Souza Lima decidem", homonimas)).toEqual(["PA", "PB"]);
  });

  it("a lista gravada e o destaque contam a mesma história", () => {
    // Hoje as duas contas saem do mesmo `pedacosDoTexto`, então este caso é
    // verdadeiro por construção: ele não é prova independente, é a TRAVA contra
    // desacoplar os dois de novo. Foi assim que a menção fantasma nasceu, com o
    // destaque resolvendo o prefixo e a lista gravada não.
    const homonimas = [
      { id: "PA", nome_completo: "Ana Souza" },
      { id: "PB", nome_completo: "Ana Souza Lima" },
    ];
    const texto = "@Ana Souza Lima decide";

    const destacados = pedacosDoTexto(
      texto,
      homonimas.map((p) => p.nome_completo),
    )
      .filter((pedaco) => pedaco.mencao)
      .map((pedaco) => pedaco.texto.slice(1));
    const gravados = mencoesNoTexto(texto, homonimas).map(
      (id) => homonimas.find((p) => p.id === id)!.nome_completo,
    );

    expect(gravados).toEqual(destacados);
  });
});

describe("O destaque da menção no fio", () => {
  it("marca o @Nome e deixa o resto como texto comum", () => {
    const pedacos = pedacosDoTexto("Oi @Sócia Vitta, olha isso", ["Sócia Vitta"]);

    expect(pedacos).toEqual([
      { texto: "Oi ", mencao: false },
      { texto: "@Sócia Vitta", mencao: true },
      { texto: ", olha isso", mencao: false },
    ]);
  });

  it("sem menção nenhuma o texto sai inteiro e sem marca", () => {
    // Par de presença do teste acima: uma marcação cravada pintaria tudo.
    expect(pedacosDoTexto("Vou olhar hoje", [])).toEqual([{ texto: "Vou olhar hoje", mencao: false }]);
  });

  it("nome que é começo de outro não é marcado pela metade", () => {
    const pedacos = pedacosDoTexto("@Ana Maria decide", ["Ana", "Ana Maria"]);

    expect(pedacos[0]).toEqual({ texto: "@Ana Maria", mencao: true });
  });

  it("o nome escrito sem @ continua texto comum", () => {
    expect(pedacosDoTexto("Falei com Sócia Vitta ontem", ["Sócia Vitta"])).toEqual([
      { texto: "Falei com Sócia Vitta ontem", mencao: false },
    ]);
  });
});

describe("A busca que os filtros montam", () => {
  it("sem filtro nenhum a URL fica limpa, sem nem a interrogação", () => {
    // Um "?" sozinho não quebra o backend, mas denuncia que a tela manda
    // filtro vazio; e `estado=""` cairia no `if valor` do router como falso,
    // escondendo aqui um erro que só apareceria com uma API mais rígida.
    expect(queryDeFiltros(SEM_FILTRO)).toBe("");
  });

  it("cada filtro escolhido vira o parâmetro que a API já aceita", () => {
    // Os nomes são escritos à mão de propósito: montá-los a partir do próprio
    // objeto faria o teste passar com qualquer chave que a tela inventasse.
    expect(queryDeFiltros({ tipo: "ajuste", produto_id: "", responsavel_id: "" })).toBe("?tipo=ajuste");
    expect(queryDeFiltros({ tipo: "", produto_id: "prod-1", responsavel_id: "" })).toBe("?produto_id=prod-1");
    expect(queryDeFiltros({ tipo: "", produto_id: "", responsavel_id: "P2" })).toBe("?responsavel_id=P2");
  });

  it("os três juntos vão na mesma busca", () => {
    expect(queryDeFiltros({ tipo: "defeito", produto_id: "prod-2", responsavel_id: "P1" })).toBe(
      "?tipo=defeito&produto_id=prod-2&responsavel_id=P1",
    );
  });

  it("o valor viaja escapado", () => {
    // Id não tem espaço hoje, mas concatenar na mão passaria a montar uma URL
    // quebrada no dia em que tiver.
    expect(queryDeFiltros({ tipo: "", produto_id: "a b&c", responsavel_id: "" })).toBe(
      "?produto_id=a+b%26c",
    );
  });

  it("diz que há filtro ativo quando há, e que não há quando não há", () => {
    expect(temFiltroAtivo(SEM_FILTRO)).toBe(false);
    expect(temFiltroAtivo({ tipo: "ajuste", produto_id: "", responsavel_id: "" })).toBe(true);
    expect(temFiltroAtivo({ tipo: "", produto_id: "prod-1", responsavel_id: "" })).toBe(true);
    expect(temFiltroAtivo({ tipo: "", produto_id: "", responsavel_id: "P1" })).toBe(true);
  });
});

describe("O link da Demanda (issue #640)", () => {
  it("monta o endereço da aba com o id da Demanda", () => {
    // O endereço escrito à mão a partir da rota real (`src/app/admin/tecnologia`),
    // e não montado a partir das constantes do módulo: montá-lo com as mesmas
    // constantes seria reescrever a função dentro do teste, e uma rota trocada
    // continuaria casando dos dois lados.
    expect(linkDaDemanda("d1", "https://app.exemplo.com")).toBe(
      "https://app.exemplo.com/admin/tecnologia?demanda=d1",
    );
  });

  it("o link que se copia é o link que a tela sabe ler", () => {
    // A prova de que os dois lados falam o mesmo formato. Sem ela, "Copiar
    // link" poderia gerar um endereço que a própria aplicação não abre.
    const link = linkDaDemanda("abc-123", "https://app.exemplo.com");

    expect(demandaIdDaUrl(new URL(link).search)).toBe("abc-123");
  });

  it("id com caractere que a URL trata sobrevive à ida e à volta", () => {
    const link = linkDaDemanda("id com espaço&outro=1", "https://app.exemplo.com");

    expect(link).not.toContain(" ");
    expect(demandaIdDaUrl(new URL(link).search)).toBe("id com espaço&outro=1");
  });

  it("sem o parâmetro não há Demanda a abrir", () => {
    expect(demandaIdDaUrl("")).toBeNull();
    expect(demandaIdDaUrl("?outra=coisa")).toBeNull();
  });

  it("parâmetro vazio ou só de espaços não é id", () => {
    // Sem isto, `?demanda=` abriria uma busca por uma Demanda de id vazio e a
    // tela acusaria "não está no Quadro" para um link que não pediu nada.
    expect(demandaIdDaUrl("?demanda=")).toBeNull();
    expect(demandaIdDaUrl("?demanda=%20%20")).toBeNull();
  });

  it("o parâmetro no meio de outros continua sendo lido", () => {
    expect(demandaIdDaUrl("?aba=quadro&demanda=d7&x=1")).toBe("d7");
  });
});

describe("A busca do Histórico, do lado da tela (issue #641)", () => {
  const COM_FILTRO = { tipo: "defeito", produto_id: "prod-2", responsavel_id: "P1" };

  it("sem filtro e sem termo a busca sai vazia", () => {
    // Nem o "?" sozinho: a API entende ausência de parâmetro como sem filtro.
    expect(queryDoHistorico(SEM_FILTRO, "")).toBe("");
  });

  it("o termo vai como `busca`", () => {
    expect(queryDoHistorico(SEM_FILTRO, "encerrar")).toBe("?busca=encerrar");
  });

  it("os filtros das outras abas vão junto", () => {
    const query = queryDoHistorico(COM_FILTRO, "encerrar");

    expect(new URLSearchParams(query.slice(1)).get("tipo")).toBe("defeito");
    expect(new URLSearchParams(query.slice(1)).get("produto_id")).toBe("prod-2");
    expect(new URLSearchParams(query.slice(1)).get("responsavel_id")).toBe("P1");
    expect(new URLSearchParams(query.slice(1)).get("busca")).toBe("encerrar");
  });

  it("os filtros sozinhos continuam valendo sem termo", () => {
    // A irmã de presença do caso acima: sem ela, um montador que ignorasse o
    // termo passaria naquele teste se o termo entrasse por outro caminho.
    const query = queryDoHistorico(COM_FILTRO, "");

    expect(new URLSearchParams(query.slice(1)).get("tipo")).toBe("defeito");
    expect(new URLSearchParams(query.slice(1)).has("busca")).toBe(false);
  });

  it("termo só com espaços não vira busca", () => {
    // Mandar `busca=%20` faria a API procurar um espaço, e a tela diria "nada
    // encontrado" para quem não buscou nada.
    expect(queryDoHistorico(SEM_FILTRO, "   ")).toBe("");
  });

  it("o termo viaja escapado", () => {
    const query = queryDoHistorico(SEM_FILTRO, "encerrar & pausar");

    expect(query).not.toContain(" ");
    expect(new URLSearchParams(query.slice(1)).get("busca")).toBe("encerrar & pausar");
  });

  it("o espaço em volta do termo não vai para a URL", () => {
    expect(new URLSearchParams(queryDoHistorico(SEM_FILTRO, "  régua  ").slice(1)).get("busca")).toBe("régua");
  });
});

describe("A linha de desfecho do Histórico", () => {
  const FECHADA = {
    id: "d1",
    titulo: "Encerrar conversas",
    descricao: null,
    tipo: "decisao" as const,
    produto_id: "prod-1",
    produto_nome: "Ana",
    estado: "concluida" as const,
    responsavel_id: "P1",
    responsavel_nome: "Pedro Vitta",
    autor_id: "P1",
    prioridade: "normal" as const,
    prazo: null,
    criado_em: "2026-09-01T09:00:00Z",
    concluida_em: "2026-09-08T15:00:00Z",
    cancelada_em: null,
    fechada_em: "2026-09-08T15:00:00Z",
    fechada_por_id: "P2",
    fechada_por_nome: "Sócia Vitta",
  };

  it("diz o desfecho, quando e por quem", () => {
    const texto = textoDoDesfecho(FECHADA);

    expect(texto).toContain("Concluída");
    expect(texto).toContain("por Sócia Vitta");
    // A data é escrita no fuso de quem olha; o que se cobra é que ela esteja
    // ali, e não o texto exato do `toLocaleString`.
    expect(texto).toContain(momentoLegivel("2026-09-08T15:00:00Z"));
  });

  it("Cancelada diz Cancelada, e não Concluída", () => {
    const texto = textoDoDesfecho({ ...FECHADA, estado: "cancelada" });

    expect(texto).toContain("Cancelada");
    expect(texto).not.toContain("Concluída");
  });

  it("sem o carimbo de quem, a linha DIZ que não há registro", () => {
    // Calar faria a falta parecer escolha de layout, e o critério da issue é
    // justamente mostrar quando e quem.
    const texto = textoDoDesfecho({ ...FECHADA, fechada_por_nome: null });

    expect(texto).toContain(SEM_REGISTRO_DE_QUEM);
    // A irmã de presença: o resto da linha continua inteiro.
    expect(texto).toContain("Concluída");
  });

  it("sem o carimbo de quando, a linha DIZ que não há registro", () => {
    const texto = textoDoDesfecho({ ...FECHADA, fechada_em: null });

    expect(texto).toContain(SEM_REGISTRO_DE_QUANDO);
    expect(texto).toContain("por Sócia Vitta");
  });
});

describe("As frases de lista vazia", () => {
  it("Minha vez vazia é boa notícia, e não falha", () => {
    const frase = fraseDaMinhaVezVazia(false);

    expect(frase).toContain("Nada esperando por você");
    // Ela não pode culpar carregamento nem mandar tentar de novo: vazio aqui
    // quer dizer que não há nada esperando, e isso é uma boa notícia.
    expect(frase.toLowerCase()).not.toContain("não foi possível");
    expect(frase.toLowerCase()).not.toContain("tente de novo");
  });

  it("Minha vez vazia COM filtro aponta o filtro e a saída", () => {
    const frase = fraseDaMinhaVezVazia(true);

    expect(frase).toContain("filtro");
    expect(frase).toContain("limpe os filtros");
  });

  it("a frase de Minha vez muda com o filtro", () => {
    // O par das duas acima: uma frase única passaria nas duas se ela citasse
    // as duas coisas ao mesmo tempo.
    expect(fraseDaMinhaVezVazia(true)).not.toBe(fraseDaMinhaVezVazia(false));
    expect(fraseDaMinhaVezVazia(false)).not.toContain("filtro");
  });

  it("Histórico vazio de verdade não fala em busca nem em filtro", () => {
    const frase = fraseDoHistoricoVazio("", false);

    expect(frase).toContain("Nenhuma Demanda foi concluída ou cancelada ainda");
    expect(frase).not.toContain("filtro");
  });

  it("busca sem resultado cita o termo procurado", () => {
    const frase = fraseDoHistoricoVazio("régua", false);

    expect(frase).toContain('"régua"');
    // Não manda limpar filtro nenhum: não há filtro ligado, e pedir uma ação
    // impossível deixa quem leu sem saída.
    expect(frase).not.toContain("filtros");
  });

  it("busca sem resultado COM filtro diz as duas coisas", () => {
    const frase = fraseDoHistoricoVazio("régua", true);

    expect(frase).toContain('"régua"');
    expect(frase).toContain("limpe os filtros");
  });

  it("filtro sem busca fala do filtro, e não de termo nenhum", () => {
    const frase = fraseDoHistoricoVazio("", true);

    expect(frase).toContain("Limpe os filtros");
    expect(frase).not.toContain('""');
  });

  it("termo só de espaços não conta como busca", () => {
    expect(fraseDoHistoricoVazio("   ", false)).toBe(fraseDoHistoricoVazio("", false));
  });

  it("as quatro frases são diferentes entre si", () => {
    // O piso das seis acima: uma frase única para os quatro casos passaria em
    // metade delas, e mandaria limpar filtro quem não tem filtro.
    const frases = new Set([
      fraseDoHistoricoVazio("", false),
      fraseDoHistoricoVazio("régua", false),
      fraseDoHistoricoVazio("", true),
      fraseDoHistoricoVazio("régua", true),
    ]);

    expect(frases.size).toBe(4);
  });
});

describe("O Markdown simples do O que muda", () => {
  it("separa parágrafo de lista", () => {
    const blocos = blocosDoTextoSimples("O card ganha a seção.\n\n- Vem do planejamento.\n- Ninguém reescreve.");

    expect(blocos.map((b) => b.lista)).toEqual([false, true]);
    expect(blocos[1].linhas.map((linha) => linha[0].texto)).toEqual(["Vem do planejamento.", "Ninguém reescreve."]);
  });

  it("linha em branco fecha o parágrafo", () => {
    // Sem isso os dois parágrafos virariam um só, e o texto sairia grudado.
    const blocos = blocosDoTextoSimples("Primeiro.\n\nSegundo.");

    expect(blocos).toHaveLength(2);
    expect(blocos.every((b) => b.linhas.length === 1)).toBe(true);
  });

  it("o negrito vira pedaço forte e o asterisco some", () => {
    const pedacos = blocosDoTextoSimples("**O que muda:** o card ganha a seção.")[0].linhas[0];

    expect(pedacos).toEqual([
      { texto: "O que muda:", forte: true },
      { texto: " o card ganha a seção.", forte: false },
    ]);
  });

  it("link do Markdown continua sendo texto", () => {
    // Nada que venha do GitHub vira elemento clicável na tela do diretor: o que
    // o parser não conhece fica como está, e não como um link.
    const pedacos = blocosDoTextoSimples("Veja [a issue](https://exemplo).")[0].linhas[0];

    expect(pedacos).toEqual([{ texto: "Veja [a issue](https://exemplo).", forte: false }]);
  });

  it("texto vazio ou nulo não vira bloco nenhum", () => {
    expect(blocosDoTextoSimples(null)).toEqual([]);
    expect(blocosDoTextoSimples("   \n  ")).toEqual([]);
  });
});
