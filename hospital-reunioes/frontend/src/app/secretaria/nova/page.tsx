"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { MultiSelect } from "@/components/ui/MultiSelect";
import {
  ArrowLeft,
  Loader2,
  CalendarPlus,
  Save,
  ChevronDown,
  Check,
  Search,
} from "lucide-react";

interface ParticipanteOption {
  id: string;
  nome_completo: string;
  cargo?: string | null;
  email?: string;
  ativo?: boolean;
  is_externo?: boolean;
}

const TIPOS = [
  "Diretoria",
  "Gerencial",
  "Coordenação",
  "Mensal",
  "Extraordinária",
];

export default function NovaReuniaoSecretaria() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const editId = searchParams.get("edit");
  const { toast: showToast } = useToast();

  const [participantes, setParticipantes] = useState<ParticipanteOption[]>([]);
  const [facilitadores, setFacilitadores] = useState<ParticipanteOption[]>([]);
  const [loadingParticipantes, setLoadingParticipantes] = useState(true);
  const [loadingInitial, setLoadingInitial] = useState(Boolean(editId));
  const [submitting, setSubmitting] = useState(false);

  const [titulo, setTitulo] = useState("");
  const [data, setData] = useState("");
  const [horaInicio, setHoraInicio] = useState("");
  const [horaFim, setHoraFim] = useState("");
  const [tipo, setTipo] = useState<string>("");
  const [objetivo, setObjetivo] = useState("");
  const [facilitadorId, setFacilitadorId] = useState<string>("");
  const [participantesSelecionados, setParticipantesSelecionados] = useState<
    string[]
  >([]);
  // Snapshot dos vínculos que vieram do banco — usado pra calcular o diff
  // (toAdd / toRemove) só em modo edição.
  const [participantesIniciais, setParticipantesIniciais] = useState<string[]>(
    []
  );

  const carregarParticipantes = useCallback(async () => {
    setLoadingParticipantes(true);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};

      // Lista de participantes pra escolher quem vai estar na reunião.
      const [resAll, resFacs] = await Promise.all([
        fetch("/api/participantes?ativo=true&limit=200", { headers }),
        fetch(
          "/api/participantes?ativo=true&access_profile=super_admin&limit=200",
          { headers }
        ),
      ]);

      if (!resAll.ok) throw new Error("Erro ao buscar participantes");
      if (!resFacs.ok) throw new Error("Erro ao buscar facilitadores");

      setParticipantes((await resAll.json()) as ParticipanteOption[]);
      setFacilitadores((await resFacs.json()) as ParticipanteOption[]);
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erro ao listar participantes",
        "error"
      );
    } finally {
      setLoadingParticipantes(false);
    }
  }, [showToast]);

  const carregarReuniaoExistente = useCallback(
    async (id_reuniao: string) => {
      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        const token = session?.access_token;
        const res = await fetch(`/api/reunioes/${id_reuniao}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          cache: "no-store",
        });
        if (!res.ok) {
          if (res.status === 404) {
            showToast("Reunião não encontrada", "error");
            router.replace("/secretaria");
            return;
          }
          throw new Error("Erro ao carregar reunião");
        }
        const r = await res.json();
        setTitulo(r.titulo || "");
        setData(r.data || "");
        setHoraInicio(r.hora_inicio ? String(r.hora_inicio).slice(0, 5) : "");
        setHoraFim(r.hora_fim ? String(r.hora_fim).slice(0, 5) : "");
        setTipo(r.tipo || "");
        setObjetivo(r.objetivo || "");
        setFacilitadorId(r.facilitador_id || "");
        const pps = (r.participantes_programada || []) as Array<{ id: string }>;
        const ids = pps.map((p) => p.id);
        setParticipantesSelecionados(ids);
        setParticipantesIniciais(ids);
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "Erro ao carregar reunião",
          "error"
        );
      } finally {
        setLoadingInitial(false);
      }
    },
    [router, showToast]
  );

  useEffect(() => {
    carregarParticipantes();
  }, [carregarParticipantes]);

  useEffect(() => {
    if (editId) carregarReuniaoExistente(editId);
  }, [editId, carregarReuniaoExistente]);

  // Facilitador é sempre participante — não dá pra desmarcar.
  useEffect(() => {
    if (!facilitadorId) return;
    setParticipantesSelecionados((prev) =>
      prev.includes(facilitadorId) ? prev : [...prev, facilitadorId]
    );
  }, [facilitadorId]);

  const opcoesParticipantes = useMemo(
    () =>
      participantes.map((p) => ({
        value: p.id,
        label: p.cargo
          ? `${p.nome_completo} (${p.cargo})`
          : p.nome_completo,
      })),
    [participantes]
  );

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!titulo.trim() || !data || !facilitadorId) {
      showToast(
        "Preencha título, data e selecione um facilitador.",
        "error"
      );
      return;
    }
    setSubmitting(true);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;

      const body: Record<string, unknown> = {
        titulo: titulo.trim(),
        data,
        hora_inicio: horaInicio || null,
        hora_fim: horaFim || null,
        tipo: tipo || null,
        objetivo: objetivo.trim() || null,
        facilitador_id: facilitadorId,
      };
      if (!editId) {
        body.participante_ids = participantesSelecionados;
      }

      const url = editId
        ? `/api/reunioes/${editId}`
        : `/api/reunioes/agendar`;
      const method = editId ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Erro ao salvar reunião");
      }

      // Em modo edição, sincronizar participantes via diff (toAdd / toRemove)
      // contra o snapshot inicial. O backend protege o facilitador no nível de
      // negócio (sempre garantido na criação) — aqui evitamos remover o atual
      // explicitamente.
      if (editId) {
        const atual = new Set(participantesSelecionados);
        const iniciais = new Set(participantesIniciais);
        const toAdd = participantesSelecionados.filter(
          (id) => !iniciais.has(id)
        );
        const toRemove = participantesIniciais.filter(
          (id) => !atual.has(id) && id !== facilitadorId
        );

        const authHeaders = {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        } as Record<string, string>;

        const ops: Promise<Response>[] = [];
        if (toAdd.length > 0) {
          ops.push(
            fetch(`/api/reunioes/${editId}/participantes`, {
              method: "POST",
              headers: authHeaders,
              body: JSON.stringify({ participante_ids: toAdd }),
            })
          );
        }
        for (const pid of toRemove) {
          ops.push(
            fetch(`/api/reunioes/${editId}/participantes/${pid}`, {
              method: "DELETE",
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            })
          );
        }
        if (ops.length > 0) {
          // allSettled em vez de all: erro de rede num DELETE/POST não deve
          // mascarar o sucesso do PATCH principal (que já persistiu título,
          // data, facilitador etc.).
          const results = await Promise.allSettled(ops);
          const falhou = results.some(
            (r) => r.status === "rejected" || !r.value.ok
          );
          if (falhou) {
            showToast(
              "Reunião salva, mas alguns participantes não puderam ser sincronizados.",
              "warning"
            );
          }
        }
      }

      showToast(
        editId ? "Reunião atualizada" : "Reunião agendada",
        "success"
      );
      router.push("/secretaria");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Erro ao salvar",
        "error"
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingInitial) {
    return (
      <div className="flex items-center justify-center py-16 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <header className="flex items-center gap-3">
        <Link
          href="/secretaria"
          className="p-2 rounded-xl hover:bg-slate-100 text-slate-500"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {editId ? "Editar reunião" : "Marcar nova reunião"}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Preencha os dados pra preparar a reunião do facilitador.
          </p>
        </div>
      </header>

      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-slate-200 bg-white p-6 space-y-5"
      >
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Título <span className="text-rose-500">*</span>
          </label>
          <input
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            required
            placeholder="Ex: Reunião de Diretoria, junho 2026"
            className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Data <span className="text-rose-500">*</span>
            </label>
            <input
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              required
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Início
            </label>
            <input
              type="time"
              value={horaInicio}
              onChange={(e) => setHoraInicio(e.target.value)}
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Término
            </label>
            <input
              type="time"
              value={horaFim}
              onChange={(e) => setHoraFim(e.target.value)}
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Tipo
            </label>
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value)}
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all bg-white"
            >
              <option value="">Selecione (opcional)</option>
              {TIPOS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Facilitador <span className="text-rose-500">*</span>
            </label>
            <FacilitadorCombobox
              options={facilitadores}
              value={facilitadorId}
              onChange={setFacilitadorId}
              loading={loadingParticipantes}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Participantes
          </label>
          <MultiSelect
            options={opcoesParticipantes}
            selected={participantesSelecionados}
            onChange={setParticipantesSelecionados}
            placeholder="Selecione quem vai participar (opcional)"
          />
          <p className="text-xs text-slate-400 mt-1.5">
            O facilitador é incluído automaticamente.
            {editId
              ? " Quem entrar agora recebe convite por email; quem sair fica removido da lista."
              : ""}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Objetivo / Pauta
          </label>
          <textarea
            rows={4}
            value={objetivo}
            onChange={(e) => setObjetivo(e.target.value)}
            placeholder="Descreva o que será discutido, o que precisa ser decidido, etc."
            className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all resize-none"
          />
        </div>

        <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-100">
          <Link
            href="/secretaria"
            className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : editId ? (
              <Save className="w-4 h-4" />
            ) : (
              <CalendarPlus className="w-4 h-4" />
            )}
            {editId ? "Salvar alterações" : "Agendar reunião"}
          </button>
        </div>
      </form>
    </div>
  );
}

interface FacilitadorComboboxProps {
  options: ParticipanteOption[];
  value: string;
  onChange: (id: string) => void;
  loading?: boolean;
}

function FacilitadorCombobox({
  options,
  value,
  onChange,
  loading,
}: FacilitadorComboboxProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const selected = options.find((p) => p.id === value);
  const filtered = useMemo(() => {
    const termo = search.trim().toLowerCase();
    if (!termo) return options;
    return options.filter((p) => {
      const nome = p.nome_completo.toLowerCase();
      const cargo = (p.cargo || "").toLowerCase();
      return nome.includes(termo) || cargo.includes(termo);
    });
  }, [options, search]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={loading}
        className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white text-left flex items-center justify-between gap-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all disabled:opacity-60"
      >
        <span
          className={`truncate ${selected ? "text-slate-900" : "text-slate-400"}`}
        >
          {loading
            ? "Carregando facilitadores..."
            : selected
            ? selected.cargo
              ? `${selected.nome_completo} (${selected.cargo})`
              : selected.nome_completo
            : "Selecione um facilitador"}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <div className="absolute z-20 mt-1.5 w-full bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden">
          <div className="p-2 border-b border-slate-100">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                autoFocus
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar facilitador..."
                className="w-full pl-8 pr-2 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-300 focus:border-indigo-400"
              />
            </div>
          </div>
          <ul className="max-h-72 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-4 py-3 text-sm text-slate-400 text-center">
                Nenhum facilitador encontrado
              </li>
            ) : (
              filtered.map((p) => {
                const isSelected = p.id === value;
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onChange(p.id);
                        setOpen(false);
                        setSearch("");
                      }}
                      className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-slate-50 ${
                        isSelected ? "bg-indigo-50 text-indigo-700" : "text-slate-700"
                      }`}
                    >
                      <Check
                        className={`w-4 h-4 flex-shrink-0 ${
                          isSelected ? "text-indigo-600" : "text-transparent"
                        }`}
                      />
                      <div className="min-w-0">
                        <div className="truncate font-medium">
                          {p.nome_completo}
                        </div>
                        {p.cargo ? (
                          <div className="truncate text-xs text-slate-400">
                            {p.cargo}
                          </div>
                        ) : null}
                      </div>
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
