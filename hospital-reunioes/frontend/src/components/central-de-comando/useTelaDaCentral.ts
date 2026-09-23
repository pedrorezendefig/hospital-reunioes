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
 * 3. **A renovação automática** (issue #858): com a tela aberta, relê pela
 *    leitura comum (GET) quando o número da tela faz 1 hora, contada do
 *    `frescor.atualizado_em` que o backend mandou, e não da abertura. Não força:
 *    quem chega primeiro depois da hora faz a única ida à fonte, e as outras
 *    abas e os outros Super admins pegam o número novo do cache do backend, sem
 *    gastar o limite do Atualizar agora (que é por endereço, e os Super admins
 *    atrás do mesmo NAT dividem um só). Se a releitura não trouxer número novo
 *    (a fonte fora, que o backend segura por 5 minutos, ou o relógio da máquina
 *    adiantado), relê de novo em 5 minutos, nunca antes. Ela é silenciosa: sem
 *    "Atualizando…" e sem aviso; se falhar, o carimbo que envelhece já diz de
 *    quando são os números. Ela não vai por cima de uma leitura ou de um clique
 *    ainda no ar.
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

/** A hora do cache do backend: o número vale 1 hora a contar de quando foi buscado. */
export const HORA_DO_CACHE_MS = 60 * 60 * 1000;

/**
 * O menor intervalo entre duas releituras automáticas: a espera do backend
 * depois de uma falha da fonte. Vale quando a hora do número já passou e a
 * releitura não trouxe outro (a fonte fora, o relógio da máquina adiantado), e
 * quando a tela não tem carimbo para contar.
 */
export const RELEITURA_MINIMA_MS = 5 * 60 * 1000;

/**
 * Folga depois da hora: o relógio da máquina e o do servidor não batem ao
 * milissegundo, e reler um instante antes da hora traria o número velho.
 */
const FOLGA_MS = 5 * 1000;

/** Quanto falta para o número da tela fazer 1 hora, com a folga, e nunca menos que a releitura mínima. */
function esperaAteRenovar(atualizadoEm: string | null): number {
  if (atualizadoEm === null) return RELEITURA_MINIMA_MS;
  const vence = Date.parse(atualizadoEm) + HORA_DO_CACHE_MS + FOLGA_MS;
  if (Number.isNaN(vence)) return RELEITURA_MINIMA_MS;
  return Math.max(vence - Date.now(), RELEITURA_MINIMA_MS);
}

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


  // O próximo disparo da renovação automática, ou nulo.
  const agendado = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 3. A renovação automática: relê em silêncio, pela leitura comum, quando o
  // número da tela faz 1 hora. É agendada na hora em que os números chegam, e
  // não num efeito que olha o estado: o efeito só roda depois do render, e o
  // relógio pode bater antes (o CI em Linux já pegou essa corrida). Só troca os
  // números se a releitura os trouxer; a falha fica calada, e o carimbo que
  // envelhece já diz de quando são os números.
  const programar = useCallback(
    function programar(ms: number) {
      if (agendado.current !== null) clearTimeout(agendado.current);
      agendado.current = setTimeout(async () => {
        agendado.current = null;
        // Uma leitura ou um clique no ar: não vai por cima dele. Se ele trouxer
        // números, reagenda pelo carimbo novo; senão, este tenta mais tarde.
        if (noAr.current !== null) return programar(RELEITURA_MINIMA_MS);
        const meu = ++selo.current;
        const resultado = await pedir<T>(`${BASE_CENTRAL}/${tela}?periodo=${periodo}`, "GET");
        if (meu !== selo.current) return;
        if ("dados" in resultado) {
          despachar({ tipo: "atualizou", dados: resultado.dados });
          programar(esperaAteRenovar(resultado.dados.frescor.atualizado_em));
        } else {
          programar(RELEITURA_MINIMA_MS);
        }
      }, ms);
    },
    [tela, periodo],
  );

  // 1. A leitura, na abertura e a cada troca de período. O selo novo aposenta
  // tudo o que ainda estiver no ar, leitura, Atualizar agora ou renovação do
  // período velho, e a saída da tela também.
  useEffect(() => {
    // As refs em variáveis do efeito: a limpeza mexe nelas, e não em nó do DOM.
    const selos = selo;
    const disparo = agendado;
    const meu = ++selos.current;
    noAr.current = meu;
    despachar({ tipo: "abrir" });
    (async () => {
      const resultado = await pedir<T>(`${BASE_CENTRAL}/${tela}?periodo=${periodo}`, "GET");
      if (noAr.current === meu) noAr.current = null;
      if (meu !== selos.current) return;
      despachar({
        tipo: "leu",
        estado:
          "dados" in resultado
            ? { tipo: "pronto", dados: resultado.dados }
            : { ...resultado.falha, status: resultado.status },
      });
      programar(
        "dados" in resultado ? esperaAteRenovar(resultado.dados.frescor.atualizado_em) : RELEITURA_MINIMA_MS,
      );
    })();
    return () => {
      ++selos.current;
      if (disparo.current !== null) clearTimeout(disparo.current);
      disparo.current = null;
    };
  }, [tela, periodo, programar]);

  // 2. O Atualizar agora.
  const atualizarAgora = useCallback(() => {
    void (async () => {
      const meu = ++selo.current;
      noAr.current = meu;
      despachar({ tipo: "atualizar" });
      const resultado = await pedir<T>(`${BASE_CENTRAL}/atualizar-agora?tela=${tela}&periodo=${periodo}`, "POST");
      if (noAr.current === meu) noAr.current = null;
      if (meu !== selo.current) return;
      if ("dados" in resultado) {
        despachar({ tipo: "atualizou", dados: resultado.dados });
        programar(esperaAteRenovar(resultado.dados.frescor.atualizado_em));
      } else {
        despachar({ tipo: "nao-atualizou", aviso: avisoDa(resultado) });
        // O clique pode ter aposentado uma renovação no ar: a corrente segue.
        programar(RELEITURA_MINIMA_MS);
      }
    })();
  }, [tela, periodo, programar]);

  return { ...quadro, atualizarAgora };
}
