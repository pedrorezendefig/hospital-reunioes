"use client";

/**
 * A tela do Planejamento da Demanda (issue #1345, PRD #1344, ADR 0075).
 *
 * O botão "Planejar com a IA" do card traz para cá. A página só hospeda: o
 * gate de Super admin, a volta ao card e a conversa, que mora no
 * `PlanejamentoDaDemanda`. Quem recusa de verdade é o backend.
 */

import { use, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Lock } from "lucide-react";

import { linkDaDemanda } from "@/components/tecnologia/demandas";
import { PLANEJAR_COM_A_IA } from "@/components/tecnologia/planejamento";
import { PlanejamentoDaDemanda } from "@/components/tecnologia/PlanejamentoDaDemanda";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";

const SEM_ACESSO = "A aba Tecnologia é do Super admin. Fale com quem administra o aplicativo se você precisa entrar.";
const SEM_SESSAO =
  "Não foi possível abrir o planejamento: a sessão não está ativa ou o servidor não respondeu. Tente recarregar a página.";

export default function PlanejamentoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token, loading: carregandoAuth } = useAuth();
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const [titulo, setTitulo] = useState("");

  if (carregandoPerfil || carregandoAuth) {
    return <p className="max-w-2xl mx-auto px-6 py-16 text-center text-sm text-text-secondary">Carregando...</p>;
  }

  if (!isSuperAdmin(participante)) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center space-y-3">
        <Lock className="w-8 h-8 mx-auto text-text-secondary" />
        <h1 className="text-lg font-bold text-text-primary">Sem acesso à aba Tecnologia</h1>
        <p className="text-sm text-text-secondary">{SEM_ACESSO}</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto w-full px-6 py-6 space-y-5">
      <div className="flex items-center gap-3 min-w-0">
        <Link
          href={linkDaDemanda(id, "")}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-text-secondary flex-shrink-0"
          title="Voltar à Demanda"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div className="min-w-0">
          <h1 className="text-base font-bold text-text-primary truncate">{titulo || PLANEJAR_COM_A_IA}</h1>
          <p className="text-xs text-text-secondary">
            A IA faz as perguntas que a Vitta faria antes de começar, uma por vez. Clique numa opção, escreva a sua
            resposta ou fale no microfone. Pode sair quando quiser: a conversa fica guardada na Demanda.
          </p>
        </div>
      </div>

      {token ? (
        <PlanejamentoDaDemanda demandaId={id} token={token} onTitulo={setTitulo} />
      ) : (
        <p role="alert" className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          {SEM_SESSAO}
        </p>
      )}
    </div>
  );
}
