"use client";

/**
 * O botão Elogio recebido (issue #1618, ADR 0088, decisão 2).
 *
 * O responsável do setor chega pelo link do email do elogio, sem senha, e só
 * confirma que o elogio chegou à equipe: não há resposta a escrever nem prazo.
 * Abrir a tela não confirma nada, porque leitor de email que abre link sozinho
 * para conferir se é seguro gastaria o uso único antes de a pessoa clicar. É o
 * botão que chama o servidor, e é o servidor que decide o uso único.
 */

import { useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Heart, Loader2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { mensagemDoPortal } from "@/lib/ouvidoria/setor";

const INSTAVEL = "Não foi possível confirmar agora. Tente novamente.";

export default function ElogioRecebidoPage() {
  const params = useParams();
  const token = params.token as string;

  const [enviando, setEnviando] = useState(false);
  const [protocolo, setProtocolo] = useState<string | null>(null);
  // O 503 e a falha do fetch deixam o botão: o link continua valendo. O 404 e
  // o 410 dizem que o link não serve mais, e o botão some.
  const [erro, setErro] = useState<{ mensagem: string; podeTentarDeNovo: boolean } | null>(null);

  async function confirmar() {
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria-setor/elogio/${encodeURIComponent(token)}/recebido`, {
        method: "POST",
      });
      const corpo = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro({
          mensagem: res.status >= 500 ? corpo.detail || INSTAVEL : mensagemDoPortal(res.status, corpo.detail),
          podeTentarDeNovo: res.status >= 500,
        });
        return;
      }
      setProtocolo(typeof corpo.protocolo === "string" ? corpo.protocolo : "");
    } catch {
      setErro({ mensagem: INSTAVEL, podeTentarDeNovo: true });
    } finally {
      setEnviando(false);
    }
  }

  if (protocolo !== null) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div
          data-testid="elogio-confirmado"
          className="w-full max-w-lg bg-white rounded-2xl border border-emerald-200 shadow-premium p-8 text-center space-y-4"
        >
          <div className="flex justify-center">
            <Logo />
          </div>
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
          <div className="space-y-1">
            <p className="text-slate-600 text-sm">Elogio confirmado na manifestação</p>
            <p className="text-2xl font-bold tracking-tight text-slate-900 tabular-nums">{protocolo}</p>
          </div>
          <p className="text-sm text-slate-500 leading-relaxed">
            Obrigado por compartilhar com a equipe. A Ouvidoria vai encerrar o caso e avisar quem
            elogiou. Você não precisa fazer mais nada.
          </p>
        </div>
      </main>
    );
  }

  const linkAcabou = erro !== null && !erro.podeTentarDeNovo;

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-premium p-8 text-center space-y-4">
        <div className="flex justify-center">
          <Logo />
        </div>
        <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto">
          <Heart className="w-7 h-7 text-emerald-600" strokeWidth={1.5} />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Um elogio para a sua equipe</h1>
        <p className="text-sm text-slate-600 leading-relaxed">
          O elogio e a nota da Ouvidoria estão no email que você recebeu. Confirme que o
          elogio chegou à equipe com o botão abaixo.
        </p>

        {erro && (
          <p
            role="alert"
            className="flex items-start gap-2 text-left text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5"
          >
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{erro.mensagem}</span>
          </p>
        )}

        {!linkAcabou && (
          <button
            type="button"
            onClick={() => void confirmar()}
            disabled={enviando}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
            Elogio recebido
          </button>
        )}
      </div>
    </main>
  );
}
