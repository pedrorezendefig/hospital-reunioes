"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface Props {
  label?: string;
  placeholder?: string;
  options: MultiSelectOption[];
  value: string[];
  onChange: (next: string[]) => void;
  allLabel?: string;
  className?: string;
}

/**
 * Dropdown com checkboxes — seleciona varios valores, aplica mudancas na hora.
 * Clique fora fecha. Aria-friendly. Sem dependencias externas.
 */
export function MultiSelectFilter({
  label,
  placeholder = "Selecione...",
  options,
  value,
  onChange,
  allLabel = "Todos",
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const selectedCount = value.length;
  const summary =
    selectedCount === 0
      ? allLabel
      : selectedCount === 1
        ? (options.find((o) => o.value === value[0])?.label ?? value[0])
        : `${selectedCount} selecionados`;

  function toggle(v: string) {
    if (value.includes(v)) {
      onChange(value.filter((x) => x !== v));
    } else {
      onChange([...value, v]);
    }
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange([]);
  }

  return (
    <div className={`flex flex-col gap-1 ${className}`} ref={rootRef}>
      {label && (
        <label className="text-xs font-medium text-slate-500 uppercase">
          {label}
        </label>
      )}
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between gap-2 text-sm border border-slate-200 rounded-lg p-2 bg-white text-left outline-none hover:border-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span
            className={`truncate ${selectedCount === 0 ? "text-slate-400" : "text-slate-700"}`}
          >
            {selectedCount === 0 && !options.length ? placeholder : summary}
          </span>
          <span className="flex items-center gap-1">
            {selectedCount > 0 && (
              <span
                onClick={clear}
                role="button"
                tabIndex={-1}
                className="p-0.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600"
                title="Limpar seleção"
                aria-label="Limpar seleção"
              >
                <X className="w-3.5 h-3.5" />
              </span>
            )}
            <ChevronDown
              className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
            />
          </span>
        </button>

        {open && (
          <div
            role="listbox"
            aria-multiselectable="true"
            className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg"
          >
            {options.length === 0 ? (
              <div className="px-3 py-2 text-xs text-slate-400">
                Nenhuma opção disponível.
              </div>
            ) : (
              options.map((opt) => {
                const checked = value.includes(opt.value);
                return (
                  <button
                    type="button"
                    key={opt.value}
                    role="option"
                    aria-selected={checked}
                    onClick={() => toggle(opt.value)}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-slate-50 ${
                      checked ? "bg-primary/5 text-slate-800" : "text-slate-700"
                    }`}
                  >
                    <span
                      className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                        checked
                          ? "bg-primary border-primary text-white"
                          : "border-slate-300 bg-white"
                      }`}
                    >
                      {checked && <Check className="w-3 h-3" strokeWidth={3} />}
                    </span>
                    <span className="truncate">{opt.label}</span>
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
