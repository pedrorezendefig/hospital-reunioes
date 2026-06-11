"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, CheckCircle, X, ListChecks } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import ChatMessage from "./ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/types/chat";

/** Item do quadro de ações montado pelo agente (shape consumido por liberar_pendencias). */
interface AcaoRascunho {
  acao?: string;
  responsavel?: string;
  cargo?: string;
  prazo?: string | null;
}

/** Rascunho enxuto da Ata Guiada (ADR 0005): só resumo + quadro de ações. */
interface RascunhoAta {
  resumo_executivo?: string;
  quadro_atribuicoes?: AcaoRascunho[];
}

interface ChatAtaGuiadaResponse {
  reply: string;
  rascunho: RascunhoAta;
}

interface ChatAtaGuiadaProps {
  idReuniao: string;
  /** Chamado após a conclusão persistir (Reunião → AGUARDANDO_VALIDACAO). */
  onConcluido: () => void;
  onClose: () => void;
}

/**
 * Chat da Ata Guiada — o Facilitador relata a reunião por texto e o agente monta
 * um rascunho enxuto (resumo + quadro de ações). O estado da conversa vive aqui no
 * frontend e só persiste no "Concluir". Espelha o ChatCorrecao (síncrono, stateless
 * no backend). Voz e IA real entram em fatias seguintes (F2/F3).
 */
export default function ChatAtaGuiada({ idReuniao, onConcluido, onClose }: ChatAtaGuiadaProps) {
  const [messages, setMessages] = useState<ChatMessageType[]>([
    {
      role: "assistant",
      content:
        "Vamos montar a ata desta reunião por aqui. Conte o que foi tratado e o que ficou decidido — eu organizo num resumo e num quadro de ações, perguntando o responsável e o prazo de cada uma. Quando estiver bom, é só concluir.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [rascunho, setRascunho] = useState<RascunhoAta>({ resumo_executivo: "", quadro_atribuicoes: [] });
  const [concluindo, setConcluindo] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMessage: ChatMessageType = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInput("");
    setSending(true);

    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const res = await fetch(`/api/reunioes/${idReuniao}/ata-guiada/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({
          rascunho,
          messages: updatedMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) throw new Error("Erro ao enviar mensagem");

      const data: ChatAtaGuiadaResponse = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, timestamp: new Date().toISOString() },
      ]);
      if (data.rascunho) setRascunho(data.rascunho);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Desculpe, houve um erro. Tente novamente.",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, messages, idReuniao, rascunho]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleConcluir = async () => {
    if (concluindo) return;
    setConcluindo(true);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const res = await fetch(`/api/reunioes/${idReuniao}/ata-guiada/concluir`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ rascunho }),
      });
      if (!res.ok) throw new Error("Erro ao concluir");
      onConcluido();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Não consegui concluir agora. Tente novamente.",
          timestamp: new Date().toISOString(),
        },
      ]);
      setConcluindo(false);
    }
  };

  const acoes = rascunho.quadro_atribuicoes ?? [];
  const temConteudo = Boolean((rascunho.resumo_executivo || "").trim()) || acoes.length > 0;

  return (
    <div
      className="bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col"
      style={{ maxHeight: "600px" }}
    >
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Ata Guiada</h3>
            <p className="text-xs text-slate-400">Converse para montar a ata</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors">
          <X className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      {/* Mensagens */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-[200px] overscroll-contain"
      >
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {sending && (
          <div className="flex gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center">
              <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin" />
            </div>
            <div className="px-3.5 py-2.5 rounded-xl rounded-tl-sm bg-slate-50 border border-slate-100">
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Rascunho montado (resumo + ações) */}
      {temConteudo && (
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50 max-h-[220px] overflow-y-auto">
          {(rascunho.resumo_executivo || "").trim() && (
            <div className="mb-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Resumo</p>
              <p className="text-sm text-slate-700 leading-relaxed">{rascunho.resumo_executivo}</p>
            </div>
          )}
          {acoes.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
                <ListChecks className="w-3.5 h-3.5" /> Ações ({acoes.length})
              </p>
              <ul className="space-y-1.5">
                {acoes.map((a, i) => (
                  <li key={i} className="flex flex-col">
                    <span className="text-sm font-medium text-slate-800">{a.acao || "—"}</span>
                    <span className="text-xs text-slate-400">
                      {a.responsavel || "Responsável a definir"} · {a.prazo || "Prazo a definir"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Input + concluir */}
      <div className="px-5 py-3 border-t border-slate-100">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Conte o que foi tratado na reunião..."
            className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all resize-none"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || sending}
            className="px-3 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <button
          onClick={handleConcluir}
          disabled={!temConteudo || concluindo || sending}
          className="mt-2 w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-green-600 to-green-700 text-white font-medium rounded-xl hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer"
        >
          <CheckCircle className="w-4 h-4" />
          {concluindo ? "Concluindo..." : "Concluir e enviar para validação"}
        </button>
      </div>
    </div>
  );
}
