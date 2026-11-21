"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";

import { chamarNsp } from "@/lib/seguranca-do-paciente/membros";
import { rotuloDaFaixa, type ItemDaFila } from "@/lib/seguranca-do-paciente/triagem";
import { formatarData } from "./NotificacoesDoNucleo";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";

const COR_DA_FAIXA: Record<string, string> = {
  A: "bg-red-100 text-red-800",
  B: "bg-orange-100 text-orange-800",
  C: "bg-amber-100 text-amber-800",
  D: "bg-sky-100 text-sky-800",
  E: "bg-slate-100 text-slate-700",
};

export function SeloDaFaixa({ faixa }: { faixa: string | null }) {
  if (!faixa) {
    return (
      <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-800">
        Classificar manualmente
      </span>
    );
  }
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${COR_DA_FAIXA[faixa] ?? "bg-slate-100 text-slate-700"}`}
    >
      {rotuloDaFaixa(faixa)}
    </span>
  );
}

function diasDesde(iso: string): number {
  const ms = Date.now() - new Date(iso).getTime();
  return Number.isNaN(ms) ? 0 : Math.max(0, Math.floor(ms / 86_400_000));
}

/**
 * A fila de triagem (issue #1992): as notificações sem triagem confirmada, da
 * mais antiga para a mais nova, na ordem do servidor. Sem relato e sem quem
 * notificou: o protocolo, a faixa e o assunto sugeridos, o setor e a data.
 */
export function FilaDeTriagem() {
  const [fila, setFila] = useState<ItemDaFila[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    chamarNsp<{ fila: ItemDaFila[] }>("/api/nsp/triagem")
      .then((corpo) => vivo && setFila(corpo.fila))
      .catch((e: Error) => vivo && setErro(e.message));
    return () => {
      vivo = false;
    };
  }, []);

  if (erro) {
    return (
      <div role="alert" className={`${CARTAO} flex gap-2 items-start px-4 py-4`}>
        <AlertCircle className="w-5 h-5 shrink-0 text-red-500" aria-hidden />
        <p className="text-sm text-red-700">{erro}</p>
      </div>
    );
  }
  if (fila === null) {
    return <Loader2 className="w-5 h-5 animate-spin text-slate-400" aria-label="Carregando" />;
  }
  if (fila.length === 0) {
    return (
      <div className={`${CARTAO} flex flex-col items-center text-center gap-2 px-4 py-10`}>
        <Inbox className="w-8 h-8 text-slate-300" aria-hidden />
        <p className="text-sm font-semibold text-slate-900">Nenhuma notificação esperando a triagem.</p>
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {fila.map((item) => {
        const dias = diasDesde(item.criado_em);
        return (
          <li key={item.id}>
            <Link
              href={`/seguranca-do-paciente/notificacoes/${item.id}/triagem`}
              className={`${CARTAO} block px-4 py-4 space-y-1.5 hover:border-primary/40`}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-base font-bold text-slate-900 tabular-nums">{item.protocolo}</span>
                <SeloDaFaixa faixa={item.faixa} />
                {item.grave_ou_morte && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                    Grave ou houve morte
                  </span>
                )}
              </span>
              {item.assunto && <span className="block text-sm text-slate-800">{item.assunto}</span>}
              <span className="block text-sm text-slate-500">
                {`${item.setor ?? "Setor não informado"}`}
                {item.data_ocorrencia ? `, ${formatarData(item.data_ocorrencia)}` : ""}
                {`. Recebida há ${dias === 1 ? "1 dia" : `${dias} dias`}.`}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
