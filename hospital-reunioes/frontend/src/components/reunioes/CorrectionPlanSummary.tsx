"use client";

import { useState, useEffect } from "react";
import { ListChecks, X, Pencil, Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";
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
  const [isExpanded, setIsExpanded] = useState(items.length <= 2);

  useEffect(() => {
    if (items.length >= 3) setIsExpanded(false);
    else if (items.length > 0) setIsExpanded(true);
  }, [items.length]);

  if (items.length === 0) return null;

  return (
    <div className="bg-amber-50/50 border border-amber-100 rounded-xl">
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left cursor-pointer hover:bg-amber-100/40 transition-colors rounded-xl"
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-2">
          <ListChecks className="w-4 h-4 text-amber-600" />
          <h4 className="text-sm font-semibold text-amber-900">
            Correções pendentes ({items.length})
          </h4>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-amber-700" />
        ) : (
          <ChevronDown className="w-4 h-4 text-amber-700" />
        )}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
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
      )}
    </div>
  );
}
