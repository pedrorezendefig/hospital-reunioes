"use client";

/**
 * A leitura de uma lista de Demandas da aba Tecnologia (issue #641).
 *
 * As abas "Minha vez" e Histórico pedem listas diferentes à mesma API, e
 * precisam das MESMAS quatro defesas. Escrever as quatro duas vezes seria
 * escrevê-las de dois jeitos, e a segunda cópia é onde o defeito mora:
 *
 * 1. **A autenticação carregando não é "sem sessão".** O `useAuth` nasce com
 *    `{ token: null, loading: true }` e só entrega o token depois de duas idas
 *    à rede. Tratar o token nulo do primeiro render como sessão ausente pisca
 *    o alerta vermelho em toda abertura da aba, com a sessão válida.
 * 2. **A falha de rede vira aviso, e não lista vazia.** Sem o `catch`, o
 *    backend fora do ar desenharia uma lista zerada, indistinguível de "nada
 *    esperando por você", que é justamente a frase de boa notícia da aba.
 * 3. **O selo de sequência.** Trocar o filtro ou digitar na busca deixa mais de
 *    um GET no ar, e a rede não devolve na ordem em que foi chamada. Cada
 *    leitura leva o seu número e só escreve na tela se ainda for a última:
 *    isso vale para a lista, para o aviso e para desligar a espera. Desligar a
 *    espera na resposta velha diria "pronto" com a leitura de verdade ainda
 *    vindo.
 * 4. **A espera começa ligada**, para a primeira pintura não ser uma lista
 *    vazia que ninguém pediu.
 *
 * Molde do `QuadroDemandas`, que resolve o mesmo problema desde a issue #639.
 * Ele continua com a cópia dele: o Quadro tem um caminho de ESCRITA (criar e
 * mover), com a regra a mais de não deixar a leitura apagar o motivo de uma
 * recusa, e estas duas abas só leem.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { BASE_TECNOLOGIA, FALHA_DE_CONEXAO } from "./demandas";

type Opcoes = {
  token: string | null;
  carregandoAuth: boolean;
  /** O que vem depois de `/api/admin/tecnologia`, com a query já montada. */
  caminho: string;
  /** A frase de quando a autenticação terminou sem token. */
  semSessao: string;
  /** A frase de quando o servidor respondeu, mas com erro. */
  falhaAoCarregar: string;
};

type Lista<T> = {
  itens: T[];
  carregando: boolean;
  erro: string | null;
  recarregar: () => Promise<void>;
};

export function useListaDeDemandas<T>({
  token,
  carregandoAuth,
  caminho,
  semSessao,
  falhaAoCarregar,
}: Opcoes): Lista<T> {
  const [itens, setItens] = useState<T[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const ultimoPedido = useRef(0);

  const carregar = useCallback(async () => {
    if (!token) return;
    const meuPedido = ultimoPedido.current + 1;
    ultimoPedido.current = meuPedido;
    setCarregando(true);
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}${caminho}`, {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      // Chegou tarde: já há um pedido mais novo no ar, e o que esta resposta
      // conta não é mais o que a tela está pedindo.
      if (meuPedido !== ultimoPedido.current) return;
      if (!resposta.ok) {
        setErro(falhaAoCarregar);
        return;
      }
      setItens(await resposta.json());
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar a lista", e);
      if (meuPedido !== ultimoPedido.current) return;
      setErro(FALHA_DE_CONEXAO);
    } finally {
      if (meuPedido === ultimoPedido.current) setCarregando(false);
    }
  }, [token, caminho, falhaAoCarregar]);

  useEffect(() => {
    if (carregandoAuth) return;
    if (!token) {
      // Resolvida a autenticação, token nulo é sessão de verdade ausente. Sem
      // este aviso a aba desenharia a lista vazia, calada, que é
      // indistinguível de "não há nada aqui".
      setCarregando(false);
      setErro(semSessao);
      return;
    }
    carregar();
  }, [carregandoAuth, token, carregar, semSessao]);

  return { itens, carregando, erro, recarregar: carregar };
}
