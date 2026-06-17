"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  AlertTriangle,
  BookOpenCheck,
  CheckCircle,
  Loader2,
  Lock,
  Undo2,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { useToast } from "@/components/ui/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import PopVivoView from "@/components/pops/PopVivoView";
import DevolucoesPanel from "@/components/pops/DevolucoesPanel";
import { ESTADO_VERSAO_POP_LABELS, type PopElaboracao } from "@/types";

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
 * Leitura da Versão completa (issue #85): Revisor e Validador leem as 11
 * seções — mesma renderização do POP vivo da elaboração — e aprovam ou
 * lançam Devolução com comentários. Os botões aparecem só no par
 * (papel designado × estado da etapa); o backend garante 403/400 de
 * qualquer forma. Demais perfis do escopo leem o histórico de Devoluções
 * (nome + timestamp) e o estado — auditoria do Gestor de Qualidade.
 */
export default function LeituraVersaoPopPage() {
  const params = useParams();
  const popId = params.id as string;
  const router = useRouter();
  const { toast } = useToast();
  const { participante } = useCurrentParticipante();

  const [dados, setDados] = useState<PopElaboracao | null>(null);
  const [loading, setLoading] = useState(true);
  const [erroStatus, setErroStatus] = useState<number | null>(null);
  const [confirmandoAprovar, setConfirmandoAprovar] = useState(false);
  const [devolvendo, setDevolvendo] = useState(false);
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
        const res = await fetch(`/api/pops/${popId}/versao`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          setErroStatus(res.status);
          return;
        }
        setDados(await res.json());
      } catch {
        setErroStatus(500);
      } finally {
        setLoading(false);
      }
    })();
  }, [popId, getToken]);

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
        titulo="POP fora do seu escopo"
        texto="A leitura desta Versão é dos designados do POP e de quem tem o Setor no escopo do perfil."
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

  const estado = dados.versao.estado;
  // A etapa ativa de quem está logado: decide os botões e os textos. O
  // backend re-aplica as guardas — isto é só apresentação.
  const etapa =
    participante?.id === dados.pop.revisor_id && estado === "EM_REVISAO"
      ? ("revisao" as const)
      : participante?.id === dados.pop.validador_id && estado === "EM_VALIDACAO"
        ? ("validacao" as const)
        : null;

  const agir = async (acao: "aprovar" | "devolver", comentarios?: string) => {
    if (!etapa) return; // botões só existem com etapa ativa; defesa extra
    const token = await getToken();
    const res = await fetch(`/api/pops/${popId}/${etapa}/${acao}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(acao === "devolver" ? { body: JSON.stringify({ comentarios }) } : {}),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      toast(typeof body?.detail === "string" ? body.detail : "Não consegui concluir a ação agora.", "error");
      return;
    }
    if (acao === "devolver") {
      toast("Versão devolvida. O Elaborador foi notificado por email.", "success");
    } else if (etapa === "revisao") {
      toast("Revisão aprovada. O Validador foi notificado por email.", "success");
    } else {
      toast("Validação aprovada. A Versão seguiu para a assinatura.", "success");
    }
    router.push("/pops");
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-slate-100">
        <div className="max-w-5xl mx-auto w-full px-6 py-3 flex items-center justify-between gap-4">
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
                <BookOpenCheck className="w-3.5 h-3.5" strokeWidth={2} />
                <span className="text-xs font-semibold uppercase tracking-wide">
                  {etapa === "revisao"
                    ? "Revisão técnica"
                    : etapa === "validacao"
                      ? "Validação final"
                      : "Leitura da Versão"}
                </span>
              </div>
              <h1 className="text-base font-bold text-slate-900 truncate">
                {dados.pop.codigo}
                <span className="text-slate-400 font-normal"> · {dados.pop.nome}</span>
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="hidden sm:inline-flex px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-semibold whitespace-nowrap">
              v{dados.versao.numero_versao} · {ESTADO_VERSAO_POP_LABELS[estado]}
            </span>
            {etapa && (
              <>
                <button
                  onClick={() => setDevolvendo(true)}
                  className="flex items-center gap-2 px-4 py-2.5 border border-amber-300 bg-amber-50 text-amber-800 text-sm font-medium rounded-xl hover:bg-amber-100 transition-all cursor-pointer"
                >
                  <Undo2 className="w-4 h-4" />
                  <span className="hidden sm:inline">Devolver com comentários</span>
                  <span className="sm:hidden">Devolver</span>
                </button>
                <button
                  onClick={() => setConfirmandoAprovar(true)}
                  className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-green-600 to-green-700 text-white text-sm font-medium rounded-xl hover:shadow-lg transition-all cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span className="hidden sm:inline">
                    {etapa === "revisao" ? "Aprovar revisão" : "Aprovar validação"}
                  </span>
                  <span className="sm:hidden">Aprovar</span>
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Versão completa — mesma renderização das seções dinâmicas da elaboração */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-6 space-y-4">
        {dados.devolucoes.length > 0 && <DevolucoesPanel devolucoes={dados.devolucoes} mounted={mounted} />}
        <PopVivoView
          pop={dados.pop}
          numeroVersao={dados.versao.numero_versao}
          rascunho={dados.rascunho ?? { secoes: [] }}
          sectionContext={null}
          mounted={mounted}
        />
      </main>

      {/* Aprovar — confirmação simples */}
      <ConfirmDialog
        open={confirmandoAprovar}
        onClose={() => setConfirmandoAprovar(false)}
        onConfirm={() => agir("aprovar")}
        title={etapa === "validacao" ? "Aprovar a Validação?" : "Aprovar a Revisão?"}
        description={
          etapa === "validacao"
            ? "A Versão segue para a assinatura digital (Em Assinatura)."
            : "A Versão segue para a Validação e o Validador é notificado por email."
        }
        confirmLabel="Aprovar"
      />

      {/* Devolver — comentários obrigatórios (a essência da Devolução) */}
      <ConfirmDialog
        open={devolvendo}
        onClose={() => setDevolvendo(false)}
        onConfirm={(comentarios) => agir("devolver", comentarios)}
        title="Devolver à elaboração?"
        description="A Versão volta ao Elaborador com os seus comentários e, no reenvio, retorna direto para você."
        confirmLabel="Devolver"
        confirmVariant="danger"
        requireReason
        reasonPlaceholder="O que precisa ser ajustado? (registrado com seu nome e horário)"
      />
    </div>
  );
}
