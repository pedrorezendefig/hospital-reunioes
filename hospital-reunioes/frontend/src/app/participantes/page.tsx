"use client";

import { useState, useEffect, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  UserPlus,
  Users,
  Search,
  UserMinus,
  X,
  AlertTriangle,
} from "lucide-react";

interface Participante {
  id: string;
  nome_completo: string;
  cargo: string;
  email: string;
  area: string | null;
  setor: string | null;
  role: string;
  ativo: boolean;
}

const ROLES: Record<string, { label: string; color: string }> = {
  diretor: { label: "Diretor", color: "bg-amber-50 text-amber-700" },
  gerente: { label: "Gerente", color: "bg-blue-50 text-blue-700" },
  coordenador: { label: "Coordenador", color: "bg-slate-50 text-slate-600" },
};

function AddModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const fd = new FormData(e.currentTarget);
    const body = Object.fromEntries(fd.entries());

    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      const res = await fetch("/api/participantes", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "Erro ao salvar");
      }
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-premium w-full max-w-md animate-fade-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <UserPlus className="w-4 h-4 text-primary" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Novo Participante</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-3">
          {[
            { name: "nome_completo", label: "Nome completo", placeholder: "Dr. João Silva" },
            { name: "cargo", label: "Cargo", placeholder: "Diretor Médico" },
            { name: "email", label: "Email", placeholder: "joao@hospital.com", type: "email" },
            { name: "area", label: "Área (opcional)", placeholder: "Enfermagem" },
            { name: "setor", label: "Setor (opcional)", placeholder: "UTI" },
          ].map((f) => (
            <div key={f.name}>
              <label className="block text-sm font-medium text-slate-700 mb-1">{f.label}</label>
              <input
                name={f.name}
                type={f.type ?? "text"}
                placeholder={f.placeholder}
                required={!f.label.includes("opcional")}
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              />
            </div>
          ))}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Perfil</label>
            <select name="role" className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 cursor-pointer">
              <option value="coordenador">Coordenador</option>
              <option value="gerente">Gerente</option>
              <option value="diretor">Diretor</option>
            </select>
          </div>
          {error && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 cursor-pointer">Cancelar</button>
            <button type="submit" disabled={loading} className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-medium hover:shadow-premium-strong transition-all disabled:opacity-50 cursor-pointer">
              {loading ? "Salvando..." : "Cadastrar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ParticipantesPage() {
  const [participantes, setParticipantes] = useState<Participante[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState("");

  const fetchParticipantes = useCallback(async () => {
    const params = new URLSearchParams();
    if (search) params.set("nome", search);
    
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    
    const res = await fetch(`/api/participantes?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) setParticipantes(await res.json());
    setLoading(false);
  }, [search]);

  useEffect(() => {
    fetchParticipantes();
  }, [fetchParticipantes]);

  async function handleDeactivate(id: string) {
    if (!confirm("Desativar este participante?")) return;
    
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    
    await fetch(`/api/participantes/${id}`, { 
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    fetchParticipantes();
  }

  return (
    <div className="space-y-6 animate-fade-in-up">
      {showModal && (
        <AddModal
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            fetchParticipantes();
          }}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Participantes</h1>
          <p className="text-slate-500 text-sm mt-0.5">Cadastro de pessoas do hospital</p>
        </div>
        <button
          id="btn-novo-participante"
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl text-sm font-medium hover:shadow-premium-strong transition-all cursor-pointer"
        >
          <UserPlus className="w-4 h-4" />
          Novo Participante
        </button>
      </div>

      {/* Busca */}
      <div className="relative w-full max-w-sm">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/40" />
        <input
          type="text"
          placeholder="Buscar por nome..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
        />
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">Carregando...</div>
        ) : participantes.length === 0 ? (
          <div className="py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
              <Users className="w-7 h-7 text-primary/40" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 text-sm">Nenhum participante cadastrado</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/60">
                {["ID", "Nome", "Cargo", "Email", "Setor", "Perfil", ""].map((h) => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {participantes.map((p) => {
                const role = ROLES[p.role] ?? ROLES.coordenador;
                return (
                  <tr key={p.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-xs text-slate-400">{p.id}</td>
                    <td className="px-5 py-3.5 font-medium text-slate-800">{p.nome_completo}</td>
                    <td className="px-5 py-3.5 text-slate-600">{p.cargo}</td>
                    <td className="px-5 py-3.5 text-slate-500">{p.email}</td>
                    <td className="px-5 py-3.5 text-slate-400">{p.setor ?? "—"}</td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${role.color}`}>
                        {role.label}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={() => handleDeactivate(p.id)}
                        className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-500 transition-colors cursor-pointer ml-auto"
                      >
                        <UserMinus className="w-3.5 h-3.5" />
                        Desativar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
