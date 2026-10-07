/**
 * O Anexo da Demanda, do lado da tela (issue #1061, PRD #1056, ADR 0069).
 *
 * O print que vem junto da Demanda vive SÓ no app: bucket privado, aberto por
 * URL assinada de vida curta, e apagado quando a Demanda é Concluída ou
 * Cancelada. Quem decide formato, teto e o máximo de dez é o backend; o que
 * mora aqui é a recusa ANTES de subir a imagem por um cabo de hospital e voltar
 * 413, com as mesmas frases do Assistente.
 */

import { avisoDaImagem } from "./assistente";
import { BASE_TECNOLOGIA, FALHA_DE_CONEXAO, motivoDaRecusa } from "./demandas";

/** O máximo por Demanda, o mesmo do backend (e do CHECK da migration 115). */
export const LIMITE_DE_ANEXOS = 10;

export const IMAGENS_DEMAIS = `Cada Demanda guarda até ${LIMITE_DE_ANEXOS} imagens: as que passaram disso ficaram de fora.`;

/** O que o card mostra de cada anexo. `url` nula quando ele foi apagado. */
export type AnexoDaDemanda = {
  id: string;
  nome: string;
  anexado_por_nome: string | null;
  criado_em: string | null;
  apagado_em: string | null;
  url: string | null;
};

export function urlDosAnexos(demandaId: string): string {
  return `${BASE_TECNOLOGIA}/demandas/${demandaId}/anexos`;
}

/**
 * Junta as imagens novas às já escolhidas, recusando na hora o que não entra.
 *
 * O aviso diz a PRIMEIRA recusa com o nome do arquivo: quem escolheu cinco de
 * uma vez precisa saber qual ficou de fora, e por quê.
 */
export function escolherImagens(atuais: File[], novas: File[]): { imagens: File[]; aviso: string | null } {
  const imagens = [...atuais];
  let aviso: string | null = null;
  for (const arquivo of novas) {
    const recusa = avisoDaImagem(arquivo);
    if (recusa) {
      aviso ??= `${arquivo.name}: ${recusa}`;
      continue;
    }
    if (imagens.length >= LIMITE_DE_ANEXOS) {
      aviso ??= IMAGENS_DEMAIS;
      continue;
    }
    imagens.push(arquivo);
  }
  return { imagens, aviso };
}

/**
 * Manda uma imagem para a Demanda e devolve o MOTIVO da recusa, ou `null` se
 * ela entrou. Nunca levanta: a Demanda já nasceu, e uma imagem que não entrou
 * vira aviso, e não uma tela quebrada.
 */
export async function anexarImagem(demandaId: string, arquivo: File, token: string | null): Promise<string | null> {
  const form = new FormData();
  form.append("imagem", arquivo, arquivo.name);
  try {
    const resposta = await fetch(urlDosAnexos(demandaId), {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    return resposta.ok ? null : await motivoDaRecusa(resposta);
  } catch (e) {
    console.error("[admin/tecnologia] falha ao anexar a imagem", e);
    return FALHA_DE_CONEXAO;
  }
}

/**
 * O aviso das imagens que o servidor recusou depois de a Demanda nascer, ou
 * `null` quando todas entraram. Uma por frase, com o nome e o motivo.
 */
export function avisoDasImagens(recusadas: { nome: string; motivo: string }[]): string | null {
  if (recusadas.length === 0) return null;
  const quais = recusadas.map((r) => `${r.nome} (${r.motivo})`).join(" ");
  const sujeito = recusadas.length === 1 ? "uma imagem não entrou" : `${recusadas.length} imagens não entraram`;
  return `A Demanda foi aberta, mas ${sujeito}: ${quais}`;
}
