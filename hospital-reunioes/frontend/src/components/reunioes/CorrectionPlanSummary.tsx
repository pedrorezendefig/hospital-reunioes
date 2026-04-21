"use client";

import { ListChecks, X, Pencil, Plus, Trash2 } from "lucide-react";
import type { CorrectionItem } from "@/types/chat";

interface CorrectionPlanSummaryProps {
  items: CorrectionItem[];
  onRemoveItem: (index: number) => void;
}

const ACTION_CONFIG = {
  update: { icon: Pencil, label: "Alterar", color: "text-blue-600 bg-blue-50" },
  add: { icon: Plus, label: "Adicionar", color: "text-green-600 bg-green-50" },
  delete: { icon: Trash2, label: "Remover", color: "text-red-600 bg-red-50" },
} as const;

export default function CorrectionPlanSummary({ items, onRemoveItem }: CorrectionPlanSummaryProps) {
  if (items.length === 0) return null;

  return (
    <div className="bg-amber-50/50 border border-amber-100 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <ListChecks className="w-4 h-4 text-amber-600" />
        <h4 className="text-sm font-semibold text-amber-900">
          Correções pendentes ({items.length})
        </h4>
      </div>
      <div className="space-y-2">
        {items.map((item, i) => {
          const config = ACTION_CONFIG[item.action as keyof typeof ACTION_CONFIG] || ACTION_CONFIG.update;
          const Icon = config.icon;
          return (
            <div
              key={i}
              className="flex items-start gap-2 bg-white rounded-lg px-3 py-2 border border-amber-100"
            >
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${config.color} flex-shrink-0 mt-0.5`}>
                <Icon className="w-3 h-3" />
                {config.label}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-700">{item.description}</p>
              </div>
              <button
                onClick={() => onRemoveItem(i)}
                className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors flex-shrink-0"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
