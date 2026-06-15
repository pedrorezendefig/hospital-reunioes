"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, Mic, Square, Crosshair, X, Paperclip, FileText } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";
import ChatMessage from "@/components/reunioes/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/types/chat";
import type { PeriodicidadeRevisaoPop, PopMaterialReferencia, RascunhoPop } from "@/types";

interface ChatElaboracaoResponse {
  reply: string;
  rascunho: RascunhoPop;
  periodicidade_sugerida: PeriodicidadeRevisaoPop | null;
}

interface MateriaisUploadResponse {
  materiais: PopMaterialReferencia[];
  erros: { filename: string; detail: string }[];
}

interface ChatElaboracaoPopProps {
  popId: string;
  /** Rascunho vivo — controlado pela tela (single source of truth na UI;
   * o backend persiste na Versão a cada turno). */
  rascunho: RascunhoPop;
  /** Reporta o rascunho atualizado a cada turno para o POP vivo refletir ao lado. */
  onRascunhoChange: (rascunho: RascunhoPop) => void;
  /** Reporta a Periodicidade sugerida pelo agente (card de escolha na tela). */
  onPeriodicidadeSugerida: (p: PeriodicidadeRevisaoPop | null) => void;
  /** Seção apontada (⌖) no POP vivo, ou null. A próxima mensagem é dirigida a ela. */
  sectionContext: string | null;
  /** Limpa a seção apontada (no chip ou após enviar a mensagem). */
  onClearSectionContext: () => void;
  /** Materiais de referência já persistidos na Versão (vêm com o GET da tela). */
  materiaisIniciais: PopMaterialReferencia[];
}

/**
 * Painel de conversa da elaboração de POP (issue #83) — o Elaborador relata
 * o procedimento por texto ou voz e o consultor ONA/JCI devolve as seções do
 * template institucional atualizadas. Espelha o ChatAtaGuiada (stateless no
 * backend; voz pelo useGravacaoVoz), com a diferença de que o rascunho
 * devolvido já foi persistido na Versão pelo backend — fechar a tela não
 * perde nada.
 *
 * Materiais de referência (issue #84): upload múltiplo (.pdf/.docx/.txt/.md)
 * persistido na Versão — o agente os lê ATIVAMENTE em toda interação (o
 * backend injeta do banco; nada é reenviado por aqui). Diferença deliberada
 * do Documento de apoio da Ata Guiada, que é efêmero e sob demanda.
 */
export default function ChatElaboracaoPop({
  popId,
  rascunho,
  onRascunhoChange,
  onPeriodicidadeSugerida,
  sectionContext,
  onClearSectionContext,
  materiaisIniciais,
}: ChatElaboracaoPopProps) {
  const [messages, setMessages] = useState<ChatMessageType[]>([
    {
      role: "assistant",
      content:
        "Vamos elaborar este POP juntos. Me conte como o procedimento funciona na prática. Eu estruturo nas seções do template institucional, seguindo as boas práticas de hospitais acreditados, e pergunto o que faltar. As seções tomam forma ao lado; quando o documento estiver pronto, use \"Aprovar versão final\".",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [materiais, setMateriais] = useState<PopMaterialReferencia[]>(materiaisIniciais);
  const [anexando, setAnexando] = useState(false);
  const [removendoId, setRemovendoId] = useState<string | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  // Ditar o relato por voz: reusa o hook compartilhado (Ata Guiada) —
  // grava, transcreve e o texto cai EDITÁVEL no input antes de enviar.
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

  // Apontou uma seção (⌖) → foca o input pra já digitar a correção.
  useEffect(() => {
    if (sectionContext) inputRef.current?.focus();
  }, [sectionContext]);

  // Upload múltiplo de Materiais de referência — por-arquivo: os válidos
  // entram na Versão, os recusados voltam com mensagem clara (sem quebrar).
  const anexarMateriais = useCallback(
    async (files: FileList) => {
      if (!files.length || anexando) return;
      setAnexando(true);
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const form = new FormData();
        Array.from(files).forEach((file) => form.append("files", file));
        const res = await fetch(`/api/pops/${popId}/elaboracao/materiais`, {
          method: "POST",
          headers: { Authorization: `Bearer ${session?.access_token}` },
          body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(typeof data?.detail === "string" ? data.detail : "Não consegui anexar os materiais.");
        }
        const { materiais: novos, erros } = data as MateriaisUploadResponse;
        if (novos.length) {
          setMateriais((prev) => [...prev, ...novos]);
          toast(
            novos.length === 1
              ? "Material de referência anexado. O agente passa a usá-lo."
              : `${novos.length} materiais de referência anexados. O agente passa a usá-los.`,
            "success"
          );
        }
        erros.forEach((e) => toast(`${e.filename}: ${e.detail}`, "error"));
      } catch (e) {
        toast(e instanceof Error ? e.message : "Não consegui anexar os materiais.", "error");
      } finally {
        setAnexando(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [popId, anexando, toast]
  );

  // Remover material o tira do contexto das interações seguintes do agente.
  const removerMaterial = useCallback(
    async (material: PopMaterialReferencia) => {
      if (removendoId) return;
      setRemovendoId(material.id);
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        const res = await fetch(`/api/pops/${popId}/elaboracao/materiais/${material.id}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${session?.access_token}` },
        });
        if (!res.ok && res.status !== 404) {
          const data = await res.json().catch(() => ({}));
          throw new Error(typeof data?.detail === "string" ? data.detail : "Não consegui remover o material.");
        }
        setMateriais((prev) => prev.filter((m) => m.id !== material.id));
        toast(`"${material.filename}" removido. Sai do contexto do agente.`, "success");
      } catch (e) {
        toast(e instanceof Error ? e.message : "Não consegui remover o material.", "error");
      } finally {
        setRemovendoId(null);
      }
    },
    [popId, removendoId, toast]
  );

  const sendMessage = useCallback(async () => {
    const capturedSectionContext = sectionContext;
    const text = input.trim();
    if (!text || sending) return;

    const userMessage: ChatMessageType = {
      role: "user",
      // Mesma marcação da Ata Guiada: a seção apontada (⌖) entra no início da
      // mensagem; o agente concentra a correção nela e preserva o resto.
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

      const res = await fetch(`/api/pops/${popId}/elaboracao/chat`, {
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

      const data: ChatElaboracaoResponse = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, timestamp: new Date().toISOString() },
      ]);
      // O rascunho é controlado pela tela: reporta o turno para o POP vivo
      // refletir. Se um turno falhar, o rascunho anterior é preservado.
      if (data.rascunho) onRascunhoChange(data.rascunho);
      onPeriodicidadeSugerida(data.periodicidade_sugerida ?? null);
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
    popId,
    rascunho,
    onRascunhoChange,
    onPeriodicidadeSugerida,
    sectionContext,
    onClearSectionContext,
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
          <h3 className="text-sm font-bold text-slate-900">Consultor de POPs</h3>
          <p className="text-xs text-slate-400">Boas práticas ONA / JCI</p>
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

      {/* Chip da seção apontada (⌖) — mesmo padrão da Ata Guiada */}
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

      {/* Materiais de referência — chips removíveis (padrão do Documento de
          apoio da Guiada, em lista: aqui o upload é múltiplo e persistido) */}
      {materiais.length > 0 && (
        <div className="px-5 pt-2 flex-shrink-0 space-y-1.5 max-h-32 overflow-y-auto">
          {materiais.map((m) => (
            <div
              key={m.id}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/5 border border-primary/20"
            >
              <FileText className="w-3.5 h-3.5 text-primary flex-shrink-0" />
              <span className="text-xs text-slate-700 truncate flex-1" title={m.filename}>
                {m.filename}
              </span>
              <button
                onClick={() => removerMaterial(m)}
                disabled={removendoId !== null}
                className="p-0.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                aria-label={`Remover ${m.filename}`}
                title="Remover material"
              >
                {removendoId === m.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".txt,.md,.pdf,.docx"
          className="hidden"
          onChange={(e) => e.target.files && anexarMateriais(e.target.files)}
        />
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Descreva o procedimento, passo a passo..."
            className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all resize-none"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={anexando || sending}
            className="px-3 py-2.5 rounded-xl border bg-white text-slate-500 border-slate-200 hover:bg-slate-50 transition-all disabled:opacity-50 cursor-pointer"
            aria-label="Anexar materiais de referência"
            title="Anexar materiais de referência (.txt, .md, .pdf, .docx)"
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
