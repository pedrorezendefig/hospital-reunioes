"use client";

import { useEffect, useState } from "react";
import { ArrowRightLeft, Crown, Loader2, Search } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import { createClient } from "@/lib/supabase/client";

interface SuperAdmin {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string | null;
  setor?: string | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  facilitadorAtualId: string | null;
  onConfirm: (novoFacilitadorId: string) => Promise<void>;
}

export default function TrocarFacilitadorModal({
  open,
  onClose,
  facilitadorAtualId,
  onConfirm,
}: Props) {
  const [superAdmins, setSuperAdmins] = useState<SuperAdmin[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelectedId(null);
    setSearch("");
    setError(null);
    setLoading(true);

    let cancelled = false;
    (async () => {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        const token = session?.access_token;
        const res = await fetch("/api/admin/super-admins", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (cancelled) return;
        if (!res.ok) {
          setError("Não foi possível carregar a lista de Super Admins.");
          setSuperAdmins([]);
          return;
        }
        const data: SuperAdmin[] = await res.json();
        setSuperAdmins(data.filter((s) => s.id !== facilitadorAtualId));
      } catch {
        if (!cancelled) setError("Erro de rede ao carregar Super Admins.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, facilitadorAtualId]);

  const filtered = superAdmins.filter(
    (s) =>
      !search ||
      s.nome_completo.toLowerCase().includes(search.toLowerCase()) ||
      s.email.toLowerCase().includes(search.toLowerCase()),
  );

  async function handleConfirm() {
    if (!selectedId) return;
    setSaving(true);
    try {
      await onConfirm(selectedId);
      onClose();
    } catch {
      // Toast de erro já é exibido pelo caller (handleTrocarFacilitador).
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminModal
      open={open}
      onClose={onClose}
      title="Trocar facilitador"
      description="Escolha um Super Admin para assumir como facilitador desta reunião."
      icon={<ArrowRightLeft className="w-5 h-5 text-amber-600" />}
      size="md"
      scrollable
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!selectedId || saving}
            className="px-4 py-2 rounded-xl bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 transition-colors disabled:opacity-60 flex items-center gap-2"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Crown className="w-4 h-4" />}
            Trocar facilitador
          </button>
        </>
      }
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-xl mb-3">
        <Search className="w-3.5 h-3.5 text-slate-400" />
        <input
          type="text"
          placeholder="Buscar por nome ou email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-transparent text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none"
        />
      </div>

      {error ? (
        <p className="py-8 text-center text-sm text-red-500">{error}</p>
      ) : loading ? (
        <div className="py-8 flex items-center justify-center text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400 italic">
          {superAdmins.length === 0
            ? "Nenhum outro Super Admin disponível."
            : "Nenhum Super Admin corresponde à busca."}
        </p>
      ) : (
        <div className="space-y-1.5 max-h-[50vh] overflow-y-auto">
          {filtered.map((sa) => {
            const selected = selectedId === sa.id;
            return (
              <button
                key={sa.id}
                type="button"
                onClick={() => setSelectedId(sa.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all ${
                  selected
                    ? "bg-amber-50 border-amber-300"
                    : "bg-white border-slate-200 hover:bg-slate-50"
                }`}
              >
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-amber-200 to-amber-300 text-amber-800 flex items-center justify-center text-sm font-semibold flex-shrink-0">
                  {sa.nome_completo.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{sa.nome_completo}</p>
                  <p className="text-xs text-slate-400 truncate">
                    {sa.email}
                    {sa.setor ? ` · ${sa.setor}` : ""}
                  </p>
                </div>
                {selected && <Crown className="w-4 h-4 text-amber-600 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </AdminModal>
  );
}
