/**
 * O vocabulário do Assistente de Tecnologia (issue #727, PRD #726, ADR 0056).
 *
 * Só o que é puro: o shape do Rascunho, o Roteiro por Tipo, o preenchimento
 * dos rótulos que ficaram em branco na hora de criar, e a guarda do
 * armazenamento de sessão. O que fala com a rede mora nos componentes.
 */

import { BASE_TECNOLOGIA, Demanda, PrioridadeDemanda, ProdutoDaEscolha, TipoDemanda } from "./demandas";

export const ROTA_ASSISTENTE = "/admin/tecnologia/nova";
export const URL_DO_CHAT = `${BASE_TECNOLOGIA}/assistente/chat`;

/**
 * O Rascunho da Demanda: os campos do formulário de hoje, mais o prazo.
 *
 * `tipo` e `produto_id` começam nulos de propósito. Um Tipo de partida seria
 * um palpite da tela, e o assistente é instruído a preservar o que já vem
 * preenchido: a Demanda nasceria com o Tipo errado sem ninguém notar.
 */
export type RascunhoDaDemanda = {
  titulo: string;
  tipo: TipoDemanda | null;
  produto_id: string | null;
  prioridade: PrioridadeDemanda;
  prazo: string | null;
  descricao: string;
};

export const RASCUNHO_VAZIO: RascunhoDaDemanda = {
  titulo: "",
  tipo: null,
  produto_id: null,
  prioridade: "normal",
  prazo: null,
  descricao: "",
};

export type MensagemDoChat = { role: "user" | "assistant"; content: string };

export type RespostaDoChat = {
  reply: string;
  rascunho: RascunhoDaDemanda;
  /** Sempre `null` por enquanto: o aviso de Demanda parecida é a fatia seguinte. */
  demanda_parecida: unknown | null;
};

/**
 * A primeira fala, escrita na tela e não pedida ao modelo: ela precisa estar
 * lá antes de qualquer ida à rede, senão quem abre a página encara uma caixa
 * vazia sem saber o que fazer.
 */
export const PRIMEIRA_MENSAGEM =
  "Oi. Me conta o que você precisa, do jeito que vier: o que aconteceu, o que você queria, " +
  "ou a dúvida que ficou. Eu vou montando o pedido aqui do lado e você confere antes de criar.";

/**
 * O aviso fixo sob a caixa de mensagem.
 *
 * Mesma promessa do "Copiar para IA": quem escreve tem que saber que o texto
 * vai para uma inteligência artificial antes de escrever, não depois.
 */
export const AVISO_DE_IA =
  "O que você escreve aqui é lido por uma inteligência artificial, como nas atas. Evite dados de paciente.";

/**
 * Os dois tetos do corpo do chat, iguais aos do backend.
 *
 * Eles moram aqui porque o backend recusa com 422 do pydantic, cujo `detail`
 * vem em LISTA e chegaria à tela como JSON cru dentro do alerta vermelho. E
 * são alcançáveis pelo canal de verdade: vinte idas e voltas de conversa
 * normal passam das quarenta mensagens. Um teto sem par na tela é um beco.
 */
export const LIMITE_DE_MENSAGENS = 40;
export const LIMITE_DA_MENSAGEM = 5000;

/**
 * Os tetos dos dois campos de texto do Rascunho, iguais aos do backend.
 *
 * O rascunho volta inteiro no corpo de cada turno e entra no prompt: sem teto,
 * os dois tetos acima protegeriam só a conversa, e o campo vizinho passaria
 * megabytes ao provedor a dez chamadas por minuto. O título é o mesmo 200 do
 * formulário de sempre.
 */
export const LIMITE_DO_TITULO = 200;
export const LIMITE_DA_DESCRICAO = 5000;

export const CONVERSA_NO_TETO =
  "Esta conversa chegou no limite. Crie a Demanda com o que já está no rascunho, ou descarte e comece outra.";

/**
 * A frase do teto de taxa.
 *
 * Ela é escrita aqui, e não lida da resposta, porque o `slowapi` devolve
 * `{"error": "Rate limit exceeded: ..."}` (sem `detail`, e em inglês), e o
 * leitor desta tela lê português e precisa saber o que fazer: esperar.
 */
export const MUITAS_MENSAGENS = "Muitas mensagens em pouco tempo. Espere um minuto e mande de novo.";

/**
 * A frase de quando o servidor respondeu e o corpo não dá para ler.
 *
 * É causa diferente da rede fora, e o código distingue as duas: aqui a resposta
 * chegou (uma conexão que caiu depois dos cabeçalhos, um proxy devolvendo HTML),
 * então dizer "verifique a conexão" mandaria olhar o lugar errado. A frase diz o
 * que a tela sabe e onde o texto ficou.
 */
export const RESPOSTA_ILEGIVEL =
  "O servidor respondeu algo que a tela não conseguiu ler. Sua mensagem continua na caixa: mande de novo.";

/**
 * A FRONTEIRA: ninguém nesta tela lê campo de corpo HTTP sem passar por aqui.
 *
 * Ela existe porque três rodadas de revisão mostraram que fechar o exemplo não
 * fecha a classe: primeiro a rede ficou protegida e o corpo não, depois o corpo
 * do chat ficou protegido e o da criação não. O problema não era esquecer um
 * caminho, era não ter um lugar por onde todos passassem.
 *
 * Duas coisas que ela garante, e que `as` não garante:
 *
 * - **nunca levanta.** Corpo que não dá para ler e corpo que dá para ler mas
 *   não serve saem pela MESMA porta (`null`), porque para quem está olhando são
 *   o mesmo caso: a resposta chegou e não dá para usar;
 * - **o que sai daqui foi conferido campo a campo** contra o que o consumidor
 *   consome. `as` é promessa não verificada; `valida` é a verificação.
 */
export async function corpoValidado<T>(
  resposta: Response,
  valida: (corpo: unknown) => corpo is T,
): Promise<T | null> {
  let corpo: unknown;
  try {
    corpo = await resposta.json();
  } catch {
    return null;
  }
  return valida(corpo) ? corpo : null;
}

/**
 * A resposta do chat serve para a tela usar?
 *
 * Ela existe para a fronteira "nunca levanta" valer para o CORPO, e não só para
 * a rede. Sem ela, um 200 que o `JSON.parse` aceita mas que não é
 * `{reply, rascunho}` passava direto e quebrava lá dentro, onde já não há quem
 * pegue: corpo `null` levantava no meio do encerramento e congelava o painel, e
 * corpo `{}` chegava ao render e apagava a página em `rascunho.titulo.trim()`.
 *
 * O que ela cobra é exatamente o que o painel consome, campo a campo. Corpo que
 * não passa não vira rascunho meio preenchido: vira desfecho de erro, e o
 * rascunho anterior, que é o que tem valor na tela, sobrevive.
 */
export function respostaDoChatValida(corpo: unknown): corpo is RespostaDoChat {
  if (typeof corpo !== "object" || corpo === null) return false;
  const resposta = corpo as Record<string, unknown>;
  if (typeof resposta.reply !== "string") return false;
  const rascunho = resposta.rascunho;
  if (typeof rascunho !== "object" || rascunho === null) return false;
  const campos = rascunho as Record<string, unknown>;
  return (
    typeof campos.titulo === "string" &&
    typeof campos.descricao === "string" &&
    typeof campos.prioridade === "string" &&
    (campos.tipo === null || typeof campos.tipo === "string") &&
    (campos.produto_id === null || typeof campos.produto_id === "string") &&
    (campos.prazo === null || typeof campos.prazo === "string")
  );
}

/** O que a tela consome da Demanda recém-criada. */
export type DemandaCriada = Demanda & { aviso_por_email?: unknown };

/**
 * A resposta da criação serve?
 *
 * O `id` é o que a tela consome de verdade: é com ele que ela monta o link do
 * card. Sem `id` não há para onde ir, e chamar `onCriada` com ele faltando
 * levaria a `/admin/tecnologia?demanda=undefined`.
 */
export function demandaCriadaValida(corpo: unknown): corpo is DemandaCriada {
  if (typeof corpo !== "object" || corpo === null) return false;
  return typeof (corpo as Record<string, unknown>).id === "string";
}

/**
 * A lista de Produtos serve?
 *
 * Sem esta peneira, um corpo que não é lista chegava ao `setProdutos` sem
 * reclamar e quebrava no RENDER seguinte, em `produtos.filter`: a página
 * inteira sumia, e o `catch` do `fetch` não via nada, porque a falha acontecia
 * fora da promessa.
 */
export function listaDeProdutosValida(corpo: unknown): corpo is ProdutoDaEscolha[] {
  return (
    Array.isArray(corpo) &&
    corpo.every(
      (p) =>
        typeof p === "object" &&
        p !== null &&
        typeof (p as Record<string, unknown>).id === "string" &&
        typeof (p as Record<string, unknown>).nome === "string",
    )
  );
}

/**
 * A frase de quando a Demanda NASCEU e a resposta não deu para ler.
 *
 * Ela é própria, e não a do chat, porque aqui o desfecho foi BOM: o servidor
 * respondeu 201, a Demanda está no Quadro com id e dono avisado. Dizer "mande
 * de novo" seria empurrar para o pior desfecho possível, porque a criação não
 * tem chave de idempotência e o segundo clique nasceria uma Demanda repetida,
 * com dois donos notificados. Por isso o botão fecha junto com esta frase, e a
 * saída oferecida é o Quadro.
 */
export const CRIADA_SEM_CONFIRMACAO =
  "A Demanda foi criada, mas a resposta do servidor não deu para ler, então não dá para abri-la daqui. " +
  "Não crie de novo: confira no Quadro.";

/** Os rótulos fixos de cada Tipo. Decisão não tem roteiro: é texto corrido. */
export const ROTEIRO_POR_TIPO: Record<TipoDemanda, string[]> = {
  defeito: ["Onde", "O que aconteceu", "O que esperava", "Quando", "Como repetir"],
  novo: ["O que precisa", "Por quê", "Quem usa", "Hoje é assim"],
  ajuste: ["O que precisa", "Por quê", "Quem usa", "Hoje é assim"],
  informacao: ["Pergunta", "Contexto", "O que já sei"],
  consultoria: ["Pergunta", "Contexto", "O que já sei"],
  terceiro: ["Quem de fora", "O que falta dele"],
  decisao: [],
};

export const NAO_INFORMADO = "não informado";

/**
 * O Tipo que vai no payload quando ninguém escolheu nenhum.
 *
 * "Criar Demanda" libera com título e Produto, e a rota de criação exige um
 * Tipo: alguém que digitou o título à mão e clicou sem conversar precisa de um
 * valor. `informacao` é o mais honesto dos sete para "alguém do hospital está
 * contando algo à Vitta e ela que classifique".
 */
export const TIPO_QUANDO_NAO_ESCOLHIDO: TipoDemanda = "informacao";

/**
 * A descrição como ela vai para a Demanda.
 *
 * Enquanto a conversa corre, rótulo sem resposta não aparece (o painel ficaria
 * cheio de campo vazio). Na hora de criar é o contrário: o rótulo que ficou em
 * branco sai escrito como "não informado", porque quem vai ler do outro lado
 * precisa saber a diferença entre "não perguntaram" e "não respondeu".
 *
 * A ordem é a do roteiro, sempre a mesma, que é a razão de o roteiro existir.
 * O que a pessoa escreveu fora dos rótulos é preservado, antes deles.
 */
export function descricaoAoCriar(tipo: TipoDemanda, descricao: string): string {
  const rotulos = ROTEIRO_POR_TIPO[tipo];
  const texto = descricao.trim();
  if (rotulos.length === 0) return texto;

  const blocos = new Map<string, string[]>();
  const soltas: string[] = [];
  let atual: string[] | null = null;
  for (const linha of texto ? texto.split("\n") : []) {
    const rotulo = rotulos.find((r) => linha.trimStart().startsWith(`${r}:`));
    if (rotulo) {
      atual = [linha.trimStart()];
      blocos.set(rotulo, atual);
    } else if (atual) {
      atual.push(linha);
    } else {
      soltas.push(linha);
    }
  }

  const corpo = rotulos.map((r) => (blocos.get(r) ?? [`${r}: ${NAO_INFORMADO}`]).join("\n"));
  return [...soltas, ...corpo].join("\n").trim();
}

/** "Criar Demanda" libera com título e Produto, e nada mais (ADR 0056, decisão 1). */
export function podeCriar(rascunho: RascunhoDaDemanda): boolean {
  return rascunho.titulo.trim().length > 0 && !!rascunho.produto_id;
}

// ─── Armazenamento de sessão ────────────────────────────────────────────────

/**
 * A conversa e o rascunho vivem na ABA do navegador, nunca no servidor
 * (ADR 0056, decisão 4). É `sessionStorage`, e não `localStorage`, porque o
 * que se quer é sobreviver a um recarregar acidental, não reaparecer amanhã
 * num pedido que a pessoa já esqueceu.
 */
export const CHAVE_DA_SESSAO = "tecnologia:assistente";

export type EstadoGuardado = { messages: MensagemDoChat[]; rascunho: RascunhoDaDemanda };

export function lerDaSessao(): EstadoGuardado | null {
  // Navegador com storage bloqueado levanta no próprio acesso, e uma tela que
  // não abre é pior do que uma tela que esqueceu o rascunho.
  try {
    const bruto = window.sessionStorage.getItem(CHAVE_DA_SESSAO);
    if (!bruto) return null;
    const lido = JSON.parse(bruto) as Partial<EstadoGuardado>;
    if (!Array.isArray(lido.messages) || typeof lido.rascunho !== "object" || lido.rascunho === null) return null;
    return { messages: lido.messages, rascunho: { ...RASCUNHO_VAZIO, ...lido.rascunho } };
  } catch {
    return null;
  }
}

export function gravarNaSessao(estado: EstadoGuardado): void {
  try {
    window.sessionStorage.setItem(CHAVE_DA_SESSAO, JSON.stringify(estado));
  } catch {
    // Sem storage a conversa segue normalmente: ela só não sobrevive ao F5.
  }
}

export function limparASessao(): void {
  try {
    window.sessionStorage.removeItem(CHAVE_DA_SESSAO);
  } catch {
    // Nada a fazer: o que não foi gravado não precisa ser apagado.
  }
}
