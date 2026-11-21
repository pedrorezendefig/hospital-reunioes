"use client";

import { useState } from "react";

import { MeusNumeros } from "@/components/inicio/MeusNumeros";
import { MinhaFila } from "@/components/inicio/MinhaFila";
import { QuemRespondeAVoce } from "@/components/inicio/QuemRespondeAVoce";

/**
 * O Início de cada pessoa (issue #1934, ADR 0104). Nesta etapa a tela já está
 * no menu, e o login ainda cai onde caía antes: a troca do destino vem por
 * último, para ninguém cair num Início pela metade.
 *
 * Os próprios números de 90 dias (issue #1946) e Quem responde a você (issue
 * #1943) vêm embaixo, cada um num pedido próprio: a falha de um não derruba o
 * outro. A lista do que foi entregue nos últimos 7 dias só aparece para quem
 * o Início diz que está em dia.
 */
export default function InicioPage() {
  const [emDia, setEmDia] = useState<boolean | null>(null);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <MinhaFila aoCarregar={(inicio) => setEmDia(inicio.em_dia ?? false)} />
      <MeusNumeros emDia={emDia} />
      <QuemRespondeAVoce />
    </div>
  );
}
