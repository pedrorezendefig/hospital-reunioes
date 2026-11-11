/**
 * O vocabulário da Demanda, do lado da tela (issue #637, PRD #634; ADR 0077).
 *
 * Desde a issue #1386 a aba é o chat do agente: aqui ficam o que a lista das
 * conversas e a conversa aberta leem da Demanda (a Etapa, o selo e O que muda)
 * e o tratamento comum das respostas do servidor.
 */

/** O prefixo da API da aba. */
export const BASE_TECNOLOGIA = "/api/admin/tecnologia";

/** A mesma frase em todo caminho de rede da aba, carregar e salvar. */
export const FALHA_DE_CONEXAO = "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";

/**
 * O motivo da recusa, dito pelo servidor.
 *
 * A tela não inventa causa: quem sabe por que recusou (o resumo que ainda não
 * existe, a integração desligada) é a API, e é a frase dela que a pessoa lê.
 */
export async function motivoDaRecusa(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
    if (corpo?.detail) return JSON.stringify(corpo.detail);
  } catch {
    // Resposta sem corpo JSON: sobra o status.
  }
  return `Não foi possível salvar (${resposta.status}).`;
}

/**
 * A Demanda como a lista lateral do chat a lê (issue #1384, ADR 0077).
 *
 * Só o que o diretor vê: o título, a Etapa e O que muda. Número e endereço da
 * issue não vêm do servidor (ADR 0054, decisão 9).
 */
export type Demanda = {
  id: string;
  titulo: string;
  criado_em?: string | null;
  /**
   * Onde o desenvolvimento está, em palavras (issue #674, ADR 0054). Backend
   * uma versão atrás não manda o campo, e aí o `temSelo` trata como
   * "Registrada", que é a conversa sem card.
   */
  etapa?: EtapaDemanda;
  partes_entregues?: number | null;
  partes_total?: number | null;
  /** Se o card já nasceu: a conversa vira só leitura, com O que muda. */
  tem_vinculo?: boolean;
  /**
   * O que a entrega muda para quem pediu (issue #676, ADR 0054, decisão 7).
   *
   * Vem do bloco "Para o diretor" da issue e NUNCA é digitado no app. Nulo é
   * "a Vitta ainda não escreveu", e a tela o traduz numa frase; nulo não é o
   * corpo técnico da issue, que não sai do GitHub.
   */
  o_que_muda?: string | null;
  partes?: ParteDaEntrega[];
  /**
   * A versão em que a Demanda subiu ("v0.169.0", issue #1065).
   *
   * O backend a manda só quando a Etapa é Em produção: a tela mostra o que
   * veio e não repete a regra.
   */
  versao?: string | null;
  /**
   * As Datas do Documento do card (issue #1552, ADR 0084): a entrega (o
   * fechamento da issue-raiz) e a entrada Em produção. O backend as manda só
   * na Etapa que as segura; nulas, a linha não aparece.
   */
  fechada_em?: string | null;
  em_producao_em?: string | null;
  /**
   * Se o pedido é bug ou melhoria (issue #1438), já traduzido do Tipo pelo
   * backend. Nulo, ou ausente, é o pedido de antes do chat: fica sem selo.
   */
  classificacao?: Classificacao | null;
  /** Se quem está logado é o autor (ADR 0083). Falso abre a Demanda só para leitura. */
  minha?: boolean;
  /**
   * Só para o Desenvolvedor (ADR 0083, decisão 3): quem pediu, e o número e o
   * endereço da issue. Para o diretor o servidor manda nulo.
   */
  autor?: string | null;
  issue_numero?: number | null;
  issue_url?: string | null;
  /** Quem cuida do card (ADR 0083, decisão 5), para todos. Nulo enquanto o card não nasceu. */
  responsavel?: string | null;
  /** O card não chegou ao GitHub (issue #1535, ADR 0083, decisão 7): o selo e o Reenviar, para todos. */
  envio_falhou?: boolean;
  /** A issue nasceu sem o Responsável (issue #1536): o aviso e o Designar de novo, só para o Desenvolvedor. */
  designacao_falhou?: boolean;
  /** O motivo técnico da falha, só para o Desenvolvedor. Para o diretor o servidor manda nulo. */
  envio_motivo?: string | null;
  /**
   * Se quem está logado pode apagar a Demanda (issue #1549, ADR 0084): o autor
   * na conversa Registrada, o Desenvolvedor no card até Planejada. Quem decide
   * é o servidor; sem o campo, o botão não aparece.
   */
  pode_apagar?: boolean;
  /**
   * Quem abriu o card (issue #1554, ADR 0084, decisão 4): o diretor, pelo
   * chat, ou a Vitta, pela issue aberta no terminal. O card da Vitta não tem
   * conversa com o agente. Sem o campo, a linha fica sem selo.
   */
  origem?: Origem | null;
  /**
   * A Revisão com o código de hoje (issue #1557, ADR 0084, decisão 3):
   * `pode_revisar` mostra o botão, pela regra do servidor; `em_revisao` abre a
   * conversa para responder, e não só para ler.
   */
  pode_revisar?: boolean;
  em_revisao?: boolean;
};

export type Origem = "diretor" | "vitta";

/** O selo da Origem na lista (issue #1554). */
export const ORIGEM_ROTULO: Record<Origem, string> = {
  diretor: "Pedido do diretor",
  vitta: "Vitta",
};

export const ORIGEM_CLASSE: Record<Origem, string> = {
  diretor: "bg-slate-100 text-slate-700",
  vitta: "bg-sky-50 text-sky-700",
};

export type Classificacao = "bug" | "melhoria";

/** O selo da lista ao lado da Etapa (issue #1438). */
export const CLASSIFICACAO_ROTULO: Record<Classificacao, string> = {
  bug: "Bug",
  melhoria: "Melhoria",
};

export const CLASSIFICACAO_CLASSE: Record<Classificacao, string> = {
  bug: "bg-rose-50 text-rose-700",
  melhoria: "bg-violet-50 text-violet-700",
};

/** Uma parte da entrega: o que ela muda, em que pé está e quando fechou. */
export type ParteDaEntrega = {
  o_que_muda: string | null;
  situacao: EtapaDemanda | null;
  /** Quando a parte fechou (issue #1552). Nula na parte aberta. */
  fechada_em?: string | null;
};

/**
 * As sete Etapas, espelho da tupla do backend (`app/services/tecnologia_vinculo.py`).
 *
 * "Em produção" entrou pela ADR 0069 (issue #1057): a subida que levou a
 * entrega ao ar, com a versão.
 */
export type EtapaDemanda =
  | "registrada"
  | "em_analise"
  | "planejada"
  | "em_desenvolvimento"
  | "entregue"
  | "em_producao"
  | "nao_sera_feita";

/**
 * O rótulo em palavras do diretor.
 *
 * Ele não vê label, número nem estado de issue: vê estas sete frases
 * (ADR 0054, decisão 9).
 */
export const ETAPA_ROTULO: Record<EtapaDemanda, string> = {
  registrada: "Registrada",
  em_analise: "Em análise",
  planejada: "Planejada",
  em_desenvolvimento: "Em desenvolvimento",
  entregue: "Entregue",
  em_producao: "Em produção",
  nao_sera_feita: "Não será feita",
};

/** A cor de cada Etapa, na mesma escala das outras marcas da tela. */
export const ETAPA_CLASSE: Record<EtapaDemanda, string> = {
  registrada: "bg-slate-100 text-slate-500",
  em_analise: "bg-slate-100 text-slate-600",
  planejada: "bg-sky-50 text-sky-700",
  em_desenvolvimento: "bg-amber-50 text-amber-700",
  entregue: "bg-emerald-50 text-emerald-700",
  em_producao: "bg-emerald-100 text-emerald-800",
  nao_sera_feita: "bg-slate-100 text-slate-500",
};

/**
 * Se a Demanda tem selo de Etapa.
 *
 * "Registrada" é a AUSÊNCIA de Vínculo (ADR 0054, decisão 9): a conversa que
 * ainda não virou card. A lista a escreve por extenso; o selo da conversa
 * aberta só existe com Vínculo.
 *
 * Etapa que o backend não mandou (versão anterior no ar) também não tem selo:
 * inventar um seria pior do que não mostrar nada.
 */
export function temSelo(demanda: Demanda): boolean {
  const etapa = demanda.etapa;
  if (!etapa || etapa === "registrada") return false;
  return etapa in ETAPA_ROTULO;
}

/**
 * O texto do selo: a Etapa e, quando há partes, "X de Y partes". Em produção
 * diz desde qual versão (issue #1065), que é o que o diretor procura.
 *
 * Sem total não há fração: "0 de 0 partes" é uma barra vazia onde não existe
 * barra, e a tela precisa distinguir a issue simples do PRD que ainda não
 * entregou nada.
 */
export function textoDoSelo(demanda: Demanda): string {
  const rotulo =
    demanda.etapa === "em_producao" && demanda.versao
      ? `${ETAPA_ROTULO.em_producao} desde ${demanda.versao}`
      : (ETAPA_ROTULO[demanda.etapa as EtapaDemanda] ?? "");
  const total = demanda.partes_total;
  const entregues = demanda.partes_entregues;
  if (typeof total === "number" && total > 0 && typeof entregues === "number") {
    return `${rotulo} · ${entregues} de ${total} partes`;
  }
  return rotulo;
}

/** Um pedaço de uma linha do "O que muda": negrito ou texto comum. */
export type PedacoForte = { texto: string; forte: boolean };

/** Um parágrafo ou uma lista do "O que muda", já quebrado em linhas. */
export type BlocoDoTextoSimples = { lista: boolean; linhas: PedacoForte[][] };

// O que abre um item de lista no bloco "Para o diretor": hífen ou asterisco.
const MARCADOR_DE_ITEM = /^[-*]\s+/;

/**
 * Uma linha quebrada nos pedaços em negrito.
 *
 * Índice ímpar do `split` é o que estava entre `**`, porque o grupo capturado
 * do separador entra na lista entre os pedaços comuns.
 */
export function pedacosFortes(linha: string): PedacoForte[] {
  return linha
    .split(/\*\*(.+?)\*\*/g)
    .map((texto, i) => ({ texto, forte: i % 2 === 1 }))
    .filter((pedaco) => pedaco.texto !== "");
}

/**
 * O texto do "O que muda" em blocos, para a tela desenhar (issue #676).
 *
 * Markdown SIMPLES de propósito: negrito e lista, e nada mais. O texto vem de
 * fora do app (o corpo de uma issue) e é desenhado como texto, nunca como HTML:
 * link e tag ficam de fora porque nada que venha do GitHub deve virar elemento
 * clicável na tela do diretor (ADR 0054, decisão 7).
 *
 * Linha em branco fecha o bloco: sem isso, dois parágrafos virariam um só e a
 * lista grudaria no texto que vem antes dela.
 */
export function blocosDoTextoSimples(texto: string | null | undefined): BlocoDoTextoSimples[] {
  const blocos: BlocoDoTextoSimples[] = [];
  let atual: BlocoDoTextoSimples | null = null;

  for (const bruta of String(texto ?? "").split("\n")) {
    const linha = bruta.trim();
    if (!linha) {
      atual = null;
      continue;
    }
    const lista = MARCADOR_DE_ITEM.test(linha);
    if (!atual || atual.lista !== lista) {
      atual = { lista, linhas: [] };
      blocos.push(atual);
    }
    atual.linhas.push(pedacosFortes(lista ? linha.replace(MARCADOR_DE_ITEM, "") : linha));
  }
  return blocos;
}

/** O bloco "Para o diretor" em seções: a frase e os tópicos (issue #1552). */
export type DocumentoDoBloco = { frase: PedacoForte[][]; topicos: PedacoForte[][] };

// O rótulo em negrito que abre uma linha do bloco no formato fixo da ADR 0084:
// "**O que muda:**" antes da frase, "**O que você precisa saber:**" antes dos
// tópicos. É moldura, e não conteúdo: o documento já tem o título da seção.
const ROTULO_DO_BLOCO = /:\s*$/;

/**
 * O bloco "Para o diretor" lido como Documento do card (issue #1552, ADR 0084,
 * decisão 7): as linhas de texto viram Em uma frase, os itens de lista viram
 * O que muda. O texto não é reescrito, só separado: o bloco fora do formato
 * fixo (o de antes da ADR) vira a frase inteira, sem perder nada.
 *
 * Nulo quando não há texto: a tela diz "Descrição em preparação".
 */
export function documentoDoBloco(texto: string | null | undefined): DocumentoDoBloco | null {
  const frase: PedacoForte[][] = [];
  const topicos: PedacoForte[][] = [];
  for (const bloco of blocosDoTextoSimples(texto)) {
    if (bloco.lista) {
      topicos.push(...bloco.linhas);
      continue;
    }
    for (const linha of bloco.linhas) {
      const [primeiro, ...resto] = linha;
      if (!primeiro?.forte || !ROTULO_DO_BLOCO.test(primeiro.texto)) {
        frase.push(linha);
        continue;
      }
      const sobra = resto
        .map((pedaco, i) => (i === 0 ? { ...pedaco, texto: pedaco.texto.trimStart() } : pedaco))
        .filter((pedaco) => pedaco.texto !== "");
      if (sobra.length > 0) frase.push(sobra);
    }
  }
  return frase.length > 0 || topicos.length > 0 ? { frase, topicos } : null;
}

const DIA_NO_HOSPITAL = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/**
 * Um instante do backend (`2026-11-06T18:00:00Z`) como o dia do hospital,
 * "06/11/2026". Nulo quando não há data legível: a linha some, em vez de
 * mostrar "Invalid Date".
 */
export function diaDoHospital(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const instante = new Date(iso);
  return Number.isNaN(instante.getTime()) ? null : DIA_NO_HOSPITAL.format(instante);
}

/** Os cinco estados da Demanda, na ordem do fluxo. */
