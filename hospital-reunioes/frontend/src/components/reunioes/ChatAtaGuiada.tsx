"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, Mic, Square, Crosshair, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";
import ChatMessage from "./ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/types/chat";
import type { RascunhoAta } from "./AtaEnxutaView";

interface ChatAtaGuiadaResponse {
  reply: string;
  rascunho: RascunhoAta;
}

interface ChatAtaGuiadaProps {
  idReuniao: string;
  /** Rascunho vivo — controlado pela tela dedicada (single source of truth). */
  rascunho: RascunhoAta;
  /** Reporta o rascunho atualizado a cada turno para a ata viva refletir ao lado. */
  onRascunhoChange: (rascunho: RascunhoAta) => void;
  /** Seção apontada (⌖) na ata viva, ou null. A próxima mensagem é dirigida a ela (#58). */
  sectionContext: string | null;
  /** Limpa a seção apontada (no botão do chip ou após enviar a mensagem). */
  onClearSectionContext: () => void;
}

/**
 * Painel de conversa da Ata Guiada — o Facilitador relata a reunião por texto ou voz
 * e o agente devolve o rascunho enxuto (resumo + quadro de ações) atualizado. O chat
 * é **controlado**: o rascunho vive na tela dedicada (que o mostra ao vivo no
 * `AtaEnxutaView` ao lado) e a conclusão acontece lá. Espelha o ChatCorrecao
 * (síncrono, stateless no backend). A voz reusa o hook useGravacaoVoz das Notas (#50).
 */
export default function ChatAtaGuiada({
  idReuniao,
  rascunho,
  onRascunhoChange,
  sectionContext,
  onClearSectionContext,
}: ChatAtaGuiadaProps) {
  const [messages, setMessages] = useState<ChatMessageType[]>([
    {
      role: "assistant",
      content:
        "Vamos montar a ata desta reunião por aqui. Conte o que foi tratado e o que ficou decidido — eu organizo num resumo e num quadro de ações, perguntando o responsável e o prazo de cada uma. A ata vai tomando forma ao lado; quando estiver boa, é só concluir.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { toast } = useToast();

  // Ditar o relato por voz (issue #50): reusa o hook compartilhado das Notas —
  // grava, transcreve pelo serviço existente e o texto cai EDITÁVEL no input
  // para o Facilitador revisar antes de enviar. Falha → toast + digitação.
  const { gravando, transcrevendo, iniciarGravacao, pararGravacao } = useGravacaoVoz({
    getToken: async () => {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      return session?.access_token ?? null;
    },
    onTexto: (texto) => {
      setInput((prev) => (prev.trim() ? `${prev.trim()} ${texto}` : texto));
      toast("Texto transcrito. Revise antes de enviar.", "success");
    },
  });

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  // Apontou uma seção (⌖) → foca o input pra já digitar a correção (como o ChatCorrecao).
  useEffect(() => {
    if (sectionContext) inputRef.current?.focus();
  }, [sectionContext]);

  const sendMessage = useCallback(async () => {
    const capturedSectionContext = sectionContext;
    const text = input.trim();
    if (!text || sending) return;

    const userMessage: ChatMessageType = {
      role: "user",
      // Mesma marcação da correção de transcrição: a seção apontada (⌖) entra no
      // início da mensagem; o agente concentra a correção nela (#58).
      content: capturedSectionContext ? `[Seção: ${capturedSectionContext}]\n${text}` : text,
      timestamp: new Date().toISOString(),
    };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInput("");
    onClearSectionContext();
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
          section_context: capturedSectionContext,
        }),
      });

      if (!res.ok) throw new Error("Erro ao enviar mensagem");

      const data: ChatAtaGuiadaResponse = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, timestamp: new Date().toISOString() },
      ]);
      // O rascunho é controlado pela tela: reporta o turno para a ata viva refletir.
      // Se um turno falhar, o rascunho anterior é preservado (não é tocado aqui).
      if (data.rascunho) onRascunhoChange(data.rascunho);
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
  }, [input, sending, messages, idReuniao, rascunho, onRascunhoChange, sectionContext, onClearSectionContext]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2.5 flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <Bot className="w-4 h-4 text-primary" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900">Assistente da Ata</h3>
          <p className="text-xs text-slate-400">Converse para montar a ata</p>
        </div>
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

      {/* Chip da seção apontada (⌖) — mesmo padrão da correção de transcrição */}
      {sectionContext && (
        <div className="px-5 pt-2 flex-shrink-0">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
            <Crosshair className="w-3 h-3" />
            Apontando: {sectionContext}
            <button onClick={onClearSectionContext} className="ml-1 hover:text-primary-dark" aria-label="Limpar seção apontada">
              <X className="w-3 h-3" />
            </button>
          </span>
        </div>
      )}

      {/* Input */}
      <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
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
            onClick={gravando ? pararGravacao : iniciarGravacao}
            disabled={transcrevendo || sending}
            className={`px-3 py-2.5 rounded-xl border transition-all disabled:opacity-50 cursor-pointer ${
              gravando
                ? "bg-red-50 text-red-600 border-red-200 hover:bg-red-100"
                : "bg-white text-slate-500 border-slate-200 hover:bg-slate-50"
            }`}
            aria-label={gravando ? "Parar gravação" : "Ditar por voz"}
            title={gravando ? "Parar gravação" : "Ditar por voz"}
          >
            {transcrevendo ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : gravando ? (
              <Square className="w-4 h-4 fill-current" />
            ) : (
              <Mic className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={sendMessage}
            disabled={!input.trim() || sending || gravando || transcrevendo}
            className="px-3 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        {(gravando || transcrevendo) && (
          <p className="mt-1.5 text-xs text-slate-400 flex items-center gap-1.5">
            {gravando ? (
              <>
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                Gravando… toque no quadrado para parar.
              </>
            ) : (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Transcrevendo…
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
