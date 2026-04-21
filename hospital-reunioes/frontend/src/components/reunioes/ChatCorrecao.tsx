"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Crosshair, CheckCircle, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import ChatMessage from "./ChatMessage";
import CorrectionPlanSummary from "./CorrectionPlanSummary";
import type { ChatMessage as ChatMessageType, CorrectionItem, ChatCorrecaoResponse } from "@/types/chat";

interface JsonAta {
  hora_inicio?: string;
  hora_fim?: string;
  local?: string;
  objetivo?: string;
  participantes?: { nome: string; cargo: string; setor?: string; presente: boolean }[];
  referencias_externas?: { nome: string; vinculo_organizacao?: string }[];
  discussao?: Array<{
    titulo: string;
    descricao?: string;
    contribuicoes?: { funcao: string; conteudo: string }[];
    divergencias?: string[];
    decisao?: string;
    responsavel?: string | null;
  }>;
  registro_narrativo?: string;
  resumo_executivo?: string;
  quadro_atribuicoes?: {
    acao: string;
    responsavel: string;
    cargo: string;
    prazo: string | null;
    entregavel: string;
    objetivo_meta?: string;
    status?: "ABERTO" | "EM_ANDAMENTO" | "CONCLUIDO";
  }[];
  proxima_reuniao?: string | null;
  lacunas_identificadas?: string[];
}

interface ChatCorrecaoProps {
  idReuniao: string;
  jsonAta: JsonAta;
  sectionContext: string | null;
  onClearSectionContext: () => void;
  onApplyCorrections: (planText: string) => Promise<void>;
  onClose: () => void;
}

export default function ChatCorrecao({
  idReuniao,
  jsonAta,
  sectionContext,
  onClearSectionContext,
  onApplyCorrections,
  onClose,
}: ChatCorrecaoProps) {
  const [messages, setMessages] = useState<ChatMessageType[]>([
    {
      role: "assistant",
      content: "Olá! Sou o assistente de correção da ATA. Você pode me dizer o que precisa ser corrigido — e se quiser, aponte para uma seção específica clicando no ícone de alvo ao lado dela.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [correctionPlan, setCorrectionPlan] = useState<CorrectionItem[]>([]);
  const [applying, setApplying] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (sectionContext) {
      inputRef.current?.focus();
    }
  }, [sectionContext]);

  const sendMessage = useCallback(async () => {
    const capturedSectionContext = sectionContext;
    const text = input.trim();
    if (!text || sending) return;

    const userMessage: ChatMessageType = {
      role: "user",
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
      const { data: { session } } = await supabase.auth.getSession();

      const res = await fetch(`/api/reunioes/${idReuniao}/chat-correcao`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({
          messages: updatedMessages.map((m) => ({ role: m.role, content: m.content })),
          section_context: capturedSectionContext,
        }),
      });

      if (!res.ok) throw new Error("Erro ao enviar mensagem");

      const data: ChatCorrecaoResponse = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          timestamp: new Date().toISOString(),
        },
      ]);

      if (data.correction_plan.length > 0) {
        setCorrectionPlan(data.correction_plan);
      }
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
  }, [input, sending, messages, sectionContext, idReuniao, onClearSectionContext]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleApply = async () => {
    if (correctionPlan.length === 0) return;
    setApplying(true);
    const planText = correctionPlan
      .map((item, i) => `${i + 1}. [${item.action.toUpperCase()}] ${item.field}: ${item.description}`)
      .join("\n");
    try {
      await onApplyCorrections(planText);
    } finally {
      setApplying(false);
    }
  };

  const handleRemoveItem = (index: number) => {
    setCorrectionPlan((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col" style={{ maxHeight: "600px" }}>
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Crosshair className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Assistente de Correção</h3>
            <p className="text-xs text-slate-400">Converse para corrigir a ATA</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors">
          <X className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-[200px]">
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
        <div ref={messagesEndRef} />
      </div>

      {/* Correction Plan Summary */}
      <div className="px-5">
        <CorrectionPlanSummary items={correctionPlan} onRemoveItem={handleRemoveItem} />
      </div>

      {/* Section Context Chip */}
      {sectionContext && (
        <div className="px-5 pt-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
            <Crosshair className="w-3 h-3" />
            Apontando: {sectionContext}
            <button onClick={onClearSectionContext} className="ml-1 hover:text-primary-dark">
              <X className="w-3 h-3" />
            </button>
          </span>
        </div>
      )}

      {/* Input */}
      <div className="px-5 py-3 border-t border-slate-100">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Descreva o que precisa ser corrigido..."
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
        {correctionPlan.length > 0 && (
          <button
            onClick={handleApply}
            disabled={applying}
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-green-600 to-green-700 text-white font-medium rounded-xl hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer"
          >
            <CheckCircle className="w-4 h-4" />
            {applying ? "Aplicando correções..." : `Aplicar ${correctionPlan.length} correção(ões)`}
          </button>
        )}
      </div>
    </div>
  );
}
