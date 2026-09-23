"use client";

/**
 * A leitura de uma tela da Central de Comando, com frescor (issue #815).
 *
 * Toda tela da Central que passa pelo cache do backend (a Visão Geral nesta
 * fatia; Dados do Google na #817, com os blocos da #818) repete as mesmas
 * regras, e é aqui que elas moram, uma vez só. A tela pluga assim:
 *
 *     const { estado, atualizando, aviso, atualizarAgora } =
 *       useTelaDaCentral<DadosDoGooglePayload>("dados-do-google", periodo);
 *
 * e desenha a `BarraDeFrescor` em cima dos blocos quando `estado` é "pronto".
 *
 * As regras:
 *
 * 1. **A leitura** (`GET /{tela}?periodo=`) na abertura e a cada troca de
 *    período. O backend serve do cache de 1 hora; a tela não guarda nada.
 * 2. **O Atualizar agora** (`POST /atualizar-agora?tela=&periodo=`) troca os
 *    números e o carimbo pelos que voltarem. Enquanto ele está no ar, o botão
 *    diz "Atualizando…". Se ele não trouxer números (o limite de taxa, a rede
 *    fora, o Google fora sem nada guardado no backend), os números de antes
 *    ficam e a razão vira `aviso`: a tela nunca zera por causa de uma falha.
 * 3. **A renovação automática**, de hora em hora com a tela aberta, contada da
 *    abertura, pela mesma rota do Atualizar agora (molde do `RefreshScope` da
 *    Central antiga, que também forçava a renovação). Ela é silenciosa: sem
 *    "Atualizando…" e sem aviso; se falhar, o carimbo que envelhece já diz de
 *    quando são os números. Forçar, e não reler, é o que faz cada renovação
 *    trazer número novo: uma releitura a 1 hora da abertura pegaria o cache
 *    ainda a segundos de vencer, e o número ficaria mais uma hora parado. O
 *    número da tela não tem idade máxima de 1 hora: se o cache já tinha quase
 *    1 hora quando a tela abriu, ele chega a quase 2 antes da primeira
 *    renovação. A barra sempre diz a idade, e o Atualizar agora resolve na hora.
 *    Ela não vai por cima de uma leitura ou de um clique ainda no ar.
 * 4. **O selo de sequência.** Cada pedido leva um número, e só escreve na tela
 *    se ainda for o último: trocar de período no meio de um Atualizar agora
 *    não deixa o número do período antigo entrar na tela do novo.
 * 5. **A sessão é lida a cada pedido** (`getAuthToken`), e não na abertura: a
 *    tela fica aberta por horas, e o token da abertura vence em 1 hora.
 *
 * Os números vêm por `fetch` a caminhos relativos, com estado local, sem
 * biblioteca de cache (PRD #809). O dado sensível só sai do backend, que exige
 * Super admin em toda rota: esta leitura não confia no guard do `layout.tsx`.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";

import { getAuthToken } from "@/hooks/useAuth";
import {
  BASE_CENTRAL,
  FALHA_DE_CONEXAO,
  MUITAS_ATUALIZACOES,
  SEM_SESSAO,
  lerRecusa,
  type Frescor,
  type Recusa,
  type TelaDaCentral,
} from "@/lib/central-de-comando/api";
import type { Periodo } from "@/lib/central-de-comando/periodo";

/** A tela aberta se renova sozinha de hora em hora: a hora do cache do backend. */
export const RENOVACAO_AUTOMATICA_MS = 60 * 60 * 1000;

/** Por que não há números na tela. */
type Falha = Recusa | { tipo: "sem-conexao"; mensagem: string };

/**
 * A leitura que não trouxe números, com o status HTTP da recusa (nulo quando o
 * servidor nem respondeu). Quem lê o status é a lente de um Objetivo, de
 * endereço variável: o 404 dela é Objetivo que não existe (issue #861).
 */
type FalhaDaLeitura = Falha & { status: number | null };

/** O que a tela mostra: esperando, os números, ou por que não há números. */
export type EstadoDaTela<T> = { tipo: "carregando" } | { tipo: "pronto"; dados: T } | FalhaDaLeitura;

type Quadro<T> = {
  estado: EstadoDaTela<T>;
  /** Um Atualizar agora clicado está no ar. */
  atualizando: boolean;
  /** Por que o último Atualizar agora clicado não trouxe números. */
  aviso: string | null;
};

type Acao<T> =
  | { tipo: "abrir" }
  | { tipo: "leu"; estado: EstadoDaTela<T> }
  | { tipo: "atualizar" }
  | { tipo: "atualizou"; dados: T }
  | { tipo: "nao-atualizou"; aviso: string };

function reduzir<T>(quadro: Quadro<T>, acao: Acao<T>): Quadro<T> {
  switch (acao.tipo) {
    case "abrir":
      return { estado: { tipo: "carregando" }, atualizando: false, aviso: null };
    case "leu":
      return { ...quadro, estado: acao.estado };
    case "atualizar":
      return { ...quadro, atualizando: true, aviso: null };
    case "atualizou":
      return { estado: { tipo: "pronto", dados: acao.dados }, atualizando: false, aviso: null };
    case "nao-atualizou":
      // Os números de antes ficam: a falha vira aviso, e não a tela.
      return { ...quadro, atualizando: false, aviso: acao.aviso };
  }
}

const QUADRO_INICIAL = { estado: { tipo: "carregando" }, atualizando: false, aviso: null } as const;

type Resposta<T> = { dados: T } | { falha: Falha; status: number | null };

/**
 * Um pedido ao backend, com a sessão do momento. Nunca levanta: devolve os
 * dados, ou a falha já em palavras com o status HTTP (nulo quando o servidor
 * nem respondeu).
 *
 * "Nunca levanta" inclui a leitura da sessão: o supabase-js relança erro que
 * não é de autenticação, e o cliente sem as variáveis públicas também levanta.
 * Se isso escapasse daqui, a marca de pedido no ar nunca seria tirada: a tela
 * ficaria em "Carregando", o botão preso em "Atualizando…" e a renovação de
 * hora em hora pararia em silêncio.
 */
async function pedir<T>(url: string, metodo: "GET" | "POST"): Promise<Resposta<T>> {
  let token: string | undefined;
  try {
    token = await getAuthToken();
  } catch (e) {
    console.error("[central-de-comando] não foi possível ler a sessão", e);
    token = undefined;
  }
  if (!token) return { falha: { tipo: "sem-conexao", mensagem: SEM_SESSAO }, status: null };
  try {
    const resposta = await fetch(url, { method: metodo, headers: { Authorization: `Bearer ${token}` } });
    if (resposta.ok) return { dados: (await resposta.json()) as T };
    return { falha: await lerRecusa(resposta), status: resposta.status };
  } catch (e) {
    console.error("[central-de-comando] falha ao falar com o servidor", e);
    return { falha: { tipo: "sem-conexao", mensagem: FALHA_DE_CONEXAO }, status: null };
  }
}

/**
 * A frase de um Atualizar agora que não trouxe números: a do servidor, menos
 * no limite de taxa, que chega sem frase em português.
 */
function avisoDa(resposta: { falha: Falha; status: number | null }): string {
  return resposta.status === 429 ? MUITAS_ATUALIZACOES : resposta.falha.mensagem;
}

export function useTelaDaCentral<T extends { frescor: Frescor }>(tela: TelaDaCentral, periodo: Periodo) {
  const [quadro, despachar] = useReducer(reduzir<T>, QUADRO_INICIAL);
  // O selo do pedido mais novo: só ele escreve na tela.
  const selo = useRef(0);
  // O selo da leitura ou do Atualizar agora clicado que ainda está no ar, ou
  // nulo. A renovação automática não vai por cima deles: se fosse, o selo novo
  // descartaria o resultado deles, e uma renovação silenciosa que falhasse
  // deixaria a tela em "Carregando" ou o botão em "Atualizando…" para sempre.
  // É ref marcada na hora do pedido, e não o estado da tela: o estado só chega
  // ao timer depois do render e do efeito, e o timer pode bater antes.
  const noAr = useRef<number | null>(null);

  // 1. A leitura, na abertura e a cada troca de período. O selo novo aposenta
  // tudo o que ainda estiver no ar, leitura ou Atualizar agora do período velho.
  useEffect(() => {
    const meu = ++selo.current;
    noAr.current = meu;
    despachar({ tipo: "abrir" });
    (async () => {
      const resultado = await pedir<T>(`${BASE_CENTRAL}/${tela}?periodo=${periodo}`, "GET");
      if (noAr.current === meu) noAr.current = null;
      if (meu !== selo.current) return;
      despachar({
        tipo: "leu",
        estado:
          "dados" in resultado
            ? { tipo: "pronto", dados: resultado.dados }
            : { ...resultado.falha, status: resultado.status },
      });
    })();
  }, [tela, periodo]);

  // 2 e 3. O Atualizar agora e a renovação automática, pela mesma rota.
  const renovar = useCallback(
    async (silenciosa: boolean) => {
      const meu = ++selo.current;
      if (!silenciosa) {
        noAr.current = meu;
        despachar({ tipo: "atualizar" });
      }
      const resultado = await pedir<T>(`${BASE_CENTRAL}/atualizar-agora?tela=${tela}&periodo=${periodo}`, "POST");
      if (noAr.current === meu) noAr.current = null;
      if (meu !== selo.current) return;
      if ("dados" in resultado) despachar({ tipo: "atualizou", dados: resultado.dados });
      else if (!silenciosa) despachar({ tipo: "nao-atualizou", aviso: avisoDa(resultado) });
    },
    [tela, periodo],
  );

  const atualizarAgora = useCallback(() => void renovar(false), [renovar]);

  useEffect(() => {
    const id = setInterval(() => {
      if (noAr.current !== null) return;
      void renovar(true);
    }, RENOVACAO_AUTOMATICA_MS);
    return () => clearInterval(id);
  }, [renovar]);

  return { ...quadro, atualizarAgora };
}
