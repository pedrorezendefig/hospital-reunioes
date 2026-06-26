"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Select } from "@/components/ui/Select";
import { ModalPortal } from "@/components/ui/ModalPortal";
import { FileUp, Upload, CheckCircle, AlertTriangle, X } from "lucide-react";

const TIPOS = [
  "Diretoria",
  "Gerencial",
  "Coordenação",
  "Mensal",
  "Extraordinária",
];

const ACCEPT = ".txt,.md,.pdf,.docx";
const VALID_EXT_REGEX = /\.(txt|md|pdf|docx)$/i;

function isFormatoValido(nome: string): boolean {
  return VALID_EXT_REGEX.test(nome);
}

function stripExtensao(nome: string): string {
  return nome.replace(VALID_EXT_REGEX, "");
}

interface UploadTranscricaoModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function UploadTranscricaoModal({
  onClose,
  onSuccess,
}: UploadTranscricaoModalProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [tipo, setTipo] = useState(TIPOS[0]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (files.length === 0) return;

    setLoading(true);
    setError(null);
    setUploadedCount(0);

    const form = e.currentTarget;
    const baseTitulo = (form.elements.namedItem("titulo") as HTMLInputElement).value;
    const data = (form.elements.namedItem("data") as HTMLInputElement).value;
    const objetivo = (form.elements.namedItem("objetivo") as HTMLTextAreaElement).value;

    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      let count = 0;
      for (const f of files) {
        const formData = new FormData();
        formData.append("file", f);
        formData.append(
          "titulo",
          files.length > 1 ? `${baseTitulo} - ${stripExtensao(f.name)}` : baseTitulo
        );
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
            // resposta não-JSON (ex: 500 do upstream)
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
    <ModalPortal>
      <div className="modal-backdrop z-[100] overflow-y-auto flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-premium w-full max-w-lg max-h-[90vh] overflow-y-auto animate-fade-in-up md:my-auto my-4 relative">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <FileUp className="w-4 h-4 text-primary" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">
              Nova Reunião: Upload de Transcrição
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
              placeholder="Ex: Reunião de Diretoria, Março 2026"
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
              <Select
                value={tipo}
                onChange={setTipo}
                options={TIPOS.map((t) => ({ value: t, label: t }))}
              />
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
              Arquivo de Transcrição (.txt, .md, .pdf, .docx)
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
                const droppedFiles = Array.from(e.dataTransfer.files).filter((f) =>
                  isFormatoValido(f.name)
                );
                if (droppedFiles.length > 0) {
                  setFiles((prev) => [...prev, ...droppedFiles].slice(0, 10));
                  setError(null);
                } else {
                  setError("Formato não suportado. Aceitos: .txt, .md, .pdf, .docx.");
                }
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
                accept={ACCEPT}
                multiple
                className="hidden"
                onChange={(e) => {
                  const selectedFiles = Array.from(e.target.files || []).filter((f) =>
                    isFormatoValido(f.name)
                  );
                  if (selectedFiles.length > 0) {
                    setFiles((prev) => [...prev, ...selectedFiles].slice(0, 10));
                    setError(null);
                  }
                }}
              />
              {files.length > 0 ? (
                <div className="text-success max-h-32 overflow-y-auto w-full flex flex-col items-center">
                  <CheckCircle className="w-8 h-8 mb-2 flex-shrink-0" strokeWidth={1.5} />
                  {files.map((f, i) => (
                    <div
                      key={i}
                      className="flex justify-between items-center w-full max-w-xs text-sm font-medium mb-1"
                    >
                      <span className="truncate">{f.name}</span>
                      <span className="text-xs text-success/70 ml-2">
                        {(f.size / 1024).toFixed(1)} KB
                      </span>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="text-xs mt-2 text-primary font-medium hover:underline relative z-10"
                    onClick={(e) => {
                      e.stopPropagation();
                      document.getElementById("file-input")?.click();
                    }}
                  >
                    + Adicionar mais arquivos
                  </button>
                </div>
              ) : (
                <div className="text-slate-400">
                  <Upload className="w-8 h-8 mx-auto mb-2" strokeWidth={1.5} />
                  <p className="text-sm">
                    Arraste os arquivos aqui ou{" "}
                    <span className="text-primary font-medium">clique para selecionar</span>
                  </p>
                  <p className="text-xs mt-1">
                    Aceita .txt, .md, .pdf e .docx (até 10 arquivos)
                  </p>
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
              {loading
                ? uploadedCount > 0
                  ? `Enviando (${uploadedCount}/${files.length})...`
                  : "Iniciando..."
                : "Processar com IA"}
            </button>
          </div>
        </form>
      </div>
      </div>
    </ModalPortal>
  );
}
