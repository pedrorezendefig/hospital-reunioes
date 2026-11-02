/**
 * O que o chat da Tecnologia herdou do Assistente de entrada (PRD #726, ADR 0056).
 *
 * O Assistente de entrada, com o rascunho e a leitura de documento, saiu na
 * issue #1386 (ADR 0077). Ficaram o aviso de IA, o teto da fala, a fronteira
 * de leitura do corpo HTTP e o print de tela, que o chat usa.
 */

import { BASE_TECNOLOGIA, FALHA_DE_CONEXAO } from "./demandas";

/**
 * O aviso fixo sob a caixa de mensagem: quem escreve tem que saber que o texto
 * vai para uma inteligência artificial antes de escrever, não depois.
 */
export const AVISO_DE_IA =
  "O que você escreve aqui é lido por uma inteligência artificial, como nas atas. Evite dados de paciente.";

/**
 * O teto de uma fala do chat, igual ao do backend. Mora aqui porque o backend
 * recusa com 422 do pydantic, cujo `detail` vem em LISTA e chegaria à tela
 * como JSON cru dentro do alerta vermelho.
 */
export const LIMITE_DA_MENSAGEM = 5000;

/**
 * A frase do teto de taxa.
 *
 * Ela é escrita aqui, e não lida da resposta, porque o `slowapi` devolve
 * `{"error": "Rate limit exceeded: ..."}` (sem `detail`, e em inglês), e o
 * leitor desta tela lê português e precisa saber o que fazer: esperar.
 */
export const MUITAS_MENSAGENS = "Muitas mensagens em pouco tempo. Espere um minuto e mande de novo.";

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

// ─── Anexar (issue #729) ────────────────────────────────────────────────────
//
// Uma regra só: **toda entrada vira texto antes de chegar ao chat**. O chat
// nunca recebe arquivo. O que chega lá é uma fala da PESSOA, com a origem à
// mostra, e é essa marca que faz o backend cercar o material como texto de
// gente, e não como instrução.

/**
 * O que a mensagem diz quando o texto não coube inteiro.
 *
 * A descrição de um print pode passar dos 5000 caracteres de uma mensagem, e
 * o teto do corpo é do backend. Cortar calado mandaria meia
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

/** A frase de quando o servidor respondeu e o corpo do anexo não deu para ler. */
export const ANEXO_ILEGIVEL =
  "O servidor respondeu algo que a tela não conseguiu ler. Anexe de novo, ou escreva o que aconteceu.";

export type ArquivoEscolhido = { name: string; size: number };

export function extensaoDe(nome: string): string {
  const ponto = nome.lastIndexOf(".");
  return ponto < 0 ? "" : nome.slice(ponto).toLowerCase();
}

function avisoDeTamanho(teto: number, saida: string): string {
  return `O arquivo passou do limite de ${Math.round(teto / (1024 * 1024))} MB. ${saida}`;
}

/** O desfecho de uma entrada de fora: virou texto, ou virou aviso na conversa. */
export type LeituraDoAnexo<T> = { corpo: T } | { aviso: string };

export type TextoTranscrito = { texto: string };

export function transcricaoValida(corpo: unknown): corpo is TextoTranscrito {
  return typeof corpo === "object" && corpo !== null && typeof (corpo as Record<string, unknown>).texto === "string";
}

/**
 * O motivo da recusa de um anexo, dito pelo servidor.
 *
 * Não é o `motivoDaRecusa` porque o verbo de lá é "salvar", e aqui nada é
 * salvo. O 413 também pode vir do proxy, sem corpo JSON nenhum, e a
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
 * Rede fora, recusa do servidor e corpo que não dá para ler voltam como valor. Toda leitura de corpo daqui passa pela
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
  // O 429 é distinguido aqui: o `slowapi` responde `{"error": ...}` SEM
  // `detail`, então a frase genérica sairia mandando "tente outro arquivo"
  // quando a saída é esperar um minuto. O balde é por endereço, então o teto
  // pode ter sido gasto por outra pessoa da casa.
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

// ─── O print de tela (issue #730) ───────────────────────────────────────────
//
// A imagem vira TEXTO antes de chegar ao chat. O que o chat recebe é uma mensagem da pessoa com a origem à
// mostra; a imagem não vai a lugar nenhum além da rota que a descreve, e lá ela
// não é guardada (ADR 0056, decisão 4).

export const URL_DA_IMAGEM = `${BASE_TECNOLOGIA}/assistente/descrever-imagem`;

/**
 * A origem do print, sem nome de arquivo.
 *
 * O nome de um print é "Captura de tela 2026-09-17 às 14.02.11.png", que não diz
 * nada a quem lê a conversa. O rótulo seco é origem que o backend reconhece e cerca: o `PREFIXO_DE_ORIGEM` de lá
 * aceita rótulo sem nome exatamente por isso.
 */
export const PREFIXO_DE_PRINT = "[print] ";

// Os aceitos e o teto, iguais aos do backend: a recusa acontece ANTES de subir a imagem por um cabo de hospital e voltar
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
 * assistente adivinhar o que a pessoa nunca mostrou.
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
 * O que a rota do print devolve: a descrição e, desde a issue #1062, o
 * identificador efêmero com que a imagem vira Anexo quando a fala entra.
 * `print_id` ausente ou nulo não derruba a leitura: a descrição continua valendo,
 * a imagem só não vira Anexo.
 */
export type PrintDescrito = TextoTranscrito & { print_id?: string | null };

export function printDescritoValido(corpo: unknown): corpo is PrintDescrito {
  if (!transcricaoValida(corpo)) return false;
  const id = (corpo as Record<string, unknown>).print_id;
  return id === undefined || id === null || typeof id === "string";
}

/** O print vai à rota que o descreve, e o que volta é TEXTO (e o identificador). */
export function descreverAImagem(arquivo: File, token: string | null): Promise<LeituraDoAnexo<PrintDescrito>> {
  return mandarOArquivo(URL_DA_IMAGEM, "imagem", arquivo, token, printDescritoValido);
}

