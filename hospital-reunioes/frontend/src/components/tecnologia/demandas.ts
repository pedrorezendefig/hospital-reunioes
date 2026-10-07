/**
 * O vocabulário da Demanda, do lado da tela (issue #637, PRD #634, ADR 0050).
 *
 * Só dado e função pura: rótulos, a máquina de estados que desenha os botões
 * de mover, e as duas contas do card (idade e atraso). Quem decide de verdade
 * é o backend, que responde 422 na transição proibida; esta tabela existe para
 * a tela não OFERECER um caminho que ela sabe que não existe.
 */

import type { AnexoDaDemanda } from "./anexos";

/** O prefixo da API da aba. */
export const BASE_TECNOLOGIA = "/api/admin/tecnologia";

/** A mesma frase em todo caminho de rede da aba, carregar e salvar. */
export const FALHA_DE_CONEXAO = "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";

/**
 * O motivo da recusa, dito pelo servidor.
 *
 * A tela não inventa causa: quem sabe por que recusou (Produto sem dono,
 * transição que não existe, responsável sem acesso) é a API, e é a frase dela
 * que a pessoa lê.
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
 * De quanto em quanto tempo o Quadro se pede de novo (issue #642).
 *
 * Trinta segundos é o número da PRD #634 (história 40) e da decisão 9 do
 * ADR 0050: quem está do outro lado responde e o outro vê sem apertar F5.
 */
export const INTERVALO_DE_ATUALIZACAO_MS = 30_000;

/**
 * O aviso de "isto valeu, mas o e-mail não saiu", quando o servidor manda um
 * (issue #642).
 *
 * A frase vem MONTADA do backend: quem sabe quantos avisos deviam sair, e se
 * saíram, é quem tentou mandá-los. Escrever a frase aqui seria repetir a regra
 * de quem recebe cada gatilho, e as duas versões divergiriam.
 *
 * Resposta sem corpo JSON, ou de um backend uma versão atrás (sem o campo), não
 * é aviso nenhum: `null` deixa a tela como estava, em vez de inventar alarme.
 */
export async function avisoPorEmail(resposta: Response): Promise<string | null> {
  try {
    const corpo = await resposta.json();
    return typeof corpo?.aviso_por_email === "string" ? corpo.aviso_por_email : null;
  } catch {
    return null;
  }
}

/** O Produto como as escolhas da Demanda o veem. */
export type ProdutoDaEscolha = { id: string; nome: string; ativo: boolean };

/** Quem tem acesso à aba: dono de Produto, responsável e, adiante, @menção. */
export type PessoaDaAba = { id: string; nome_completo: string };

export type EstadoDemanda = "nova" | "em_andamento" | "aguardando" | "concluida" | "cancelada";

export type TipoDemanda =
  | "decisao"
  | "informacao"
  | "terceiro"
  | "ajuste"
  | "novo"
  | "defeito"
  | "consultoria";

export type PrioridadeDemanda = "baixa" | "normal" | "alta";

export type Demanda = {
  id: string;
  titulo: string;
  descricao: string | null;
  tipo: TipoDemanda;
  produto_id: string;
  produto_nome: string | null;
  estado: EstadoDemanda;
  responsavel_id: string | null;
  responsavel_nome: string | null;
  autor_id: string | null;
  prioridade: PrioridadeDemanda;
  prazo: string | null;
  criado_em: string | null;
  concluida_em: string | null;
  cancelada_em: string | null;
  /**
   * Onde o desenvolvimento está, em palavras (issue #674, ADR 0054).
   *
   * Vem para TODO MUNDO, inclusive para quem não é da Vitta: é o selo que o
   * diretor lê. Backend uma versão atrás não manda o campo, e aí o `??` do
   * `temSelo` trata como "Registrada", que é a ausência de selo.
   */
  etapa?: EtapaDemanda;
  partes_entregues?: number | null;
  partes_total?: number | null;
  github_sincronizado_em?: string | null;
  /**
   * Número e endereço da issue: só para quem tem login no GitHub.
   *
   * O backend OMITE o objeto inteiro para quem não tem (ADR 0054, decisão 9),
   * então aqui ele é indistinguível de "não há Vínculo". É de propósito: o
   * diretor não vê número nem link em nenhum dos dois casos.
   */
  vinculo?: VinculoDaDemanda | null;
  /**
   * O que a entrega muda para quem pediu (issue #676, ADR 0054, decisão 7).
   *
   * Vem do bloco "Para o diretor" da issue e NUNCA é digitado no app. Nulo é
   * "a Vitta ainda não escreveu", e a tela o traduz numa frase; nulo não é o
   * corpo técnico da issue, que não sai do GitHub.
   */
  o_que_muda?: string | null;
  partes?: ParteDaEntrega[];
};

/** O que só quem é da Vitta vê do Vínculo. */
export type VinculoDaDemanda = { numero: number; url: string | null };

/**
 * Uma parte da entrega como o card a mostra.
 *
 * O `numero` é interno e vem NULO para quem não tem login no GitHub (ADR 0054,
 * decisão 9). A tela não o desenha em lugar nenhum: ele está aqui porque a
 * resposta o traz para quem é da Vitta, e não porque alguma tela o mostre.
 */
export type ParteDaEntrega = {
  numero: number | null;
  o_que_muda: string | null;
  situacao: EtapaDemanda | null;
};

/**
 * Quem está olhando a aba, do ponto de vista do Vínculo (issue #674).
 *
 * As duas respostas vêm do backend porque a tela não tem como dá-las: ela não
 * sabe qual participante é o usuário logado (o `useAuth` carrega o id do
 * Supabase Auth, e não o `participantes.id`), nem se o token do GitHub está
 * configurado no ambiente do servidor.
 */
export type EuNaAba = {
  id: string;
  nome_completo: string | null;
  tem_github_login: boolean;
  integracao_configurada: boolean;
};

/** O "eu" de antes da resposta: sem controle nenhum à vista. */
export const EU_DESCONHECIDO: EuNaAba = {
  id: "",
  nome_completo: null,
  tem_github_login: false,
  integracao_configurada: false,
};

/**
 * As sete Etapas, espelho da tupla do backend (`app/services/tecnologia_vinculo.py`).
 *
 * "Em produção" entrou pela ADR 0069 (issue #1057): a subida que levou a
 * entrega ao ar. O Painel a mostra no bloco Entregas, com a versão (#1059).
 */
export type EtapaDemanda =
  | "registrada"
  | "em_analise"
  | "planejada"
  | "em_desenvolvimento"
  | "entregue"
  | "em_producao"
  | "nao_sera_feita";

export const ETAPAS: EtapaDemanda[] = [
  "registrada",
  "em_analise",
  "planejada",
  "em_desenvolvimento",
  "entregue",
  "em_producao",
  "nao_sera_feita",
];

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

/** A cor de cada Etapa, na mesma escala das outras marcas do card. */
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
 * Se o card desenha selo.
 *
 * "Registrada" é a AUSÊNCIA de Vínculo, e a ausência de selo é como ela
 * aparece (ADR 0054, decisão 9): um selo cinza dizendo "Registrada" em toda
 * Demanda de Decisão e de Informação viraria ruído em quase todo o Quadro.
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
 * Se o que se escreve na Conversa sai do app (issue #680, ADR 0054, decisão 4).
 *
 * Toda resposta numa Demanda com Vínculo é publicada como comentário na issue,
 * num repositório público. Quem não tem login no GitHub não vê o Vínculo
 * (decisão 9), então o único sinal de que ele existe é o mesmo do selo: a
 * Etapa saiu de "Registrada". É por isso que a caixa de resposta avisa, e
 * avisa sem número, link nem label.
 */
export function conversaPublicada(demanda: Demanda): boolean {
  return temSelo(demanda);
}

/**
 * O texto do selo: a Etapa e, quando há partes, "X de Y partes".
 *
 * Sem total não há fração: "0 de 0 partes" é uma barra vazia onde não existe
 * barra, e o card precisa distinguir a issue simples do PRD que ainda não
 * entregou nada.
 */
export function textoDoSelo(demanda: Demanda): string {
  const rotulo = ETAPA_ROTULO[demanda.etapa as EtapaDemanda] ?? "";
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

export type LinhaDaConversa = {
  id: string;
  autor_id: string | null;
  autor_nome: string | null;
  linha: string;
  texto: string;
  mencoes: string[];
  movimento_campo: string | null;
  criado_em: string | null;
  editado_em: string | null;
  /**
   * Até quando ESTA pessoa pode corrigir ESTA linha, dito pelo backend.
   *
   * A tela não sabe qual participante é o usuário logado: o `useAuth` carrega
   * o id do Supabase Auth, e não o `participantes.id` que assina a linha. Vem
   * o instante, e não um "pode: sim", porque o modal fica aberto enquanto os
   * 10 minutos correm.
   */
  editavel_ate: string | null;
  /** A imagem que a resposta levou (issue #1062), com a URL assinada de vida curta. */
  imagem?: AnexoDaDemanda | null;
};

/** Os cinco estados da Demanda, na ordem do fluxo. */
export const ESTADOS: EstadoDemanda[] = ["nova", "em_andamento", "aguardando", "concluida", "cancelada"];

export const ESTADO_ROTULO: Record<EstadoDemanda, string> = {
  nova: "Nova",
  em_andamento: "Em andamento",
  aguardando: "Aguardando",
  concluida: "Concluída",
  cancelada: "Cancelada",
};

/**
 * As três raias do Quadro, na ordem (issue #1058, PRD #1056).
 *
 * Concluída e Cancelada continuam sendo estados no banco, mas deixaram de ser
 * coluna: encerrar é uma ação no card aberto, e a Demanda encerrada sai do
 * Quadro na hora. O que já fechou mora no Histórico.
 */
export const RAIAS: EstadoDemanda[] = ["nova", "em_andamento", "aguardando"];

/** Espelho da tabela do backend (`app/services/tecnologia.py`). */
export const TRANSICOES: Record<EstadoDemanda, EstadoDemanda[]> = {
  nova: ["em_andamento", "aguardando", "concluida", "cancelada"],
  em_andamento: ["aguardando", "concluida", "cancelada"],
  aguardando: ["em_andamento", "concluida", "cancelada"],
  concluida: ["em_andamento"],
  cancelada: ["em_andamento"],
};

export function destinosDe(estado: EstadoDemanda): EstadoDemanda[] {
  return TRANSICOES[estado] ?? [];
}

export const TIPOS: TipoDemanda[] = [
  "decisao",
  "informacao",
  "terceiro",
  "ajuste",
  "novo",
  "defeito",
  "consultoria",
];

export const TIPO_ROTULO: Record<TipoDemanda, string> = {
  decisao: "Decisão",
  informacao: "Informação",
  terceiro: "Terceiro",
  ajuste: "Ajuste",
  novo: "Novo",
  defeito: "Defeito",
  consultoria: "Consultoria",
};

export const PRIORIDADES: PrioridadeDemanda[] = ["baixa", "normal", "alta"];

export const PRIORIDADE_ROTULO: Record<PrioridadeDemanda, string> = {
  baixa: "Baixa",
  normal: "Normal",
  alta: "Alta",
};

/** A partir daqui a idade vira vermelha (ADR 0050, decisão 5). */
export const IDADE_VERMELHA_A_PARTIR_DE = 14;

/** Quantos dias inteiros a Demanda tem. Data futura conta como zero. */
export function idadeEmDias(criadoEm: string | null, agora: Date = new Date()): number {
  if (!criadoEm) return 0;
  const nascimento = new Date(criadoEm);
  if (Number.isNaN(nascimento.getTime())) return 0;
  const dias = Math.floor((agora.getTime() - nascimento.getTime()) / 86_400_000);
  return dias > 0 ? dias : 0;
}

export function textoDaIdade(dias: number): string {
  if (dias <= 0) return "hoje";
  if (dias === 1) return "há 1 dia";
  return `há ${dias} dias`;
}

/**
 * Prazo vencido é atraso; sem prazo o card só envelhece.
 *
 * A comparação é de DIA, não de instante: o prazo é uma data (`2026-10-01`), e
 * medir por hora marcaria como atrasado, às 9 da manhã, um prazo que vence
 * hoje. O meio-dia é o mesmo truque do painel de Pendências, que tira a
 * diferença de fuso do caminho.
 */
export function estaAtrasado(prazo: string | null, agora: Date = new Date()): boolean {
  if (!prazo) return false;
  const vencimento = new Date(`${prazo}T12:00:00`);
  if (Number.isNaN(vencimento.getTime())) return false;
  const hoje = new Date(agora);
  hoje.setHours(12, 0, 0, 0);
  return vencimento.getTime() < hoje.getTime();
}

/** A data do prazo como a gente lê. */
export function prazoLegivel(prazo: string): string {
  return new Date(`${prazo}T12:00:00`).toLocaleDateString("pt-BR");
}

/** Data e hora da linha da Conversa. */
export function momentoLegivel(quando: string | null): string {
  if (!quando) return "";
  const d = new Date(quando);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/**
 * A janela de correção, do lado da tela (issue #638).
 *
 * Quem recusa de verdade é o backend, que responde 422 depois dos 10 minutos.
 * Esta conta existe para a tela não oferecer um clique que já se sabe recusado.
 *
 * A conta roda a cada render, e não num relógio próprio: um modal aberto e
 * parado desde antes do prazo ainda mostra o botão, e quem clicar lê a recusa
 * honesta do backend. Um `setInterval` só para apagar um botão custaria mais do
 * que resolve.
 */
export function podeCorrigirAgora(editavelAte: string | null, agora: Date = new Date()): boolean {
  if (!editavelAte) return false;
  const limite = new Date(editavelAte);
  if (Number.isNaN(limite.getTime())) return false;
  return limite.getTime() >= agora.getTime();
}

/**
 * O que a pessoa digitou depois do último @, ou `null` quando não há menção
 * em aberto.
 *
 * O termo vai até o fim do texto porque nome tem espaço ("Sócia Vitta"), e
 * parar no primeiro espaço nunca acharia o segundo nome. Quem fecha a lista é
 * o filtro: assim que o termo deixa de ser começo de algum nome (a pessoa
 * seguiu escrevendo a frase), nenhuma opção casa e o autocomplete some.
 */
export function termoDaMencao(texto: string): string | null {
  const corte = texto.lastIndexOf("@");
  if (corte < 0) return null;
  const depois = texto.slice(corte + 1);
  // Quebra de linha fecha a menção: o @ ficou num parágrafo anterior.
  if (depois.includes("\n")) return null;
  return depois;
}

/** As pessoas cujo nome começa pelo termo digitado, sem distinguir maiúsculas. */
export function pessoasDoAutocomplete(termo: string, pessoas: PessoaDaAba[]): PessoaDaAba[] {
  const alvo = termo.toLowerCase();
  return pessoas.filter((p) => p.nome_completo.toLowerCase().startsWith(alvo));
}

/** Troca o @termo em aberto pelo nome escolhido, e deixa o cursor depois dele. */
export function aplicarMencao(texto: string, nome: string): string {
  const corte = texto.lastIndexOf("@");
  const antes = corte < 0 ? texto : texto.slice(0, corte);
  return `${antes}@${nome} `;
}

/**
 * Dos escolhidos no autocomplete, os que o texto ainda chama.
 *
 * Apagar o "@Fulano" da frase tem que tirar a menção: senão a linha continuaria
 * dizendo que chamou alguém que o texto não chama mais (e, na fatia do e-mail,
 * avisaria essa pessoa à toa).
 *
 * Quem decide é o mesmo `pedacosDoTexto` que pinta o destaque, e não um
 * `includes` por nome. Com `includes`, um nome que é começo de outro entrava de
 * carona: "@Ana Souza Lima" gravava também a "Ana Souza", e o erro era MUDO,
 * porque o destaque (que já resolvia o prefixo) marcava só o nome longo. A
 * mesma frase tem que produzir a mesma resposta nos dois lugares, senão a tela
 * e a coluna contam histórias diferentes.
 */
export function mencoesNoTexto(texto: string, escolhidas: PessoaDaAba[]): string[] {
  const chamados = new Set(
    pedacosDoTexto(
      texto,
      escolhidas.map((p) => p.nome_completo),
    )
      .filter((pedaco) => pedaco.mencao)
      // O pedaço marcado carrega o "@" na frente; o nome é o resto.
      .map((pedaco) => pedaco.texto.slice(1)),
  );
  return escolhidas.filter((p) => chamados.has(p.nome_completo)).map((p) => p.id);
}

/** Um pedaço do texto da linha: menção a destacar ou texto comum. */
export type PedacoDoTexto = { texto: string; mencao: boolean };

/**
 * O texto quebrado em pedaços, com as menções marcadas.
 *
 * É o par na tela da coluna `mencoes`: sem ele, a lista gravada pelo backend
 * não apareceria em lugar nenhum, e chamar alguém ficaria indistinguível de
 * escrever o nome dela no meio da frase.
 *
 * Os nomes são procurados do mais longo para o mais curto porque um nome pode
 * ser começo de outro: com "Ana" antes de "Ana Maria", "@Ana Maria" seria
 * marcado pela metade.
 */
export function pedacosDoTexto(texto: string, nomesMencionados: string[]): PedacoDoTexto[] {
  const alvos = [...nomesMencionados].sort((a, b) => b.length - a.length).map((nome) => `@${nome}`);
  const pedacos: PedacoDoTexto[] = [];
  let comum = "";
  let i = 0;
  while (i < texto.length) {
    const achado = alvos.find((alvo) => texto.startsWith(alvo, i));
    if (achado) {
      if (comum) {
        pedacos.push({ texto: comum, mencao: false });
        comum = "";
      }
      pedacos.push({ texto: achado, mencao: true });
      i += achado.length;
    } else {
      comum += texto[i];
      i += 1;
    }
  }
  if (comum) pedacos.push({ texto: comum, mencao: false });
  return pedacos;
}

/**
 * O endereço da Demanda, montado e lido no mesmo lugar (issue #640).
 *
 * As duas funções abaixo são os dois lados do MESMO formato: `linkDaDemanda`
 * escreve o que o botão "Copiar link" põe no clipboard, e `demandaIdDaUrl` lê o
 * que o Quadro recebe na barra de endereços. Escrever a URL à mão de um lado e
 * lê-la à mão do outro seria o jeito mais fácil de copiar um link que a própria
 * aplicação não abre.
 */
export const ROTA_TECNOLOGIA = "/admin/tecnologia";

/** A tela de Produtos, atrás da engrenagem ao lado de "Nova Demanda" (issue #1060). */
export const ROTA_PRODUTOS = `${ROTA_TECNOLOGIA}/produtos`;

/** O nome do parâmetro que carrega o id da Demanda no link. */
export const PARAM_DEMANDA = "demanda";

/** O endereço completo da Demanda, para mandar no WhatsApp. */
export function linkDaDemanda(id: string, origem: string): string {
  return `${origem}${ROTA_TECNOLOGIA}?${PARAM_DEMANDA}=${encodeURIComponent(id)}`;
}

/**
 * O id da Demanda que veio no link, ou `null` quando não veio nenhum.
 *
 * Valor vazio ou só de espaços conta como "não veio": `?demanda=` abriria uma
 * busca por uma Demanda de id vazio, e a tela acusaria "não está no Quadro"
 * para um link que não pediu Demanda alguma.
 */
export function demandaIdDaUrl(busca: string): string | null {
  const id = new URLSearchParams(busca).get(PARAM_DEMANDA)?.trim();
  return id ? id : null;
}

/**
 * O Painel (issue #1059, PRD #1056), no lugar de "Minha vez" e do Histórico da
 * issue #641.
 *
 * Cada bloco lê a Demanda com um campo a mais, resolvido pelo backend: por que
 * o card está no "Com você", a versão em que a entrega subiu, e quem fechou a
 * Demanda e quando. São campos calculados lá porque a tela não tem como
 * calculá-los: ela não sabe qual participante é o usuário logado (o `useAuth`
 * carrega o id do Supabase Auth, e não o `participantes.id`), e o desfecho
 * mora em duas colunas diferentes conforme o estado.
 */

/** A Demanda como o bloco "Com você" a lê. */
export type DemandaComVoce = Demanda & { motivo: string };

/**
 * O par na tela do `motivo` que o backend carimba.
 *
 * Sem ele, quem abre o "Com você" vê um card cujo responsável é OUTRA pessoa e
 * não descobre por que ele está ali.
 */
export const MOTIVO_ROTULO: Record<string, string> = {
  responsavel: "Você é o responsável",
  mencao: "Mencionaram você",
  // A Entrega devolveu o card para quem pediu (issue #679). O texto é o MESMO
  // do e-mail que sai na devolução: quem abre a aba depois de ler o aviso
  // precisa reconhecer o card pelo que leu.
  entregue: "Entregue, confira e conclua",
};

/**
 * A Demanda como o bloco Entregas a lê.
 *
 * A `versao` vem do backend só quando a Etapa é Em produção: a tela mostra o
 * que veio e não repete a regra.
 */
export type DemandaDaEntrega = Demanda & { versao: string | null };

/** A Demanda como o bloco Histórico a lê. */
export type DemandaDoHistorico = Demanda & {
  fechada_em: string | null;
  fechada_por_id: string | null;
  fechada_por_nome: string | null;
};

/**
 * O que a busca do Histórico procura, dito na própria tela.
 *
 * A frase mora aqui porque ela é a promessa da caixa: o backend varre o
 * título, a descrição e o texto das respostas da Conversa, e quem digita
 * precisa saber disso antes de concluir que "não tem nada sobre X".
 */
export const O_QUE_A_BUSCA_PROCURA = "Busque por título, descrição ou texto da Conversa";

/** Quando o carimbo do desfecho não veio. */
export const SEM_REGISTRO_DE_QUANDO = "sem registro de quando";
export const SEM_REGISTRO_DE_QUEM = "sem registro de quem";

/**
 * A linha de desfecho do Histórico: o que aconteceu, quando e por quem.
 *
 * Quando falta um carimbo, a frase DIZ que falta, em vez de calar: uma linha
 * que mostrasse só "Concluída" faria a data ausente parecer escolha de layout,
 * e o critério da issue é justamente mostrar quando e quem.
 */
export function textoDoDesfecho(demanda: DemandaDoHistorico): string {
  const rotulo = ESTADO_ROTULO[demanda.estado] ?? demanda.estado;
  const quando = momentoLegivel(demanda.fechada_em);
  return [
    rotulo,
    quando ? `em ${quando}` : `(${SEM_REGISTRO_DE_QUANDO})`,
    demanda.fechada_por_nome ? `por ${demanda.fechada_por_nome}` : `(${SEM_REGISTRO_DE_QUEM})`,
  ].join(" ");
}

/**
 * A busca do Histórico.
 *
 * Termo só com espaços não vai: mandar `busca=%20` faria a API procurar um
 * espaço, e a tela diria "nada encontrado" para quem não buscou nada.
 */
export function queryDoHistorico(termo: string): string {
  const limpo = termo.trim();
  return limpo ? `?${new URLSearchParams({ busca: limpo })}` : "";
}

/**
 * A frase do "Com você" vazio.
 *
 * Vazio aqui é BOA NOTÍCIA, e a frase precisa dizer isso: "nada esperando por
 * você" não é falha de carregamento.
 */
export function fraseDoComVoceVazio(): string {
  return (
    "Nada esperando por você agora. Uma Demanda aparece aqui quando você vira o responsável dela, " +
    "ou quando alguém te menciona na Conversa e você ainda não respondeu."
  );
}

/**
 * A frase do Histórico vazio.
 *
 * Dois casos, porque são duas causas diferentes e o código as distingue: o
 * Histórico ainda não tem nada, ou a busca não achou. Uma frase só mandaria
 * mudar o termo a quem não buscou nada.
 */
export function fraseDoHistoricoVazio(termo: string): string {
  if (termo.trim()) {
    return `Nenhuma Demanda concluída ou cancelada com "${termo.trim()}" no título, na descrição ou na Conversa.`;
  }
  return "Nenhuma Demanda foi concluída ou cancelada ainda. Quando a primeira fechar, ela aparece aqui.";
}

/** O Painel inteiro, como a rota `/painel` o devolve (issue #1059). */
export type PainelDaAba = {
  numeros: NumerosDoPainel;
  com_voce: DemandaComVoce[];
  entregas: DemandaDaEntrega[];
  historico: DemandaDoHistorico[];
};

/** Os quatro números do topo. Nenhum é por pessoa (ADR 0061). */
export type NumerosDoPainel = {
  abertas: number;
  com_o_hospital: number;
  em_desenvolvimento: number;
  entregues_30_dias: number;
};

/** O rótulo de cada número, na ordem em que a faixa os mostra. */
export const ROTULO_DOS_NUMEROS: [keyof NumerosDoPainel, string][] = [
  ["abertas", "Abertas"],
  ["com_o_hospital", "Com o hospital"],
  ["em_desenvolvimento", "Em desenvolvimento"],
  ["entregues_30_dias", "Entregues em 30 dias"],
];

/** A frase do bloco Entregas vazio: nada em desenvolvimento não é falha. */
export function fraseDasEntregasVazias(): string {
  return "Nenhuma Demanda aberta está com a Vitta em desenvolvimento agora.";
}

/** As duas abas da Tecnologia (issue #1059). */
export type AbaDaTecnologia = "quadro" | "painel";

/**
 * Até onde a tela conta como celular: abaixo do `md` do Tailwind, o mesmo
 * ponto em que o Quadro deixa de ter três colunas lado a lado.
 */
export const CONSULTA_DO_CELULAR = "(max-width: 767px)";

/**
 * A aba com que a Tecnologia abre (issue #1059).
 *
 * No celular é o Painel: três raias empilhadas numa tela estreita são uma
 * rolagem longa, e quem abre pelo telefone quer saber o que espera por ele.
 *
 * O link de uma Demanda (`?demanda=`) abre sempre o Quadro, inclusive no
 * celular: é o Quadro quem lê o link e abre o card, e abrir no Painel
 * deixaria o link do e-mail sem card nenhum.
 */
export function abaInicial(celular: boolean, busca: string): AbaDaTecnologia {
  if (demandaIdDaUrl(busca)) return "quadro";
  return celular ? "painel" : "quadro";
}
