"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import {
  Bell,
  CheckCheck,
  AtSign,
  RefreshCw,
  MessageSquare,
  Clock,
  UserCheck,
  PenLine,
  X,
} from "lucide-react";
import { Notificacao } from "@/types";

const TIPO_CONFIG: Record<string, { icon: typeof Bell; color: string; bg: string }> = {
  MENCAO: { icon: AtSign, color: "text-primary", bg: "bg-primary/10" },
  STATUS_ALTERADO: { icon: RefreshCw, color: "text-amber-600", bg: "bg-amber-50" },
  COMENTARIO: { icon: MessageSquare, color: "text-blue-600", bg: "bg-blue-50" },
  PRAZO_PROXIMO: { icon: Clock, color: "text-red-600", bg: "bg-red-50" },
  RESPONSAVEL_ATRIBUIDO: { icon: UserCheck, color: "text-emerald-600", bg: "bg-emerald-50" },
  ACEITE_INTERNO: { icon: PenLine, color: "text-amber-600", bg: "bg-amber-50" },
};

const POLL_INTERVAL_MS = 30000;

export function NotificacoesDropdown() {
  const [open, setOpen] = useState(false);
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  // Guard contra o double-effect do React StrictMode em dev — o useEffect de
  // polling roda 2× no mount e sem esse ref o primeiro fetchCount sai duas
  // vezes em rápida sucessão (visível no log do backend).
  const pollStartedRef = useRef(false);
  const router = useRouter();

  // getSession() aciona o auto-refresh do supabase-js quando o access_token
  // está a <60s de expirar, então pedir a sessão a cada request evita 401
  // silencioso em abas abertas por mais de 1h (TTL padrão do JWT).
  const getAuthHeaders = useCallback(async (): Promise<HeadersInit | null> => {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) return null;
    return { Authorization: `Bearer ${session.access_token}` };
  }, []);

  // Fetch count
  const fetchCount = useCallback(async () => {
    try {
      const headers = await getAuthHeaders();
      if (!headers) return;
      const res = await fetch("/api/notificacoes/count", { headers });
      if (res.ok) {
        const data = await res.json();
        setCount(data.nao_lidas ?? 0);
      }
    } catch (e) {
      console.error("Erro ao buscar contagem:", e);
    }
  }, [getAuthHeaders]);

  // Fetch notifications list
  const fetchNotificacoes = useCallback(async () => {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      if (!headers) return;
      const res = await fetch("/api/notificacoes?limit=20", { headers });
      if (res.ok) setNotificacoes(await res.json());
    } catch (e) {
      console.error("Erro ao buscar notificações:", e);
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  // Poll for count
  useEffect(() => {
    if (pollStartedRef.current) return;
    pollStartedRef.current = true;
    fetchCount();
    const interval = setInterval(fetchCount, POLL_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      pollStartedRef.current = false;
    };
  }, [fetchCount]);

  // Fetch list when opening
  useEffect(() => {
    if (open) fetchNotificacoes();
  }, [open, fetchNotificacoes]);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  // Mark one as read
  async function handleMarkRead(notif: Notificacao) {
    try {
      const headers = await getAuthHeaders();
      if (!headers) return;
      await fetch(`/api/notificacoes/${notif.id}/lida`, {
        method: "PATCH",
        headers,
      });
      setNotificacoes((prev) =>
        prev.map((n) => (n.id === notif.id ? { ...n, lida: true } : n))
      );
      setCount((c) => Math.max(0, c - 1));
    } catch (e) {
      console.error(e);
    }

    // Navigate: os tipos comuns apontam para a pendência relacionada no
    // kanban. O aceite interno guarda o id da reunião, não o token (issue
    // #295): o link vem do endpoint autenticado, que só atende o próprio
    // destinatário e mantém o banco hash-only.
    if (notif.referencia_id) {
      setOpen(false);
      if (notif.tipo === "ACEITE_INTERNO") {
        await irParaOAceite(notif.referencia_id);
      } else {
        router.push(`/pendencias/kanban?highlight=${notif.referencia_id}`);
      }
    }
  }

  // Pede o link de aceite ao backend e navega. Sem link (aceite já registrado,
  // ata fora do modo interno, token de outra pessoa) leva à reunião, que é
  // onde a pessoa entende o que aconteceu.
  async function irParaOAceite(idReuniao: string) {
    try {
      const headers = await getAuthHeaders();
      if (!headers) return;
      const res = await fetch("/api/aceite/meu-link", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ id_reuniao: idReuniao }),
      });
      if (res.ok) {
        const { url } = await res.json();
        router.push(url);
        return;
      }
    } catch (e) {
      console.error(e);
    }
    router.push(`/reunioes/${idReuniao}`);
  }

  // Mark all as read
  async function handleMarkAllRead() {
    try {
      const headers = await getAuthHeaders();
      if (!headers) return;
      await fetch("/api/notificacoes/ler-todas", {
        method: "PATCH",
        headers,
      });
      setNotificacoes((prev) => prev.map((n) => ({ ...n, lida: true })));
      setCount(0);
    } catch (e) {
      console.error(e);
    }
  }

  function timeAgo(dateStr?: string): string {
    if (!dateStr) return "";
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    const diff = Math.floor((now - then) / 1000);
    if (diff < 60) return "agora";
    if (diff < 3600) return `${Math.floor(diff / 60)}min`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
  }

  return (
    <div ref={dropdownRef} className="relative">
      {/* Bell Button */}
      <button
        onClick={() => setOpen(!open)}
        className="relative w-10 h-10 rounded-xl hover:bg-slate-100 flex items-center justify-center text-slate-500 hover:text-slate-700 transition-colors"
        aria-label="Notificações"
      >
        <Bell className="w-5 h-5" strokeWidth={1.5} />
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center px-1 animate-pulse">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 mt-2 w-[380px] bg-white border border-slate-200 rounded-2xl shadow-premium-strong z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-800">Notificações</h3>
            <div className="flex items-center gap-2">
              {count > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-xs text-primary hover:text-primary-dark font-medium flex items-center gap-1 transition-colors"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Ler todas
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="w-6 h-6 rounded-md hover:bg-slate-100 flex items-center justify-center text-slate-400"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* List */}
          <div className="max-h-[400px] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-10">
                <div className="w-5 h-5 border-2 border-slate-200 border-t-primary rounded-full animate-spin" />
              </div>
            ) : notificacoes.length === 0 ? (
              <div className="text-center py-10 text-slate-400">
                <Bell className="w-8 h-8 mx-auto mb-2 text-slate-200" />
                <p className="text-sm">Sem notificações</p>
              </div>
            ) : (
              notificacoes.map((notif) => {
                const cfg = TIPO_CONFIG[notif.tipo] || TIPO_CONFIG.COMENTARIO;
                const Icon = cfg.icon;

                return (
                  <button
                    key={notif.id}
                    onClick={() => handleMarkRead(notif)}
                    className={`flex items-start gap-3 w-full px-4 py-3 text-left transition-colors hover:bg-slate-50 border-b border-slate-50 last:border-0 ${
                      !notif.lida ? "bg-primary/[0.02]" : ""
                    }`}
                  >
                    {/* Icon */}
                    <div
                      className={`w-8 h-8 rounded-lg ${cfg.bg} flex items-center justify-center shrink-0 mt-0.5`}
                    >
                      <Icon className={`w-4 h-4 ${cfg.color}`} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p
                        className={`text-sm leading-snug ${
                          !notif.lida
                            ? "font-semibold text-slate-800"
                            : "text-slate-600"
                        }`}
                      >
                        {notif.titulo}
                      </p>
                      {notif.mensagem && (
                        <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">
                          {notif.mensagem}
                        </p>
                      )}
                      <span className="text-[10px] text-slate-400 mt-1 block">
                        {timeAgo(notif.created_at)}
                      </span>
                    </div>

                    {/* Unread indicator */}
                    {!notif.lida && (
                      <div className="w-2 h-2 rounded-full bg-primary shrink-0 mt-2" />
                    )}
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
