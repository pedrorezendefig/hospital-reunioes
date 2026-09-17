/**
 * O vocabulário do Assistente de Tecnologia (issue #727, PRD #726, ADR 0056).
 *
 * Só o que é puro: o shape do Rascunho, o Roteiro por Tipo, o preenchimento
 * dos rótulos que ficaram em branco na hora de criar, e a guarda do
 * armazenamento de sessão. O que fala com a rede mora nos componentes.
 */

import {
  BASE_TECNOLOGIA,
  Demanda,
  FALHA_DE_CONEXAO,
  PrioridadeDemanda,
  ProdutoDaEscolha,
  TipoDemanda,
} from "./demandas";

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

// ─── Falar e anexar (issue #729) ────────────────────────────────────────────
//
// Três entradas novas, e uma regra só: **toda entrada vira texto antes de
// chegar ao chat**. O chat nunca recebe arquivo. O que chega lá é uma mensagem
// da PESSOA, com a origem à mostra, e é essa marca que faz o backend cercar o
// material como texto de gente, e não como instrução.

/** A rota de transcrição que já existe (Reuniões, POPs, Ata Guiada). */
export const URL_DA_TRANSCRICAO = "/api/transcricao/voz";
export const URL_DA_EXTRACAO = `${BASE_TECNOLOGIA}/assistente/extrair-documento`;

/**
 * Os prefixos de origem (PRD #726, história 37).
 *
 * Eles são para a PESSOA ver o que o assistente recebeu, e são também o que o
 * backend lê para cercar o material. Mudar um destes textos sem mudar o
 * reconhecimento do outro lado tira a cerca em silêncio.
 */
export const PREFIXO_DE_AUDIO = "[áudio] ";

export function prefixoDeDocumento(nome: string): string {
  return `[documento ${nome}] `;
}

/**
 * O que a mensagem diz quando o texto não coube inteiro.
 *
 * Um documento de cinco megabytes vira muito mais que os 5000 caracteres de
 * uma mensagem, e o teto do corpo é do backend. Cortar calado mandaria meia
 * verdade ao assistente sem ninguém saber; por isso o corte é DITO, dentro da
 * própria mensagem, que é o que a pessoa lê na conversa.
 */
export const TEXTO_CORTADO = "\n(o texto é maior que isto: o resto ficou de fora)";

/** A fala que uma entrada de fora vira, com a origem na frente e dentro do teto. */
export function mensagemComOrigem(prefixo: string, texto: string): string {
  const corpo = texto.trim();
  const cabe = LIMITE_DA_MENSAGEM - prefixo.length;
  if (corpo.length <= cabe) return `${prefixo}${corpo}`;
  return `${prefixo}${corpo.slice(0, cabe - TEXTO_CORTADO.length)}${TEXTO_CORTADO}`;
}

// Os aceitos e os tetos, iguais aos do backend. Eles moram aqui para a recusa
// acontecer ANTES de subir 25 MB por um cabo de hospital e voltar 413; o
// backend continua sendo quem decide, e a frase dele aparece se ele recusar.
export const AUDIOS_ACEITOS = [".mp3", ".m4a", ".ogg", ".wav", ".webm"];
export const DOCUMENTOS_ACEITOS = [".pdf", ".docx", ".txt", ".md"];
export const DOCUMENTOS_DE_TEXTO = [".txt", ".md"];

export const LIMITE_DO_AUDIO = 25 * 1024 * 1024;
export const LIMITE_DO_DOCUMENTO_TEXTO = 5 * 1024 * 1024;
export const LIMITE_DO_DOCUMENTO_BINARIO = 15 * 1024 * 1024;

export const AUDIO_FORA_DA_LISTA =
  "Só dá para mandar áudio .mp3, .m4a, .ogg, .wav ou .webm. Converta o arquivo e tente de novo.";
export const DOCUMENTO_FORA_DA_LISTA =
  "Só dá para ler arquivo .pdf, .docx, .txt ou .md. Salve em um desses formatos e anexe de novo.";

export const AUDIO_SEM_FALA = "Não identifiquei fala nesse áudio. Tente outro arquivo ou escreva o que aconteceu.";

/** A frase de quando o servidor respondeu e o corpo do anexo não deu para ler. */
export const ANEXO_ILEGIVEL =
  "O servidor respondeu algo que a tela não conseguiu ler. Anexe de novo, ou escreva o que aconteceu.";

export type ArquivoEscolhido = { name: string; size: number };

export function extensaoDe(nome: string): string {
  const ponto = nome.lastIndexOf(".");
  return ponto < 0 ? "" : nome.slice(ponto).toLowerCase();
}

/**
 * O teto do documento depende do formato, como no extrator do backend: texto
 * puro vai a 5 MB e binário a 15 MB. Um teto único aqui discordaria do 413 de
 * lá, e a tela recusaria o que o servidor aceita (ou o contrário).
 */
export function tetoDoDocumento(nome: string): number {
  return DOCUMENTOS_DE_TEXTO.includes(extensaoDe(nome)) ? LIMITE_DO_DOCUMENTO_TEXTO : LIMITE_DO_DOCUMENTO_BINARIO;
}

function avisoDeTamanho(teto: number, saida: string): string {
  return `O arquivo passou do limite de ${Math.round(teto / (1024 * 1024))} MB. ${saida}`;
}

/** O que impede este áudio de virar mensagem, ou `null` se nada impede. */
export function avisoDoAudio(arquivo: ArquivoEscolhido): string | null {
  if (!AUDIOS_ACEITOS.includes(extensaoDe(arquivo.name))) return AUDIO_FORA_DA_LISTA;
  if (arquivo.size > LIMITE_DO_AUDIO) {
    return avisoDeTamanho(LIMITE_DO_AUDIO, "Mande um trecho menor, ou escreva o que aconteceu.");
  }
  return null;
}

/** O que impede este documento de virar mensagem, ou `null` se nada impede. */
export function avisoDoDocumento(arquivo: ArquivoEscolhido): string | null {
  if (!DOCUMENTOS_ACEITOS.includes(extensaoDe(arquivo.name))) return DOCUMENTO_FORA_DA_LISTA;
  const teto = tetoDoDocumento(arquivo.name);
  if (arquivo.size > teto) return avisoDeTamanho(teto, "Anexe um arquivo menor, ou cole aqui o trecho que importa.");
  return null;
}

/** O desfecho de uma entrada de fora: virou texto, ou virou aviso na conversa. */
export type LeituraDoAnexo<T> = { corpo: T } | { aviso: string };

export type TextoTranscrito = { texto: string };
export type DocumentoExtraido = { texto: string; filename: string };

export function transcricaoValida(corpo: unknown): corpo is TextoTranscrito {
  return typeof corpo === "object" && corpo !== null && typeof (corpo as Record<string, unknown>).texto === "string";
}

/**
 * O `filename` é cobrado porque é ELE que vira o prefixo de origem na conversa,
 * e quem o entrega já limpo (sem colchete, sem quebra de linha) é o backend:
 * usar o nome local em vez do que voltou seria pular essa limpeza.
 */
export function documentoExtraidoValido(corpo: unknown): corpo is DocumentoExtraido {
  if (!transcricaoValida(corpo)) return false;
  return typeof (corpo as Record<string, unknown>).filename === "string";
}

/**
 * O motivo da recusa de um anexo, dito pelo servidor.
 *
 * Não é o `motivoDaRecusa` das Demandas porque o verbo de lá é "salvar", e aqui
 * nada é salvo. O 413 também pode vir do proxy, sem corpo JSON nenhum, e a
 * frase de saída precisa fazer sentido nesse caso: quem lê acabou de escolher
 * um arquivo, e o que ela pode fazer é escolher outro.
 */
export async function motivoDoAnexo(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // Resposta sem corpo JSON (um 413 do proxy, um HTML de erro): sobra o status.
  }
  return `Não foi possível ler o arquivo (${resposta.status}). Tente outro arquivo, ou escreva o que aconteceu.`;
}

/**
 * Manda o arquivo e devolve o DESFECHO. Nunca levanta.
 *
 * Mesma forma do `pedirOTurno`: rede fora, recusa do servidor e corpo que não
 * dá para ler voltam como valor. Toda leitura de corpo daqui passa pela
 * fronteira `corpoValidado`, com um validador do que o consumidor consome.
 */
async function mandarOArquivo<T>(
  url: string,
  campo: string,
  arquivo: File,
  token: string | null,
  valida: (corpo: unknown) => corpo is T,
): Promise<LeituraDoAnexo<T>> {
  const form = new FormData();
  form.append(campo, arquivo, arquivo.name);
  let resposta: Response;
  try {
    resposta = await fetch(url, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
  } catch (e) {
    console.error("[admin/tecnologia] falha ao mandar o anexo", e);
    return { aviso: FALHA_DE_CONEXAO };
  }
  // O 429 é distinguido aqui, como o `pedirOTurno` já fazia: o `slowapi`
  // responde `{"error": ...}` SEM `detail`, então a frase genérica sairia
  // mandando "tente outro arquivo" quando a saída é esperar um minuto. É a
  // mesma frase do turno, e não uma terceira: a causa é a mesma, e o balde é
  // por endereço, então o teto pode ter sido gasto por outra pessoa da casa.
  if (!resposta.ok) {
    return { aviso: resposta.status === 429 ? MUITAS_MENSAGENS : await motivoDoAnexo(resposta) };
  }
  const corpo = await corpoValidado(resposta, valida);
  if (corpo === null) {
    console.error("[admin/tecnologia] a resposta do anexo não deu para usar");
    return { aviso: ANEXO_ILEGIVEL };
  }
  return { corpo };
}

/**
 * O áudio encaminhado vai à MESMA rota de voz, como blob. Sem rota nova.
 *
 * O hook de gravação não serve aqui: o que ele faz de próprio é tomar conta do
 * microfone (permissão, MediaRecorder, soltar o aparelho ao sair da tela), e
 * um arquivo que a pessoa escolheu não tem nada disso. O que os dois caminhos
 * compartilham é a rota, não o ciclo de vida.
 */
export function transcreverArquivoDeAudio(
  arquivo: File,
  token: string | null,
): Promise<LeituraDoAnexo<TextoTranscrito>> {
  return mandarOArquivo(URL_DA_TRANSCRICAO, "audio", arquivo, token, transcricaoValida);
}

export function extrairODocumento(arquivo: File, token: string | null): Promise<LeituraDoAnexo<DocumentoExtraido>> {
  return mandarOArquivo(URL_DA_EXTRACAO, "arquivo", arquivo, token, documentoExtraidoValido);
}

// ─── O print de tela (issue #730) ───────────────────────────────────────────
//
// A quarta entrada, pela mesma regra das três: a imagem vira TEXTO antes de
// chegar ao chat. O que o chat recebe é uma mensagem da pessoa com a origem à
// mostra; a imagem não vai a lugar nenhum além da rota que a descreve, e lá ela
// não é guardada (ADR 0056, decisão 4).

export const URL_DA_IMAGEM = `${BASE_TECNOLOGIA}/assistente/descrever-imagem`;

/**
 * A origem do print, sem nome de arquivo.
 *
 * O nome de um print é "Captura de tela 2026-09-17 às 14.02.11.png", que não diz
 * nada a quem lê a conversa (o do documento diz: alguém o batizou). O rótulo
 * seco é origem que o backend reconhece e cerca: o `PREFIXO_DE_ORIGEM` de lá
 * aceita rótulo sem nome exatamente por isso.
 */
export const PREFIXO_DE_PRINT = "[print] ";

// Os aceitos e o teto, iguais aos do backend, pela mesma razão dos outros dois:
// a recusa acontece ANTES de subir a imagem por um cabo de hospital e voltar
// 413. Quem decide continua sendo o backend, e a frase dele é a que aparece.
export const IMAGENS_ACEITAS = [".png", ".jpg", ".jpeg", ".webp"];
export const LIMITE_DA_IMAGEM = 5 * 1024 * 1024;

export const IMAGEM_FORA_DA_LISTA =
  "Só dá para ler print .png, .jpg, .jpeg ou .webp. Salve a imagem em um desses formatos e anexe de novo.";

/**
 * A frase de quando a descrição voltou em branco.
 *
 * O backend já recusa a descrição vazia com 502, então esta frase é a rede de
 * baixo, e não o caminho de todo dia: um `[print] ` seco na conversa mandaria o
 * assistente adivinhar o que a pessoa nunca mostrou. Mesmo papel do
 * `AUDIO_SEM_FALA` no áudio mudo.
 */
export const PRINT_SEM_LEITURA = "Não consegui ler esse print. Mande outro, ou escreva o que aparece na tela.";

/** O que impede este print de virar mensagem, ou `null` se nada impede. */
export function avisoDaImagem(arquivo: ArquivoEscolhido): string | null {
  if (!IMAGENS_ACEITAS.includes(extensaoDe(arquivo.name))) return IMAGEM_FORA_DA_LISTA;
  if (arquivo.size > LIMITE_DA_IMAGEM) {
    return avisoDeTamanho(LIMITE_DA_IMAGEM, "Anexe uma imagem menor, ou escreva o que aparece na tela.");
  }
  return null;
}

/**
 * O print vai à rota que o descreve, e o que volta é TEXTO.
 *
 * O validador é o da transcrição, e não um próprio: o que o consumidor consome
 * aqui é exatamente um `texto`, como na voz. O print não tem `filename` a
 * cobrar, porque o prefixo dele não leva nome.
 */
export function descreverAImagem(arquivo: File, token: string | null): Promise<LeituraDoAnexo<TextoTranscrito>> {
  return mandarOArquivo(URL_DA_IMAGEM, "imagem", arquivo, token, transcricaoValida);
}

/**
 * A conversa teve print?
 *
 * Só fala da PESSOA conta, e só com o prefixo no começo: é o mesmo critério do
 * `PREFIXO_DE_ORIGEM` do backend, que é quem cerca o material. Fala do
 * assistente não conta nem se começar com o texto do prefixo, porque o que
 * interessa é o que entrou de fora, não o que o modelo escreveu de volta.
 */
export function conversaTevePrint(messages: MensagemDoChat[]): boolean {
  return messages.some((m) => m.role === "user" && m.content.startsWith(PREFIXO_DE_PRINT));
}

/**
 * O aviso que quem vai criar a Demanda lê quando a conversa teve print.
 *
 * Ele existe porque a descrição do print chega, por caminho de código, ao corpo
 * de uma issue de repositório PÚBLICO: descrição do modelo, mensagem na
 * conversa, `rascunho.descricao`, coluna `descricao` da Demanda, e daí
 * `corpo_da_issue_nova` no clique de "Levar para desenvolvimento". O projeto já
 * tirou de propósito o nome civil de um funcionário desse corpo (rodada de
 * segurança do PR #688), e um print de tela de hospital pode trazer o nome de um
 * paciente transcrito.
 *
 * **Isto não é controle**, e o projeto sabe a diferença: é o mesmo argumento da
 * cerca do prompt. A barreira em código entre a descrição de origem print e a
 * issue pública é a issue #772, que precisa de decisão do diretor. O que o aviso
 * faz é chegar no único momento em que quem lê ainda pode agir: a descrição está
 * na tela, editável, e o clique de criar ainda não aconteceu.
 *
 * Ele **não bloqueia** a criação. Guarda-corpo que vira beco não é guarda-corpo,
 * e a decisão de criar continua sendo de quem está olhando.
 */
export const AVISO_DO_PRINT =
  "Esta conversa teve print. O texto do rascunho pode ir para um registro público quando a Vitta levar a " +
  "Demanda para desenvolvimento: confira que não ficou nome de paciente, número de prontuário nem leito na " +
  "descrição antes de criar.";
