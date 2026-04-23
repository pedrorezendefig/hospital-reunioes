"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useToast } from "@/components/ui/Toast";
import { createClient } from "@/lib/supabase/client";
import { MultiSelect } from "@/components/ui/MultiSelect";
import { DeleteButton } from "@/components/DeleteButton";
import { isSuperAdmin } from "@/lib/auth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  Plus,
  FileUp,
  Upload,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
  FileText,
  X,
  Trash2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const PAGE_SIZE = 15;

// ──────────────────────────────────────────
// Types
// ──────────────────────────────────────────
type StatusAta =
  | "PROGRAMADA"
  | "PROCESSANDO"
  | "AGUARDANDO_RESOLUCAO"
  | "ERRO"
  | "AGUARDANDO_VALIDACAO"
  | "AGUARDANDO_ASSINATURA"
  | "ASSINADA"
  | "MIGRADA";

interface Reuniao {
  id_reuniao: string;
  data: string;
  tipo: string | null;
  objetivo: string | null;
  status_ata: StatusAta;
  total_acoes: number;
  acoes_concluidas: number;
  fonte: string;
  url_pdf_preliminar: string | null;
  created_at: string | null;
}

// ──────────────────────────────────────────
// Status Badge Component
// ──────────────────────────────────────────
const STATUS_CONFIG: Record<
  StatusAta,
  { label: string; bg: string; text: string; dot: string }
> = {
  PROGRAMADA: {
    label: "Programada",
    bg: "bg-slate-50",
    text: "text-slate-700",
    dot: "bg-slate-400",
  },
  PROCESSANDO: {
    label: "Processando",
    bg: "bg-blue-50",
    text: "text-blue-700",
    dot: "bg-blue-400 animate-pulse",
  },
  AGUARDANDO_RESOLUCAO: {
    label: "Resolver Participantes",
    bg: "bg-purple-50",
    text: "text-purple-700",
    dot: "bg-purple-500",
  },
  ERRO: {
    label: "Erro",
    bg: "bg-red-50",
    text: "text-red-700",
    dot: "bg-red-500",
  },
  AGUARDANDO_VALIDACAO: {
    label: "Aguard. Validação",
    bg: "bg-yellow-50",
    text: "text-yellow-700",
    dot: "bg-yellow-400",
  },
  AGUARDANDO_ASSINATURA: {
    label: "Aguard. Assinatura",
    bg: "bg-orange-50",
    text: "text-orange-700",
    dot: "bg-orange-400",
  },
  ASSINADA: {
    label: "Assinada",
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    dot: "bg-emerald-500",
  },
  MIGRADA: {
    label: "Migrada",
    bg: "bg-amber-50",
    text: "text-amber-700",
    dot: "bg-amber-500",
  },
};

function StatusBadge({ status }: { status: StatusAta }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.ERRO;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

// ──────────────────────────────────────────
// Upload Modal Component
// ──────────────────────────────────────────
function UploadModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);

  const TIPOS = [
    "Diretoria",
    "Gerencial",
    "Coordenação",
    "Mensal",
    "Extraordinária",
  ];

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (files.length === 0) return;

    setLoading(true);
    setError(null);
    setUploadedCount(0);

    const form = e.currentTarget;
    const baseTitulo = (form.elements.namedItem("titulo") as HTMLInputElement).value;
    const data = (form.elements.namedItem("data") as HTMLInputElement).value;
    const tipo = (form.elements.namedItem("tipo") as HTMLSelectElement).value;
    const objetivo = (form.elements.namedItem("objetivo") as HTMLTextAreaElement).value;

    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      
      let count = 0;
      for (const f of files) {
        const formData = new FormData();
        formData.append("file", f);
        formData.append("titulo", files.length > 1 ? `${baseTitulo} - ${f.name.replace(/\.txt$/i, '')}` : baseTitulo);
        formData.append("data", data);
        formData.append("tipo", tipo);
        if (objetivo) formData.append("objetivo", objetivo);

        const res = await fetch("/api/reunioes/upload-transcricao", {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        });
        if (!res.ok) {
          let errorMsg = `Erro ao enviar ${f.name} (HTTP ${res.status})`;
          try {
            const resData = await res.json();
            errorMsg = resData.detail || errorMsg;
          } catch {
             // Caso a resposta não seja JSON válido (ex: 500 Internal Server Error do Nginx/FastAPI)
          }
          throw new Error(errorMsg);
        }
        count++;
        setUploadedCount(count);
      }
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao realizar upload individual");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop z-[100] overflow-y-auto w-screen h-screen flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-premium w-full max-w-lg max-h-[90vh] overflow-y-auto animate-fade-in-up md:my-auto my-4 relative">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <FileUp className="w-4 h-4 text-primary" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">
              Nova Reunião — Upload de Transcrição
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Título */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Título da Reunião
            </label>
            <input
              name="titulo"
              type="text"
              required
              placeholder="Ex: Reunião de Diretoria — Março 2026"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
            />
          </div>

          {/* Data + Tipo */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Data
              </label>
              <input
                name="data"
                type="date"
                required
                defaultValue={new Date().toISOString().split("T")[0]}
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Tipo
              </label>
              <select
                name="tipo"
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all bg-white"
              >
                {TIPOS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Objetivo */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Objetivo (opcional)
            </label>
            <textarea
              name="objetivo"
              rows={2}
              placeholder="Descreva o objetivo principal da reunião..."
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all resize-none"
            />
          </div>

          {/* Drop zone */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Arquivo de Transcrição (.txt)
            </label>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const droppedFiles = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith(".txt"));
                if (droppedFiles.length > 0) {
                  setFiles(prev => [...prev, ...droppedFiles].slice(0, 10)); // Limite de 10 max
                  setError(null);
                } else setError("Apenas arquivos .txt são aceitos");
              }}
              className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-all duration-200 cursor-pointer ${
                dragging
                  ? "border-primary bg-primary/5"
                  : files.length > 0
                  ? "border-success bg-success/5"
                  : "border-slate-200 hover:border-primary/40 hover:bg-slate-50"
              }`}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <input
                id="file-input"
                type="file"
                accept=".txt"
                multiple
                className="hidden"
                onChange={(e) => {
                  const selectedfiles = Array.from(e.target.files || []).filter(f => f.name.endsWith(".txt"));
                  if (selectedfiles.length > 0) {
                     setFiles(prev => [...prev, ...selectedfiles].slice(0, 10));
                     setError(null);
                  }
                }}
              />
              {files.length > 0 ? (
                <div className="text-success max-h-32 overflow-y-auto w-full flex flex-col items-center">
                  <CheckCircle className="w-8 h-8 mb-2 flex-shrink-0" strokeWidth={1.5} />
                  {files.map((f, i) => (
                    <div key={i} className="flex justify-between items-center w-full max-w-xs text-sm font-medium mb-1">
                      <span className="truncate">{f.name}</span>
                      <span className="text-xs text-success/70 ml-2">{(f.size / 1024).toFixed(1)} KB</span>
                    </div>
                  ))}
                  <button type="button" className="text-xs mt-2 text-primary font-medium hover:underline relative z-10" onClick={(e) => { e.stopPropagation(); document.getElementById("file-input")?.click(); }}>+ Adicionar mais arquivos</button>
                </div>
              ) : (
                <div className="text-slate-400">
                  <Upload className="w-8 h-8 mx-auto mb-2" strokeWidth={1.5} />
                  <p className="text-sm">
                    Arraste os arquivos aqui ou{" "}
                    <span className="text-primary font-medium">clique para selecionar</span>
                  </p>
                  <p className="text-xs mt-1">Somente arquivos .txt (múltiplos permitidos)</p>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={files.length === 0 || loading}
              className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-medium hover:shadow-premium-strong transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (uploadedCount > 0 ? `Enviando (${uploadedCount}/${files.length})...` : "Iniciando...") : "Processar com IA"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// Main Page
// ──────────────────────────────────────────
export default function ReunioesPage() {
  const { toast } = useToast();
  const [reunioes, setReunioes] = useState<Reuniao[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string[]>([]);
  const [filterTipo, setFilterTipo] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { participante: currentUser } = useCurrentParticipante();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [mounted, setMounted] = useState(false);

  const canSuperAdmin = isSuperAdmin(currentUser);

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchReunioes = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token ?? null;
      const res = await fetch(`/api/reunioes?limit=200`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) setReunioes(await res.json());
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReunioes();
  }, [fetchReunioes]);

  // Polling quando há reuniões em PROCESSANDO ou AGUARDANDO_RESOLUCAO
  useEffect(() => {
    const hasProcessing = reunioes.some(
      (r) => r.status_ata === "PROCESSANDO" || r.status_ata === "AGUARDANDO_RESOLUCAO"
    );
    if (hasProcessing && !pollingRef.current) {
      pollingRef.current = setInterval(fetchReunioes, 15000);
    } else if (!hasProcessing && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [reunioes, fetchReunioes]);

  async function handleDeletar(id: string) {
    if (!window.confirm("Deseja excluir esta reunião permanentemente?")) return;
    setDeletingId(id);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const res = await fetch(`/api/reunioes/${id}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Erro HTTP ${res.status}`);
      }
      setReunioes((prev) => prev.filter((r) => r.id_reuniao !== id));
      toast("Reunião excluída com sucesso.", "success");
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Erro ao excluir reunião.", "error");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleForceDeletar(id: string, reason?: string) {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const reasonFinal = reason?.trim() || "Excluída via super admin";
    const res = await fetch(`/api/reunioes/${id}/force`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ reason: reasonFinal }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast(data.detail || `Erro HTTP ${res.status}`, "error");
      throw new Error(data.detail || "Erro ao excluir");
    }
    setReunioes((prev) => prev.filter((r) => r.id_reuniao !== id));
    toast("Reunião excluída (super admin).", "success");
  }

  async function handleAprovarTodas() {
    const pendentes = reunioes.filter(r => r.status_ata === "AGUARDANDO_VALIDACAO").length;
    if (pendentes === 0) return;
    if (!window.confirm(`Isso irá aprovar na marra ${pendentes} ata(s) aguardando validação e gerar suas pendências. Continuar?`)) return;
    
    try {
      setLoading(true);
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      
      const res = await fetch(`/api/reunioes/aprovar-bypass-todas`, { 
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        toast("Atas aprovadas com sucesso!", "success");
        await fetchReunioes();
      }
    } catch {
      toast("Erro ao aprovar atas em lote.", "error");
    } finally {
      setLoading(false);
    }
  }

  function handleUploadSuccess() {
    setShowModal(false);
    setTimeout(fetchReunioes, 500);
    setTimeout(() => {
      window.location.reload();
    }, 10000);
  }

  const TIPOS = ["Diretoria", "Gerencial", "Coordenação", "Mensal", "Extraordinária"];
  const STATUS_LIST = Object.keys(STATUS_CONFIG) as StatusAta[];

  const reunioesFiltradas = useMemo(
    () =>
      reunioes.filter((r) => {
        if (filterStatus.length > 0 && !filterStatus.includes(r.status_ata)) return false;
        if (filterTipo.length > 0 && !filterTipo.includes(r.tipo ?? "")) return false;
        return true;
      }),
    [reunioes, filterStatus, filterTipo],
  );

  const totalPages = Math.max(1, Math.ceil(reunioesFiltradas.length / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [filterStatus, filterTipo]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const reunioesPaginadas = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return reunioesFiltradas.slice(start, start + PAGE_SIZE);
  }, [reunioesFiltradas, page]);

  return (
    <div className="space-y-6 animate-fade-in-up">
      {showModal && (
        <UploadModal
          onClose={() => setShowModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reuniões</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Gerencie o ciclo de vida das reuniões e atas
          </p>
        </div>
        <div className="flex gap-3">
          {canSuperAdmin && (
            <Link
              href="/reunioes/importar"
              className="flex items-center gap-2 px-4 py-2.5 border border-border text-text-secondary rounded-xl text-sm font-medium hover:bg-primary/5 hover:text-primary transition-all cursor-pointer"
            >
              <FileUp className="w-4 h-4" />
              Importar ATA
            </Link>
          )}
          <button
            id="btn-aprovar-todas"
            onClick={handleAprovarTodas}
            disabled={reunioes.filter(r => r.status_ata === "AGUARDANDO_VALIDACAO").length === 0}
            className="flex items-center gap-2 px-4 py-2.5 border border-primary/20 text-primary bg-primary/5 rounded-xl text-sm font-medium hover:bg-primary/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            <CheckCircle className="w-4 h-4" />
            Aprovar Todas (Bypass)
          </button>
          <button
            id="btn-nova-reuniao"
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl text-sm font-medium hover:shadow-premium-strong transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Nova Reunião
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap items-end">
        <MultiSelect
          label="Status"
          options={STATUS_LIST.map((s) => ({ value: s, label: STATUS_CONFIG[s].label }))}
          selected={filterStatus}
          onChange={setFilterStatus}
          placeholder="Todos os status"
          allLabel="Todos os status"
        />
        <MultiSelect
          label="Tipo"
          options={TIPOS.map((t) => ({ value: t, label: t }))}
          selected={filterTipo}
          onChange={setFilterTipo}
          placeholder="Todos os tipos"
          allLabel="Todos os tipos"
        />
        {(filterStatus.length > 0 || filterTipo.length > 0) && (
          <button
            onClick={() => {
              setFilterStatus([]);
              setFilterTipo([]);
            }}
            className="px-3 py-2 text-sm text-slate-500 hover:text-slate-700 transition-colors cursor-pointer"
          >
            Limpar filtros ×
          </button>
        )}
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-primary/40" />
            Carregando reuniões...
          </div>
        ) : reunioesFiltradas.length === 0 ? (
          <div className="py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
              <FileText className="w-7 h-7 text-primary/40" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 text-sm font-medium">
              Nenhuma reunião encontrada
            </p>
            <p className="text-slate-400 text-xs mt-1">
              {reunioes.length === 0
                ? "Clique em \"Nova Reunião\" para começar"
                : "Nenhuma reunião corresponde aos filtros selecionados"}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/60">
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  ID
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Data
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Tipo
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Status
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Ações
                </th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {reunioesPaginadas.map((r) => (
                <tr
                  key={r.id_reuniao}
                  className="hover:bg-slate-50/50 transition-colors"
                >
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-500">
                    {r.id_reuniao}
                  </td>
                  <td className="px-5 py-3.5 text-slate-700">
                    {mounted ? new Date(r.data + "T12:00:00").toLocaleDateString("pt-BR") : "—"}
                  </td>
                  <td className="px-5 py-3.5 text-slate-600">
                    {r.tipo ?? "—"}
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusBadge status={r.status_ata} />
                  </td>
                  <td className="px-5 py-3.5 text-slate-500">
                    {r.total_acoes > 0 ? (
                      <span className="text-xs">
                        {r.acoes_concluidas}/{r.total_acoes} concluídas
                      </span>
                    ) : (
                      <span className="text-xs text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-2">
                      {(r.status_ata === "PROGRAMADA" || r.status_ata === "ERRO") && (
                        <button
                          onClick={() => handleDeletar(r.id_reuniao)}
                          disabled={deletingId === r.id_reuniao}
                          title="Excluir reunião"
                          className="p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                      {/* Super admin: force delete em qualquer status */}
                      <DeleteButton
                        visible={
                          canSuperAdmin &&
                          r.status_ata !== "PROGRAMADA" &&
                          r.status_ata !== "ERRO"
                        }
                        confirmTitle="Excluir reunião em qualquer status?"
                        confirmDescription={
                          r.status_ata === "ASSINADA"
                            ? "ATENÇÃO: esta ATA está ASSINADA digitalmente. Ao confirmar, o registro será removido permanentemente. Ação registrada no audit log."
                            : "A reunião será removida permanentemente. Ação registrada no audit log."
                        }
                        onDelete={(reason) => handleForceDeletar(r.id_reuniao, reason)}
                        buttonVariant="ghost"
                        label="Excluir"
                      />
                      <a
                        href={`/reunioes/${r.id_reuniao}`}
                        className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-primary/10 text-primary hover:bg-primary/15 transition-colors cursor-pointer"
                      >
                        Ver detalhe
                        <ArrowRight className="w-3 h-3" />
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Paginação */}
        {!loading && reunioesFiltradas.length > PAGE_SIZE && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/40">
            <p className="text-xs text-slate-500">
              Mostrando{" "}
              <span className="font-medium text-slate-700">
                {(page - 1) * PAGE_SIZE + 1}
              </span>{" "}
              —{" "}
              <span className="font-medium text-slate-700">
                {Math.min(page * PAGE_SIZE, reunioesFiltradas.length)}
              </span>{" "}
              de{" "}
              <span className="font-medium text-slate-700">
                {reunioesFiltradas.length}
              </span>{" "}
              reuniões
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg text-slate-500 hover:bg-white hover:text-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                aria-label="Página anterior"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-slate-600 px-2">
                Página <span className="font-medium">{page}</span> de{" "}
                <span className="font-medium">{totalPages}</span>
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded-lg text-slate-500 hover:bg-white hover:text-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                aria-label="Próxima página"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Polling indicator */}
      {reunioes.some((r) => r.status_ata === "PROCESSANDO" || r.status_ata === "AGUARDANDO_RESOLUCAO") && (
        <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
          <RefreshCw className="w-3 h-3 animate-spin" />
          Atualizando automaticamente a cada 15s...
        </div>
      )}
    </div>
  );
}
