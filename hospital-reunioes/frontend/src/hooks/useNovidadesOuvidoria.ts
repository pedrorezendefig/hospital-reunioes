"use client";

import { useEffect, useState } from "react";
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
 * A contagem é refeita a cada navegação, e é isso que faz o número cair quando
 * o ouvidor abre os casos: abrir o Dossiê carimba o visto no servidor, e a
 * próxima tela pergunta de novo. Sem isso, o distintivo ficaria congelado no
 * número da primeira carga até alguém recarregar a página no F5.
 *
 * Falha de leitura vira `indisponivel`, nunca zero: o menu sem distintivo
 * afirma "nada novo", e afirmar isso com uma resposta que não chegou é
 * justamente o que esta fatia não pode fazer.
 */
export function useNovidadesOuvidoria(): ContagemDeNovidades {
  const { participante } = useCurrentParticipante();
  const pathname = usePathname();
  const daOuvidoria = temPerfilOuvidoria(participante);
  const [contagem, setContagem] = useState<ContagemDeNovidades>({
    estado: "sem_contagem",
  });

  useEffect(() => {
    if (!daOuvidoria) {
      setContagem({ estado: "sem_contagem" });
      return;
    }
    let cancelado = false;

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
          setContagem({ estado: "sem_contagem" });
          return;
        }
        if (!res.ok) {
          setContagem({ estado: "indisponivel" });
          return;
        }
        const corpo = await res.json();
        if (cancelado) return;
        // `total: null` é o servidor dizendo que não conseguiu contar (alguma
        // das leituras caiu, e o `degradado` diz qual). Zero seria mentira.
        setContagem(
          typeof corpo?.total === "number"
            ? { estado: "ok", total: corpo.total }
            : { estado: "indisponivel" }
        );
      } catch {
        if (!cancelado) setContagem({ estado: "indisponivel" });
      }
    }

    contar();
    return () => {
      cancelado = true;
    };
  }, [daOuvidoria, pathname]);

  return contagem;
}
