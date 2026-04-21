"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ClipboardList,
  Zap,
  CheckCircle2,
  Target,
  Mail,
  Building2,
  MapPin,
  Hash,
  ChevronRight,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import type { UserRole } from "@/types";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PerfilStats {
  reunioes: number;
  pendencias_ativas: number;
  concluidas: number;
  no_prazo_percentual: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

const ROLE_BADGE: Record<UserRole, string> = {
  diretor: "bg-gradient-to-r from-primary to-primary-light text-white",
  gerente: "bg-blue-100 text-blue-700",
  coordenador: "bg-slate-100 text-slate-600",
};

const ROLE_LABEL: Record<UserRole, string> = {
  diretor: "Diretor",
  gerente: "Gerente",
  coordenador: "Coordenador",
};

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse bg-slate-200 rounded-lg ${className ?? ""}`}
    />
  );
}

function ProfileSkeleton() {
  return (
    <div className="max-w-4xl mx-auto animate-fade-in-up">
      {/* Breadcrumb skeleton */}
      <div className="mb-6">
        <SkeletonBlock className="h-4 w-48" />
      </div>

      {/* Card skeleton */}
      <div className="bg-white rounded-2xl shadow-premium border border-border p-8 mb-8">
        <div className="flex items-start gap-6">
          <SkeletonBlock className="w-20 h-20 rounded-full shrink-0" />
          <div className="flex-1 space-y-3">
            <SkeletonBlock className="h-7 w-56" />
            <SkeletonBlock className="h-5 w-40" />
            <div className="flex gap-3">
              <SkeletonBlock className="h-6 w-24 rounded-full" />
              <SkeletonBlock className="h-6 w-16 rounded-full" />
            </div>
          </div>
        </div>
        <div className="border-t border-border mt-6 pt-6 grid grid-cols-2 md:grid-cols-3 gap-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <SkeletonBlock className="h-3 w-16" />
              <SkeletonBlock className="h-5 w-32" />
            </div>
          ))}
        </div>
      </div>

      {/* KPI skeleton */}
      <SkeletonBlock className="h-5 w-48 mb-4" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="bg-white rounded-2xl shadow-premium border border-border p-6"
          >
            <SkeletonBlock className="h-4 w-10 mb-3" />
            <SkeletonBlock className="h-8 w-12" />
            <SkeletonBlock className="h-3 w-20 mt-2" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── KPI Card ────────────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon,
  value,
  label,
  color,
}: {
  icon: React.ElementType;
  value: string | number;
  label: string;
  color: string;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-premium border border-border p-6 hover:shadow-lg transition-shadow duration-200">
      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-xl mb-3 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-3xl font-bold text-text">{value}</p>
      <p className="text-sm text-text-secondary mt-1">{label}</p>
    </div>
  );
}

// ─── Info Field ──────────────────────────────────────────────────────────────

function InfoField({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </span>
      <span className="text-sm font-medium text-text">{value}</span>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function PerfilPage() {
  const router = useRouter();
  const { token, loading: authLoading } = useAuth();
  const {
    participante,
    loading: loadingMe,
    error: errorMe,
  } = useCurrentParticipante();

  const [stats, setStats] = useState<PerfilStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.push("/login");
      return;
    }

    async function fetchStats() {
      setLoadingStats(true);
      try {
        const headers = { Authorization: `Bearer ${token}` };
        const statsRes = await fetch("/api/perfil/stats", { headers });
        const statsData = statsRes.ok ? await statsRes.json() : null;
        setStats(statsData);
      } catch (err) {
        console.error("Erro ao carregar stats do perfil:", err);
        // Stats nao sao bloqueantes — perfil renderiza sem o resumo de atividade.
      } finally {
        setLoadingStats(false);
      }
    }

    fetchStats();
  }, [token, authLoading, router]);

  // Surface erro do hook (ex: falha de rede em /api/participantes/me).
  useEffect(() => {
    if (errorMe) {
      setError("Erro ao carregar dados do perfil.");
    } else if (!loadingMe && !participante) {
      setError("Participante nao encontrado para este usuario.");
    } else {
      setError(null);
    }
  }, [errorMe, loadingMe, participante]);

  // ─── Loading ─────────────────────────────────────────────────────────────────

  if (authLoading || loadingMe || loadingStats) {
    return <ProfileSkeleton />;
  }

  // ─── Error state ─────────────────────────────────────────────────────────────

  if (error || !participante) {
    return (
      <div className="max-w-4xl mx-auto animate-fade-in-up">
        <div className="bg-white rounded-2xl shadow-premium border border-border p-12 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-50 mb-4">
            <Zap className="w-8 h-8 text-red-400" />
          </div>
          <h2 className="text-xl font-semibold text-text mb-2">
            Perfil indisponivel
          </h2>
          <p className="text-text-secondary mb-6">
            {error || "Nao foi possivel carregar os dados do perfil."}
          </p>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary-dark transition-colors"
          >
            Voltar ao Dashboard
          </button>
        </div>
      </div>
    );
  }

  // ─── Render ──────────────────────────────────────────────────────────────────

  const initials = getInitials(participante.nome_completo);
  const role = (participante.role ?? "coordenador") as UserRole;
  const roleBadgeClass = ROLE_BADGE[role] || ROLE_BADGE.coordenador;
  const roleLabel = ROLE_LABEL[role] || role;

  return (
    <div className="max-w-4xl mx-auto animate-fade-in-up">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-text-secondary mb-6">
        <Link
          href="/dashboard"
          className="hover:text-primary transition-colors"
        >
          Dashboard
        </Link>
        <ChevronRight className="w-4 h-4" />
        <span className="text-text font-medium">Meu Perfil</span>
      </nav>

      {/* Profile Card */}
      <div className="bg-white rounded-2xl shadow-premium border border-border p-8 mb-8">
        {/* Header row */}
        <div className="flex items-start gap-6">
          {/* Avatar */}
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center shrink-0">
            <span className="text-2xl font-bold text-white">{initials}</span>
          </div>

          {/* Name & badges */}
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-text truncate">
              {participante.nome_completo}
            </h1>
            <p className="text-text-secondary mt-0.5">
              {participante.cargo || "Cargo nao informado"}
            </p>
            <div className="flex items-center gap-3 mt-3">
              <span
                className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide ${roleBadgeClass}`}
              >
                {roleLabel}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${
                  participante.ativo
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-600"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    participante.ativo ? "bg-green-500" : "bg-red-400"
                  }`}
                />
                {participante.ativo ? "Ativo" : "Inativo"}
              </span>
            </div>
          </div>
        </div>

        {/* Info grid */}
        <div className="border-t border-border mt-6 pt-6 grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-5">
          <InfoField
            icon={Mail}
            label="E-mail"
            value={participante.email}
          />
          <InfoField
            icon={Building2}
            label="Setor"
            value={participante.setor || "---"}
          />
          <InfoField
            icon={MapPin}
            label="Area"
            value={participante.area || "---"}
          />
          <InfoField
            icon={Hash}
            label="ID"
            value={participante.id}
          />
        </div>
      </div>

      {/* Activity Summary */}
      {stats && (
        <>
          <h2 className="text-lg font-semibold text-text mb-4">
            Resumo de Atividade
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard
              icon={ClipboardList}
              value={stats.reunioes}
              label="Reunioes"
              color="bg-primary/10 text-primary"
            />
            <KpiCard
              icon={Zap}
              value={stats.pendencias_ativas}
              label="Pendencias Ativas"
              color="bg-amber-50 text-amber-600"
            />
            <KpiCard
              icon={CheckCircle2}
              value={stats.concluidas}
              label="Concluidas"
              color="bg-green-50 text-green-600"
            />
            <KpiCard
              icon={Target}
              value={`${stats.no_prazo_percentual}%`}
              label="No Prazo"
              color="bg-blue-50 text-blue-600"
            />
          </div>
        </>
      )}
    </div>
  );
}
