"use client";

import { BookOpenCheck, Library, GraduationCap, FileText } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperadminPops } from "@/lib/auth";
import { PERFIL_POP_LABELS, type PerfilPop } from "@/types";
import { SetoresManager } from "@/components/pops/SetoresManager";
import { UsuariosPopsManager } from "@/components/pops/UsuariosPopsManager";

/**
 * Área POPs (ADR 0007) — Leva 1: fundação de acesso.
 *
 * O ciclo de vida dos POPs (elaboração → revisão → validação → assinatura →
 * Biblioteca → treinamentos) chega nas próximas fatias. Nesta leva, o
 * Superadmin (POPs) cadastra Setores e gere o acesso dos usuários.
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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            icon: FileText,
            title: "Elaboração",
            text: "Elaboração assistida por IA, revisão e validação — em breve.",
          },
          {
            icon: Library,
            title: "Biblioteca",
            text: "Repositório oficial dos POPs publicados, por Setor — em breve.",
          },
          {
            icon: GraduationCap,
            title: "Treinamentos",
            text: "Capacitação da equipe nos POPs publicados — em breve.",
          },
        ].map(({ icon: Icon, title, text }) => (
          <div
            key={title}
            className="bg-white rounded-2xl border border-border shadow-premium p-5 opacity-75"
          >
            <Icon className="w-5 h-5 text-primary mb-2" />
            <h2 className="font-semibold text-text">{title}</h2>
            <p className="text-sm text-text-secondary mt-1">{text}</p>
          </div>
        ))}
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
