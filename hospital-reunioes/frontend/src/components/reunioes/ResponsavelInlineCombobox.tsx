"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Edit3, Loader2, Search, UserPlus, X } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { createClient } from "@/lib/supabase/client";
import { getErrorMessage } from "@/lib/errors";

export interface ParticipanteOpcao {
  id: string;
  nome: string;
  cargo: string;
}

interface ResponsavelInlineComboboxProps {
  reuniaoId: string;
  atribuicaoIndex: number;
  participantes: ParticipanteOpcao[];
  valorAtual: { responsavel: string; cargo: string };
  onAtualizado: (novo: { responsavel: string; cargo: string }) => void;
  disabled?: boolean;
}

export function ResponsavelInlineCombobox({
  reuniaoId,
  atribuicaoIndex,
  participantes,
  valorAtual,
  onAtualizado,
  disabled,
}: ResponsavelInlineComboboxProps) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [termo, setTermo] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [modoLivre, setModoLivre] = useState(false);
  const [nomeLivre, setNomeLivre] = useState(valorAtual.responsavel);
  const [cargoLivre, setCargoLivre] = useState(valorAtual.cargo);
  const [loading, setLoading] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtrados = useMemo(() => {
    const t = termo.trim().toLowerCase();
    if (!t) return participantes;
    return participantes.filter(
      (p) => p.nome.toLowerCase().includes(t) || (p.cargo ?? "").toLowerCase().includes(t),
    );
  }, [termo, participantes]);

  useEffect(() => {
    function clickFora(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setModoLivre(false);
      }
    }
    document.addEventListener("mousedown", clickFora);
    return () => document.removeEventListener("mousedown", clickFora);
  }, []);

  useEffect(() => {
    if (open && !modoLivre) inputRef.current?.focus();
  }, [open, modoLivre]);

  useEffect(() => {
    setHighlight(filtrados.length > 0 ? 0 : -1);
  }, [filtrados.length]);

  async function getToken(): Promise<string | undefined> {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token;
  }

  async function persistir(payload: {
    responsavel_participante_id?: string;
    responsavel?: string;
    cargo?: string;
  }) {
    setLoading(true);
    try {
      const token = await getToken();
      const res = await fetch(
        `/api/reunioes/${reuniaoId}/quadro-atribuicoes/${atribuicaoIndex}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(payload),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Erro ao atualizar responsável");
      }
      const data = await res.json();
      onAtualizado({
        responsavel: String(data?.responsavel ?? payload.responsavel ?? ""),
        cargo: String(data?.cargo ?? payload.cargo ?? ""),
      });
      setOpen(false);
      setModoLivre(false);
      toast("Responsável atualizado", "success");
    } catch (err) {
      toast(getErrorMessage(err) || "Erro ao atualizar responsável", "error");
    } finally {
      setLoading(false);
    }
  }

  function escolherParticipante(p: ParticipanteOpcao) {
    if (loading) return;
    void persistir({ responsavel_participante_id: p.id });
  }

  function aplicarLivre() {
    const nome = nomeLivre.trim();
    const cargo = cargoLivre.trim();
    if (!nome && !cargo) {
      toast("Informe ao menos o nome ou o cargo", "warning");
      return;
    }
    void persistir({ responsavel: nome, cargo });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (modoLivre) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((i) => Math.min(i + 1, filtrados.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (highlight >= 0 && filtrados[highlight]) {
        e.preventDefault();
        escolherParticipante(filtrados[highlight]);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => {
          if (disabled || loading) return;
          setOpen((v) => !v);
          setModoLivre(false);
          setTermo("");
        }}
        disabled={disabled}
        className={`group w-full text-left rounded-lg px-2 py-1 -mx-2 -my-1 border border-transparent transition-colors ${
          disabled
            ? "cursor-not-allowed opacity-60"
            : "hover:bg-primary/5 hover:border-primary/20 cursor-pointer"
        } ${open ? "bg-primary/5 border-primary/20" : ""}`}
        title="Trocar responsável"
      >
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-slate-700 truncate">
              {valorAtual.responsavel || (
                <span className="text-slate-400 italic">Sem responsável</span>
              )}
            </p>
            <p className="text-xs text-slate-400 truncate">
              {valorAtual.cargo || <span className="italic">Sem cargo</span>}
            </p>
          </div>
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin shrink-0" />
          ) : (
            <Edit3 className="w-3.5 h-3.5 text-slate-300 group-hover:text-primary shrink-0" />
          )}
        </div>
      </button>

      {open && (
        <div className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-30 max-h-80 overflow-y-auto min-w-[260px]">
          {!modoLivre && (
            <>
              <div className="px-2 pt-2 pb-1 sticky top-0 bg-white border-b border-slate-100">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    ref={inputRef}
                    type="text"
                    value={termo}
                    onChange={(e) => setTermo(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Buscar participante..."
                    className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-md focus:ring-1 focus:ring-primary/50 focus:border-primary/40 outline-none"
                  />
                </div>
              </div>

              {filtrados.length === 0 && (
                <div className="px-3 py-3 text-xs text-slate-400 italic text-center">
                  Nenhum participante encontrado
                </div>
              )}

              {filtrados.length > 0 && (
                <div className="py-1">
                  {filtrados.map((p, i) => {
                    const isHighlighted = highlight === i;
                    const isCurrent =
                      valorAtual.responsavel.trim().toLowerCase() ===
                      p.nome.trim().toLowerCase();
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => escolherParticipante(p)}
                        onMouseEnter={() => setHighlight(i)}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors ${
                          isHighlighted ? "bg-primary/5" : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-slate-800 truncate font-medium">{p.nome}</div>
                          {p.cargo && (
                            <div className="text-[11px] text-slate-400 truncate">{p.cargo}</div>
                          )}
                        </div>
                        {isCurrent && <Check className="w-3.5 h-3.5 text-primary shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              )}

              <button
                type="button"
                onClick={() => {
                  setModoLivre(true);
                  setNomeLivre(valorAtual.responsavel);
                  setCargoLivre(valorAtual.cargo);
                }}
                className="w-full border-t border-slate-100 px-3 py-2 text-left text-xs font-medium text-amber-700 hover:bg-amber-50 inline-flex items-center gap-1.5 transition-colors"
              >
                <UserPlus className="w-3.5 h-3.5" />
                Digitar livremente
              </button>
            </>
          )}

          {modoLivre && (
            <div className="p-3 space-y-2">
              <div>
                <label className="text-[10px] font-medium text-slate-500 uppercase block mb-1">
                  Nome
                </label>
                <input
                  type="text"
                  value={nomeLivre}
                  onChange={(e) => setNomeLivre(e.target.value)}
                  placeholder="Nome do responsável"
                  className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-md focus:ring-1 focus:ring-primary/50 focus:border-primary/40 outline-none"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-[10px] font-medium text-slate-500 uppercase block mb-1">
                  Cargo
                </label>
                <input
                  type="text"
                  value={cargoLivre}
                  onChange={(e) => setCargoLivre(e.target.value)}
                  placeholder="Cargo ou função"
                  className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-md focus:ring-1 focus:ring-primary/50 focus:border-primary/40 outline-none"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={aplicarLivre}
                  disabled={loading}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 bg-primary text-white text-xs font-medium px-2 py-1.5 rounded-md hover:bg-primary-dark disabled:opacity-50 transition-colors"
                >
                  <Check className="w-3.5 h-3.5" />
                  {loading ? "Salvando..." : "Aplicar"}
                </button>
                <button
                  type="button"
                  onClick={() => setModoLivre(false)}
                  className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700 px-2 py-1.5 rounded-md transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
