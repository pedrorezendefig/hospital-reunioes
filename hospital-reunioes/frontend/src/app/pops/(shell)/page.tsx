"use client";

import Link from "next/link";
import { BookOpenCheck, Library, GraduationCap } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperadminPops } from "@/lib/auth";
import { PERFIL_POP_LABELS, type PerfilPop } from "@/types";
import { PopsManager } from "@/components/pops/PopsManager";
import { SetoresManager } from "@/components/pops/SetoresManager";
import { UsuariosPopsManager } from "@/components/pops/UsuariosPopsManager";

/**
 * Área POPs (ADR 0007) — Leva 1.
 *
 * Criação pelo formulário institucional e lista por estado (issue #82) para
 * os 4 perfis, cada um no seu escopo. A elaboração com agente, Biblioteca e
 * treinamentos chegam nas próximas fatias. O Superadmin (POPs) segue
 * cadastrando Setores e gerindo o acesso dos usuários.
 */
export default function PopsPage() {
  const { participante, loading } = useCurrentParticipante();
  const superadmin = isSuperadminPops(participante);
  const perfil = participante?.perfil_pop as PerfilPop | undefined;

  return (
    <div className="animate-fade-in-up space-y-8">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <BookOpenCheck className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Gestão de POPs</h1>
          <p className="text-sm text-text-secondary">
            Procedimentos Operacionais Padrão do HSM
            {perfil ? ` · seu perfil: ${PERFIL_POP_LABELS[perfil]}` : ""}
          </p>
        </div>
      </div>

      <PopsManager />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link
          href="/pops/biblioteca"
          className="bg-white rounded-2xl border border-border shadow-premium p-5 transition hover:border-primary/40 hover:shadow-lg"
        >
          <Library className="w-5 h-5 text-primary mb-2" />
          <h2 className="font-semibold text-text">Biblioteca</h2>
          <p className="text-sm text-text-secondary mt-1">
            Repositório oficial dos POPs publicados, por Setor, com o PDF assinado.
          </p>
        </Link>
        <div className="bg-white rounded-2xl border border-border shadow-premium p-5 opacity-75">
          <GraduationCap className="w-5 h-5 text-primary mb-2" />
          <h2 className="font-semibold text-text">Treinamentos</h2>
          <p className="text-sm text-text-secondary mt-1">
            Capacitação da equipe nos POPs publicados — em breve.
          </p>
        </div>
      </div>

      {!loading && superadmin && (
        <div className="space-y-8">
          <SetoresManager />
          <UsuariosPopsManager />
        </div>
      )}
    </div>
  );
}
