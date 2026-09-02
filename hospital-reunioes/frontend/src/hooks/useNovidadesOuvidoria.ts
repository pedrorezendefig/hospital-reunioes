"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { createClient } from "@/lib/supabase/client";
import { temPerfilOuvidoria } from "@/lib/auth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import type { ContagemDeNovidades } from "@/lib/ouvidoria/novidades";

/**
 * O contador de novidades da Ouvidoria para o menu (issue #487, RN-69).
 *
 * Quem não tem o Perfil da Ouvidoria não busca nada: o item do menu existe para
 * todo mundo, mas o número diz "a Ouvidoria ainda não viu", que não significa
 * nada fora dela. O servidor recusa do mesmo jeito (403); esta guarda existe
 * para a tela não bater numa porta que já se sabe fechada.
 *
 * O menu vive em TODA tela do app, então perguntar a cada navegação sairia caro
 * do jeito errado: o hospital sai por um IP só, o rate limiter da rota conta por
 * IP, e uma tarde de movimento derrubaria o contador de todo mundo ao mesmo
 * tempo, com o distintivo virando "?" justamente no dia em que ele importa.
 * Duas regras seguram isso, e as duas são sobre quando o número pode ter mudado:
 *
 * * dentro da janela de reuso, a navegação comum reaproveita a última contagem.
 *   Nada aconteceu no servidor que pudesse mudar o número: ninguém abriu caso
 *   nenhum, e o que chega de novo chega na próxima janela;
 * * sair da tela de um caso reconta na hora, mesmo dentro da janela. Ali o
 *   número mudou de verdade: abrir o Dossiê carimba o visto, e o ouvidor que
 *   fecha o caso e continua vendo o número de antes conclui que o clique dele
 *   não valeu.
 *
 * O valor mora no módulo, e não no componente, para que a troca de layout entre
 * seções (que remonta a casca) não vire uma pergunta nova ao servidor.
 *
 * Falha de leitura vira `indisponivel`, nunca zero: o menu sem distintivo
 * afirma "nada novo", e afirmar isso com uma resposta que não chegou é
 * justamente o que esta fatia não pode fazer. A falha entra na janela de reuso
 * junto com os acertos, de propósito: é justamente quando o servidor está
 * recusando (um 429, o banco fora) que insistir a cada navegação piora o que
 * já está ruim.
 *
 * Nada disto depende do service worker: `/api/ouvidoria/` é `NetworkOnly`
 * (`lib/pwa/cache-runtime.ts`), então não existe resposta velha guardada no
 * aparelho para reaparecer como número certo depois de uma falha.
 */
/**
 * Por quanto tempo a última contagem serve para as telas seguintes. Curto o
 * bastante para o número não envelhecer na cara do ouvidor, longo o bastante
 * para uma sequência de navegações não virar uma sequência de requisições.
 */
export const JANELA_DE_REUSO_MS = 60_000;

/**
 * O caminho da tela de um caso. Sair dela é o único evento do app que muda o
 * número por conta própria, porque abrir o Dossiê carimba o visto no servidor.
 */
export const PREFIXO_DA_TELA_DO_CASO = "/ouvidoria/m/";

/** A última contagem e quando ela foi feita. Vive na aba, não no servidor. */
let ultimaContagem: { em: number; contagem: ContagemDeNovidades } | null = null;

/** Joga fora a contagem guardada. Existe para os testes começarem limpos. */
export function esquecerNovidades(): void {
  ultimaContagem = null;
}

export function useNovidadesOuvidoria(): ContagemDeNovidades {
  const { participante } = useCurrentParticipante();
  const pathname = usePathname();
  const daOuvidoria = temPerfilOuvidoria(participante);
  const [contagem, setContagem] = useState<ContagemDeNovidades>(
    ultimaContagem?.contagem ?? { estado: "sem_contagem" }
  );
  const telaAnterior = useRef<string | null>(null);

  useEffect(() => {
    const anterior = telaAnterior.current;
    telaAnterior.current = pathname;
    if (!daOuvidoria) {
      setContagem({ estado: "sem_contagem" });
      return;
    }
    // Só a SAÍDA da tela do caso reconta. A entrada não adianta: o carimbo é
    // gravado pela leitura do Dossiê, que acontece depois desta volta.
    const veioDeUmCaso =
      anterior !== null &&
      anterior !== pathname &&
      anterior.startsWith(PREFIXO_DA_TELA_DO_CASO);
    const aindaVale =
      ultimaContagem !== null &&
      Date.now() - ultimaContagem.em < JANELA_DE_REUSO_MS;
    if (aindaVale && !veioDeUmCaso) {
      setContagem(ultimaContagem!.contagem);
      return;
    }
    let cancelado = false;

    function guardar(nova: ContagemDeNovidades) {
      ultimaContagem = { em: Date.now(), contagem: nova };
      setContagem(nova);
    }

    async function contar() {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        const token = session?.access_token;
        // Sem sessão não há contagem nem falha a declarar: quem trata a
        // ausência de login é o layout, e não o distintivo do menu.
        if (!token) return;

        const res = await fetch("/api/ouvidoria/novidades", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (cancelado) return;
        // Perfil revogado no meio da sessão: não é falha de leitura, é um
        // número que deixou de ser desta pessoa. Anunciar "não consegui contar"
        // aqui seria prometer um distintivo que não é dela.
        if (res.status === 403) {
          guardar({ estado: "sem_contagem" });
          return;
        }
        if (!res.ok) {
          guardar({ estado: "indisponivel" });
          return;
        }
        const corpo = await res.json();
        if (cancelado) return;
        // `total: null` é o servidor dizendo que não conseguiu contar (alguma
        // das leituras caiu, e o `degradado` diz qual). Zero seria mentira.
        guardar(
          typeof corpo?.total === "number"
            ? { estado: "ok", total: corpo.total }
            : { estado: "indisponivel" }
        );
      } catch {
        if (!cancelado) guardar({ estado: "indisponivel" });
      }
    }

    contar();
    return () => {
      cancelado = true;
    };
  }, [daOuvidoria, pathname]);

  return contagem;
}
