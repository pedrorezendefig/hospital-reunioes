"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Send,
  CalendarDays,
  User,
  MessageSquare,
  ChevronDown,
  Loader2,
  Trash2,
  AtSign,
  FileText,
  Briefcase
} from "lucide-react";
import { Pendencia, StatusPendencia, Comentario } from "@/types";
import { PENDENCIA_STATUS_CONFIG, ALL_STATUSES } from "@/constants/pendencias";
import { isSuperAdmin } from "@/lib/auth";
import { DeleteButton } from "@/components/DeleteButton";
import { Select } from "@/components/ui/Select";

interface Props {
  pendencia: Pendencia;
  token: string | null;
  participantes: { id: string; nome_completo: string; setor?: string; is_externo?: boolean }[];
  /** @deprecated mantido por compat — use currentUser.is_super_admin. */
  userRole?: string;
  currentUser?: { id?: string; email?: string; is_super_admin?: boolean } | null;
  onClose: () => void;
  onStatusUpdated?: (id_acao: string, newStatus: StatusPendencia) => void;
  onPendenciaUpdated?: (updated: Pendencia) => void;
  onPendenciaDeleted?: (id_acao: string) => void;
}

export function PendenciaDetailModal({
  pendencia,
  token,
  participantes,
  userRole: _userRole = "coordenador",
  currentUser,
  onClose,
  onStatusUpdated,
  onPendenciaUpdated,
  onPendenciaDeleted
}: Props) {
  const [comentarios, setComentarios] = useState<Comentario[]>([]);
  const [loadingComentarios, setLoadingComentarios] = useState(true);
  const [novoComentario, setNovoComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  
  // Track savings fields for UI feedback
  const [savingFields, setSavingFields] = useState<Record<string, boolean>>({});

  // Local state for edits
  const [localTitle, setLocalTitle] = useState(pendencia.descricao_acao || "");
  const [localMeta, setLocalMeta] = useState(pendencia.meta_entregavel || "");
  const [localCargo, setLocalCargo] = useState(pendencia.cargo || "");
  const [localPrazo, setLocalPrazo] = useState(pendencia.prazo || "");

  // Mention autocomplete — só quem enxerga a Pendência é mencionável (issue #270)
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mencionaveis, setMencionaveis] = useState<{ id: string; nome_completo: string; setor?: string }[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const titleTextareaRef = useRef<HTMLTextAreaElement>(null);
  const commentsEndRef = useRef<HTMLDivElement>(null);

  // Super admin
  const canSuperAdmin = isSuperAdmin(currentUser);

  // Sync state if props change (e.g., from websocket or parent)
  useEffect(() => {
    setLocalTitle(pendencia.descricao_acao || "");
    setLocalMeta(pendencia.meta_entregavel || "");
    setLocalCargo(pendencia.cargo || "");
    setLocalPrazo(pendencia.prazo || "");
  }, [pendencia]);

  // Fetch comments
  const fetchComentarios = useCallback(async () => {
    if (!token) return;
    setLoadingComentarios(true);
    try {
      const res = await fetch(`/api/pendencias/${pendencia.id_acao}/comentarios`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setComentarios(await res.json());
    } catch (e) {
      console.error("Erro ao carregar comentários:", e);
    } finally {
      setLoadingComentarios(false);
    }
  }, [pendencia.id_acao, token]);

  useEffect(() => {
    fetchComentarios();
  }, [fetchComentarios]);

  // Carrega quem pode ser mencionado nesta Pendência
  useEffect(() => {
    if (!token) return;
    fetch(`/api/pendencias/${pendencia.id_acao}/mencionaveis`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : []))
      .then(setMencionaveis)
      .catch(() => setMencionaveis([]));
  }, [pendencia.id_acao, token]);

  // Scroll to bottom on new comments
  useEffect(() => {
    commentsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [comentarios]);

  // Close on ESC
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Auto-resize title textarea
  const adjustTitleHeight = useCallback(() => {
    if (titleTextareaRef.current) {
      titleTextareaRef.current.style.height = "auto";
      titleTextareaRef.current.style.height = (titleTextareaRef.current.scrollHeight) + "px";
    }
  }, []);

  useEffect(() => {
    adjustTitleHeight();
    // Atraso para garantir que o scrollHeight seja lido corretamente após a animação de entrada do modal
    const timeoutId = setTimeout(adjustTitleHeight, 150);
    return () => clearTimeout(timeoutId);
  }, [localTitle, adjustTitleHeight]);

  // Handle generic field update
  async function handleUpdateField(field: keyof Pendencia, value: string | null) {
    if (pendencia[field] === value) return; // No change
    if (!token) return;

    setSavingFields(prev => ({ ...prev, [field]: true }));
    try {
      const updatePayload: Record<string, string | null> = { [field]: value };
      if (field === "status" && value === "REPACTUADA") {
        updatePayload.prazo = null;
      }
      
      if (field === "responsavel_id") {
        const p = participantes.find(part => part.id === value);
        updatePayload["responsavel_nome"] = p ? p.nome_completo : "";
      }

      // If updating co-responsavel, also set the name
      if (field === "co_responsavel_id") {
        const p = participantes.find(part => part.id === value);
        updatePayload["co_responsavel_nome"] = p ? p.nome_completo : "";
      }

      const res = await fetch(`/api/pendencias/${pendencia.id_acao}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(updatePayload),
      });

      if (res.ok) {
        const updatedFromApi = await res.json();
        // Invoke parent update
        if (onPendenciaUpdated) {
          onPendenciaUpdated(updatedFromApi);
        }
        // If it was just status (handled below but just in case), trigger legacy
        if (field === "status" && onStatusUpdated && value) {
          onStatusUpdated(pendencia.id_acao, value as StatusPendencia);
        }
      } else {
        // Revert local state on error
        setLocalTitle(pendencia.descricao_acao || "");
        setLocalMeta(pendencia.meta_entregavel || "");
        setLocalCargo(pendencia.cargo || "");
        setLocalPrazo(pendencia.prazo || "");
        console.error("Falha ao atualizar o campo:", field);
      }
    } catch (e) {
      console.error(`Erro ao atualizar campo ${field}:`, e);
      // Revert local state
      setLocalTitle(pendencia.descricao_acao || "");
      setLocalMeta(pendencia.meta_entregavel || "");
      setLocalCargo(pendencia.cargo || "");
      setLocalPrazo(pendencia.prazo || "");
    } finally {
      setSavingFields(prev => ({ ...prev, [field]: false }));
    }
  }

  // Handle status update (special case for dropdown)
  async function handleStatusChange(novo: StatusPendencia) {
    setStatusDropdownOpen(false);
    if (novo === pendencia.status) return;
    setStatusLoading(true);
    try {
      await handleUpdateField("status", novo);
    } finally {
      setStatusLoading(false);
    }
  }

  // Handle comment submission
  async function handleSubmitComentario() {
    if (!novoComentario.trim() || !token) return;
    setEnviando(true);
    try {
      const res = await fetch(`/api/pendencias/${pendencia.id_acao}/comentarios`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ conteudo: novoComentario }),
      });
      if (res.ok) {
        const novo = await res.json();
        setComentarios((prev) => [...prev, novo]);
        setNovoComentario("");
      }
    } catch (e) {
      console.error("Erro ao enviar comentário:", e);
    } finally {
      setEnviando(false);
    }
  }

  // Super admin: force delete
  async function handleForceDelete(reason?: string) {
    if (!token) throw new Error("Sem token");
    const reasonFinal = reason?.trim() || "Excluída via kanban por super admin";
    const res = await fetch(`/api/pendencias/${pendencia.id_acao}/force`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason: reasonFinal }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Erro ao excluir pendência (force)");
    }
    onPendenciaDeleted?.(pendencia.id_acao);
    onClose();
  }

  // Handle comment delete
  async function handleDeleteComentario(id: string) {
    if (!token) return;
    try {
      const res = await fetch(
        `/api/pendencias/${pendencia.id_acao}/comentarios/${id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        setComentarios((prev) => prev.filter((c) => c.id !== id));
      }
    } catch (e) {
      console.error("Erro ao excluir comentário:", e);
    }
  }

  // Mention handling
  function handleTextareaChange(value: string) {
    setNovoComentario(value);

    const cursorPos = textareaRef.current?.selectionStart ?? 0;
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");

    if (lastAtIndex >= 0) {
      const textAfterAt = textBeforeCursor.substring(lastAtIndex + 1);
      if (!textAfterAt.includes(" ") || textAfterAt.split(" ").length <= 3) {
        setShowMentions(true);
        setMentionFilter(textAfterAt.toLowerCase());
        setMentionIndex(0);
        return;
      }
    }
    setShowMentions(false);
  }

  function insertMention(nome: string) {
    const cursorPos = textareaRef.current?.selectionStart ?? 0;
    const textBeforeCursor = novoComentario.substring(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");
    const textAfterCursor = novoComentario.substring(cursorPos);

    const newText =
      novoComentario.substring(0, lastAtIndex) + `@${nome} ` + textAfterCursor;
    setNovoComentario(newText);
    setShowMentions(false);

    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  const filteredParticipantes = mencionaveis.filter((p) =>
    p.nome_completo.toLowerCase().includes(mentionFilter)
  );

  function getInitials(name: string) {
    return name
      .split(" ")
      .map((n) => n[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
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

  function renderContent(text: string) {
    const parts = text.split(/(@[\w\s]+?)(?=\s@|\s*$|[.,;!?\)])/g);
    return parts.map((part, i) =>
      part.startsWith("@") ? (
        <span
          key={i}
          className="font-semibold text-primary bg-primary/5 px-0.5 rounded"
        >
          {part}
        </span>
      ) : (
        <span key={i}>{part}</span>
      )
    );
  }

  const statusCfg = PENDENCIA_STATUS_CONFIG[pendencia.status];
  const StatusIcon = statusCfg.icon;

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return createPortal(
    <>
      <div
        className="modal-backdrop z-[200] transition-opacity animate-fade-in"
        onClick={onClose}
      />

      <div className="fixed inset-0 z-[210] flex items-center justify-center p-4 sm:p-6 pointer-events-none">
        <div className="bg-white pointer-events-auto rounded-2xl shadow-premium w-full max-w-5xl h-[90vh] sm:h-[85vh] flex flex-col md:flex-row overflow-hidden animate-scale-in">
          
          {/* PAINEL ESQUERDO: DETALHES EDITÁVEIS */}
          <div className="flex-1 flex flex-col relative bg-white overflow-y-auto custom-scrollbar">
            
            <div className="sticky top-0 bg-slate-50 z-10 px-6 pt-6 pb-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-slate-500 bg-slate-200/50 px-2 py-1 rounded-md">
                  {pendencia.id_acao}
                </span>

                <div className="relative">
                  <button
                    onClick={() => setStatusDropdownOpen(!statusDropdownOpen)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${statusCfg.bg} ${statusCfg.color} hover:brightness-95 transition-all outline-none focus:ring-2 focus:ring-offset-1 focus:ring-${statusCfg.color.split("-")[1]}-400`}
                  >
                    {statusLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <StatusIcon className="w-3.5 h-3.5" strokeWidth={2.5} />
                    )}
                    {statusCfg.label}
                    <ChevronDown className="w-3.5 h-3.5 opacity-70" />
                  </button>

                  {statusDropdownOpen && (
                    <>
                      <div
                        className="fixed inset-0 z-10"
                        onClick={() => setStatusDropdownOpen(false)}
                      />
                      <div className="absolute left-0 mt-2 w-48 bg-white border border-slate-200 rounded-xl shadow-lg z-20 overflow-hidden animate-slide-in-top">
                        {ALL_STATUSES.map((s) => {
                          const cfg = PENDENCIA_STATUS_CONFIG[s];
                          const Icon = cfg.icon;
                          return (
                            <button
                                key={s}
                                onClick={() => handleStatusChange(s)}
                                className={`flex items-center gap-2 w-full px-4 py-3 text-sm text-left transition-colors ${
                                  s === pendencia.status ? "bg-slate-50 font-semibold" : "hover:bg-slate-50 font-medium"
                                }`}
                              >
                              <Icon className={`w-4 h-4 ${cfg.color}`} strokeWidth={2} />
                              <span className={cfg.color}>{cfg.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Super admin: force-delete pendência */}
                <DeleteButton
                  visible={canSuperAdmin}
                  confirmTitle="Excluir pendência?"
                  confirmDescription="Tem certeza? A pendência será removida permanentemente."
                  onDelete={handleForceDelete}
                  label="Excluir"
                />
                {/* Mobile close button only */}
                <button
                  onClick={onClose}
                  className="md:hidden w-8 h-8 rounded-lg bg-slate-100 text-slate-500 flex items-center justify-center hover:bg-slate-200"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="p-6 md:p-8 space-y-8 flex-1">
              
              {/* Título / Descrição */}
              <div className="relative group">
                 {savingFields["descricao_acao"] && (
                   <Loader2 className="w-4 h-4 animate-spin text-primary absolute right-2 top-2" />
                 )}
                 <textarea
                   ref={titleTextareaRef}
                   value={localTitle}
                   onChange={(e) => setLocalTitle(e.target.value)}
                   onBlur={(e) => handleUpdateField("descricao_acao", e.target.value)}
                   placeholder="Descrição da Pendência (Clique para editar...)"
                   className="w-full text-xl md:text-2xl font-bold text-slate-900 leading-snug bg-transparent border-transparent hover:bg-slate-50 focus:bg-white hover:border-slate-200 focus:border-primary focus:ring-1 focus:ring-primary rounded-xl px-4 py-3 -ml-4 transition-all outline-none resize-none overflow-y-hidden"
                   rows={1}
                 />
              </div>

              {/* Metadata Grid com Inline Editing */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                
                {/* Responsável */}
                <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-100 group/item relative transition-colors focus-within:bg-white focus-within:border-primary/40 focus-within:shadow-sm">
                   {savingFields["responsavel_id"] && (
                     <Loader2 className="w-3 h-3 text-primary animate-spin absolute top-4 right-4" />
                   )}
                   <div className="flex items-center gap-1.5 mb-1.5">
                     <User className="w-3.5 h-3.5 text-slate-400" />
                     <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Responsável</span>
                   </div>
                   <Select
                      value={pendencia.responsavel_id || ""}
                      onChange={(v) => handleUpdateField("responsavel_id", v)}
                      placeholder="Nenhum"
                      options={[
                        { value: "", label: "Nenhum" },
                        ...participantes.map(p => ({ value: p.id, label: p.nome_completo })),
                      ]}
                   />
                </div>

                {/* Co-Responsável — visível quando responsável é externo */}
                {(() => {
                  const responsavelParticipante = participantes.find(p => p.id === pendencia.responsavel_id);
                  const isResponsavelExterno = responsavelParticipante?.is_externo === true;
                  const canEditCoResp = isResponsavelExterno && isSuperAdmin(currentUser);
                  const hasCoResp = pendencia.co_responsavel_id || pendencia.co_responsavel_nome;

                  if (!isResponsavelExterno && !hasCoResp) return null;

                  return (
                    <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 group/item relative transition-colors focus-within:bg-white focus-within:border-primary/40 focus-within:shadow-sm">
                      {savingFields["co_responsavel_id"] && (
                        <Loader2 className="w-3 h-3 text-primary animate-spin absolute top-4 right-4" />
                      )}
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <User className="w-3.5 h-3.5 text-amber-500" />
                        <span className="text-[11px] font-semibold text-amber-600 uppercase tracking-wider">Co-Responsável</span>
                        <span className="text-[10px] text-amber-400 ml-1">(externo)</span>
                      </div>
                      {canEditCoResp ? (
                        <>
                          <Select
                            value={pendencia.co_responsavel_id || ""}
                            onChange={(v) => handleUpdateField("co_responsavel_id", v)}
                            placeholder="Nenhum"
                            options={[
                              { value: "", label: "Nenhum" },
                              ...participantes.filter(p => !p.is_externo).map(p => ({ value: p.id, label: p.nome_completo })),
                            ]}
                          />
                        </>
                      ) : (
                        <span className="text-sm font-medium text-slate-800">
                          {pendencia.co_responsavel_nome || "Não definido"}
                        </span>
                      )}
                    </div>
                  );
                })()}

                {/* Prazo */}
                <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-100 group/item relative transition-colors focus-within:bg-white focus-within:border-primary/40 focus-within:shadow-sm">
                   {savingFields["prazo"] && (
                     <Loader2 className="w-3 h-3 text-primary animate-spin absolute top-4 right-4" />
                   )}
                   <div className="flex items-center gap-1.5 mb-1.5">
                     <CalendarDays className="w-3.5 h-3.5 text-slate-400" />
                     <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Prazo</span>
                   </div>
                   <input
                      type="date"
                      value={pendencia.status === "REPACTUADA" ? "" : localPrazo}
                      disabled={pendencia.status === "REPACTUADA"}
                      onChange={(e) => setLocalPrazo(e.target.value)}
                      onBlur={(e) => handleUpdateField("prazo", e.target.value)}
                      className={`w-full bg-transparent text-sm font-medium outline-none cursor-text decoration-transparent ${
                        pendencia.status === "REPACTUADA" ? "text-slate-400 cursor-not-allowed" : "text-slate-800"
                      }`}
                   />
                </div>

                {/* Cargo */}
                <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-100 group/item relative transition-colors focus-within:bg-white focus-within:border-primary/40 focus-within:shadow-sm">
                   {savingFields["cargo"] && (
                     <Loader2 className="w-3 h-3 text-primary animate-spin absolute top-4 right-4" />
                   )}
                   <div className="flex items-center gap-1.5 mb-1.5">
                     <Briefcase className="w-3.5 h-3.5 text-slate-400" />
                     <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Cargo</span>
                   </div>
                   <input
                      type="text"
                      placeholder="Não definido"
                      value={localCargo}
                      onChange={(e) => setLocalCargo(e.target.value)}
                      onBlur={(e) => handleUpdateField("cargo", e.target.value)}
                      className="w-full bg-transparent text-sm font-medium text-slate-800 outline-none"
                   />
                </div>

                {/* Origem (Reunião — readonly link, mantendo a estética) */}
                <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-100 relative">
                   <div className="flex items-center gap-1.5 mb-1.5">
                     <FileText className="w-3.5 h-3.5 text-slate-400" />
                     <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                       Reunião DOC
                     </span>
                   </div>
                   {pendencia.id_reuniao ? (
                     <a
                       href={`/reunioes/${pendencia.id_reuniao}`}
                       className="text-sm font-medium text-primary hover:underline block truncate"
                     >
                       {pendencia.id_reuniao}
                     </a>
                   ) : (
                     <span className="text-sm font-medium text-slate-400 block truncate">-</span>
                   )}
                </div>

              </div>

              {/* Meta Entregável - Área Livre */}
              <div className="relative group/box mt-6">
                <div className="flex justify-between items-center mb-2">
                   <span className="text-xs font-bold text-slate-500 uppercase tracking-wider ml-1">Meta / Entregável Esperado</span>
                   {savingFields["meta_entregavel"] && (
                     <Loader2 className="w-3 h-3 text-primary animate-spin mr-1" />
                   )}
                </div>
                <textarea
                  value={localMeta}
                  onChange={(e) => setLocalMeta(e.target.value)}
                  onBlur={(e) => handleUpdateField("meta_entregavel", e.target.value)}
                  placeholder="Descreva o que exatamente deve ser entregue para considerar concluído..."
                  className="w-full min-h-[140px] text-sm text-slate-700 bg-white border border-slate-200 hover:border-slate-300 focus:border-primary focus:ring-1 focus:ring-primary rounded-xl px-4 py-3 transition-colors outline-none resize-y"
                />
              </div>

            </div>
          </div>

          {/* PAINEL DIREITO: ATIVIDADE / COMENTÁRIOS */}
          <div className="w-full md:w-[380px] lg:w-[420px] bg-slate-50 border-l border-slate-100 flex flex-col shrink-0">
            
            <div className="px-6 py-5 border-b border-slate-200/60 flex items-center justify-between bg-slate-50 sticky top-0 z-10">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-slate-500" />
                <h3 className="text-sm font-bold text-slate-800">
                  Atividade ({comentarios.length})
                </h3>
              </div>
              <button
                onClick={onClose}
                className="hidden md:flex w-8 h-8 rounded-lg text-slate-400 hover:bg-slate-200 hover:text-slate-600 items-center justify-center transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
              {loadingComentarios ? (
                <div className="flex flex-col items-center justify-center h-40 space-y-3">
                  <Loader2 className="w-6 h-6 animate-spin text-slate-300" />
                  <span className="text-xs text-slate-400">Carregando histórico...</span>
                </div>
              ) : comentarios.length === 0 ? (
                <div className="text-center flex flex-col items-center justify-center h-40 text-slate-400">
                   <MessageSquare className="w-8 h-8 opacity-20 mb-3" />
                   <span className="text-sm">Sem rastros de atividade.</span>
                   <span className="text-xs mt-1">Seja o primeiro a interagir!</span>
                </div>
              ) : (
                <div className="space-y-4">
                  {comentarios.map((c) => (
                    <div
                      key={c.id}
                      className="group/comment flex gap-3 p-3 -mx-3 rounded-xl hover:bg-white transition-colors"
                    >
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary/20 to-primary/5 flex items-center justify-center shrink-0 border border-primary/10">
                        <span className="text-[10px] font-bold text-primary">
                          {getInitials(c.autor_nome)}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-semibold text-slate-900">
                            {c.autor_nome}
                          </span>
                          <span className="text-[10px] font-medium text-slate-400">
                            {timeAgo(c.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap break-words">
                          {renderContent(c.conteudo)}
                        </p>
                      </div>
                      <button
                        onClick={() => handleDeleteComentario(c.id)}
                        className="opacity-0 group-hover/comment:opacity-100 transition-opacity shrink-0 w-7 h-7 rounded-lg hover:bg-red-50 flex items-center justify-center text-slate-300 hover:text-red-500 mt-0.5"
                        title="Excluir"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                  <div ref={commentsEndRef} />
                </div>
              )}
            </div>

            {/* Comment Input */}
            <div className="p-4 bg-white border-t border-slate-200/60 shrink-0 shadow-[0_-4px_24px_rgba(0,0,0,0.02)]">
              <div className="relative">
                <textarea
                  ref={textareaRef}
                  value={novoComentario}
                  onChange={(e) => handleTextareaChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (showMentions) {
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setMentionIndex((i) =>
                          Math.min(i + 1, filteredParticipantes.length - 1)
                        );
                      } else if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setMentionIndex((i) => Math.max(i - 1, 0));
                      } else if (e.key === "Enter" && filteredParticipantes[mentionIndex]) {
                        e.preventDefault();
                        insertMention(filteredParticipantes[mentionIndex].nome_completo);
                      } else if (e.key === "Escape") {
                        setShowMentions(false);
                      }
                    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      handleSubmitComentario();
                    }
                  }}
                  placeholder="Escreva algo... (@ para menção)"
                  className="w-full resize-none rounded-xl bg-slate-50 border border-slate-200 px-4 py-3 pr-12 text-sm outline-none focus:bg-white focus:border-primary focus:ring-1 focus:ring-primary/50 min-h-[90px] max-h-[160px] transition-all custom-scrollbar"
                  rows={2}
                />
                <button
                  onClick={handleSubmitComentario}
                  disabled={!novoComentario.trim() || enviando}
                  className="absolute right-3 bottom-3 w-8 h-8 rounded-lg bg-primary text-white flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                >
                  {enviando ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5 -ml-0.5" />
                  )}
                </button>

                {/* Mentions Menu */}
                {showMentions && filteredParticipantes.length > 0 && (
                  <div className="absolute bottom-full left-0 mb-2 w-full bg-white border border-slate-200 rounded-xl shadow-premium max-h-48 overflow-y-auto z-50 animate-slide-in-bottom">
                    {filteredParticipantes.slice(0, 8).map((p, i) => (
                      <button
                        key={p.id}
                        onClick={() => insertMention(p.nome_completo)}
                        className={`flex items-center gap-3 w-full px-4 py-2 text-sm text-left transition-colors ${
                          i === mentionIndex ? "bg-primary/5 border-l-2 border-primary" : "border-l-2 border-transparent hover:bg-slate-50"
                        }`}
                      >
                        <div className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center shrink-0">
                          <span className="text-[9px] font-bold text-slate-500">
                            {getInitials(p.nome_completo)}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <span className="text-slate-800 font-semibold truncate block">
                            {p.nome_completo}
                          </span>
                          {p.setor && (
                            <span className="text-[10px] text-slate-400 font-medium">{p.setor}</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex justify-between items-center mt-2.5 px-1">
                 <p className="text-[10px] text-slate-400 font-medium flex items-center gap-1">
                   <AtSign className="w-3 h-3" />
                   Mencione equipe com @
                 </p>
                 <span className="text-[10px] text-slate-300 font-medium px-1.5 py-0.5 rounded border border-slate-200">
                   Cmd/Ctrl + Enter
                 </span>
              </div>
            </div>
            
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes fade-in {
          0% { opacity: 0; }
          100% { opacity: 1; }
        }
        @keyframes scale-in {
          0% { opacity: 0; transform: scale(0.97) translateY(10px); }
          100% { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes slide-in-top {
          0% { opacity: 0; transform: translateY(-5px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        @keyframes slide-in-bottom {
          0% { opacity: 0; transform: translateY(5px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in { animation: fade-in 0.2s ease-out forwards; }
        .animate-scale-in { animation: scale-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .animate-slide-in-top { animation: slide-in-top 0.2s ease-out forwards; }
        .animate-slide-in-bottom { animation: slide-in-bottom 0.2s ease-out forwards; }
        
        .custom-scrollbar::-webkit-scrollbar {
          width: 5px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent; 
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(0,0,0,0.1);
          border-radius: 5px;
        }
        .custom-scrollbar:hover::-webkit-scrollbar-thumb {
          background: rgba(0,0,0,0.2); 
        }
      `}</style>
    </>,
    document.body
  );
}
