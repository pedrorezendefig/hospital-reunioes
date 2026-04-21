"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, X, Check } from "lucide-react";

interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectProps {
  options: MultiSelectOption[];
  selected: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  label?: string;
  allLabel?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
}

export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = "Selecione...",
  label,
  allLabel = "Todos",
  disabled = false,
  className = "",
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const filteredOptions = options.filter((opt) =>
    opt.label.toLowerCase().includes(search.toLowerCase())
  );

  const isAllSelected = selected.length === 0;

  const toggle = useCallback(
    (value: string) => {
      if (selected.includes(value)) {
        onChange(selected.filter((v) => v !== value));
      } else {
        onChange([...selected, value]);
      }
    },
    [selected, onChange]
  );

  const clearAll = useCallback(() => {
    onChange([]);
    setOpen(false);
  }, [onChange]);

  // Fecha ao clicar fora
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className={`flex flex-col gap-1.5 relative ${className}`} ref={containerRef}>
      {label && (
        <label className="text-xs font-medium text-slate-500 uppercase">
          {label}
        </label>
      )}

      {/* Trigger */}
      <div
        role="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => !disabled && setOpen((v) => !v)}
        className={`
          relative min-h-[38px] flex flex-wrap items-center gap-1.5 px-2 py-1.5
          border border-slate-200 rounded-lg cursor-pointer select-none
          transition-all duration-150
          ${open ? "border-primary ring-1 ring-primary" : "hover:border-slate-300"}
          ${disabled ? "opacity-50 cursor-not-allowed bg-slate-50" : "bg-white"}
        `}
      >
        {isAllSelected ? (
          <span className="text-sm text-slate-400 px-1">{placeholder}</span>
        ) : (
          selected.map((val) => {
            const opt = options.find((o) => o.value === val);
            return (
              <span
                key={val}
                className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary/10 text-primary text-xs font-medium rounded-md"
              >
                {opt?.label ?? val}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(val);
                  }}
                  className="hover:text-primary-dark transition-colors"
                  aria-label={`Remover ${opt?.label ?? val}`}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            );
          })
        )}

        <ChevronDown
          className={`w-4 h-4 text-slate-400 ml-auto shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 w-full min-w-[200px] bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden animate-fade-in-up">
          {/* Search */}
          <div className="p-2 border-b border-slate-100">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar..."
              className="w-full text-sm px-2.5 py-1.5 border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              onClick={(e) => e.stopPropagation()}
              autoFocus
            />
          </div>

          {/* All option */}
          <button
            type="button"
            onClick={clearAll}
            className={`flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-left hover:bg-slate-50 transition-colors ${
              isAllSelected ? "font-semibold text-primary bg-primary/5" : "text-slate-600"
            }`}
          >
            <span className={`w-4 h-4 rounded border ${isAllSelected ? "bg-primary border-primary flex items-center justify-center" : "border-slate-300"}`}>
              {isAllSelected && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
            </span>
            {allLabel}
          </button>

          <div className="max-h-52 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">Nenhuma opção encontrada</p>
            ) : (
              filteredOptions.map((opt) => {
                const checked = selected.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggle(opt.value);
                    }}
                    className={`flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-left hover:bg-slate-50 transition-colors ${
                      checked ? "font-medium text-primary bg-primary/5" : "text-slate-700"
                    }`}
                  >
                    <span className={`w-4 h-4 rounded border shrink-0 ${checked ? "bg-primary border-primary flex items-center justify-center" : "border-slate-300"}`}>
                      {checked && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
                    </span>
                    {opt.label}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
