"use client";

/**
 * O Ao vivo da Central de Comando: quantas pessoas estão no Site agora (issue
 * #816, ADR 0058; glossário, "Ao vivo").
 *
 * É o único número em tempo real da Central, e o único que NÃO passa pelo
 * cache: cada consulta vai direto à rota de tempo real do backend
 * (`GET /ao-vivo`), que lê a fonte de tempo real do Google. A tela consulta a
 * cada 30 segundos e na volta, e para quando sai (ADR 0050, decisão 9; o mesmo
 * desenho do Quadro de Demandas: `usePolling` para o intervalo, gatado pela aba
 * à vista). A volta é o `focus` da janela ou a aba que reaparece: trocar de aba
 * nem sempre dispara `focus` (issue #843), e quando os dois disparam juntos a
 * volta consulta uma vez só.
 *
 * Degradação silenciosa: se a consulta falha, o número não zera nem some de
 * repente, e a tela não cai. `null` é "não sei" (nunca houve número bom, ou a
 * primeira consulta falhou); quem desenha some nesse caso. Havendo um número
 * guardado, uma falha o mantém. Zero só aparece quando a fonte diz zero.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { getAuthToken } from "@/hooks/useAuth";
import { usePolling } from "@/hooks/usePolling";
import { BASE_CENTRAL } from "@/lib/central-de-comando/api";

/** A tela consulta o Ao vivo a cada 30 segundos (ADR 0050, decisão 9). */
export const INTERVALO_AO_VIVO_MS = 30 * 1000;

/**
 * A volta para a tela costuma disparar `visibilitychange` e `focus` quase
 * juntos. Uma segunda volta dentro desta janela não pede de novo.
 */
const JANELA_DA_VOLTA_MS = 2 * 1000;

const CAMINHO_AO_VIVO = `${BASE_CENTRAL}/ao-vivo`;

/**
 * Uma consulta ao Ao vivo, com a sessão do momento. Nunca levanta: devolve o
 * número de agora, ou `null` quando não deu (sem sessão, rede fora, o servidor
 * recusou, ou um corpo sem o número). `null` é "não sei", e não zero: quem lê
 * mantém o último número em vez de mostrar ninguém.
 *
 * A sessão é lida a cada consulta (`getAuthToken`), e não na abertura: a tela
 * fica aberta por horas, e o token da abertura vence em 1 hora.
 */
async function buscarAoVivo(): Promise<number | null> {
  let token: string | undefined;
  try {
    token = await getAuthToken();
  } catch {
    return null;
  }
  if (!token) return null;
  try {
    const resposta = await fetch(CAMINHO_AO_VIVO, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resposta.ok) return null;
    const corpo = (await resposta.json()) as { pessoas?: unknown };
    return typeof corpo.pessoas === "number" && Number.isFinite(corpo.pessoas) ? corpo.pessoas : null;
  } catch {
    return null;
  }
}

/**
 * O número do Ao vivo, ou `null` enquanto não há um número bom. Renovado
 * sozinho a cada 30 segundos com a aba à vista e na volta para a tela, e parado
 * quando a tela sai. A falha nunca zera nem levanta.
 */
export function useAoVivo(): number | null {
  const [pessoas, setPessoas] = useState<number | null>(null);
  const [abaVisivel, setAbaVisivel] = useState(true);
  const montado = useRef(true);

  const consultar = useCallback(async () => {
    const numero = await buscarAoVivo();
    // `null` é falha ou "não sei": mantém o que já estava, nunca zera.
    if (montado.current && numero !== null) setPessoas(numero);
  }, []);

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  // A primeira consulta, na abertura: o `usePolling` é só o intervalo, sem
  // chamada imediata, e quem abre a tela não pode esperar 30 segundos.
  useEffect(() => {
    void consultar();
  }, [consultar]);

  // A cada 30 segundos, só com a aba à vista: pedir para uma aba escondida
  // gasta rede a troco de nada, e a volta abaixo recarrega na hora.
  usePolling(() => void consultar(), INTERVALO_AO_VIVO_MS, abaVisivel);

  // A volta para a tela consulta na hora (ADR 0050, decisão 9). A aba que
  // reaparece e o foco da janela costumam chegar juntos: o segundo, dentro da
  // janela, não pede de novo.
  const ultimaVolta = useRef<number | null>(null);
  const aoVoltar = useCallback(() => {
    const agora = Date.now();
    if (ultimaVolta.current !== null && agora - ultimaVolta.current < JANELA_DA_VOLTA_MS) return;
    ultimaVolta.current = agora;
    void consultar();
  }, [consultar]);

  useEffect(() => {
    window.addEventListener("focus", aoVoltar);
    return () => window.removeEventListener("focus", aoVoltar);
  }, [aoVoltar]);

  // A aba escondida desliga o intervalo; à vista, liga e conta como volta. A
  // leitura da abertura só diz se a aba está à vista: a primeira consulta já
  // foi feita acima.
  useEffect(() => {
    const aoTrocar = () => {
      const visivel = document.visibilityState === "visible";
      setAbaVisivel(visivel);
      if (visivel) aoVoltar();
    };
    setAbaVisivel(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", aoTrocar);
    return () => document.removeEventListener("visibilitychange", aoTrocar);
  }, [aoVoltar]);

  return pessoas;
}
