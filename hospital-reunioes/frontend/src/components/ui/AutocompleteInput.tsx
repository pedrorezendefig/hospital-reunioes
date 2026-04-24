"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

interface AutocompleteInputProps {
  value: string;
  onChange: (next: string) => void;
  options: string[];
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  id?: string;
  name?: string;
}

export function AutocompleteInput({
  value,
  onChange,
  options,
  placeholder,
  required,
  disabled,
  className = "",
  id,
  name,
}: AutocompleteInputProps) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  const hasOptions = options.length > 0;

  const filtered = (() => {
    const termo = value.trim().toLowerCase();
    if (!termo) return options;
    return options.filter((opt) => opt.toLowerCase().includes(termo));
  })();

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  useEffect(() => {
    if (!open) setHighlight(-1);
  }, [open]);

  useEffect(() => {
    if (highlight >= filtered.length) setHighlight(filtered.length - 1);
  }, [filtered.length, highlight]);

  function handleSelect(opt: string) {
    onChange(opt);
    setOpen(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!hasOptions) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((i) => Math.min((i < 0 ? -1 : i) + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setHighlight((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && highlight >= 0 && filtered[highlight]) {
        e.preventDefault();
        handleSelect(filtered[highlight]);
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
      }
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={inputRef}
        id={id}
        name={name}
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (hasOptions) setOpen(true);
        }}
        onFocus={() => {
          if (hasOptions) setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        role={hasOptions ? "combobox" : undefined}
        aria-expanded={hasOptions ? open : undefined}
        aria-controls={hasOptions ? listboxId : undefined}
        aria-autocomplete={hasOptions ? "list" : undefined}
        autoComplete="off"
        className={hasOptions ? `${className} pr-9` : className}
      />

      {hasOptions && (
        <button
          type="button"
          tabIndex={-1}
          onClick={() => {
            setOpen((o) => !o);
            inputRef.current?.focus();
          }}
          aria-label={open ? "Fechar opções" : "Abrir opções"}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600"
        >
          <ChevronDown
            className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      )}

      {open && hasOptions && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg"
        >
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-xs text-slate-400">
              Nenhuma opção corresponde. Você pode digitar um valor livre.
            </div>
          ) : (
            filtered.map((opt, idx) => {
              const isHighlighted = highlight === idx;
              const isSelected = opt === value;
              return (
                <button
                  type="button"
                  key={opt}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => handleSelect(opt)}
                  className={`w-full px-3 py-2 text-sm text-left transition-colors ${
                    isHighlighted ? "bg-slate-50" : "hover:bg-slate-50"
                  } ${isSelected ? "text-slate-900 font-medium" : "text-slate-700"}`}
                >
                  {opt}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
