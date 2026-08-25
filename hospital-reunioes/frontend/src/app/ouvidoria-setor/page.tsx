"use client";

/**
 * Página de destino do email de acionamento (issue #325).
 *
 * O portal do setor com link tokenizado, onde o responsável lê o caso e
 * responde sem senha, é a fatia seguinte do PRD #317. Até lá o email precisa
 * apontar para algum lugar honesto: esta página confirma o protocolo que o
 * responsável recebeu e diz o que fazer enquanto o portal não existe.
 *
 * Pública de propósito, e por isso não mostra nada do caso: quem chega aqui é
 * o responsável do setor, que não tem login no app. O protocolo vem da URL e
 * nada é lido do banco.
 */

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Megaphone } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

function DestinoDoSetor() {
  const protocolo = useSearchParams().get("protocolo");

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-premium p-8 text-center">
        <div className="flex justify-center mb-6">
          <Logo />
        </div>

        <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
          <Megaphone className="w-7 h-7 text-primary" strokeWidth={1.5} />
        </div>

        <h1 className="text-xl font-bold text-slate-900">Demanda da Ouvidoria</h1>

        {protocolo && (
          <p className="mt-3 inline-block px-4 py-2 rounded-xl bg-slate-50 border border-slate-200 font-mono text-lg font-bold text-slate-800">
            {protocolo}
          </p>
        )}

        <p className="text-slate-600 text-sm leading-relaxed mt-5">
          A Ouvidoria acionou o seu setor sobre esta manifestação. O prazo e o resumo do caso estão
          no email que você recebeu.
        </p>
        <p className="text-slate-600 text-sm leading-relaxed mt-3">
          A página para responder e anexar arquivos por aqui entra na próxima entrega. Até lá,
          responda diretamente à Ouvidoria informando o número do protocolo.
        </p>
      </div>
    </main>
  );
}

export default function PortalDoSetorPage() {
  return (
    <Suspense fallback={null}>
      <DestinoDoSetor />
    </Suspense>
  );
}
