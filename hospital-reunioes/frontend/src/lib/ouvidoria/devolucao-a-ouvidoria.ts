/**
 * A Devolução à Ouvidoria, lida da trilha (issue #601, PRD #598, ADR 0048).
 *
 * A área que recebeu um caso que não é dela o devolve pelo link do email
 * (issue #600). O caso volta a `em_classificacao` e o motivo NÃO ganha coluna:
 * ele vive no movimento da trilha, e é de lá que o Dossiê o lê.
 *
 * O que o servidor grava é uma frase com prefixo fixo (`observacao_da_devolucao`,
 * em `app/services/ouvidoria_devolucao_a_ouvidoria.py`), e este módulo é o
 * único lugar do frontend que a desmonta. O prefixo é o contrato entre os dois
 * lados: mudá-lo lá sem mudá-lo aqui faz o bloco sumir da tela em silêncio, e é
 * por isso que ele mora numa constante exportada, com teste próprio dos dois
 * lados.
 *
 * A Retenção zera a observação depois de cinco anos (issue #375). O bloco
 * simplesmente deixa de aparecer no caso anonimizado, que é o comportamento
 * certo: o que a LGPD apagou não volta pela tela.
 */

import type { EventoDaTrilha } from "./trilha";
import type { StatusManifestacao } from "./prazo";

/**
 * O rótulo que abre a observação do movimento da devolução. Palavra por
 * palavra o `_PREFIXO` do módulo do backend, mais o espaço que separa o setor.
 */
export const PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA = "Devolvido pela área";

const SEPARADOR = ": ";

/**
 * A descrição que o servidor dá à transição `aguardando_area -> em_classificacao`,
 * palavra por palavra o `ROTULO_DO_ESTADO["em_classificacao"]` de
 * `app/services/ouvidoria_trilha.py`.
 *
 * É ela, e não o texto, que diz qual foi o CAMINHO no grafo, e é o caminho que
 * separa a devolução da resposta da área: as duas são movimento de quem não tem
 * login e as duas carregam texto livre.
 */
const DESCRICAO_DA_VOLTA_A_CLASSIFICACAO = "Caso em classificação";

/** A devolução como o Dossiê a mostra. */
export interface DevolucaoLida {
  /** A área que devolveu, do jeito que ela estava gravada no caso naquele dia. */
  setor: string;
  motivo: string;
  /** O nome do responsável do setor que clicou, guardado no movimento. */
  autor: string;
  ocorrido_em: string;
  /** Quantas vezes este caso já voltou por esta porta (história 22). */
  vezes: number;
}

/**
 * Um evento é uma Devolução à Ouvidoria quando percorreu o CAMINHO dela no
 * grafo, ninguém logado o escreveu e ele traz a frase da devolução.
 *
 * As três condições, porque nenhuma sozinha basta:
 *
 * - só a frase não basta: o motivo da devolução por insuficiência é texto livre
 *   do OUVIDOR e chega à trilha sem o rótulo interno (o servidor o retira),
 *   então nada impede que ele comece igualzinho;
 * - frase mais `sistema` também não bastam: a RESPOSTA da área é movimento de
 *   quem também não tem login e também carrega texto livre. O titular que não
 *   achou o botão escreve "Devolvido pela área X: ..." no campo do que foi
 *   feito, e a contagem de voltas passaria a mentir;
 * - o que fecha é a descrição, que nomeia a transição. É a régua do próprio
 *   módulo da trilha: quem decide o que cada evento É são os dois estados.
 *
 * Sobra a devolução por insuficiência escrita pelo ouvidor, que o `sistema`
 * elimina, e é por isso que ele fica.
 */
function ehDevolucao(evento: EventoDaTrilha): boolean {
  return (
    evento.descricao === DESCRICAO_DA_VOLTA_A_CLASSIFICACAO &&
    evento.sistema &&
    typeof evento.texto === "string" &&
    evento.texto.startsWith(`${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} `) &&
    evento.texto.includes(SEPARADOR)
  );
}

function desmontar(texto: string): { setor: string; motivo: string } {
  const semPrefixo = texto.slice(PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA.length + 1);
  const corte = semPrefixo.indexOf(SEPARADOR);
  return {
    setor: semPrefixo.slice(0, corte),
    // `slice` e não `split`: o motivo é texto livre e pode conter ": " à
    // vontade. Cortar no PRIMEIRO separador perde tudo o que vem depois dele.
    motivo: semPrefixo.slice(corte + SEPARADOR.length),
  };
}

/**
 * A devolução que o ouvidor precisa ler agora, ou nulo quando não há.
 *
 * Só o caso que está DE VOLTA na fila do ouvidor mostra o bloco: ele é o convite
 * a despachar de novo, e não um histórico. Depois do reacionamento o caso está
 * com a área certa, e o que aconteceu antes continua na linha do tempo.
 *
 * `movimentos` chega do mais novo para o mais antigo (é assim que o servidor
 * entrega a linha do tempo), então a devolução corrente é a PRIMEIRA da lista,
 * e não a última: num pingue-pongue, a mais recente é a que diz de onde o caso
 * acabou de voltar.
 */
export function devolucaoAOuvidoria(
  movimentos: EventoDaTrilha[],
  status: StatusManifestacao
): DevolucaoLida | null {
  if (status !== "em_classificacao") return null;
  const devolucoes = movimentos.filter(ehDevolucao);
  const corrente = devolucoes[0];
  if (!corrente) return null;
  return {
    ...desmontar(corrente.texto as string),
    autor: corrente.autor,
    ocorrido_em: corrente.ocorrido_em,
    vezes: devolucoes.length,
  };
}
