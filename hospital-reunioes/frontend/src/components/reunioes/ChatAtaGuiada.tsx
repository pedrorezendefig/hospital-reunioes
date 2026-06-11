"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, Mic, Square, Crosshair, X, Paperclip, FileText } from "lucide-react";
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

  // Documento de apoio (ADR 0006): anexo efêmero — extraído no backend e mantido só
  // em memória aqui; reenviado ao agente a cada turno como contexto sob demanda. Não
  // persiste na Reunião.
  const [documentoApoio, setDocumentoApoio] = useState<{ nome: string; texto: string } | null>(null);
  const [anexando, setAnexando] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const anexarDocumento = useCallback(
    async (file: File) => {
      if (anexando) return;
      setAnexando(true);
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const form = new FormData();
        form.append("file", file);

        const res = await fetch(`/api/reunioes/${idReuniao}/ata-guiada/extrair-documento`, {
          method: "POST",
          headers: { Authorization: `Bearer ${session?.access_token}` },
          body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          // 422 do backend traz uma mensagem clara em `detail` (formato/ilegível).
          throw new Error(typeof data?.detail === "string" ? data.detail : "Não consegui ler este arquivo.");
        }

        setDocumentoApoio({ nome: file.name, texto: data.texto ?? "" });
        toast("Documento anexado. Vou usá-lo quando você pedir.", "success");
      } catch (e) {
        toast(e instanceof Error ? e.message : "Não consegui ler este arquivo.", "error");
      } finally {
        setAnexando(false);
      }
    },
    [anexando, idReuniao, toast],
  );

  const removerDocumento = useCallback(() => setDocumentoApoio(null), []);

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
          // Contexto sob demanda: vai a cada turno; o agente só usa quando referenciado.
          documento_apoio: documentoApoio?.texto ?? null,
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
  }, [
    input,
    sending,
    messages,
    idReuniao,
    rascunho,
    onRascunhoChange,
    sectionContext,
    onClearSectionContext,
    documentoApoio,
  ]);

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
        {/* Documento de apoio anexado — chip removível (ADR 0006) */}
        {documentoApoio && (
          <div className="mb-2 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/5 border border-primary/20">
            <FileText className="w-3.5 h-3.5 text-primary flex-shrink-0" />
            <span className="text-xs text-slate-700 truncate flex-1" title={documentoApoio.nome}>
              {documentoApoio.nome}
            </span>
            <button
              onClick={removerDocumento}
              disabled={sending}
              className="p-0.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors flex-shrink-0 cursor-pointer disabled:opacity-50"
              aria-label="Remover documento de apoio"
              title="Remover documento de apoio"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.pdf,.docx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) anexarDocumento(file);
            e.target.value = ""; // permite reanexar o mesmo arquivo
          }}
        />
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
            onClick={() => fileInputRef.current?.click()}
            disabled={anexando || sending || gravando || transcrevendo}
            className="px-3 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 transition-all disabled:opacity-50 cursor-pointer"
            aria-label="Anexar documento de apoio"
            title="Anexar documento de apoio (.txt, .md, .pdf, .docx)"
          >
            {anexando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
          </button>
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
