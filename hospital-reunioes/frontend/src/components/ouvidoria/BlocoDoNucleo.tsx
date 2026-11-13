"use client";

/**
 * O Núcleo de Segurança do Paciente no Dossiê (issue #1621, ADR 0088).
 *
 * Três coisas num bloco só, porque são o mesmo assunto do caso: o alerta do
 * agente com o porquê (enquanto ninguém decidiu), o selo Em análise pelo NSP
 * (depois do envio) e o botão Enviar ao NSP, sempre disponível enquanto o caso
 * não foi ao Núcleo, com ou sem o alerta. O botão pede uma confirmação antes,
 * porque o Núcleo recebe o relato integral mesmo no caso sigiloso.
 */

import { useState } from "react";
import { AlertCircle, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import {
  ALERTA_DO_NUCLEO,
  estaComONucleo,
  pedeDecisaoDoNucleo,
  SELO_DO_NUCLEO,
  type CamposDoNucleo,
} from "@/lib/ouvidoria/nucleo";

const FALHA = "Não foi possível enviar o caso ao Núcleo agora. Tente novamente.";

interface BlocoDoNucleoProps {
  caso: CamposDoNucleo & { id: string };
  token: string | null;
  /** O envio deu certo e o Dossiê na tela ficou velho. */
  onEnviado: () => void;
}

export function BlocoDoNucleo({ caso, token, onEnviado }: BlocoDoNucleoProps) {
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const comONucleo = estaComONucleo(caso);
  const alerta = pedeDecisaoDoNucleo(caso);
  const descartado = caso.nsp_decisao === "descartado";

  async function enviar() {
    if (!token) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${caso.id}/nsp`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setConfirmando(false);
        onEnviado();
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      setErro(typeof corpo.detail === "string" ? corpo.detail : FALHA);
    } catch {
      setErro(FALHA);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="space-y-2">
      {comONucleo && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-900 text-sm">
          <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-semibold">{SELO_DO_NUCLEO}</p>
            <p className="text-xs mt-0.5 text-indigo-800">
              O caso foi enviado ao Núcleo de Segurança do Paciente. A resposta e o encerramento seguem
              normalmente.
            </p>
          </div>
        </div>
      )}

      {alerta && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 text-sm">
          <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-semibold">{ALERTA_DO_NUCLEO}</p>
            {caso.nsp_justificativa_simples && (
              <p className="mt-0.5 whitespace-pre-wrap break-words">{caso.nsp_justificativa_simples}</p>
            )}
            <p className="text-xs mt-1 text-rose-800">
              Decida em Validar e acionar, ou envie agora pelo botão abaixo.
            </p>
          </div>
        </div>
      )}

      {descartado && (
        <p className="text-xs text-slate-500 px-1">
          Envio ao Núcleo descartado: {caso.nsp_decisao_motivo || "sem motivo registrado"}
        </p>
      )}

      {!comONucleo && (
        <div className="flex flex-wrap items-center gap-2">
          {!confirmando ? (
            <button
              type="button"
              onClick={() => {
                setErro(null);
                setConfirmando(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-white text-rose-700 border border-rose-200 hover:bg-rose-50 transition-colors"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              Enviar ao NSP
            </button>
          ) : (
            <div className="w-full px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-700 space-y-2">
              <p>
                O Núcleo de Segurança do Paciente recebe um email com o link do caso. A tela do link mostra o
                relato integral e o paciente, mesmo no caso sigiloso.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void enviar()}
                  disabled={enviando}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-60 transition-colors"
                >
                  {enviando && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />}
                  Confirmar envio ao NSP
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmando(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium uppercase tracking-wide text-slate-600 hover:bg-slate-100 transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {erro && (
        <div
          role="alert"
          className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erro}</span>
        </div>
      )}
    </div>
  );
}

export default BlocoDoNucleo;
