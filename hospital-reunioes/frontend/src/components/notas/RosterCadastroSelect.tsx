"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Check, Search } from "lucide-react";

type Option = { id: string; nome: string };

interface RosterCadastroSelectProps {
  options: Option[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Seletor de Colaboradores do cadastro para o roster da Nota (issue #43):
 * dropdown estilizado com busca + multi-seleção, no lugar do `<select>` nativo.
 *
 * É um "picker controlado" — não guarda seleção nem renderiza chips. A fonte da
 * verdade dos selecionados são os chips do roster acima; aqui só avisamos o pai
 * via `onToggle`. Os já marcados aparecem com ✓ (clicar de novo desmarca), e o
 * dropdown permanece aberto para marcar vários de uma vez.
 */
export function RosterCadastroSelect({
  options,
  selectedIds,
  onToggle,
  placeholder = "Adicionar do cadastro…",
  className = "",
}: RosterCadastroSelectProps) {
  const [open, setOpen] = useState(false);
  const [busca, setBusca] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const filtradas = options.filter((o) =>
    o.nome.toLowerCase().includes(busca.trim().toLowerCase()),
  );

  // Fecha ao clicar fora.
  useEffect(() => {
    function onClickFora(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setBusca("");
      }
    }
    document.addEventListener("mousedown", onClickFora);
    return () => document.removeEventListener("mousedown", onClickFora);
  }, []);

  function fechar() {
    setOpen(false);
    setBusca("");
  }

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {/* Trigger — mesma cara dos inputs da Nota */}
      <button
        type="button"
        onClick={() => (open ? fechar() : setOpen(true))}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`w-full flex items-center gap-2 rounded-xl border bg-bg p-2.5 text-sm text-left transition-colors ${
          open ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/40"
        }`}
      >
        <span className="flex-1 text-text-secondary">{placeholder}</span>
        <ChevronDown
          className={`w-4 h-4 text-text-secondary shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 w-full min-w-[220px] bg-white border border-border rounded-xl shadow-lg overflow-hidden animate-fade-in-up">
          <div className="p-2 border-b border-border">
            <div className="relative">
              <Search className="w-4 h-4 text-text-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    fechar();
                  }
                }}
                placeholder="Buscar…"
                aria-label="Buscar Colaborador do cadastro"
                className="w-full text-sm pl-8 pr-2.5 py-1.5 rounded-lg border border-border outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                autoFocus
              />
            </div>
          </div>

          <div className="max-h-52 overflow-y-auto py-1" role="listbox" aria-multiselectable="true">
            {filtradas.length === 0 ? (
              <p className="text-sm text-text-secondary text-center py-4">
                {options.length === 0 ? "Nenhum Colaborador no cadastro" : "Nada encontrado"}
              </p>
            ) : (
              filtradas.map((o) => {
                const marcado = selectedIds.includes(o.id);
                return (
                  <button
                    key={o.id}
                    type="button"
                    role="option"
                    aria-selected={marcado}
                    onClick={() => onToggle(o.id)}
                    className={`flex items-center gap-2.5 w-full px-3 py-2 text-sm text-left transition-colors hover:bg-black/5 ${
                      marcado ? "text-primary font-medium" : "text-text"
                    }`}
                  >
                    <span
                      className={`w-4 h-4 rounded border shrink-0 flex items-center justify-center ${
                        marcado ? "bg-primary border-primary" : "border-border"
                      }`}
                    >
                      {marcado && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
                    </span>
                    {o.nome}
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
