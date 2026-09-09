/**
 * O vocabulário da Demanda, do lado da tela (issue #637, PRD #634, ADR 0050).
 *
 * Só dado e função pura: rótulos, a máquina de estados que desenha os botões
 * de mover, e as duas contas do card (idade e atraso). Quem decide de verdade
 * é o backend, que responde 422 na transição proibida; esta tabela existe para
 * a tela não OFERECER um caminho que ela sabe que não existe.
 */

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
};

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
};

/** A ordem das colunas no Quadro. */
export const ESTADOS: EstadoDemanda[] = ["nova", "em_andamento", "aguardando", "concluida", "cancelada"];

export const ESTADO_ROTULO: Record<EstadoDemanda, string> = {
  nova: "Nova",
  em_andamento: "Em andamento",
  aguardando: "Aguardando",
  concluida: "Concluída",
  cancelada: "Cancelada",
};

/**
 * As duas colunas que nascem recolhidas.
 *
 * O contador continua à vista: recolher é dar espaço às colunas vivas, não
 * esconder o que foi fechado (PRD #634, história 24).
 */
export const COLUNAS_RECOLHIDAS: EstadoDemanda[] = ["concluida", "cancelada"];

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
 * O que a barra de filtros do Quadro guarda (issue #639).
 *
 * Campo vazio quer dizer "todos", e nao "sem responsavel": o filtro so estreita
 * o Quadro, e a API entende ausencia do parametro como sem filtro.
 *
 * O `estado` fica de fora de proposito: ele e o eixo das colunas, e filtrar por
 * ele deixaria o Quadro com uma coluna cheia e quatro vazias, sem dizer por que.
 */
export type FiltrosDoQuadro = { tipo: string; produto_id: string; responsavel_id: string };

/** O Quadro inteiro: nenhum filtro escolhido. */
export const SEM_FILTRO: FiltrosDoQuadro = { tipo: "", produto_id: "", responsavel_id: "" };

/**
 * A busca da listagem, com os filtros que a API ja aceita.
 *
 * Sem filtro nenhum a busca sai vazia, nem o "?" sozinho, e os valores viajam
 * escapados pelo `URLSearchParams`: e a mesma URL que a tela pediria a mao, sem
 * o risco de um id com espaco quebrar a chamada.
 */
export function queryDeFiltros(filtros: FiltrosDoQuadro): string {
  const busca = new URLSearchParams();
  if (filtros.tipo) busca.set("tipo", filtros.tipo);
  if (filtros.produto_id) busca.set("produto_id", filtros.produto_id);
  if (filtros.responsavel_id) busca.set("responsavel_id", filtros.responsavel_id);
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

/**
 * Se algum filtro esta valendo.
 *
 * A tela precisa saber para AVISAR: um Quadro filtrado e calado e
 * indistinguivel de um Quadro vazio, e quem volta a aba com o filtro de ontem
 * concluiria que as Demandas sumiram.
 */
export function temFiltroAtivo(filtros: FiltrosDoQuadro): boolean {
  return Boolean(filtros.tipo || filtros.produto_id || filtros.responsavel_id);
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
