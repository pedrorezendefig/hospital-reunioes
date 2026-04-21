"use client";

import { Trash2, Loader2 } from "lucide-react";

interface DesmarcarModalProps {
  show: boolean;
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function DesmarcarModal({ show, loading, onConfirm, onCancel }: DesmarcarModalProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 z-[200] bg-black/40 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6 animate-fade-in-up">
        <div className="w-12 h-12 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-4">
          <Trash2 className="w-6 h-6 text-red-600" />
        </div>
        <h3 className="text-lg font-bold text-slate-900 text-center mb-1">Desmarcar Reunião?</h3>
        <p className="text-sm text-slate-500 text-center mb-6">
          Esta ação irá deletar a reunião permanentemente de todo o sistema. Esta ação não pode ser desfeita.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            {loading ? "Desmarcando..." : "Sim, Desmarcar"}
          </button>
        </div>
      </div>
    </div>
  );
}
