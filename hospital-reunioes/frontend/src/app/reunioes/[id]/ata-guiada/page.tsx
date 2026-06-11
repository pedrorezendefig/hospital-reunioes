"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Sparkles, CheckCircle, Loader2, Lock, AlertTriangle } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSecretaria } from "@/lib/auth";
import AtaEnxutaView, { type RascunhoAta } from "@/components/reunioes/AtaEnxutaView";
import ChatAtaGuiada from "@/components/reunioes/ChatAtaGuiada";

interface ReuniaoMinima {
  id_reuniao: string;
  titulo: string | null;
  tipo: string | null;
  data: string;
  status_ata: string;
}

/** Aviso de tela cheia com link de volta — reaproveitado pelos estados de bloqueio. */
function TelaAviso({
  id,
  icon: Icon,
  titulo,
  texto,
}: {
  id: string;
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
          href={`/reunioes/${id}`}
          className="inline-flex items-center gap-2 mt-6 px-5 py-2.5 rounded-xl border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition-all"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar à reunião
        </Link>
      </div>
    </div>
  );
}

/**
 * Tela dedicada da Ata Guiada (ADR 0006): ata viva (resumo + quadro ao vivo, mesmo
 * visual da Ata final) + chat lateral (texto/voz). A partir de uma Reunião PROGRAMADA;
 * "Concluir e gerar pendências" finaliza a ata num clique (#66): conclui
 * (→ AGUARDANDO_VALIDACAO) e finaliza sem assinatura (→ APROVADA, liberando as
 * Pendências), levando o Facilitador direto ao calendário. Sem ClickSign, sem PDF.
 */
export default function AtaGuiadaPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();
  const { toast } = useToast();
  const { participante: currentUser } = useCurrentParticipante();

  const [reuniao, setReuniao] = useState<ReuniaoMinima | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [rascunho, setRascunho] = useState<RascunhoAta>({ resumo_executivo: "", quadro_atribuicoes: [] });
  // Seção apontada (⌖) na ata viva — dirige a próxima mensagem do chat (#58).
  const [sectionContext, setSectionContext] = useState<string | null>(null);
  const [concluindo, setConcluindo] = useState(false);
  // O passo "concluir" já passou? Guarda a re-tentativa: se a geração de pendências
  // falhar, um novo clique pula o concluir (que exigiria PROGRAMADA) e re-tenta só o
  // aprovar-sem-assinatura — idempotente, sem duplicar pendências (#66).
  const jaConcluiu = useRef(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const getToken = async () => {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    return session?.access_token;
  };

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(`/api/reunioes/${id}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error("Não foi possível abrir esta reunião.");
        setReuniao(await res.json());
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Erro ao carregar a reunião.");
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const acoes = rascunho.quadro_atribuicoes ?? [];
  const temConteudo = Boolean((rascunho.resumo_executivo || "").trim()) || acoes.length > 0;

  // Botão único (#66): conclui a ata (→ AGUARDANDO_VALIDACAO) e finaliza sem assinatura
  // (→ APROVADA, gerando as Pendências) numa tacada, levando o Facilitador direto ao
  // calendário. Os dois endpoints reaproveitados são idempotentes: se a geração de
  // pendências falhar, a Reunião fica em AGUARDANDO_VALIDACAO e o clique é re-tentável.
  const handleConcluir = async () => {
    if (concluindo || !temConteudo) return;
    setConcluindo(true);
    try {
      const token = await getToken();
      const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

      if (!jaConcluiu.current) {
        const resConcluir = await fetch(`/api/reunioes/${id}/ata-guiada/concluir`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...auth },
          body: JSON.stringify({ rascunho }),
        });
        // 400 = a Reunião não está mais PROGRAMADA — já foi concluída numa tentativa
        // anterior cuja resposta se perdeu (rede). Idempotente: segue para o aprovar,
        // que valida o estado real. Outros erros (403/404/500) são falha de verdade.
        if (!resConcluir.ok && resConcluir.status !== 400) throw new Error("concluir");
        jaConcluiu.current = true;
      }

      const resAprovar = await fetch(`/api/reunioes/${id}/aprovar-sem-assinatura`, {
        method: "POST",
        headers: auth,
      });
      if (!resAprovar.ok) throw new Error("aprovar");
      const { total_pendencias: totalPendencias = 0 } = await resAprovar.json();

      toast(`Ata concluída — ${totalPendencias} pendência(s) gerada(s).`, "success");
      router.push("/reunioes/calendario");
    } catch {
      toast("Não consegui concluir agora. Tente novamente.", "error");
      setConcluindo(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (erro || !reuniao) {
    return <TelaAviso id={id} icon={AlertTriangle} titulo="Reunião indisponível" texto={erro ?? "Tente novamente."} />;
  }

  // Secretária não tem acesso à Ata (o backend bloqueia com 403; aqui escondemos a UI).
  if (isSecretaria(currentUser)) {
    return (
      <TelaAviso
        id={id}
        icon={Lock}
        titulo="Sem acesso à Ata Guiada"
        texto="A montagem da ata é do Facilitador. Você continua com a agenda e os participantes da reunião."
      />
    );
  }

  // A Ata Guiada só se monta enquanto a Reunião está PROGRAMADA.
  if (reuniao.status_ata !== "PROGRAMADA") {
    return (
      <TelaAviso
        id={id}
        icon={AlertTriangle}
        titulo="Ata já em andamento"
        texto="Esta reunião não está mais na fase de montagem. Veja a ata e o fluxo de validação na página da reunião."
      />
    );
  }

  const titulo = reuniao.titulo || reuniao.tipo || "Reunião";
  const dataFmt = mounted ? new Date(reuniao.data + "T12:00:00").toLocaleDateString("pt-BR") : "";

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-slate-100">
        <div className="max-w-7xl mx-auto w-full px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              href={`/reunioes/${id}`}
              className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-500 flex-shrink-0"
              title="Voltar à reunião"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-primary">
                <Sparkles className="w-3.5 h-3.5" strokeWidth={2} />
                <span className="text-xs font-semibold uppercase tracking-wide">Ata Guiada</span>
              </div>
              <h1 className="text-base font-bold text-slate-900 truncate">
                {titulo}
                {dataFmt && <span className="text-slate-400 font-normal"> · {dataFmt}</span>}
              </h1>
            </div>
          </div>
          <button
            onClick={handleConcluir}
            disabled={!temConteudo || concluindo}
            className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-green-600 to-green-700 text-white text-sm font-medium rounded-xl hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer flex-shrink-0"
          >
            {concluindo ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
            <span className="hidden sm:inline">Concluir e gerar pendências</span>
            <span className="sm:hidden">Concluir</span>
          </button>
        </div>
      </header>

      {/* Ata viva (esquerda) + chat (direita) */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 grid lg:grid-cols-[1fr_minmax(360px,400px)] gap-6 items-start">
        <div className="space-y-5">
          <AtaEnxutaView
            resumoExecutivo={rascunho.resumo_executivo}
            quadro={acoes}
            secoes="ambas"
            mounted={mounted}
            correctionMode
            alvoPorAcao
            sectionContext={sectionContext}
            onSectionContext={setSectionContext}
            placeholderVazio={
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 px-6 py-16 text-center">
                <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
                  <Sparkles className="w-6 h-6 text-primary" />
                </div>
                <p className="text-slate-900 font-medium">A ata aparece aqui conforme você conversa</p>
                <p className="text-slate-500 text-sm mt-1 max-w-md mx-auto">
                  Conte ao assistente o que foi tratado e o que ficou decidido — o resumo e o quadro de ações tomam
                  forma ao vivo, com responsável e prazo de cada item.
                </p>
              </div>
            }
          />
        </div>

        <div className="lg:sticky lg:top-[5.5rem] h-[calc(100vh-7.5rem)] min-h-[460px]">
          <ChatAtaGuiada
            idReuniao={id}
            rascunho={rascunho}
            onRascunhoChange={setRascunho}
            sectionContext={sectionContext}
            onClearSectionContext={() => setSectionContext(null)}
          />
        </div>
      </main>
    </div>
  );
}
