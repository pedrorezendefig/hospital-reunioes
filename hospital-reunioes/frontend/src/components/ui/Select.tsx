"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function Select({
  options,
  value,
  onChange,
  placeholder = "Selecione...",
  label,
  disabled = false,
  id,
  className = "",
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const typeAhead = useRef({ buffer: "", timer: 0 });

  const generatedId = useId();
  const triggerId = id ?? generatedId;
  const listboxId = `${triggerId}-listbox`;
  const optionId = (index: number) => `${triggerId}-option-${index}`;

  const selectedIndex = options.findIndex((opt) => opt.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  // Mantém a opção ativa visível conforme a navegação por teclado.
  useEffect(() => {
    if (!open || activeIndex < 0 || !listRef.current) return;
    const node = listRef.current.querySelector<HTMLElement>(
      `#${CSS.escape(optionId(activeIndex))}`
    );
    node?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeIndex]);

  // Fecha ao clicar fora.
  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const openList = useCallback(() => {
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  }, [selectedIndex]);

  const closeList = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const commit = useCallback(
    (index: number) => {
      const opt = options[index];
      if (!opt) return;
      onChange(opt.value);
      closeList();
    },
    [options, onChange, closeList]
  );

  // Type-ahead: acumula caracteres digitados e salta para a opção correspondente.
  const runTypeAhead = useCallback(
    (char: string) => {
      window.clearTimeout(typeAhead.current.timer);
      typeAhead.current.buffer += char.toLowerCase();
      typeAhead.current.timer = window.setTimeout(() => {
        typeAhead.current.buffer = "";
      }, 500);

      const term = typeAhead.current.buffer;
      const from = activeIndex >= 0 ? activeIndex : 0;

      // Procura a partir da próxima opção e dá a volta na lista.
      for (let step = 0; step < options.length; step++) {
        const index = (from + step) % options.length;
        if (options[index].label.toLowerCase().startsWith(term)) {
          if (open) setActiveIndex(index);
          else commit(index);
          return;
        }
      }
    },
    [activeIndex, options, open, commit]
  );

  function handleKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) {
          openList();
        } else {
          setActiveIndex((i) => Math.min(i + 1, options.length - 1));
        }
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!open) {
          openList();
        } else {
          setActiveIndex((i) => Math.max(i - 1, 0));
        }
        break;
      case "Home":
        if (open) {
          e.preventDefault();
          setActiveIndex(0);
        }
        break;
      case "End":
        if (open) {
          e.preventDefault();
          setActiveIndex(options.length - 1);
        }
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (open) commit(activeIndex);
        else openList();
        break;
      case "Escape":
        if (open) {
          e.preventDefault();
          closeList();
        }
        break;
      case "Tab":
        if (open) setOpen(false);
        break;
      default:
        if (e.key.length === 1 && !e.altKey && !e.ctrlKey && !e.metaKey) {
          runTypeAhead(e.key);
        }
    }
  }

  return (
    <div
      ref={containerRef}
      className={`flex flex-col gap-1.5 relative ${className}`}
    >
      {label && (
        <label
          htmlFor={triggerId}
          className="text-xs font-medium text-slate-500 uppercase"
        >
          {label}
        </label>
      )}

      {/* Trigger */}
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-activedescendant={
          open && activeIndex >= 0 ? optionId(activeIndex) : undefined
        }
        className={`
          relative min-h-[38px] flex items-center gap-1.5 px-3 py-1.5 w-full text-left
          border border-slate-200 rounded-lg cursor-pointer select-none
          transition-all duration-150
          ${open ? "border-primary ring-1 ring-primary" : "hover:border-slate-300"}
          ${disabled ? "opacity-50 cursor-not-allowed bg-slate-50" : "bg-white"}
        `}
      >
        <span
          className={`text-sm truncate ${
            selectedOption ? "text-slate-700" : "text-slate-400"
          }`}
        >
          {selectedOption?.label ?? placeholder}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 ml-auto shrink-0 transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-labelledby={label ? triggerId : undefined}
          className="absolute z-50 top-full mt-1 left-0 w-full min-w-[200px] max-h-60 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lg animate-fade-in-up"
        >
          {options.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-4">
              Nenhuma opção disponível
            </p>
          ) : (
            options.map((opt, index) => {
              const isSelected = opt.value === value;
              const isActive = index === activeIndex;
              return (
                <div
                  key={opt.value}
                  id={optionId(index)}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => commit(index)}
                  className={`flex items-center gap-2.5 px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                    isActive ? "bg-slate-50" : ""
                  } ${
                    isSelected
                      ? "font-medium text-primary bg-primary/5"
                      : "text-slate-700"
                  }`}
                >
                  <span className="w-4 h-4 shrink-0 flex items-center justify-center">
                    {isSelected && (
                      <Check className="w-4 h-4 text-primary" strokeWidth={3} />
                    )}
                  </span>
                  {opt.label}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
