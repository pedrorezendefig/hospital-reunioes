"use client";

import { useState, useEffect, useCallback } from "react";
import { StickyNote, Plus, Pencil, Archive, Loader2, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import type { Nota } from "@/types";

function formatarData(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function NotasPage() {
  const { toast } = useToast();

  const [notas, setNotas] = useState<Nota[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);

  // Editor: editId = null → criando nova; editId preenchido → editando existente.
  const [editorAberto, setEditorAberto] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [corpo, setCorpo] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async (tk: string) => {
    setLoading(true);
    try {
      const res = await fetch("/api/notas", {
        headers: { Authorization: `Bearer ${tk}` },
      });
      if (res.ok) {
        const data = (await res.json()) as Nota[];
        setNotas(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error("Erro ao carregar notas:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const tk = session?.access_token ?? null;
      setToken(tk);
      if (tk) {
        await carregar(tk);
      } else {
        setLoading(false);
      }
    }
    init();
  }, [carregar]);

  function abrirNova() {
    setEditId(null);
    setCorpo("");
    setEditorAberto(true);
  }

  function abrirEdicao(nota: Nota) {
    setEditId(nota.id);
    setCorpo(nota.corpo);
    setEditorAberto(true);
  }

  function fecharEditor() {
    setEditorAberto(false);
    setEditId(null);
    setCorpo("");
  }

  async function salvar() {
    const texto = corpo.trim();
    if (!texto || !token) return;
    setSalvando(true);
    try {
      const url = editId ? `/api/notas/${editId}` : "/api/notas";
      const method = editId ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ corpo: texto }),
      });
      if (res.ok) {
        toast(editId ? "Nota atualizada." : "Nota criada.", "success");
        fecharEditor();
        await carregar(token);
      } else {
        toast("Não foi possível salvar a Nota.", "error");
      }
    } catch (e) {
      console.error("Erro ao salvar nota:", e);
      toast("Erro ao salvar a Nota.", "error");
    } finally {
      setSalvando(false);
    }
  }

  async function arquivar(id: string) {
    if (!token) return;
    if (!window.confirm("Arquivar esta Nota? Ela sai do histórico ativo.")) {
      return;
    }
    try {
      const res = await fetch(`/api/notas/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast("Nota arquivada.", "success");
        setNotas((prev) => prev.filter((n) => n.id !== id));
      } else {
        toast("Não foi possível arquivar a Nota.", "error");
      }
    } catch (e) {
      console.error("Erro ao arquivar nota:", e);
      toast("Erro ao arquivar a Nota.", "error");
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Cabeçalho */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <StickyNote className="w-6 h-6 text-primary" />
            Notas
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Registros leves do que foi tratado — conversas, feedbacks e eventos.
          </p>
        </div>
        {!editorAberto && (
          <button
            onClick={abrirNova}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors shrink-0"
          >
            <Plus className="w-4 h-4" />
            Nova nota
          </button>
        )}
      </div>

      {/* Editor de corpo */}
      {editorAberto && (
        <div className="mb-6 bg-surface border border-border rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-text">
              {editId ? "Editar nota" : "Nova nota"}
            </h2>
            <button
              onClick={fecharEditor}
              className="p-1 rounded-lg text-text-secondary hover:bg-black/5 transition-colors"
              aria-label="Fechar editor"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <textarea
            value={corpo}
            onChange={(e) => setCorpo(e.target.value)}
            placeholder="Escreva o que foi tratado…"
            rows={6}
            className="w-full rounded-xl border border-border bg-bg p-3 text-sm text-text resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <div className="flex justify-end gap-2 mt-3">
            <button
              onClick={fecharEditor}
              className="px-4 py-2 rounded-xl text-sm text-text-secondary hover:bg-black/5 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={salvar}
              disabled={!corpo.trim() || salvando}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {salvando && <Loader2 className="w-4 h-4 animate-spin" />}
              Salvar
            </button>
          </div>
        </div>
      )}

      {/* Histórico */}
      {loading ? (
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : notas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <StickyNote className="w-12 h-12 text-text-secondary/40 mb-3" />
          <p className="text-text font-medium">Nenhuma nota ainda</p>
          <p className="text-sm text-text-secondary mt-1">
            Crie a primeira para registrar uma conversa ou feedback.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {notas.map((nota) => (
            <li
              key={nota.id}
              className="bg-surface border border-border rounded-2xl p-4 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-text whitespace-pre-wrap break-words flex-1">
                  {nota.corpo}
                </p>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => abrirEdicao(nota)}
                    className="p-2 rounded-lg text-text-secondary hover:bg-primary/5 hover:text-primary transition-colors"
                    aria-label="Editar nota"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => arquivar(nota.id)}
                    className="p-2 rounded-lg text-text-secondary hover:bg-red-50 hover:text-red-600 transition-colors"
                    aria-label="Arquivar nota"
                  >
                    <Archive className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {nota.created_at && (
                <p className="text-xs text-text-secondary mt-2">
                  {formatarData(nota.created_at)}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
