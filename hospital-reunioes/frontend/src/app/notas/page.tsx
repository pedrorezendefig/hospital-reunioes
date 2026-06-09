"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { StickyNote, Plus, Pencil, Archive, ListTodo, Loader2, Sparkles, X, Mic, Square } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import type { Nota, NotaParticipante, PendenciaProposta } from "@/types";

type ParticipanteOpt = { id: string; nome_completo: string; is_externo?: boolean };

// Linha editável do painel de propostas: guarda o nome externo ORIGINAL da
// proposta para a opção "Externo: …" sobreviver a trocas de seleção.
type PropostaRow = PendenciaProposta & { externoOriginal: string | null };

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

  // Comando por voz (issue #35): o Facilitador dita; o áudio é transcrito e o
  // texto cai EDITÁVEL no corpo — ele revisa e salva manualmente. O áudio fica
  // só em memória (nunca persiste). Falha → aviso + digitação como fallback.
  const [gravando, setGravando] = useState(false);
  const [transcrevendo, setTranscrevendo] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const cancelarGravacaoRef = useRef(false);

  // Roster da Nota (issue #34): quem participou — Colaborador do cadastro ou
  // nome avulso (externo). Editado junto do corpo e gravado no salvar.
  const [roster, setRoster] = useState<NotaParticipante[]>([]);
  const [rosterAvulso, setRosterAvulso] = useState("");

  // Add manual de Pendência (issue #33): form inline aberto numa nota por vez.
  const [participantes, setParticipantes] = useState<ParticipanteOpt[]>([]);
  const [pendNotaId, setPendNotaId] = useState<string | null>(null);
  const [pendDescricao, setPendDescricao] = useState("");
  const [pendResponsavelId, setPendResponsavelId] = useState("");
  const [pendPrazo, setPendPrazo] = useState("");
  const [pendSalvando, setPendSalvando] = useState(false);

  // Extração por IA (issue #34): propõe-confirma — propostas editáveis por
  // nota, abertas num painel inline; só as confirmadas viram Pendências.
  const [extraindoId, setExtraindoId] = useState<string | null>(null);
  const [propNotaId, setPropNotaId] = useState<string | null>(null);
  const [propostas, setPropostas] = useState<PropostaRow[]>([]);
  const [confirmandoProps, setConfirmandoProps] = useState(false);

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
        // Cadastro de participantes para o select de responsável do add manual.
        fetch("/api/participantes", { headers: { Authorization: `Bearer ${tk}` } })
          .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
          .then((data) => {
            if (Array.isArray(data)) setParticipantes(data);
          })
          .catch(console.error);
      } else {
        setLoading(false);
      }
    }
    init();
  }, [carregar]);

  function abrirNova() {
    setEditId(null);
    setCorpo("");
    setRoster([]);
    setRosterAvulso("");
    setEditorAberto(true);
  }

  async function abrirEdicao(nota: Nota) {
    setEditId(nota.id);
    setCorpo(nota.corpo);
    setRoster([]);
    setRosterAvulso("");
    setEditorAberto(true);
    if (!token) return;
    try {
      const res = await fetch(`/api/notas/${nota.id}/participantes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = (await res.json()) as NotaParticipante[];
        setRoster(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error("Erro ao carregar participantes da nota:", e);
    }
  }

  function fecharEditor() {
    abortarGravacao();
    setEditorAberto(false);
    setEditId(null);
    setCorpo("");
    setRoster([]);
    setRosterAvulso("");
  }

  // ─── Comando por voz (issue #35) ──────────────────────────────────────────

  function pararStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  // Encerra a gravação em andamento e DESCARTA o áudio (cancelar/fechar editor).
  function abortarGravacao() {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      cancelarGravacaoRef.current = true;
      mr.stop();
    }
    setGravando(false);
  }

  // Solta a gravação na limpeza do componente para não deixar o microfone aberto.
  useEffect(() => () => pararStream(), []);

  async function iniciarGravacao() {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      toast("Seu navegador não permite gravar áudio. Digite a nota.", "error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find(
        (m) => MediaRecorder.isTypeSupported?.(m),
      );
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      cancelarGravacaoRef.current = false;
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        pararStream();
        if (cancelarGravacaoRef.current) {
          cancelarGravacaoRef.current = false;
          return; // gravação cancelada — descarta o áudio sem transcrever
        }
        void transcreverAudio(blob);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setGravando(true);
    } catch (e) {
      console.error("Erro ao acessar o microfone:", e);
      pararStream();
      toast("Não foi possível acessar o microfone. Verifique a permissão ou digite a nota.", "error");
    }
  }

  function pararGravacao() {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") mr.stop(); // dispara onstop → transcreve
    setGravando(false);
  }

  async function transcreverAudio(blob: Blob) {
    if (!token) return;
    if (blob.size === 0) {
      toast("Não captei áudio. Tente de novo ou digite a nota.", "error");
      return;
    }
    setTranscrevendo(true);
    try {
      const ext = (blob.type.split("/")[1] || "webm").split(";")[0];
      const form = new FormData();
      form.append("audio", blob, `nota-voz.${ext}`);
      const res = await fetch("/api/notas/transcrever", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        toast("Não foi possível transcrever o áudio. Digite a nota manualmente.", "error");
        return;
      }
      const data = (await res.json()) as { texto?: string };
      const texto = (data?.texto ?? "").trim();
      if (!texto) {
        toast("Não identifiquei fala no áudio. Tente de novo ou digite a nota.", "info");
        return;
      }
      // Cai EDITÁVEL no corpo: anexa ao que já houver, sem apagar o que foi digitado.
      setCorpo((prev) => (prev.trim() ? `${prev.trim()}\n${texto}` : texto));
      toast("Texto transcrito. Revise antes de salvar.", "success");
    } catch (e) {
      console.error("Erro ao transcrever áudio:", e);
      toast("Erro ao transcrever o áudio. Digite a nota manualmente.", "error");
    } finally {
      setTranscrevendo(false);
    }
  }

  function adicionarRosterCadastro(pid: string) {
    if (!pid || roster.some((r) => r.participante_id === pid)) return;
    const p = participantes.find((x) => x.id === pid);
    if (!p) return;
    setRoster((prev) => [...prev, { participante_id: pid, nome_avulso: null, nome: p.nome_completo }]);
  }

  function adicionarRosterAvulso() {
    const nome = rosterAvulso.trim();
    if (!nome) return;
    if (roster.some((r) => r.nome.toLowerCase() === nome.toLowerCase())) {
      setRosterAvulso("");
      return;
    }
    setRoster((prev) => [...prev, { participante_id: null, nome_avulso: nome, nome }]);
    setRosterAvulso("");
  }

  function removerRoster(idx: number) {
    setRoster((prev) => prev.filter((_, i) => i !== idx));
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
      if (!res.ok) {
        toast("Não foi possível salvar a Nota.", "error");
        return;
      }
      // Roster (issue #34): grava quem participou junto do corpo.
      const notaId = editId ?? ((await res.json()) as Nota).id;
      const rosterRes = await fetch(`/api/notas/${notaId}/participantes`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          participantes: roster.map((r) =>
            r.participante_id ? { participante_id: r.participante_id } : { nome_avulso: r.nome_avulso },
          ),
        }),
      });
      if (!rosterRes.ok) {
        toast("Nota salva, mas houve erro ao gravar os participantes.", "error");
      } else {
        toast(editId ? "Nota atualizada." : "Nota criada.", "success");
      }
      fecharEditor();
      await carregar(token);
    } catch (e) {
      console.error("Erro ao salvar nota:", e);
      toast("Erro ao salvar a Nota.", "error");
    } finally {
      setSalvando(false);
    }
  }

  function abrirFormPendencia(notaId: string) {
    fecharPropostas();
    setPendNotaId(notaId);
    setPendDescricao("");
    setPendResponsavelId("");
    setPendPrazo("");
  }

  function fecharFormPendencia() {
    setPendNotaId(null);
    setPendDescricao("");
    setPendResponsavelId("");
    setPendPrazo("");
  }

  function fecharPropostas() {
    setPropNotaId(null);
    setPropostas([]);
  }

  async function extrairPendencias(notaId: string) {
    if (!token || extraindoId) return;
    fecharFormPendencia();
    fecharPropostas();
    setExtraindoId(notaId);
    try {
      const res = await fetch(`/api/notas/${notaId}/extrair-pendencias`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        toast("A IA está indisponível no momento. Tente novamente.", "error");
        return;
      }
      const data = (await res.json()) as { propostas: PendenciaProposta[] };
      const recebidas = Array.isArray(data?.propostas) ? data.propostas : [];
      if (recebidas.length === 0) {
        toast("Nenhuma pendência identificada no texto da Nota.", "info");
        return;
      }
      setPropostas(
        recebidas.map((p) => ({
          ...p,
          externoOriginal: p.responsavel_id ? null : p.responsavel_nome,
        })),
      );
      setPropNotaId(notaId);
    } catch (e) {
      console.error("Erro ao extrair pendências:", e);
      toast("Erro ao extrair Pendências da Nota.", "error");
    } finally {
      setExtraindoId(null);
    }
  }

  function atualizarProposta(idx: number, patch: Partial<PropostaRow>) {
    setPropostas((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function descartarProposta(idx: number) {
    setPropostas((prev) => {
      const rest = prev.filter((_, i) => i !== idx);
      if (rest.length === 0) setPropNotaId(null);
      return rest;
    });
  }

  async function confirmarPropostas() {
    if (!propNotaId || !token || propostas.length === 0) return;
    setConfirmandoProps(true);
    try {
      const res = await fetch(`/api/notas/${propNotaId}/pendencias`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          pendencias: propostas.map((p) => ({
            descricao_acao: p.descricao_acao.trim(),
            responsavel_id: p.responsavel_id,
            responsavel_nome: p.responsavel_id ? null : p.responsavel_nome,
            prazo: p.prazo || null,
          })),
        }),
      });
      if (res.ok) {
        const criadas = (await res.json()) as unknown[];
        toast(
          criadas.length === 1
            ? "1 Pendência criada. Acompanhe no painel de Pendências."
            : `${criadas.length} Pendências criadas. Acompanhe no painel de Pendências.`,
          "success",
        );
        fecharPropostas();
      } else {
        toast("Não foi possível criar as Pendências.", "error");
      }
    } catch (e) {
      console.error("Erro ao confirmar propostas:", e);
      toast("Erro ao criar as Pendências.", "error");
    } finally {
      setConfirmandoProps(false);
    }
  }

  async function adicionarPendencia() {
    const descricao = pendDescricao.trim();
    if (!descricao || !pendNotaId || !token) return;
    setPendSalvando(true);
    try {
      const res = await fetch(`/api/notas/${pendNotaId}/pendencias`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          pendencias: [
            {
              descricao_acao: descricao,
              responsavel_id: pendResponsavelId || null,
              prazo: pendPrazo || null,
            },
          ],
        }),
      });
      if (res.ok) {
        toast("Pendência criada. Acompanhe no painel de Pendências.", "success");
        fecharFormPendencia();
      } else {
        toast("Não foi possível criar a Pendência.", "error");
      }
    } catch (e) {
      console.error("Erro ao criar pendência:", e);
      toast("Erro ao criar a Pendência.", "error");
    } finally {
      setPendSalvando(false);
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
            placeholder="Escreva ou dite o que foi tratado…"
            rows={6}
            className="w-full rounded-xl border border-border bg-bg p-3 text-sm text-text resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
          />

          {/* Comando por voz (issue #35): grava, transcreve e joga o texto
              editável no corpo — o Facilitador revisa e salva manualmente. */}
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <button
              onClick={gravando ? pararGravacao : iniciarGravacao}
              disabled={transcrevendo}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                gravando
                  ? "bg-red-50 text-red-600 border border-red-200 hover:bg-red-100"
                  : "border border-border text-text-secondary hover:bg-black/5"
              }`}
              aria-label={gravando ? "Parar gravação" : "Gravar nota por voz"}
            >
              {transcrevendo ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : gravando ? (
                <Square className="w-4 h-4 fill-current" />
              ) : (
                <Mic className="w-4 h-4" />
              )}
              {transcrevendo ? "Transcrevendo…" : gravando ? "Parar" : "Gravar voz"}
            </button>
            {gravando && (
              <span className="inline-flex items-center gap-1.5 text-xs text-red-600">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                Gravando…
              </span>
            )}
            {!gravando && !transcrevendo && (
              <span className="text-xs text-text-secondary">
                Dite a nota; o texto transcrito cai aqui pra você revisar.
              </span>
            )}
          </div>

          {/* Roster (issue #34): quem participou — Colaborador do cadastro ou
              nome avulso (externo). Afia o casamento do responsável na IA. */}
          <div className="mt-3">
            <p className="text-xs font-medium text-text-secondary mb-1.5">
              Quem participou (opcional)
            </p>
            {roster.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {roster.map((r, idx) => (
                  <span
                    key={`${r.participante_id ?? r.nome}-${idx}`}
                    className={`inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full text-xs ${
                      r.participante_id
                        ? "bg-primary/10 text-primary"
                        : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {r.nome}
                    {!r.participante_id && <span className="opacity-70">(externo)</span>}
                    <button
                      onClick={() => removerRoster(idx)}
                      className="p-0.5 rounded-full hover:bg-black/10 transition-colors"
                      aria-label={`Remover ${r.nome}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex flex-col sm:flex-row gap-2">
              <select
                value=""
                onChange={(e) => adicionarRosterCadastro(e.target.value)}
                className="flex-1 rounded-xl border border-border bg-bg p-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                aria-label="Adicionar participante do cadastro"
              >
                <option value="">Adicionar do cadastro…</option>
                {participantes
                  .filter((p) => !roster.some((r) => r.participante_id === p.id))
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nome_completo}
                    </option>
                  ))}
              </select>
              <div className="flex gap-2 flex-1">
                <input
                  type="text"
                  value={rosterAvulso}
                  onChange={(e) => setRosterAvulso(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      adicionarRosterAvulso();
                    }
                  }}
                  placeholder="Ou nome avulso (externo)…"
                  className="flex-1 rounded-xl border border-border bg-bg p-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                  aria-label="Nome avulso de participante externo"
                />
                <button
                  onClick={adicionarRosterAvulso}
                  disabled={!rosterAvulso.trim()}
                  className="px-3 rounded-xl border border-border text-text-secondary hover:bg-black/5 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  aria-label="Adicionar nome avulso"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

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
                    onClick={() => extrairPendencias(nota.id)}
                    disabled={extraindoId !== null}
                    className="p-2 rounded-lg text-text-secondary hover:bg-primary/5 hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    aria-label="Extrair pendências com IA"
                    title="Extrair pendências com IA"
                  >
                    {extraindoId === nota.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => abrirFormPendencia(nota.id)}
                    className="p-2 rounded-lg text-text-secondary hover:bg-primary/5 hover:text-primary transition-colors"
                    aria-label="Adicionar pendência"
                    title="Adicionar pendência"
                  >
                    <ListTodo className="w-4 h-4" />
                  </button>
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

              {/* Add manual de Pendência (issue #33): nasce com origem nesta
                  Nota e cai no mesmo painel/cobrança das demais. */}
              {pendNotaId === nota.id && (
                <div className="mt-3 pt-3 border-t border-border">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-text flex items-center gap-1.5">
                      <ListTodo className="w-4 h-4 text-primary" />
                      Nova pendência
                    </h3>
                    <button
                      onClick={fecharFormPendencia}
                      className="p-1 rounded-lg text-text-secondary hover:bg-black/5 transition-colors"
                      aria-label="Fechar formulário de pendência"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <input
                    type="text"
                    value={pendDescricao}
                    onChange={(e) => setPendDescricao(e.target.value)}
                    placeholder="O que precisa ser feito…"
                    className="w-full rounded-xl border border-border bg-bg p-3 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <div className="flex flex-col sm:flex-row gap-2 mt-2">
                    <select
                      value={pendResponsavelId}
                      onChange={(e) => setPendResponsavelId(e.target.value)}
                      className="flex-1 rounded-xl border border-border bg-bg p-3 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                      aria-label="Responsável"
                    >
                      <option value="">Responsável (opcional)</option>
                      {participantes.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome_completo}
                        </option>
                      ))}
                    </select>
                    <input
                      type="date"
                      value={pendPrazo}
                      onChange={(e) => setPendPrazo(e.target.value)}
                      className="rounded-xl border border-border bg-bg p-3 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                      aria-label="Prazo"
                    />
                  </div>
                  <div className="flex justify-end gap-2 mt-3">
                    <button
                      onClick={fecharFormPendencia}
                      className="px-4 py-2 rounded-xl text-sm text-text-secondary hover:bg-black/5 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={adicionarPendencia}
                      disabled={!pendDescricao.trim() || pendSalvando}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {pendSalvando && <Loader2 className="w-4 h-4 animate-spin" />}
                      Criar pendência
                    </button>
                  </div>
                </div>
              )}

              {/* Propostas da IA (issue #34): propõe-confirma — o Facilitador
                  edita/descarta; só as confirmadas viram Pendências. */}
              {propNotaId === nota.id && (
                <div className="mt-3 pt-3 border-t border-border">
                  <div className="flex items-center justify-between mb-1">
                    <h3 className="text-sm font-semibold text-text flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-primary" />
                      Pendências propostas pela IA
                    </h3>
                    <button
                      onClick={fecharPropostas}
                      className="p-1 rounded-lg text-text-secondary hover:bg-black/5 transition-colors"
                      aria-label="Descartar todas as propostas"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <p className="text-xs text-text-secondary mb-3">
                    Revise, edite ou descarte. Só as confirmadas viram Pendências.
                  </p>
                  <div className="space-y-2">
                    {propostas.map((p, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl border border-border bg-bg p-2.5"
                      >
                        <div className="flex items-start gap-2">
                          <input
                            type="text"
                            value={p.descricao_acao}
                            onChange={(e) =>
                              atualizarProposta(idx, { descricao_acao: e.target.value })
                            }
                            placeholder="O que precisa ser feito…"
                            className="flex-1 rounded-lg border border-border bg-surface p-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                            aria-label={`Descrição da proposta ${idx + 1}`}
                          />
                          <button
                            onClick={() => descartarProposta(idx)}
                            className="p-2 rounded-lg text-text-secondary hover:bg-red-50 hover:text-red-600 transition-colors"
                            aria-label={`Descartar proposta ${idx + 1}`}
                            title="Descartar proposta"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                        <div className="flex flex-col sm:flex-row gap-2 mt-2">
                          <select
                            value={p.responsavel_id ?? (p.responsavel_nome ? "__ext__" : "")}
                            onChange={(e) => {
                              const v = e.target.value;
                              if (v === "__ext__") {
                                atualizarProposta(idx, {
                                  responsavel_id: null,
                                  responsavel_nome: p.externoOriginal,
                                });
                              } else {
                                atualizarProposta(idx, {
                                  responsavel_id: v || null,
                                  responsavel_nome: null,
                                });
                              }
                            }}
                            className="flex-1 rounded-lg border border-border bg-surface p-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                            aria-label={`Responsável da proposta ${idx + 1}`}
                          >
                            <option value="">Sem responsável</option>
                            {p.externoOriginal && (
                              <option value="__ext__">Externo: {p.externoOriginal}</option>
                            )}
                            {participantes.map((opt) => (
                              <option key={opt.id} value={opt.id}>
                                {opt.nome_completo}
                              </option>
                            ))}
                          </select>
                          <input
                            type="date"
                            value={p.prazo ?? ""}
                            onChange={(e) => atualizarProposta(idx, { prazo: e.target.value || null })}
                            className="rounded-lg border border-border bg-surface p-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
                            aria-label={`Prazo da proposta ${idx + 1}`}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-end gap-2 mt-3">
                    <button
                      onClick={fecharPropostas}
                      className="px-4 py-2 rounded-xl text-sm text-text-secondary hover:bg-black/5 transition-colors"
                    >
                      Descartar tudo
                    </button>
                    <button
                      onClick={confirmarPropostas}
                      disabled={
                        confirmandoProps ||
                        propostas.length === 0 ||
                        propostas.some((p) => !p.descricao_acao.trim())
                      }
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {confirmandoProps && <Loader2 className="w-4 h-4 animate-spin" />}
                      {propostas.length === 1
                        ? "Confirmar 1 pendência"
                        : `Confirmar ${propostas.length} pendências`}
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
