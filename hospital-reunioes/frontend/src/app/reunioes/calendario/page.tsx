"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useToast } from "@/components/ui/Toast";
import { createClient } from "@/lib/supabase/client";
import { UploadTranscricaoModal } from "@/components/reunioes/UploadTranscricaoModal";
import { MultiSelect } from "@/components/ui/MultiSelect";
import { useFacilitadores } from "@/hooks/useFacilitadores";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Upload,
  CalendarDays,
  Clock,
  Users,
  X,
  AlertTriangle,
  CheckCircle,
  Search,
  Calendar,
  LayoutGrid,
  Trash2,
  Crown,
  Loader2,
  Repeat2,
  Filter,
} from "lucide-react";

// ──────────────────────────────────────────
// Types
// ──────────────────────────────────────────
interface Participante {
  id: string;
  nome_completo: string;
  cargo: string;
  email: string;
  setor: string | null;
}

interface EventoCalendario {
  id_reuniao: string;
  data: string;
  hora_inicio: string | null;
  tipo: string | null;
  titulo: string | null;
  objetivo: string | null;
  status_ata: string;
  facilitador_id?: string | null;
  id_grupo_recorrencia?: string | null;
  nome_grupo_recorrencia?: string | null;
  participantes: { id: string; nome: string; cargo: string }[];
}

// ──────────────────────────────────────────
// Constants
// ──────────────────────────────────────────
const TIPOS = [
  "Diretoria",
  "Gerencial",
  "Coordenação",
  "Mensal",
  "Extraordinária",
];

const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

// Slots de horário do time-picker (07:00 → 19:30 a cada 30min)
const TIME_SLOTS: string[] = [];
for (let h = 7; h <= 19; h++) {
  TIME_SLOTS.push(`${String(h).padStart(2, "0")}:00`);
  if (h < 19) TIME_SLOTS.push(`${String(h).padStart(2, "0")}:30`);
}

// Horas para o grid semanal (07–19)
const WEEK_HOURS = Array.from({ length: 13 }, (_, i) => i + 7);

// ──────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────
function getMonthGrid(year: number, month: number): (Date | null)[] {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const grid: (Date | null)[] = Array(firstDay).fill(null);
  for (let d = 1; d <= daysInMonth; d++) grid.push(new Date(year, month, d));
  while (grid.length % 7 !== 0) grid.push(null);
  return grid;
}

function getWeekDates(anchor: Date): Date[] {
  const day = anchor.getDay();
  const monday = new Date(anchor);
  monday.setDate(anchor.getDate() - day);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

function formatDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatHora(hora: string | null): string {
  if (!hora) return "";
  return hora.substring(0, 5);
}

function getHourFromHora(hora: string | null): number {
  if (!hora) return 0;
  return parseInt(hora.split(":")[0], 10);
}

function getStatusColor(status: string) {
  switch (status) {
    case "PROGRAMADA":
      return "bg-slate-100 text-slate-800 hover:bg-slate-200 border-slate-200";
    case "PROCESSANDO":
      return "bg-amber-100 text-amber-800 hover:bg-amber-200 border-amber-200";
    case "AGUARDANDO_VALIDACAO":
      return "bg-blue-100 text-blue-800 hover:bg-blue-200 border-blue-200";
    case "AGUARDANDO_ASSINATURA":
      return "bg-sky-100 text-sky-800 hover:bg-sky-200 border-sky-200";
    case "ASSINADA":
      return "bg-emerald-100 text-emerald-800 hover:bg-emerald-200 border-emerald-200";
    case "ERRO":
      return "bg-red-100 text-red-800 hover:bg-red-200 border-red-200";
    default:
      return "bg-slate-50 text-slate-500 hover:bg-slate-100 border-slate-100";
  }
}

function getStatusColorWeek(status: string) {
  switch (status) {
    case "PROGRAMADA":
      return "bg-slate-500 hover:bg-slate-600";
    case "PROCESSANDO":
      return "bg-amber-500 hover:bg-amber-600";
    case "AGUARDANDO_VALIDACAO":
      return "bg-blue-500 hover:bg-blue-600";
    case "AGUARDANDO_ASSINATURA":
      return "bg-sky-500 hover:bg-sky-600";
    case "ASSINADA":
      return "bg-emerald-500 hover:bg-emerald-600";
    case "ERRO":
      return "bg-red-500 hover:bg-red-600";
    default:
      return "bg-slate-500 hover:bg-slate-600";
  }
}

function formatStatus(status: string) {
  switch (status) {
    case "PROGRAMADA": return "Programada";
    case "PROCESSANDO": return "Processando IA";
    case "AGUARDANDO_VALIDACAO": return "Aguard. Validação";
    case "AGUARDANDO_ASSINATURA": return "Aguard. Assinatura";
    case "ASSINADA": return "Ata Assinada";
    case "ERRO": return "Erro no Processamento";
    case "CANCELADA": return "Cancelada";
    default: return status;
  }
}

// ──────────────────────────────────────────
// Time Picker Component
// ──────────────────────────────────────────
function TimePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="mt-2">
      {value && (
        <p className="text-xs text-indigo-600 font-semibold mb-2 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Selecionado: {value}
        </p>
      )}
      <div className="grid grid-cols-6 gap-1 max-h-36 overflow-y-auto pr-1">
        {TIME_SLOTS.map((slot) => (
          <button
            key={slot}
            type="button"
            onClick={() => onChange(slot === value ? "" : slot)}
            className={`py-1 px-1 rounded-lg text-[11px] font-medium transition-all cursor-pointer border ${
              value === slot
                ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-300"
            }`}
          >
            {slot}
          </button>
        ))}
      </div>
      {/* hidden input for form compatibility */}
      <input type="hidden" name="hora_inicio" value={value} />
    </div>
  );
}

// ──────────────────────────────────────────
// Modal de Agendamento
// ──────────────────────────────────────────
function AgendarModal({
  defaultDate,
  defaultTime,
  onClose,
  onSuccess,
}: {
  defaultDate: Date | null;
  defaultTime?: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [participantesBusca, setParticipantesBusca] = useState<Participante[]>([]);
  const [busca, setBusca] = useState("");
  const [selecionados, setSelecionados] = useState<Participante[]>([]);
  const [showDropdown, setShowDropdown] = useState(true);
  const [horaSelec, setHoraSelec] = useState(defaultTime ?? "");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const defaultDateStr = defaultDate
    ? formatDateKey(defaultDate)
    : new Date().toISOString().split("T")[0];

  // Buscar participantes
  const fetchParticipantes = useCallback(async (query: string) => {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const params = new URLSearchParams({ exclude_self: "true" });
    if (query) params.set("nome", query);
    const res = await fetch(`/api/participantes?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) {
      const data: Participante[] = await res.json();
      setParticipantesBusca(data);
    }
  }, []);

  useEffect(() => {
    fetchParticipantes("");
  }, [fetchParticipantes]);

  useEffect(() => {
    const timer = setTimeout(() => fetchParticipantes(busca), 300);
    return () => clearTimeout(timer);
  }, [busca, fetchParticipantes]);

  function toggleParticipante(p: Participante) {
    setSelecionados((prev) =>
      prev.find((s) => s.id === p.id)
        ? prev.filter((s) => s.id !== p.id)
        : [...prev, p]
    );
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const form = e.currentTarget;
    const titulo = (form.elements.namedItem("titulo") as HTMLInputElement).value;
    const data = (form.elements.namedItem("data") as HTMLInputElement).value;
    const tipo = (form.elements.namedItem("tipo") as HTMLSelectElement).value;
    const objetivo = (form.elements.namedItem("objetivo") as HTMLTextAreaElement).value;

    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;

      const res = await fetch("/api/reunioes/agendar", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          titulo,
          data,
          hora_inicio: horaSelec || null,
          tipo: tipo || null,
          objetivo: objetivo || null,
          participante_ids: selecionados.map((p) => p.id),
        }),
      });

      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Erro ao agendar reunião");
      }
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setLoading(false);
    }
  }

  const disponiveis = participantesBusca.filter(
    (p) => !selecionados.find((s) => s.id === p.id)
  );

  return (
    <div className="modal-backdrop z-[100] flex items-start justify-center pt-16 px-4 pb-4">
      <div className="bg-white rounded-2xl shadow-premium-strong w-full max-w-2xl max-h-[88vh] overflow-y-auto animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between px-7 py-5 border-b border-slate-100 sticky top-0 bg-white z-10 rounded-t-2xl">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center">
              <CalendarDays className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Agendar Reunião</h2>
              <p className="text-xs text-slate-400">Preencha os dados abaixo</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-7 space-y-5">
          {/* Título */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Título</label>
            <input
              name="titulo"
              type="text"
              required
              placeholder="Ex: Reunião de Diretoria — Abril 2026"
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
            />
          </div>

          {/* Data + Tipo em grid */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">Data</label>
              <input
                name="data"
                type="date"
                required
                defaultValue={defaultDateStr}
                className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">Tipo</label>
              <select
                name="tipo"
                className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all cursor-pointer"
              >
                <option value="">— Selecionar —</option>
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          {/* Horário */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              <Clock className="inline w-3.5 h-3.5 mr-1 opacity-60" />
              Horário da Reunião
            </label>
            <div className="border border-slate-200 rounded-xl p-3 bg-slate-50/50">
              <p className="text-xs text-slate-500 mb-2">Selecione o horário de início:</p>
              <TimePicker value={horaSelec} onChange={setHoraSelec} />
            </div>
          </div>

          {/* Pauta */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Pauta (opcional)</label>
            <textarea
              name="objetivo"
              rows={3}
              placeholder="Descreva a pauta da reunião..."
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all resize-none"
            />
          </div>

          {/* Participantes */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              <Users className="inline w-3.5 h-3.5 mr-1 opacity-60" />
              Participantes
              {selecionados.length > 0 && (
                <span className="ml-2 px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold">
                  {selecionados.length} selecionado{selecionados.length > 1 ? "s" : ""}
                </span>
              )}
            </label>

            {/* Tags dos selecionados */}
            {selecionados.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3 p-3 bg-indigo-50/60 rounded-xl border border-indigo-100">
                {selecionados.map((p) => (
                  <span
                    key={p.id}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-indigo-200 text-indigo-700 text-xs font-medium shadow-sm"
                  >
                    {p.nome_completo}
                    <button
                      type="button"
                      onClick={() => toggleParticipante(p)}
                      className="hover:opacity-70 cursor-pointer ml-0.5"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {selecionados.length > 0 && (
              <p className="text-xs text-slate-500 mb-2">
                Os participantes selecionados serão notificados por email assim que a reunião for salva.
              </p>
            )}

            {/* Campo de busca */}
            <div className="relative" ref={dropdownRef}>
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar participante..."
                value={busca}
                onFocus={() => setShowDropdown(true)}
                onChange={(e) => { setBusca(e.target.value); setShowDropdown(true); }}
                className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
              />
            </div>

            {/* Lista de participantes — sempre visível */}
            {showDropdown && disponiveis.length > 0 && (
              <div className="mt-2 border border-slate-200 rounded-xl bg-white overflow-hidden shadow-sm">
                <div className="text-[10px] text-slate-400 font-medium px-4 py-2 bg-slate-50 border-b border-slate-100 uppercase tracking-wide">
                  {busca ? `Resultados para "${busca}"` : "Participantes disponíveis"}
                </div>
                <div className="max-h-64 overflow-y-auto divide-y divide-slate-50">
                  {disponiveis.slice(0, 10).map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => { toggleParticipante(p); setBusca(""); }}
                      className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-indigo-50 transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                          <span className="text-indigo-700 text-xs font-semibold">
                            {p.nome_completo.charAt(0)}
                          </span>
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-800">{p.nome_completo}</p>
                          <p className="text-xs text-slate-500">{p.cargo}{p.setor ? ` · ${p.setor}` : ""}</p>
                        </div>
                      </div>
                      <div className="w-7 h-7 rounded-full bg-indigo-100 group-hover:bg-indigo-200 flex items-center justify-center flex-shrink-0 transition-colors">
                        <Plus className="w-3.5 h-3.5 text-indigo-600" />
                      </div>
                    </button>
                  ))}
                </div>
                {disponiveis.length > 10 && (
                  <p className="text-xs text-slate-400 text-center py-2 border-t border-slate-50">
                    +{disponiveis.length - 10} mais — refine a busca
                  </p>
                )}
              </div>
            )}

            {showDropdown && disponiveis.length === 0 && busca && (
              <p className="mt-2 text-sm text-slate-400 text-center py-4">
                Nenhum participante encontrado para &quot;{busca}&quot;
              </p>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 text-white text-sm font-medium hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? "Agendando..." : "Agendar Reunião"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// Event Card Mensal
// ──────────────────────────────────────────
function EventCard({
  evento,
  colIndex,
  rowIndex,
  totalRows,
  backYear,
  backMonth,
  onDelete,
  onDeleteGroup,
}: {
  evento: EventoCalendario;
  colIndex: number;
  rowIndex: number;
  totalRows: number;
  backYear: number;
  backMonth: number;
  onDelete: (id: string) => void;
  onDeleteGroup: () => void;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingGroup, setDeletingGroup] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isLastCols = colIndex >= 5;
  const isLastRow = rowIndex >= totalRows - 1;

  const detailHref = `/reunioes/${evento.id_reuniao}?from=calendario&year=${backYear}&month=${backMonth}`;

  const { toast } = useToast();

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();

    // Bloqueio por status conforme regra de negócio
    if (evento.status_ata !== "PROGRAMADA" && evento.status_ata !== "ERRO") {
      toast("Essa reunião não pode ser apagada", "warning");
      return;
    }

    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    setDeleting(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const res = await fetch(`/api/reunioes/${evento.id_reuniao}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Falha ao deletar");
      onDelete(evento.id_reuniao);
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  async function handleDeleteGroupAction(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();

    if (!confirm("Tem certeza que deseja apagar TODAS as reuniões desta série recorrente?")) return;
    setDeletingGroup(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      
      const res = await fetch(`/api/reunioes/grupo/${evento.id_grupo_recorrencia}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
         const b = await res.json().catch(() => ({}));
         throw new Error(b.detail || "Falha ao deletar grupo");
      }
      onDeleteGroup();
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Erro desconhecido", "error");
      setDeletingGroup(false);
    }
  }

  return (
    <div
      className="relative group/card"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => { setShowTooltip(false); setConfirmDelete(false); }}
    >
      {/* Pill clicável — navega direto para os detalhes */}
      <a
        href={detailHref}
        onClick={(e) => e.stopPropagation()}
        className={`w-full text-left px-2 py-1.5 rounded-lg border transition-colors cursor-pointer leading-tight flex flex-col pr-7 gap-0.5 ${getStatusColor(evento.status_ata)}`}
      >
        <span className="text-[11px] font-semibold truncate leading-snug">
          {evento.titulo || evento.tipo || "Reunião"}
        </span>
        {evento.hora_inicio && (
          <span className="text-[10px] opacity-70 font-medium">{formatHora(evento.hora_inicio)}{evento.tipo ? ` · ${evento.tipo}` : ""}</span>
        )}
      </a>

      {/* Lixeira — aparece no hover */}
      <button
        onClick={handleDelete}
        disabled={deleting}
        title={confirmDelete ? "Clique novamente para confirmar" : "Desmarcar reunião"}
        className={`absolute right-0.5 top-0.5 w-5 h-5 flex items-center justify-center rounded transition-all opacity-0 group-hover/card:opacity-100 ${
          confirmDelete
            ? "bg-red-500 text-white"
            : "bg-indigo-200/80 hover:bg-red-500 text-indigo-700 hover:text-white"
        } disabled:opacity-60`}
      >
        {deleting ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Trash2 className="w-2.5 h-2.5" />}
      </button>

      {showTooltip && (
        <div
          className={`absolute z-[60] w-64 bg-white rounded-xl shadow-2xl border border-slate-100 p-3 text-left animate-fade-in-up 
            ${isLastCols ? "right-0" : "left-0"} 
            ${isLastRow ? "bottom-full mb-1" : "top-full mt-1"}
          `}
        >
          <p className="text-sm font-semibold text-slate-900 mb-0.5 leading-snug">
            {evento.titulo || evento.tipo || "Reunião Programada"}
          </p>
          <div className="flex items-center gap-1.5 mb-1 text-[10px] font-bold uppercase tracking-wider">
            <span className={`w-1.5 h-1.5 rounded-full ${getStatusColorWeek(evento.status_ata).split(" ")[0]}`} />
            <span className={getStatusColor(evento.status_ata).split(" ")[1]}>{formatStatus(evento.status_ata)}</span>
            {evento.tipo && <span className="text-slate-300">|</span>}
            {evento.tipo && <span className="text-slate-400">{evento.tipo}</span>}
          </div>
          {evento.nome_grupo_recorrencia && (
            <div className="flex items-center gap-1 mt-1 text-[10px] text-indigo-700 font-semibold bg-indigo-50 px-2 py-0.5 rounded w-fit">
               <Repeat2 className="w-3 h-3" />
               Série: {evento.nome_grupo_recorrencia}
            </div>
          )}
          {evento.hora_inicio && (
            <p className="text-xs text-slate-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatHora(evento.hora_inicio)}
            </p>
          )}
          {evento.objetivo && (
            <p className="text-xs text-slate-400 mt-1.5 line-clamp-2">
              {evento.objetivo}
            </p>
          )}
          {evento.participantes && evento.participantes.length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-slate-50">
              <p className="text-[10px] text-slate-400 font-medium mb-0.5">
                Participantes
              </p>
              {evento.participantes
                .filter((p) => p.nome)
                .slice(0, 4)
                .map((p) => {
                  const isFacilitador = p.id === evento.facilitador_id;
                  return (
                    <div key={p.id} className="flex items-center gap-1">
                      <p className={`text-[10px] truncate ${
                        isFacilitador ? "text-amber-700 font-semibold" : "text-slate-600"
                      }`}>
                        {p.nome}
                      </p>
                      {isFacilitador && (
                        <Crown className="w-2.5 h-2.5 text-amber-500 flex-shrink-0" />
                      )}
                    </div>
                  );
                })}
              {evento.participantes.length > 4 && (
                <p className="text-[10px] text-slate-400">
                  +{evento.participantes.length - 4} mais
                </p>
              )}
            </div>
          )}
          {confirmDelete && (
            <div className="mt-2 pt-2 border-t border-red-100">
              <p className="text-[10px] text-red-600 font-medium">Clique na lixeira novamente para confirmar</p>
            </div>
          )}
          
          {evento.id_grupo_recorrencia && (
             <button
               onClick={handleDeleteGroupAction}
               disabled={deletingGroup}
               className="mt-2 w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded bg-red-50 text-red-600 hover:bg-red-100 transition-colors text-[10px] font-semibold"
             >
               {deletingGroup ? <Loader2 className="w-3 h-3 animate-spin"/> : <Trash2 className="w-3 h-3" />}
               Excluir toda a série recorrente
             </button>
          )}

          <a
            href={detailHref}
            className="mt-2 inline-block text-[10px] text-indigo-600 hover:underline font-medium"
            onClick={(e) => e.stopPropagation()}
          >
            Ver detalhe →
          </a>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Visão Semanal
// ──────────────────────────────────────────
function WeekView({
  weekDates,
  eventosPorDia,
  todayKey,
  onSlotClick,
  weekAnchorKey,
  onDeleteEvento,
  onDeleteGroup,
}: {
  weekDates: Date[];
  eventosPorDia: Record<string, EventoCalendario[]>;
  todayKey: string;
  onSlotClick: (date: Date, hora: string) => void;
  weekAnchorKey: string;
  onDeleteEvento: (id: string) => void;
  onDeleteGroup: () => void;
}) {
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinutes = now.getMinutes();
  const nowOffset = ((currentHour - 7) * 60 + currentMinutes) / 60; // offset em horas desde 07:00

  return (
    <div className="overflow-auto">
      {/* Cabeçalho dos dias */}
      <div className="grid grid-cols-8 border-b border-slate-100 sticky top-0 bg-white z-10">
        <div className="py-3 px-3 text-xs text-slate-400 font-medium border-r border-slate-100" />
        {weekDates.map((d, i) => {
          const key = formatDateKey(d);
          const isToday = key === todayKey;
          return (
            <div
              key={i}
              className={`py-3 px-2 text-center border-r border-slate-100 last:border-r-0 ${
                isToday ? "bg-indigo-50" : ""
              }`}
            >
              <p className="text-[10px] text-slate-400 uppercase tracking-wide">
                {DIAS_SEMANA[d.getDay()]}
              </p>
              <p
                className={`text-base font-bold mt-0.5 w-9 h-9 flex items-center justify-center rounded-full mx-auto ${
                  isToday
                    ? "bg-indigo-600 text-white"
                    : "text-slate-700"
                }`}
              >
                {d.getDate()}
              </p>
            </div>
          );
        })}
      </div>

      {/* Grid de horas × dias */}
      <div className="relative">
        {WEEK_HOURS.map((hour) => (
          <div key={hour} className="grid grid-cols-8 border-b border-slate-50 group">
            {/* Coluna de hora */}
            <div className="py-4 px-3 text-xs text-slate-400 border-r border-slate-100 text-right self-start pt-2 min-h-[120px]">
              {String(hour).padStart(2, "0")}:00
            </div>

            {/* Slots de cada dia */}
            {weekDates.map((d, di) => {
              const key = formatDateKey(d);
              const isToday = key === todayKey;
              const evs = (eventosPorDia[key] ?? []).filter(
                (ev) => getHourFromHora(ev.hora_inicio) === hour
              );

              return (
                <div
                  key={di}
                  className={`relative border-r border-slate-50 last:border-r-0 min-h-[120px] p-1 cursor-pointer transition-colors hover:bg-indigo-50/30 ${
                    isToday ? "bg-indigo-50/20" : ""
                  }`}
                  onClick={() => onSlotClick(d, `${String(hour).padStart(2, "0")}:00`)}
                >
                  {evs.map((ev) => (
                    <WeekEventCard
                      key={ev.id_reuniao}
                      ev={ev}
                      weekAnchorKey={weekAnchorKey}
                      onDelete={onDeleteEvento}
                      onDeleteGroup={onDeleteGroup}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        ))}

        {/* Indicador de hora atual */}
        {nowOffset >= 0 && nowOffset <= 12 && (
          <div
            className="absolute left-0 right-0 flex items-center pointer-events-none z-20"
            style={{ top: `${(nowOffset / 13) * 100}%` }}
          >
            <div className="w-12 flex-shrink-0" />
            <div className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0 -ml-1" />
            <div className="flex-1 border-t border-red-400 border-dashed" />
          </div>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// Event Card da Visão Semanal
// ──────────────────────────────────────────
function WeekEventCard({
  ev,
  weekAnchorKey,
  onDelete,
  onDeleteGroup,
}: {
  ev: EventoCalendario;
  weekAnchorKey: string;
  onDelete: (id: string) => void;
  onDeleteGroup: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingGroup, setDeletingGroup] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);

  const { toast } = useToast();

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();

    // Bloqueio por status conforme regra de negócio
    if (ev.status_ata !== "PROGRAMADA") {
      toast("Essa reunião já aconteceu não pode ser apagada", "warning");
      return;
    }

    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    setDeleting(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const res = await fetch(`/api/reunioes/${ev.id_reuniao}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Falha ao deletar");
      onDelete(ev.id_reuniao);
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  async function handleDeleteGroupAction(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!ev.id_grupo_recorrencia) return;
    
    setDeletingGroup(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const res = await fetch(`/api/reunioes/grupo/${ev.id_grupo_recorrencia}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Falha ao deletar grupo");
      onDeleteGroup();
    } catch {
      setDeletingGroup(false);
    }
  }

  const detailHref = `/reunioes/${ev.id_reuniao}?from=calendario&week=${weekAnchorKey}`;

  return (
    <div
      className="relative group/weekcard mb-1"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => { setShowTooltip(false); setConfirmDelete(false); }}
    >
      <a
        href={detailHref}
        onClick={(e) => e.stopPropagation()}
        className={`block w-full px-2 py-2 rounded-lg text-white transition-colors shadow-sm leading-tight pr-7 ${
          confirmDelete ? "bg-red-500 hover:bg-red-600" : getStatusColorWeek(ev.status_ata)
        }`}
      >
        <span className="text-[11px] font-semibold truncate block leading-snug">
          {ev.titulo || ev.tipo || "Reunião"}
        </span>
        <span className="text-[10px] opacity-80 block mt-0.5">
          {formatHora(ev.hora_inicio)}{ev.tipo ? ` · ${ev.tipo}` : ""}
        </span>
        {ev.participantes.length > 0 && (
          <span className="text-[10px] opacity-60 block mt-0.5">
            {ev.participantes.length} part.
          </span>
        )}
        {ev.id_grupo_recorrencia && (
          <span className="inline-block mt-1 px-1 bg-white/20 rounded text-[9px] font-bold uppercase tracking-wider">
            Série
          </span>
        )}
      </a>
      {/* Lixeira */}
      <button
        onClick={handleDelete}
        disabled={deleting}
        title={confirmDelete ? "Clique novamente para confirmar" : "Desmarcar reunião"}
        className="absolute right-1 top-1 w-4 h-4 flex items-center justify-center rounded opacity-0 group-hover/weekcard:opacity-100 transition-opacity bg-white/20 hover:bg-red-500 text-white disabled:opacity-50"
      >
        {deleting ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Trash2 className="w-2.5 h-2.5" />}
      </button>
      
      {ev.id_grupo_recorrencia && (
        <button
          onClick={handleDeleteGroupAction}
          disabled={deletingGroup}
          title="Excluir toda a série"
          className="absolute right-1 top-6 w-4 h-4 flex items-center justify-center rounded opacity-0 group-hover/weekcard:opacity-100 transition-opacity bg-white/20 hover:bg-red-700 text-white disabled:opacity-50"
        >
          {deletingGroup ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Trash2 className="w-2.5 h-2.5" />}
        </button>
      )}

      {showTooltip && (
        <div className="absolute z-[60] w-64 bg-white rounded-xl shadow-2xl border border-slate-100 p-3 text-left animate-fade-in-up left-full ml-2 top-0">
          <p className="text-sm font-semibold text-slate-900 mb-0.5 leading-snug">
            {ev.titulo || ev.tipo || "Reunião Programada"}
          </p>
          <div className="flex items-center gap-1.5 mb-1 text-[10px] font-bold uppercase tracking-wider">
            <span className={`w-1.5 h-1.5 rounded-full ${getStatusColorWeek(ev.status_ata).split(" ")[0]}`} />
            <span className={getStatusColor(ev.status_ata).split(" ")[1]}>{formatStatus(ev.status_ata)}</span>
            {ev.tipo && <span className="text-slate-300">|</span>}
            {ev.tipo && <span className="text-slate-400">{ev.tipo}</span>}
          </div>
          {ev.nome_grupo_recorrencia && (
            <div className="flex items-center gap-1 mt-1 text-[10px] text-indigo-700 font-semibold bg-indigo-50 px-2 py-0.5 rounded w-fit">
              <Repeat2 className="w-3 h-3" />
              Série: {ev.nome_grupo_recorrencia}
            </div>
          )}
          {ev.hora_inicio && (
            <p className="text-xs text-slate-500 flex items-center gap-1 mt-1">
              <Clock className="w-3 h-3" />
              {formatHora(ev.hora_inicio)}
            </p>
          )}
          {ev.objetivo && (
            <p className="text-xs text-slate-400 mt-1.5 line-clamp-2">
              {ev.objetivo}
            </p>
          )}
          {ev.participantes && ev.participantes.length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-slate-50">
              <p className="text-[10px] text-slate-400 font-medium mb-0.5">Participantes</p>
              {ev.participantes
                .filter((p) => p.nome)
                .slice(0, 4)
                .map((p) => {
                  const isFacilitador = p.id === ev.facilitador_id;
                  return (
                    <div key={p.id} className="flex items-center gap-1">
                      <p className={`text-[10px] truncate ${isFacilitador ? "text-amber-700 font-semibold" : "text-slate-600"}`}>
                        {p.nome}
                      </p>
                      {isFacilitador && <Crown className="w-2.5 h-2.5 text-amber-500 flex-shrink-0" />}
                    </div>
                  );
                })}
              {ev.participantes.length > 4 && (
                <p className="text-[10px] text-slate-400">+{ev.participantes.length - 4} mais</p>
              )}
            </div>
          )}
          {ev.id_grupo_recorrencia && (
            <button
              onClick={handleDeleteGroupAction}
              disabled={deletingGroup}
              className="mt-2 w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded bg-red-50 text-red-600 hover:bg-red-100 transition-colors text-[10px] font-semibold"
            >
              {deletingGroup ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              Excluir toda a série recorrente
            </button>
          )}
          <a
            href={detailHref}
            className="mt-2 inline-block text-[10px] text-indigo-600 hover:underline font-medium"
            onClick={(e) => e.stopPropagation()}
          >
            Ver detalhe →
          </a>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Main Page
// ──────────────────────────────────────────
export default function CalendarioPage() {
  const today = new Date();
  const searchParams = useSearchParams();
  const [todayKey, setTodayKey] = useState("");
  useEffect(() => { setTodayKey(formatDateKey(new Date())); }, []);

  // Restaura o estado do calendário ao voltar dos detalhes
  const initYear = searchParams.get("year") ? parseInt(searchParams.get("year")!, 10) : today.getFullYear();
  const initMonth = searchParams.get("month") ? parseInt(searchParams.get("month")!, 10) : today.getMonth();
  const initView = searchParams.get("view") === "week" ? "week" : "month" as "month" | "week";
  const initWeekAnchor = (() => {
    const w = searchParams.get("week");
    if (w) {
      const [y, m, d] = w.split("-").map(Number);
      return new Date(y, m - 1, d);
    }
    return today;
  })();

  const [viewYear, setViewYear] = useState(initYear);
  const [viewMonth, setViewMonth] = useState(initMonth);
  const [viewMode, setViewMode] = useState<"month" | "week">(initView);
  const [weekAnchor, setWeekAnchor] = useState(initWeekAnchor);
  const [eventos, setEventos] = useState<EventoCalendario[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [selectedTime, setSelectedTime] = useState<string | undefined>(undefined);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [expandedDays, setExpandedDays] = useState<Record<string, boolean>>({});

  // Filtro de facilitadores (client-side: o range de mês/semana já é pequeno)
  const { facilitadores } = useFacilitadores();
  const [filtroFacilitadores, setFiltroFacilitadores] = useState<string[]>(
    searchParams.get("facilitador") ? searchParams.get("facilitador")!.split(",").filter(Boolean) : []
  );

  // Calcula o range de datas a buscar
  const fetchRange = useCallback(() => {
    if (viewMode === "month") {
      const dataInicio = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-01`;
      const ultimoDia = new Date(viewYear, viewMonth + 1, 0).getDate();
      const dataFim = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(ultimoDia).padStart(2, "0")}`;
      return { dataInicio, dataFim };
    } else {
      const days = getWeekDates(weekAnchor);
      return { dataInicio: formatDateKey(days[0]), dataFim: formatDateKey(days[6]) };
    }
  }, [viewMode, viewYear, viewMonth, weekAnchor]);

  const fetchEventos = useCallback(async () => {
    setLoading(true);
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      const { dataInicio, dataFim } = fetchRange();
      const res = await fetch(
        `/api/reunioes/calendario?data_inicio=${dataInicio}&data_fim=${dataFim}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (res.ok) setEventos(await res.json());
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }, [fetchRange]);

  useEffect(() => {
    fetchEventos();
  }, [fetchEventos]);

  // Aplica filtro de facilitadores antes de agrupar (client-side)
  const eventosFiltrados = useMemo(() => {
    if (filtroFacilitadores.length === 0) return eventos;
    const set = new Set(filtroFacilitadores);
    return eventos.filter((ev) => ev.facilitador_id && set.has(ev.facilitador_id));
  }, [eventos, filtroFacilitadores]);

  // Mapa data → eventos
  const eventosPorDia = eventosFiltrados.reduce<Record<string, EventoCalendario[]>>(
    (acc, ev) => {
      const key = ev.data;
      if (!acc[key]) acc[key] = [];
      acc[key].push(ev);
      return acc;
    },
    {}
  );

  const grid = getMonthGrid(viewYear, viewMonth);
  const totalRows = grid.length / 7;
  const weekDates = getWeekDates(weekAnchor);

  // Navegação mensal
  function navMes(dir: -1 | 1) {
    let m = viewMonth + dir;
    let y = viewYear;
    if (m < 0) { m = 11; y--; }
    if (m > 11) { m = 0; y++; }
    setViewMonth(m);
    setViewYear(y);
  }

  // Navegação semanal
  function navSemana(dir: -1 | 1) {
    const next = new Date(weekAnchor);
    next.setDate(weekAnchor.getDate() + dir * 7);
    setWeekAnchor(next);
  }

  function handleDayClick(date: Date) {
    setSelectedDate(date);
    setSelectedTime(undefined);
    setShowModal(true);
  }

  function handleSlotClick(date: Date, hora: string) {
    setSelectedDate(date);
    setSelectedTime(hora);
    setShowModal(true);
  }

  function handleAgendarSuccess() {
    setShowModal(false);
    setSuccessMsg("Reunião agendada com sucesso. Os participantes foram notificados por email.");
    setTimeout(() => setSuccessMsg(null), 5000);
    fetchEventos();
  }

  function handleUploadSuccess() {
    setShowUploadModal(false);
    setSuccessMsg("Transcrição enviada. A IA está processando — a reunião aparecerá no calendário em instantes.");
    setTimeout(() => setSuccessMsg(null), 6000);
    fetchEventos();
  }

  function handleDeleteEvento(id: string) {
    setEventos((prev) => prev.filter((ev) => ev.id_reuniao !== id));
  }

  function handleDeleteGroup() {
    setSuccessMsg("Série de reuniões recorrentes deletada com sucesso.");
    setTimeout(() => setSuccessMsg(null), 4000);
    fetchEventos();
  }

  // Label do período exibido
  const weekLabel = (() => {
    const s = weekDates[0];
    const e = weekDates[6];
    if (s.getMonth() === e.getMonth()) {
      return `${s.getDate()}–${e.getDate()} de ${MESES[s.getMonth()]} ${s.getFullYear()}`;
    }
    return `${s.getDate()} ${MESES[s.getMonth()]} – ${e.getDate()} ${MESES[e.getMonth()]} ${e.getFullYear()}`;
  })();

  return (
    <div className="space-y-6 animate-fade-in-up">
      {showModal && (
        <AgendarModal
          defaultDate={selectedDate}
          defaultTime={selectedTime}
          onClose={() => setShowModal(false)}
          onSuccess={handleAgendarSuccess}
        />
      )}

      {showUploadModal && (
        <UploadTranscricaoModal
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Calendário de Reuniões</h1>
          <p className="text-slate-500 text-sm mt-0.5">Agende e visualize reuniões presenciais</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            id="btn-importar-transcricao"
            onClick={() => setShowUploadModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 hover:border-slate-300 transition-all cursor-pointer"
          >
            <Upload className="w-4 h-4" />
            Importar Transcrição
          </button>
          <button
            id="btn-agendar-reuniao"
            onClick={() => {
              setSelectedDate(today);
              setSelectedTime(undefined);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-xl text-sm font-medium hover:shadow-lg transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Agendar Reunião
          </button>
        </div>
      </div>

      {/* Sucesso */}
      {successMsg && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-700 text-sm animate-fade-in-up">
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          {successMsg}
        </div>
      )}

      {/* Barra de Filtros */}
      <div className="bg-white p-4 rounded-xl border border-border shadow-premium flex flex-col gap-3">
        <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm">
          <Filter className="w-4 h-4" />
          <span>Filtros</span>
          {filtroFacilitadores.length > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full font-medium">
              Ativos
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 items-end">
          <MultiSelect
            id="filtro-facilitador-calendario"
            label="Facilitador"
            options={facilitadores.map((f) => ({ value: f.id, label: f.nome_completo }))}
            selected={filtroFacilitadores}
            onChange={setFiltroFacilitadores}
            placeholder="Todos os Facilitadores"
            allLabel="Todos os Facilitadores"
          />
          {filtroFacilitadores.length > 0 && (
            <div className="flex flex-col justify-end">
              <button
                onClick={() => setFiltroFacilitadores([])}
                className="text-sm font-medium text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 transition-colors py-2 px-3 rounded-lg w-full text-center"
              >
                Limpar Filtros
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Calendário */}
      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-visible">
        {/* Cabeçalho do calendário */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          {/* Navegação (esquerda) */}
          <button
            onClick={() => viewMode === "month" ? navMes(-1) : navSemana(-1)}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <ChevronLeft className="w-5 h-5 text-slate-600" />
          </button>

          {/* Título do período */}
          <div className="text-center flex-1 mx-4">
            <h2 className="text-lg font-bold text-slate-900">
              {viewMode === "month"
                ? `${MESES[viewMonth]} ${viewYear}`
                : weekLabel}
            </h2>
            {loading && (
              <p className="text-xs text-slate-400 mt-0.5">Carregando eventos...</p>
            )}
          </div>

          {/* Toggle de visão (direita) */}
          <div className="flex items-center gap-2">
            <div className="flex items-center bg-slate-100 rounded-xl p-1 gap-1">
              <button
                onClick={() => setViewMode("month")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  viewMode === "month"
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                Mensal
              </button>
              <button
                onClick={() => setViewMode("week")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  viewMode === "week"
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                <Calendar className="w-3.5 h-3.5" />
                Semanal
              </button>
            </div>
            <button
              onClick={() => viewMode === "month" ? navMes(1) : navSemana(1)}
              className="p-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
            >
              <ChevronRight className="w-5 h-5 text-slate-600" />
            </button>
          </div>
        </div>

        {/* Conteúdo: Mensal ou Semanal */}
        {viewMode === "month" ? (
          <>
            {/* Grid dias da semana */}
            <div className="grid grid-cols-7 border-b border-slate-100">
              {DIAS_SEMANA.map((d) => (
                <div
                  key={d}
                  className="py-2 text-center text-xs font-semibold text-slate-500 uppercase tracking-wide"
                >
                  {d}
                </div>
              ))}
            </div>

            {/* Grid de dias */}
            <div className="grid grid-cols-7">
              {grid.map((date, i) => {
                const key = date ? formatDateKey(date) : `empty-${i}`;
                const isToday = date ? key === todayKey : false;
                const isPast = date ? date < today && !isToday : false;
                const evs = date ? eventosPorDia[key] ?? [] : [];
                const colIndex = i % 7;
                const rowIndex = Math.floor(i / 7);

                return (
                  <div
                    key={i}
                    onClick={() => date && handleDayClick(date)}
                    className={`min-h-[160px] p-2 border-b border-r border-slate-50 flex flex-col transition-colors ${
                      date
                        ? isPast
                          ? "cursor-pointer hover:bg-slate-50/60"
                          : "cursor-pointer hover:bg-indigo-50/40"
                        : ""
                    }`}
                  >
                    {date && (
                      <>
                        <span
                          className={`self-start w-7 h-7 flex items-center justify-center rounded-full text-sm font-medium mb-1 transition-colors ${
                            isToday
                              ? "bg-indigo-600 text-white"
                              : isPast
                              ? "text-slate-300"
                              : "text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          {date.getDate()}
                        </span>
                        <div className="space-y-0.5 flex-1">
                          {(() => {
                            const isExpanded = expandedDays[key] || false;
                            const displayEvs = isExpanded ? evs : evs.slice(0, 3);
                            return (
                              <>
                                {displayEvs.map((ev) => (
                                  <EventCard
                                    key={ev.id_reuniao}
                                    evento={ev}
                                    colIndex={colIndex}
                                    rowIndex={rowIndex}
                                    totalRows={totalRows}
                                    backYear={viewYear}
                                    backMonth={viewMonth}
                                    onDelete={handleDeleteEvento}
                                    onDeleteGroup={handleDeleteGroup}
                                  />
                                ))}
                                {evs.length > 3 && !isExpanded && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setExpandedDays((prev) => ({ ...prev, [key]: true }));
                                    }}
                                    className="text-[10px] text-indigo-500 font-medium px-1 hover:underline cursor-pointer text-left w-full"
                                  >
                                    +{evs.length - 3} mais
                                  </button>
                                )}
                              </>
                            );
                          })()}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <WeekView
            weekDates={weekDates}
            eventosPorDia={eventosPorDia}
            todayKey={todayKey}
            onSlotClick={handleSlotClick}
            weekAnchorKey={formatDateKey(weekAnchor)}
            onDeleteEvento={handleDeleteEvento}
            onDeleteGroup={handleDeleteGroup}
          />
        )}

        {/* Legenda */}
        <div className="px-6 py-3 border-t border-slate-50 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 inline-block" />
            Programada
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
            Processando IA
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-400 inline-block" />
            Aguard. Validação
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block" />
            Aguard. Assinatura
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
            Assinada
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-400 inline-block" />
            Erro
          </span>
          <span className="text-slate-300">·</span>
          <span>
            {viewMode === "month"
              ? "Clique no evento para ver detalhes, ou no dia para agendar"
              : "Clique em qualquer slot para agendar uma reunião"}
          </span>
          {viewMode === "week" && (
            <>
              <span className="text-slate-300">·</span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-0.5 bg-red-400 inline-block rounded" />
                Hora atual
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
