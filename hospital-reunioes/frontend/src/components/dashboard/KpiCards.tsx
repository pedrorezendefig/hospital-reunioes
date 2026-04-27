"use client";

import {
  AlertTriangle,
  PenLine,
  Clock,
  Loader2,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Stats {
  atasParadas: number;
  aguardamAssinatura: number;
  atrasadas: number;
  vencemEm3Dias: number;
  conformidade: number;
  totalPendencias: number;
}

export interface KpiCardsProps {
  stats: Stats | null;
  loading: boolean;
  onNavigate: (href: string) => void;
}

// ─── KPI definitions ─────────────────────────────────────────────────────────

function buildKpis(stats: Stats | null) {
  return [
    {
      id: "vencem-3dias",
      label: "Vencem em 3 dias",
      sublabel: null as string | null,
      value: stats?.vencemEm3Dias ?? 0,
      icon: Clock,
      alertColor: "border-warning/40 bg-warning/5",
      neutralColor: "border-border",
      iconColor: "text-warning",
      bgIcon: "bg-warning/10",
      href: "/pendencias?criticas=true",
    },
    {
      id: "atas-paradas",
      label: "Atas Paradas",
      sublabel: "> 3 dias" as string | null,
      value: stats?.atasParadas ?? 0,
      icon: AlertTriangle,
      alertColor: "border-warning/40 bg-warning/5",
      neutralColor: "border-border",
      iconColor: "text-warning",
      bgIcon: "bg-warning/10",
      href: "/reunioes/calendario",
    },
    {
      id: "aguardam-assinatura",
      label: "Aguardam Assinatura",
      sublabel: null as string | null,
      value: stats?.aguardamAssinatura ?? 0,
      icon: PenLine,
      alertColor: "border-primary/40 bg-primary/5",
      neutralColor: "border-border",
      iconColor: "text-primary",
      bgIcon: "bg-primary/10",
      href: "/reunioes/calendario",
    },
  ];
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function KpiCards({ stats, loading, onNavigate }: KpiCardsProps) {
  const kpis = buildKpis(stats);

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      {/* Conformidade — primeiro card */}
      <div
        onClick={() => onNavigate("/pendencias")}
        className="bg-surface rounded-2xl p-5 border border-border shadow-premium hover:shadow-premium-strong hover:-translate-y-1 transition-all duration-300 cursor-pointer animate-fade-in-up"
      >
        <div className="flex items-center justify-between mb-3">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              (stats?.conformidade ?? 0) >= 80
                ? "bg-success/10"
                : (stats?.conformidade ?? 0) >= 50
                  ? "bg-warning/10"
                  : "bg-error/10"
            }`}
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin text-slate-300" />
            ) : (
              <div className="relative w-7 h-7">
                <svg width="28" height="28" viewBox="0 0 28 28">
                  <circle
                    cx="14"
                    cy="14"
                    r="10"
                    fill="none"
                    stroke="#e2e8f0"
                    strokeWidth="3"
                  />
                  <circle
                    cx="14"
                    cy="14"
                    r="10"
                    fill="none"
                    stroke={
                      (stats?.conformidade ?? 0) >= 80
                        ? "var(--color-success)"
                        : (stats?.conformidade ?? 0) >= 50
                          ? "var(--color-warning)"
                          : "var(--color-error)"
                    }
                    strokeWidth="3"
                    strokeDasharray="62.83"
                    strokeDashoffset={
                      62.83 * (1 - (stats?.conformidade ?? 0) / 100)
                    }
                    strokeLinecap="butt"
                    transform="rotate(-90 14 14)"
                    style={{ transition: "stroke-dashoffset 0.7s ease" }}
                  />
                </svg>
              </div>
            )}
          </div>
        </div>
        {loading ? (
          <Loader2 className="w-6 h-6 animate-spin text-slate-300 mb-1" />
        ) : (
          <div
            className={`text-3xl font-bold ${
              (stats?.conformidade ?? 0) >= 80
                ? "text-success"
                : (stats?.conformidade ?? 0) >= 50
                  ? "text-warning"
                  : "text-error"
            }`}
          >
            {stats?.conformidade ?? 0}%
          </div>
        )}
        <div className="text-sm font-medium text-text-secondary mt-1">
          Conformidade
        </div>
        <div className="text-xs text-text-secondary/70 mt-0.5">
          {(stats?.totalPendencias ?? 0) - (stats?.atrasadas ?? 0)} em dia ·{" "}
          {stats?.atrasadas ?? 0} atrasadas
        </div>
      </div>

      {kpis.map((kpi, i) => {
        const Icon = kpi.icon;
        const isActive = kpi.value > 0;
        return (
          <div
            id={kpi.id}
            key={kpi.id}
            onClick={() => onNavigate(kpi.href)}
            className={`bg-surface rounded-2xl p-5 border ${
              isActive ? kpi.alertColor : kpi.neutralColor
            } shadow-premium hover:shadow-premium-strong hover:-translate-y-1 transition-all duration-300 cursor-pointer animate-fade-in-up delay-${i + 1}`}
          >
            <div className="flex items-center justify-between mb-3">
              <div
                className={`w-10 h-10 rounded-xl ${kpi.bgIcon} flex items-center justify-center`}
              >
                <Icon className={`w-5 h-5 ${kpi.iconColor}`} strokeWidth={2} />
              </div>
            </div>
            {loading ? (
              <Loader2 className="w-6 h-6 animate-spin text-slate-300 mb-1" />
            ) : (
              <div className="text-3xl font-bold text-text">{kpi.value}</div>
            )}
            <div className="text-sm font-medium text-text-secondary mt-1">
              {kpi.label}
            </div>
            {kpi.sublabel && (
              <div className="text-xs text-text-secondary/70">
                {kpi.sublabel}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
