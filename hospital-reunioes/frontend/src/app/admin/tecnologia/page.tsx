"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { TecnologiaModulo } from "@/components/tecnologia/TecnologiaModulo";

/** `?demanda=<id>` é o aviso do sino da Conversa da Demanda (issue #1537). */
function TecnologiaComADemandaDoSino() {
  const demanda = useSearchParams().get("demanda");
  return <TecnologiaModulo demandaInicial={demanda} />;
}

export default function TecnologiaPage() {
  return (
    <Suspense fallback={null}>
      <TecnologiaComADemandaDoSino />
    </Suspense>
  );
}
