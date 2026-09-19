"use client";

/**
 * O Ao vivo da Central de Comando: quantas pessoas estão no Site agora (issue
 * #816, ADR 0058; glossário, "Ao vivo").
 *
 * É o único número em tempo real da Central, e o único que NÃO passa pelo
 * cache: cada consulta vai direto à rota de tempo real do backend
 * (`GET /ao-vivo`), que lê a fonte de tempo real do Google. A tela consulta a
 * cada 30 segundos e ao voltar o foco, e para quando sai (ADR 0050, decisão 9;
 * o mesmo desenho do Quadro de Demandas: `usePolling` para o intervalo, gatado
 * pela aba à vista, e o `focus` para recarregar na volta).
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
 * sozinho a cada 30 segundos com a aba à vista e ao voltar o foco, e parado
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
  // gasta rede a troco de nada, e o foco abaixo recarrega na volta.
  usePolling(() => void consultar(), INTERVALO_AO_VIVO_MS, abaVisivel);

  // A volta para a janela consulta na hora (ADR 0050, decisão 9).
  useEffect(() => {
    const aoFocar = () => void consultar();
    window.addEventListener("focus", aoFocar);
    return () => window.removeEventListener("focus", aoFocar);
  }, [consultar]);

  // A aba escondida desliga o intervalo; à vista, liga. Fica só com dizer se a
  // aba está à vista: recarregar na volta é do `focus`, para não pedir duas vezes.
  useEffect(() => {
    const aoTrocar = () => setAbaVisivel(document.visibilityState === "visible");
    aoTrocar();
    document.addEventListener("visibilitychange", aoTrocar);
    return () => document.removeEventListener("visibilitychange", aoTrocar);
  }, []);

  return pessoas;
}
