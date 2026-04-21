import { StatusPendencia } from "@/types";
import {
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  RotateCcw,
} from "lucide-react";

/**
 * Unified STATUS_CONFIG for pendencias.
 *
 * Merges properties used across:
 *   - pendencias/page.tsx        (label, color, bg, icon)
 *   - pendencias/kanban/page.tsx  (label, color, textColor, bg, bgLight, borderColor, headerGradient, icon)
 *   - PendenciaDetailModal.tsx   (label, color, bg, icon)
 *
 * `color` – in page.tsx / modal it was a Tailwind text-color class (e.g. "text-[#D99B4B]");
 *           in kanban it was a raw hex (e.g. "#FFC067").
 * To keep backward-compat with both usages we expose:
 *   - `color`       → Tailwind text-color class (page + modal usage)
 *   - `rawColor`    → raw hex string (kanban header gradient / column accent)
 *   - `textColor`   → Tailwind text class for card body text (kanban cards)
 *   - `bg`          → badge background (page + modal: semi-transparent; kanban: solid)
 *   - `bgSolid`     → solid Tailwind bg class (kanban column header dot)
 *   - `bgLight`     → very light column background (kanban)
 *   - `borderColor` → border class (kanban column)
 *   - `headerGradient` → gradient classes for kanban column header
 *   - `icon`        → LucideIcon component
 */
export const PENDENCIA_STATUS_CONFIG: Record<
  StatusPendencia,
  {
    label: string;
    /** Tailwind text-color class for badges (e.g. "text-[#D99B4B]") */
    color: string;
    /** Raw hex color (e.g. "#FFC067") used by kanban column accents */
    rawColor: string;
    /** Tailwind text class for kanban card body text */
    textColor: string;
    /** Badge background — semi-transparent for badge usage */
    bg: string;
    /** Solid Tailwind bg class for kanban column header */
    bgSolid: string;
    /** Very light column background (kanban) */
    bgLight: string;
    /** Border class (kanban column) */
    borderColor: string;
    /** Gradient classes for kanban column header */
    headerGradient: string;
    /** Lucide icon component */
    icon: typeof Clock;
  }
> = {
  PENDENTE: {
    label: "Pendente",
    color: "text-[#D99B4B]",
    rawColor: "#FFC067",
    textColor: "text-amber-900/80",
    bg: "bg-[#FFC067]/20",
    bgSolid: "bg-[#FFC067]",
    bgLight: "bg-amber-50/50",
    borderColor: "border-amber-100",
    headerGradient: "from-[#FFC067] to-[#FFAB40]",
    icon: Clock,
  },
  EM_PROGRESSO: {
    label: "Em Progresso",
    color: "text-[#4A90E2]",
    rawColor: "#7CC2F2",
    textColor: "text-blue-900/80",
    bg: "bg-[#7CC2F2]/20",
    bgSolid: "bg-[#7CC2F2]",
    bgLight: "bg-blue-50/50",
    borderColor: "border-blue-100",
    headerGradient: "from-[#7CC2F2] to-[#64B5F6]",
    icon: RotateCcw,
  },
  CONCLUIDO: {
    label: "Concluido",
    color: "text-[#388E3C]",
    rawColor: "#88D7A4",
    textColor: "text-emerald-900/80",
    bg: "bg-[#88D7A4]/20",
    bgSolid: "bg-[#88D7A4]",
    bgLight: "bg-emerald-50/50",
    borderColor: "border-emerald-100",
    headerGradient: "from-[#88D7A4] to-[#66BB6A]",
    icon: CheckCircle2,
  },
  ATRASADO: {
    label: "Atrasado",
    color: "text-[#D32F2F]",
    rawColor: "#FC9D9D",
    textColor: "text-red-900/80",
    bg: "bg-[#FC9D9D]/20",
    bgSolid: "bg-[#FC9D9D]",
    bgLight: "bg-red-50/50",
    borderColor: "border-red-100",
    headerGradient: "from-[#FC9D9D] to-[#FF8A80]",
    icon: AlertCircle,
  },
  CANCELADO: {
    label: "Cancelado",
    color: "text-slate-500",
    rawColor: "#94a3b8",
    textColor: "text-slate-500",
    bg: "bg-slate-100",
    bgSolid: "bg-slate-300",
    bgLight: "bg-slate-50",
    borderColor: "border-slate-200",
    headerGradient: "from-slate-300 to-slate-400",
    icon: XCircle,
  },
  REPACTUADA: {
    label: "Repactuada",
    color: "text-[#C084FC]",
    rawColor: "#C084FC",
    textColor: "text-purple-900/80",
    bg: "bg-[#C084FC]/20",
    bgSolid: "bg-[#C084FC]",
    bgLight: "bg-purple-50/50",
    borderColor: "border-purple-100",
    headerGradient: "from-[#C084FC] to-[#A855F7]",
    icon: RotateCcw,
  },
};

export const ALL_STATUSES = Object.keys(PENDENCIA_STATUS_CONFIG) as StatusPendencia[];
