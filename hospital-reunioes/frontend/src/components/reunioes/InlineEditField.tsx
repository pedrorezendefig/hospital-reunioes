"use client";

import { useState } from "react";
import { Edit3, Save, Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface InlineEditFieldProps {
  label: string;
  value: string;
  onSave: (v: string) => Promise<void>;
  type?: "text" | "select" | "time" | "textarea" | "date";
  options?: { label: string; value: string }[];
  icon?: LucideIcon;
}

export default function InlineEditField({
  label,
  value,
  onSave,
  type = "text",
  options,
  icon: Icon,
}: InlineEditFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(draft);
    setSaving(false);
    setEditing(false);
  };

  // Format YYYY-MM-DD -> DD/MM/YYYY for display
  const displayValue = (() => {
    if (type === "date" && value && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const [y, m, d] = value.split("-");
      return `${d}/${m}/${y}`;
    }
    return value;
  })();

  if (!editing) {
    return (
      <div className="group flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          {Icon && <Icon className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" strokeWidth={1.5} />}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-0.5">{label}</p>
            <p className="text-slate-800 text-sm font-medium">{displayValue || <span className="text-slate-300 font-normal italic">Não definido</span>}</p>
          </div>
        </div>
        <button
          onClick={() => { setDraft(value); setEditing(true); }}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 flex-shrink-0"
        >
          <Edit3 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400 font-medium">{label}</p>
      {type === "select" && options ? (
        <select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="">— Selecionar —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
        />
      ) : (
        <input
          type={type}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-dark transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          Salvar
        </button>
        <button
          onClick={() => setEditing(false)}
          className="px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-medium rounded-lg hover:bg-slate-200 transition-colors"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}
