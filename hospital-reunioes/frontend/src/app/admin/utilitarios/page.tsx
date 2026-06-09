"use client";

import { useState } from "react";
import { getAuthToken } from "@/hooks/useAuth";
import {
  AlertTriangle,
  Check,
  CheckCircle,
  Copy,
  Download,
  FileCode2,
  RotateCcw,
  Upload,
  Wrench,
} from "lucide-react";

const ACCEPT = ".pdf,.docx";
const VALID_EXT_REGEX = /\.(pdf|docx)$/i;
const MAX_FILE_BYTES = 15 * 1024 * 1024; // espelha o limite do backend

interface ConversaoMarkdownResponse {
  markdown: string;
  nome_arquivo_sugerido: string;
  title: string | null;
  avisos: string[];
}

export default function UtilitariosPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ConversaoMarkdownResponse | null>(null);
  const [copied, setCopied] = useState(false);

  function selecionarArquivo(f: File | undefined) {
    setError(null);
    setResultado(null);
    if (!f) return;
    if (!VALID_EXT_REGEX.test(f.name)) {
      setError("Formato não suportado. Aceitos: .pdf e .docx.");
      return;
    }
    if (f.size > MAX_FILE_BYTES) {
      setError("Arquivo excede o limite de 15 MB.");
      return;
    }
    setFile(f);
  }

  async function handleConverter() {
    if (!file || loading) return;
    setLoading(true);
    setError(null);
    setResultado(null);

    try {
      const token = await getAuthToken();
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/admin/utilitarios/converter-markdown", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) {
        let errorMsg = `Erro ao converter ${file.name} (HTTP ${res.status})`;
        try {
          const resData = await res.json();
          errorMsg = resData.detail || errorMsg;
        } catch {
          // resposta não-JSON (ex: 500 do upstream)
        }
        throw new Error(errorMsg);
      }
      setResultado((await res.json()) as ConversaoMarkdownResponse);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao converter o arquivo");
    } finally {
      setLoading(false);
    }
  }

  async function handleCopiar() {
    if (!resultado) return;
    await navigator.clipboard.writeText(resultado.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleBaixar() {
    if (!resultado) return;
    const blob = new Blob([resultado.markdown], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = resultado.nome_arquivo_sugerido;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleNovoArquivo() {
    setFile(null);
    setResultado(null);
    setError(null);
    setCopied(false);
  }

  return (
    <div className="animate-fade-in-up space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <Wrench className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Conversor para Markdown</h1>
          <p className="text-sm text-text-secondary">
            Converta PDF ou DOCX em Markdown — processamento local, sem consumo de IA
          </p>
        </div>
      </div>

      {/* Upload */}
      <div className="bg-white rounded-2xl shadow-premium border border-slate-100 p-6 space-y-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            selecionarArquivo(e.dataTransfer.files[0]);
          }}
          className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 cursor-pointer ${
            dragging
              ? "border-primary bg-primary/5"
              : file
              ? "border-success bg-success/5"
              : "border-slate-200 hover:border-primary/40 hover:bg-slate-50"
          }`}
          onClick={() => document.getElementById("conversor-file-input")?.click()}
        >
          <input
            id="conversor-file-input"
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => selecionarArquivo(e.target.files?.[0])}
          />
          {file ? (
            <div className="text-success flex flex-col items-center">
              <CheckCircle className="w-8 h-8 mb-2" strokeWidth={1.5} />
              <p className="text-sm font-medium">{file.name}</p>
              <p className="text-xs text-success/70 mt-1">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
          ) : (
            <div className="text-slate-400">
              <Upload className="w-8 h-8 mx-auto mb-2" strokeWidth={1.5} />
              <p className="text-sm">
                Arraste o arquivo aqui ou{" "}
                <span className="text-primary font-medium">clique para selecionar</span>
              </p>
              <p className="text-xs mt-1">Aceita .pdf e .docx (até 15 MB, 1 arquivo por vez)</p>
            </div>
          )}
        </div>

        {error && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        <button
          onClick={handleConverter}
          disabled={!file || loading}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-medium hover:shadow-premium-strong transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {loading ? "Convertendo..." : "Converter para Markdown"}
        </button>
      </div>

      {/* Resultado */}
      {resultado && (
        <div className="bg-white rounded-2xl shadow-premium border border-slate-100 p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <FileCode2 className="w-5 h-5 text-primary flex-shrink-0" />
              <span className="text-sm font-medium text-slate-900 truncate">
                {resultado.nome_arquivo_sugerido}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopiar}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-success" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
                {copied ? "Copiado" : "Copiar"}
              </button>
              <button
                onClick={handleBaixar}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <Download className="w-4 h-4" />
                Baixar .md
              </button>
              <button
                onClick={handleNovoArquivo}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-500 text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <RotateCcw className="w-4 h-4" />
                Novo arquivo
              </button>
            </div>
          </div>

          {resultado.avisos.length > 0 && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-100 text-amber-700 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {resultado.avisos.join(" ")}
            </div>
          )}

          <pre className="bg-slate-50 border border-slate-100 rounded-xl p-4 font-mono text-sm text-slate-800 whitespace-pre-wrap break-words max-h-[60vh] overflow-y-auto">
            {resultado.markdown}
          </pre>
        </div>
      )}
    </div>
  );
}
