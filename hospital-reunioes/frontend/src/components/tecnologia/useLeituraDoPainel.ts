"use client";

/**
 * A leitura do Painel da aba Tecnologia (issue #1059; nasceu na issue #641
 * para as abas "Minha vez" e Histórico, que o Painel substituiu).
 *
 * O Painel inteiro vem de uma rota só, e a busca do Histórico troca a leitura
 * a cada termo. Ela precisa de quatro defesas:
 *
 * 1. **A autenticação carregando não é "sem sessão".** O `useAuth` nasce com
 *    `{ token: null, loading: true }` e só entrega o token depois de duas idas
 *    à rede. Tratar o token nulo do primeiro render como sessão ausente pisca
 *    o alerta vermelho em toda abertura da aba, com a sessão válida.
 * 2. **A falha vira aviso, e o Painel de antes sai da tela.** Sem o `catch`, o
 *    backend fora do ar desenharia blocos zerados, indistinguíveis de "nada
 *    esperando por você", que é justamente a frase de boa notícia do Painel. E
 *    o Painel ANTERIOR também não pode ficar: embaixo do alerta vermelho, com a
 *    caixa de busca já mostrando o termo novo, ele e o contador afirmariam um
 *    resultado que esta leitura não obteve. Por isso a falha devolve `null`, e
 *    não um Painel vazio.
 * 3. **O selo de sequência, conferido DUAS vezes.** Digitar na busca deixa
 *    mais de um GET no ar, e a rede não devolve na ordem em que
 *    foi chamada. Cada leitura leva o seu número e só escreve na tela se ainda
 *    for a última: isso vale para a lista, para o aviso e para desligar a
 *    espera. A segunda conferência, depois de ler o CORPO, é o que fecha a
 *    corrida de verdade: o corpo é outra espera, e um pedido novo pode começar
 *    e terminar enquanto o corpo do velho ainda está chegando.
 * 4. **A espera começa ligada**, para a primeira pintura não ser um Painel
 *    vazio que ninguém pediu.
 *
 * Molde do `QuadroDemandas`, que resolve o mesmo problema desde a issue #639.
 * Ele continua com a cópia dele: o Quadro tem um caminho de ESCRITA (criar e
 * mover), com a regra a mais de não deixar a leitura apagar o motivo de uma
 * recusa, e o Painel só lê.
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

type Leitura<T> = {
  /** O que a última leitura boa trouxe, ou `null` quando ainda não há ou falhou. */
  dados: T | null;
  carregando: boolean;
  erro: string | null;
  recarregar: () => Promise<void>;
};

export function useLeituraDoPainel<T>({
  token,
  carregandoAuth,
  caminho,
  semSessao,
  falhaAoCarregar,
}: Opcoes): Leitura<T> {
  const [dados, setDados] = useState<T | null>(null);
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
        // O Painel de ANTES sai da tela junto. Deixá-lo desenhado embaixo do
        // alerta vermelho faria a tela afirmar um fato que esta leitura não
        // verificou, e com mais força do que uma frase: o Histórico ainda
        // contaria "3 Demandas fechadas" para uma busca que o servidor recusou.
        setDados(null);
        setErro(falhaAoCarregar);
        return;
      }
      const lidos = await resposta.json();
      // A segunda conferência do selo, e é ela que fecha a corrida. Ler o corpo
      // é outra espera: entre a guarda de cima e esta linha o JS cedeu o
      // controle, e um pedido mais novo pode ter começado E terminado nesse
      // meio tempo. Sem esta linha, o corpo GRANDE de um pedido velho (o
      // Histórico não pagina, e a busca varre a Conversa) chega depois e
      // repinta a lista por cima da resposta certa.
      if (meuPedido !== ultimoPedido.current) return;
      setDados(lidos);
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar o Painel", e);
      if (meuPedido !== ultimoPedido.current) return;
      setDados(null);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      if (meuPedido === ultimoPedido.current) setCarregando(false);
    }
  }, [token, caminho, falhaAoCarregar]);

  useEffect(() => {
    if (carregandoAuth) return;
    if (!token) {
      // Resolvida a autenticação, token nulo é sessão de verdade ausente. Sem
      // este aviso o Painel desenharia blocos vazios, calado, que é
      // indistinguível de "não há nada aqui".
      setCarregando(false);
      setErro(semSessao);
      return;
    }
    carregar();
  }, [carregandoAuth, token, carregar, semSessao]);

  return { dados, carregando, erro, recarregar: carregar };
}
