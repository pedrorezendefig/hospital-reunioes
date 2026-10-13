"use client";

import { Loader2, Mic, Square } from "lucide-react";

import { useToast } from "@/components/ui/Toast";
import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";
import { createClient } from "@/lib/supabase/client";

/**
 * O botão "Ditar" dos campos de texto longo de Contas médicas (issue #1145).
 *
 * Grava pelo hook de voz que a Ata guiada e o POP já usam, e a transcrição vai
 * à mesma rota (`/api/transcricao/voz`), aberta para o eixo do módulo. O texto
 * volta por `aoTranscrever` e cai no campo, onde a pessoa revisa: o botão é
 * `type="button"`, então nunca envia o formulário em que está. O aviso de
 * paciente fica fixo ao lado, porque o áudio vai a um serviço de fora.
 */
export const AVISO_DO_DITADO = "Não dite nome nem dado de paciente.";

/** O ditado entra depois do que a pessoa já escreveu, separado por espaço. */
export function juntarDitado(atual: string, ditado: string): string {
  const base = atual.trim();
  return base ? `${base} ${ditado}` : ditado;
}

export function Ditar({ campo, aoTranscrever }: { campo: string; aoTranscrever: (texto: string) => void }) {
  const { toast } = useToast();
  const { gravando, transcrevendo, iniciarGravacao, pararGravacao } = useGravacaoVoz({
    getToken: async () => {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      return session?.access_token ?? null;
    },
    onTexto: (texto) => {
      aoTranscrever(texto);
      toast("Texto ditado no campo. Revise antes de enviar.", "success");
    },
  });

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={gravando ? pararGravacao : iniciarGravacao}
        disabled={transcrevendo}
        aria-label={gravando ? `Parar o ditado: ${campo}` : `Ditar: ${campo}`}
        className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
          gravando
            ? "border-red-200 bg-red-50 text-red-600 hover:bg-red-100"
            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
        }`}
      >
        {transcrevendo ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        ) : gravando ? (
          <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
        ) : (
          <Mic className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {transcrevendo ? "Transcrevendo" : gravando ? "Parar" : "Ditar"}
      </button>
      <p className="text-xs normal-case font-normal text-slate-500">{AVISO_DO_DITADO}</p>
    </div>
  );
}
