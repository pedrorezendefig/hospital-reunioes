"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle, Loader2, Lock, AlertTriangle, Sparkles, CalendarClock } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import PopVivoView from "@/components/pops/PopVivoView";
import ChatElaboracaoPop from "@/components/pops/ChatElaboracaoPop";
import DevolucoesPanel from "@/components/pops/DevolucoesPanel";
import {
  ESTADO_VERSAO_POP_LABELS,
  PERIODICIDADE_REVISAO_POP_LABELS,
  type PeriodicidadeRevisaoPop,
  type PopElaboracao,
  type RascunhoPop,
} from "@/types";

/** Aviso de tela cheia com link de volta — estados de bloqueio (padrão Ata Guiada). */
function TelaAviso({
  icon: Icon,
  titulo,
  texto,
}: {
  icon: typeof Lock;
  titulo: string;
  texto: string;
}) {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-6">
      <div className="bg-white rounded-2xl border border-border shadow-premium max-w-md w-full px-8 py-10 text-center">
        <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
          <Icon className="w-6 h-6 text-slate-500" />
        </div>
        <h1 className="text-lg font-bold text-slate-900">{titulo}</h1>
        <p className="text-sm text-slate-500 mt-1.5">{texto}</p>
        <Link
          href="/pops"
          className="inline-flex items-center gap-2 mt-6 px-5 py-2.5 rounded-xl border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition-all"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar aos POPs
        </Link>
      </div>
    </div>
  );
}

/**
 * Tela dedicada de elaboração (issue #83, padrão Ata Guiada/ADR 0006): o POP
 * vivo — as 11 seções do template institucional ao vivo — + chat lateral com
 * o consultor ONA/JCI (texto/voz, seção apontada ⌖). O rascunho persiste na
 * Versão a cada turno (reabrir recupera); o agente sugere a Periodicidade e
 * o Elaborador escolhe a final. "Aprovar versão final" → EM_REVISAO + email
 * ao Revisor. Edição exclusiva do Elaborador designado.
 */
export default function ElaboracaoPopPage() {
  const params = useParams();
  const popId = params.id as string;
  const router = useRouter();
  const { toast } = useToast();

  const [dados, setDados] = useState<PopElaboracao | null>(null);
  const [loading, setLoading] = useState(true);
  const [erroStatus, setErroStatus] = useState<number | null>(null);
  const [rascunho, setRascunho] = useState<RascunhoPop>({});
  const [periodicidadeSugerida, setPeriodicidadeSugerida] = useState<PeriodicidadeRevisaoPop | null>(null);
  const [periodicidadeEscolhida, setPeriodicidadeEscolhida] = useState<PeriodicidadeRevisaoPop | null>(null);
  const [salvandoPeriodicidade, setSalvandoPeriodicidade] = useState(false);
  // Seção apontada (⌖) no POP vivo — dirige a próxima mensagem do chat.
  const [sectionContext, setSectionContext] = useState<string | null>(null);
  const [confirmandoAprovar, setConfirmandoAprovar] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const getToken = useCallback(async () => {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    return session?.access_token;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(`/api/pops/${popId}/elaboracao`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          setErroStatus(res.status);
          return;
        }
        const data: PopElaboracao = await res.json();
        setDados(data);
        // Reabrir a tela recupera o estado: o rascunho persistido na Versão.
        setRascunho(data.rascunho ?? {});
        setPeriodicidadeSugerida(data.periodicidade_sugerida);
        setPeriodicidadeEscolhida(data.pop.periodicidade_revisao);
      } catch {
        setErroStatus(500);
      } finally {
        setLoading(false);
      }
    })();
  }, [popId, getToken]);

  const escolherPeriodicidade = async (valor: PeriodicidadeRevisaoPop) => {
    if (salvandoPeriodicidade) return;
    const anterior = periodicidadeEscolhida;
    setPeriodicidadeEscolhida(valor);
    setSalvandoPeriodicidade(true);
    try {
      const token = await getToken();
      const res = await fetch(`/api/pops/${popId}/elaboracao/periodicidade`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ periodicidade_revisao: valor }),
      });
      if (!res.ok) throw new Error();
      toast(`Periodicidade de revisão: ${PERIODICIDADE_REVISAO_POP_LABELS[valor]}.`, "success");
    } catch {
      setPeriodicidadeEscolhida(anterior);
      toast("Não consegui gravar a periodicidade. Tente novamente.", "error");
    } finally {
      setSalvandoPeriodicidade(false);
    }
  };

  const aprovarVersaoFinal = async () => {
    const token = await getToken();
    const res = await fetch(`/api/pops/${popId}/elaboracao/aprovar`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      toast(typeof body?.detail === "string" ? body.detail : "Não consegui aprovar agora.", "error");
      return;
    }
    toast("Versão final aprovada. O Revisor foi notificado por email.", "success");
    router.push("/pops");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (erroStatus === 403) {
    return (
      <TelaAviso
        icon={Lock}
        titulo="Elaboração restrita"
        texto="A elaboração deste POP é exclusiva do Elaborador designado."
      />
    );
  }

  if (erroStatus || !dados) {
    return (
      <TelaAviso
        icon={AlertTriangle}
        titulo="POP indisponível"
        texto="Não foi possível abrir este POP. Tente novamente."
      />
    );
  }

  // A edição só acontece com a Versão nas mãos do Elaborador.
  const editavel = dados.versao.estado === "A_ELABORAR" || dados.versao.estado === "EM_ELABORACAO";
  if (!editavel) {
    return (
      <TelaAviso
        icon={CheckCircle}
        titulo="Elaboração concluída"
        texto={`Esta Versão está em ${ESTADO_VERSAO_POP_LABELS[dados.versao.estado]}. A edição se encerrou ao enviar ao fluxo de revisão.`}
      />
    );
  }

  const temConteudo = Object.values(rascunho).some((v) => (v || "").trim());

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-slate-100">
        <div className="max-w-7xl mx-auto w-full px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              href="/pops"
              className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-500 flex-shrink-0"
              title="Voltar aos POPs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-primary">
                <Sparkles className="w-3.5 h-3.5" strokeWidth={2} />
                <span className="text-xs font-semibold uppercase tracking-wide">Elaboração de POP</span>
              </div>
              <h1 className="text-base font-bold text-slate-900 truncate">
                {dados.pop.codigo}
                <span className="text-slate-400 font-normal"> · {dados.pop.nome}</span>
              </h1>
            </div>
          </div>
          <button
            onClick={() => setConfirmandoAprovar(true)}
            disabled={!temConteudo}
            className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-green-600 to-green-700 text-white text-sm font-medium rounded-xl hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer flex-shrink-0"
          >
            <CheckCircle className="w-4 h-4" />
            <span className="hidden sm:inline">Aprovar versão final</span>
            <span className="sm:hidden">Aprovar</span>
          </button>
        </div>
      </header>

      {/* POP vivo (esquerda) + chat (direita) */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 grid lg:grid-cols-[1fr_minmax(360px,400px)] gap-6 items-start">
        <div className="space-y-4">
          {/* Devoluções (issue #85): os comentários do Revisor/Validador — o
              agente já os recebe como contexto em cada turno do chat */}
          {dados.devolucoes.length > 0 && <DevolucoesPanel devolucoes={dados.devolucoes} mounted={mounted} />}

          {/* Periodicidade de revisão — o agente sugere, o Elaborador decide */}
          <div className="bg-white rounded-2xl border border-border shadow-premium px-5 py-3.5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex items-center gap-2 text-slate-700">
              <CalendarClock className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold">Periodicidade de revisão</span>
            </div>
            {periodicidadeSugerida && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                <Sparkles className="w-3 h-3" />
                Agente sugere: {PERIODICIDADE_REVISAO_POP_LABELS[periodicidadeSugerida]}
              </span>
            )}
            <div className="flex items-center gap-2 ml-auto">
              <label className="text-xs text-slate-400">Escolha final</label>
              <select
                value={periodicidadeEscolhida ?? ""}
                onChange={(e) => escolherPeriodicidade(e.target.value as PeriodicidadeRevisaoPop)}
                disabled={salvandoPeriodicidade}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white disabled:opacity-60"
              >
                {(Object.keys(PERIODICIDADE_REVISAO_POP_LABELS) as PeriodicidadeRevisaoPop[]).map((p) => (
                  <option key={p} value={p}>
                    {PERIODICIDADE_REVISAO_POP_LABELS[p]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <PopVivoView
            pop={dados.pop}
            numeroVersao={dados.versao.numero_versao}
            rascunho={rascunho}
            sectionContext={sectionContext}
            onSectionContext={setSectionContext}
            mounted={mounted}
          />
        </div>

        <div className="lg:sticky lg:top-[5.5rem] h-[calc(100vh-7.5rem)] min-h-[460px]">
          <ChatElaboracaoPop
            popId={popId}
            rascunho={rascunho}
            onRascunhoChange={setRascunho}
            onPeriodicidadeSugerida={setPeriodicidadeSugerida}
            sectionContext={sectionContext}
            onClearSectionContext={() => setSectionContext(null)}
            materiaisIniciais={dados.materiais ?? []}
          />
        </div>
      </main>

      <ConfirmDialog
        open={confirmandoAprovar}
        onClose={() => setConfirmandoAprovar(false)}
        onConfirm={aprovarVersaoFinal}
        title="Aprovar versão final?"
        description="A Versão segue para a Revisão e a edição se encerra. O Revisor designado é notificado por email com o prazo."
        confirmLabel="Aprovar e enviar"
      />
    </div>
  );
}
