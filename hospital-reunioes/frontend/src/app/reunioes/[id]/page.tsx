"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useToast } from "@/components/ui/Toast";
import { createClient } from "@/lib/supabase/client";
import {
  ArrowLeft,
  Download,
  Bot,
  ClipboardCheck,
  PenLine,
  BadgeCheck,
  XCircle,
  Pen,
  CheckCircle,
  AlertTriangle,
  FileText,
  Clock,
  Users,
  ListChecks,
  CalendarDays,
  Loader2,
  Upload,
  Plus,
  X,
  Search,
  Sparkles,
  CheckSquare,
  Square,
  Edit3,
  Save,
  Repeat2,
  Trash2,
  Crown,
  Crosshair,
  Target,
  MessageSquare,
  ArrowRightLeft,
} from "lucide-react";
import ChatCorrecao from "@/components/reunioes/ChatCorrecao";
import ChatAtaGuiada from "@/components/reunioes/ChatAtaGuiada";
import { SignatariosCard } from "@/components/reunioes/SignatariosCard";
import TrocarFacilitadorModal from "@/components/reunioes/TrocarFacilitadorModal";
import { DeleteButton } from "@/components/DeleteButton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { isSecretaria, isSuperAdmin } from "@/lib/auth";
import { getErrorMessage } from "@/lib/errors";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  ParticipanteCombobox,
  type ResolucaoEstado,
} from "@/components/participantes/ParticipanteCombobox";
import { ResponsavelInlineCombobox } from "@/components/reunioes/ResponsavelInlineCombobox";

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
  | "APROVADA";

interface ParticipanteProgramada {
  id: string;
  nome: string;
  cargo: string;
  email: string;
  area?: string;
}

interface ParticipanteCadastrado {
  id: string;
  nome_completo: string;
  cargo: string | null;
  email: string;
  area?: string;
}

interface Participante {
  nome: string;
  cargo: string;
  setor?: string;
  presente: boolean;
}

interface Atribuicao {
  acao: string;
  responsavel: string;
  cargo: string;
  prazo: string | null;
  entregavel: string;
  objetivo_meta?: string;
  status?: "ABERTO" | "EM_ANDAMENTO" | "CONCLUIDO";
}

interface ContribuicaoDiscussao {
  nome?: string;
  funcao: string;
  conteudo: string;
}

interface TopicoDiscussao {
  titulo: string;
  descricao?: string;
  contribuicoes?: ContribuicaoDiscussao[];
  divergencias?: string[];
  decisao?: string;
  responsavel?: string | null;
}

interface JsonAta {
  hora_inicio?: string;
  hora_fim?: string;
  objetivo?: string;
  participantes?: Participante[];
  discussao?: TopicoDiscussao[];
  registro_narrativo?: string;
  resumo_executivo?: string;
  quadro_atribuicoes?: Atribuicao[];
  proxima_reuniao?: string | null;
  lacunas_identificadas?: string[];
  error?: string;
  _mock?: boolean;
}

interface Reuniao {
  id_reuniao: string;
  data: string;
  tipo: string | null;
  titulo: string | null;
  objetivo: string | null;
  status_ata: StatusAta;
  total_acoes: number;
  acoes_concluidas: number;
  hora_inicio: string | null;
  hora_fim: string | null;
  json_ata: JsonAta | null;
  url_pdf_preliminar: string | null;
  url_pdf_assinado: string | null;
  url_transcricao: string | null;
  envelope_key_clicksign: string | null;
  data_assinatura: string | null;
  fonte: string;
  metodo_geracao?: "TRANSCRICAO" | "GUIADA";
  created_at: string;
  facilitador_id: string | null;
  participantes_programada?: ParticipanteProgramada[];
  participantes_nao_reconhecidos?: Array<{ nome: string; cargo: string; setor?: string }>;
}

// ──────────────────────────────────────────
// Status Timeline
// ──────────────────────────────────────────
const TIMELINE_STEPS: { status: StatusAta; label: string; icon: typeof Bot }[] = [
  { status: "PROCESSANDO", label: "Processando IA", icon: Bot },
  { status: "AGUARDANDO_RESOLUCAO", label: "Resolver Participantes", icon: Users },
  { status: "AGUARDANDO_VALIDACAO", label: "Aguard. Validação", icon: ClipboardCheck },
  { status: "AGUARDANDO_ASSINATURA", label: "Aguard. Assinatura", icon: PenLine },
  { status: "ASSINADA", label: "Assinada", icon: BadgeCheck },
];

// Ramo terminal sem assinatura: a Ata vai de Validação direto pra Aprovada,
// no lugar de Aguard. Assinatura → Assinada. Compartilha o tronco (3 primeiros
// passos) com TIMELINE_STEPS pra não duplicar a manutenção.
const TIMELINE_STEPS_APROVADA: { status: StatusAta; label: string; icon: typeof Bot }[] = [
  ...TIMELINE_STEPS.slice(0, 3),
  { status: "APROVADA", label: "Aprovada", icon: CheckCircle },
];

const STATUS_ORDER: Record<StatusAta, number> = {
  PROGRAMADA: -1,
  PROCESSANDO: 0,
  ERRO: 0,
  AGUARDANDO_RESOLUCAO: 1,
  AGUARDANDO_VALIDACAO: 2,
  AGUARDANDO_ASSINATURA: 3,
  ASSINADA: 4,
  APROVADA: 3, // índice de APROVADA em TIMELINE_STEPS_APROVADA (ramo terminal)
};

function StatusTimeline({ current }: { current: StatusAta }) {
  const isAprovada = current === "APROVADA";
  const steps = isAprovada ? TIMELINE_STEPS_APROVADA : TIMELINE_STEPS;
  const currentOrder = STATUS_ORDER[current] ?? 0;
  const isError = current === "ERRO";

  return (
    <div className="flex items-center gap-2">
      {steps.map((step, i) => {
        const done = currentOrder > i;
        const active = currentOrder === i && !isError;
        const Icon = step.icon;
        return (
          <div key={step.status} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                done
                  ? "bg-gradient-to-r from-primary to-primary-dark text-white"
                  : active
                  ? "bg-primary/10 text-primary ring-2 ring-primary/30"
                  : "bg-slate-100 text-slate-400"
              }`}
            >
              <Icon className="w-3.5 h-3.5" strokeWidth={done || active ? 2 : 1.5} />
              {step.label}
            </div>
            {i < steps.length - 1 && (
              <div className={`h-px w-6 ${done ? "bg-primary" : "bg-slate-200"}`} />
            )}
          </div>
        );
      })}
      {isError && (
        <div className="ml-2 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
          <XCircle className="w-3.5 h-3.5" />
          Erro
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Section Card
// ──────────────────────────────────────────
function Section({
  title,
  icon: Icon,
  children,
  action,
}: {
  title: string;
  icon?: typeof FileText;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          {Icon && <Icon className="w-4.5 h-4.5 text-primary" strokeWidth={1.5} />}
          <h2 className="font-semibold text-slate-900">{title}</h2>
        </div>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

// ──────────────────────────────────────────
// Inline Edit Field
// ──────────────────────────────────────────
function InlineEditField({
  label,
  value,
  onSave,
  type = "text",
  options,
  icon: Icon,
}: {
  label: string;
  value: string;
  onSave: (v: string) => Promise<void>;
  type?: "text" | "select" | "time" | "textarea" | "date";
  options?: { label: string; value: string }[];
  icon?: typeof FileText;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(draft);
    setSaving(false);
    setEditing(false);
  };

  // Format YYYY-MM-DD → DD/MM/YYYY for display
  const displayValue = (() => {
    if (type === "date" && value && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const [y, m, d] = value.split("-");
      return `${d}/${m}/${y}`;
    }
    return value;
  })();

  if (!editing) {
    return (
      <div className="group flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          {Icon && <Icon className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" strokeWidth={1.5} />}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-0.5">{label}</p>
            <p className="text-slate-800 text-sm font-medium">{displayValue || <span className="text-slate-300 font-normal italic">Não definido</span>}</p>
          </div>
        </div>
        <button
          onClick={() => { setDraft(value); setEditing(true); }}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 flex-shrink-0"
        >
          <Edit3 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400 font-medium">{label}</p>
      {type === "select" && options ? (
        <select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="">— Selecionar —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
        />
      ) : (
        <input
          type={type}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full px-3 py-2 rounded-xl border border-primary/40 bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-dark transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          Salvar
        </button>
        <button
          onClick={() => setEditing(false)}
          className="px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-medium rounded-lg hover:bg-slate-200 transition-colors"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// Recorrência Panel
// ──────────────────────────────────────────
const DIAS_SEMANA = [
  { label: "Dom", value: 0 },
  { label: "Seg", value: 1 },
  { label: "Ter", value: 2 },
  { label: "Qua", value: 3 },
  { label: "Qui", value: 4 },
  { label: "Sex", value: 5 },
  { label: "Sáb", value: 6 },
];

function gerarDatas(
  dataBase: string,
  diaSemana: number,
  frequencia: "semanal" | "quinzenal",
  quantidade: number
): string[] {
  const datas: string[] = [];
  const intervalo = frequencia === "semanal" ? 7 : 14;

  // Encontra o próximo dia da semana desejado a partir da data base
  const base = new Date(dataBase + "T12:00:00");
  const atual = new Date(base);
  // Avança para o próximo dia da semana pedido (nunca a data base em si)
  do {
    atual.setDate(atual.getDate() + 1);
  } while (atual.getDay() !== diaSemana);

  for (let i = 0; i < quantidade; i++) {
    const y = atual.getFullYear();
    const m = String(atual.getMonth() + 1).padStart(2, "0");
    const d = String(atual.getDate()).padStart(2, "0");
    datas.push(`${y}-${m}-${d}`);
    atual.setDate(atual.getDate() + intervalo);
  }
  return datas;
}

function RecorrenciaPanel({
  reuniao,
  getToken,
}: {
  reuniao: Reuniao;
  getToken: () => Promise<string | undefined>;
}) {
  const [open, setOpen] = useState(false);
  const [frequencia, setFrequencia] = useState<"semanal" | "quinzenal">("semanal");
  const [diaSemana, setDiaSemana] = useState<number>(1); // segunda-feira
  const [quantidade, setQuantidade] = useState(4);
  const [horario, setHorario] = useState(reuniao.hora_inicio ?? "");
  const [nomeGrupo, setNomeGrupo] = useState("");
  const [criando, setCriando] = useState(false);
  const [sucesso, setSucesso] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const datas = open ? gerarDatas(reuniao.data, diaSemana, frequencia, quantidade) : [];

  const participanteIds = (reuniao.participantes_programada ?? []).map((p) => p.id);

  const handleCriar = async () => {
    setCriando(true);
    setErro(null);
    const token = await getToken();
    let criados = 0;
    const idGrupo = crypto.randomUUID();

    for (const data of datas) {
      const payload = {
        titulo: reuniao.titulo || reuniao.tipo || "Reunião",
        data,
        hora_inicio: horario || null,
        tipo: reuniao.tipo ?? null,
        objetivo: reuniao.objetivo || null,
        participante_ids: participanteIds,
        id_grupo_recorrencia: idGrupo,
        nome_grupo_recorrencia: nomeGrupo.trim() || null,
      };
      const res = await fetch("/api/reunioes/agendar", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) criados++;
    }

    setCriando(false);
    if (criados === datas.length) {
      setSucesso(criados);
    } else {
      setErro(`Apenas ${criados} de ${datas.length} reuniões foram criadas.`);
    }
  };

  const formatData = (iso: string) => {
    const [y, m, d] = iso.split("-");
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return date.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
  };

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
      <button
        onClick={() => { setOpen(!open); setSucesso(null); setErro(null); }}
        className="w-full px-6 py-4 flex items-center gap-2.5 hover:bg-slate-50 transition-colors"
      >
        <Repeat2 className="w-4 h-4 text-primary flex-shrink-0" strokeWidth={1.5} />
        <h2 className="font-semibold text-slate-900 text-left flex-1">Recorrência</h2>
        <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
          {open ? "Fechar" : "Configurar"}
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-100 px-6 py-5 space-y-5">
          {sucesso !== null ? (
            <div className="text-center py-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-100 flex items-center justify-center mx-auto mb-3">
                <CheckCircle className="w-6 h-6 text-emerald-600" />
              </div>
              <p className="font-semibold text-slate-900">{sucesso} reuniões criadas!</p>
              <p className="text-xs text-slate-500 mt-1">Elas aparecem no calendário com os mesmos detalhes.</p>
              <button
                onClick={() => { setSucesso(null); setOpen(false); }}
                className="mt-4 px-4 py-2 text-sm text-primary hover:underline"
              >
                Fechar
              </button>
            </div>
          ) : (
            <>
              {/* Frequência */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Frequência</p>
                <div className="grid grid-cols-2 gap-2">
                  {(["semanal", "quinzenal"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFrequencia(f)}
                      className={`py-2 rounded-xl border text-sm font-medium transition-all ${
                        frequencia === f
                          ? "bg-primary/10 border-primary/40 text-primary"
                          : "border-slate-200 text-slate-600 hover:border-slate-300"
                      }`}
                    >
                      {f === "semanal" ? "Semanal" : "Quinzenal"}
                    </button>
                  ))}
                </div>
              </div>

              {/* Dia da semana */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Dia da semana</p>
                <div className="grid grid-cols-7 gap-1">
                  {DIAS_SEMANA.map((d) => (
                    <button
                      key={d.value}
                      onClick={() => setDiaSemana(d.value)}
                      className={`py-1.5 rounded-lg text-xs font-medium transition-all ${
                        diaSemana === d.value
                          ? "bg-primary text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Horário */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Horário</p>
                <input
                  type="time"
                  value={horario}
                  onChange={(e) => setHorario(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>

              {/* Nome do Grupo */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Nome da Série (Opcional)</p>
                <input
                  type="text"
                  placeholder="Ex: Semanal UTI"
                  value={nomeGrupo}
                  onChange={(e) => setNomeGrupo(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>

              {/* Repetições */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Repetições</p>
                  <span className="text-sm font-bold text-primary">{quantidade}x</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={52}
                  value={quantidade}
                  onChange={(e) => setQuantidade(Number(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>1</span>
                  <span>52 semanas</span>
                </div>
              </div>

              {/* Preview */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  Preview — {datas.length} datas
                </p>
                <div className="max-h-36 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50 divide-y divide-slate-100">
                  {datas.map((d, i) => (
                    <div key={d} className="flex items-center gap-2 px-3 py-1.5">
                      <span className="text-xs text-slate-400 w-5 text-right">{i + 1}</span>
                      <span className="text-sm text-slate-700">{formatData(d)}</span>
                      {horario && <span className="ml-auto text-xs text-slate-400">{horario}</span>}
                    </div>
                  ))}
                </div>
              </div>

              {erro && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-2">{erro}</p>
              )}

              <button
                onClick={handleCriar}
                disabled={criando || datas.length === 0}
                className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-primary to-primary-dark text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-primary/20 transition-all disabled:opacity-60"
              >
                {criando ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Criando reuniões...</>
                ) : (
                  <><Repeat2 className="w-4 h-4" /> Criar {datas.length} reuniões recorrentes</>
                )}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Preparação Checklist
// ──────────────────────────────────────────
function PreparacaoChecklist({ reuniao }: { reuniao: Reuniao }) {
  const participantes = reuniao.participantes_programada ?? [];
  const items = [
    { label: "Definir pauta da reunião", done: !!reuniao.objetivo?.trim(), tip: "Descreva o propósito principal" },
    { label: "Definir tipo de reunião", done: !!reuniao.tipo, tip: "Ex: Gerencial, Diretoria, Mensal..." },
    { label: "Definir horário de início", done: !!reuniao.hora_inicio, tip: "Quando a reunião vai começar?" },
    { label: `Adicionar participantes (${participantes.length} adicionados)`, done: participantes.length > 0, tip: "Adicione ao menos um participante" },
  ];
  const done = items.filter((i) => i.done).length;
  const pct = Math.round((done / items.length) * 100);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-500">{done} de {items.length} concluídos</span>
        <span className="text-xs font-semibold text-primary">{pct}%</span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-1.5">
        <div
          className="bg-gradient-to-r from-primary to-primary-dark h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="space-y-2 pt-1">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-2.5">
            {item.done ? (
              <CheckSquare className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
            ) : (
              <Square className="w-4 h-4 text-slate-300 flex-shrink-0 mt-0.5" />
            )}
            <div>
              <p className={`text-sm ${item.done ? "text-slate-500 line-through" : "text-slate-800 font-medium"}`}>
                {item.label}
              </p>
              {!item.done && <p className="text-xs text-slate-400">{item.tip}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// Main Page
// ──────────────────────────────────────────
export default function ReuniaoDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const searchParams = useSearchParams();

  const { toast } = useToast();

  const fromCalendario = searchParams.get("from") === "calendario";
  const backYear = searchParams.get("year");
  const backMonth = searchParams.get("month");
  const backWeek = searchParams.get("week");

  const backHref = (() => {
    if (!fromCalendario) return "/reunioes/calendario";
    if (backWeek) return `/reunioes/calendario?view=week&week=${backWeek}`;
    if (backYear && backMonth) return `/reunioes/calendario?year=${backYear}&month=${backMonth}`;
    return "/reunioes/calendario";
  })();
  const backLabel = fromCalendario ? "Calendário" : "Reuniões";

  const [reuniao, setReuniao] = useState<Reuniao | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Standard flow state
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmSemAssinatura, setConfirmSemAssinatura] = useState(false);

  // Chat correction mode
  const [correctionMode, setCorrectionMode] = useState(false);
  const [sectionContext, setSectionContext] = useState<string | null>(null);

  // Desmarcar reunião
  const [showDesmarcarModal, setShowDesmarcarModal] = useState(false);
  const [desmarcando, setDesmarcando] = useState(false);
  const [showTrocarFacilitador, setShowTrocarFacilitador] = useState(false);

  // Participant management
  const [allParticipantes, setAllParticipantes] = useState<ParticipanteCadastrado[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [showParticipanteSearch, setShowParticipanteSearch] = useState(false);
  const [addingParticipante, setAddingParticipante] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);

  // Transcript upload
  const [uploadLoading, setUploadLoading] = useState(false);
  const [ataGuiadaAberta, setAtaGuiadaAberta] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Resolução de participantes não reconhecidos — chave = nome identificado pela IA
  const [resolucoes, setResolucoes] = useState<Record<string, ResolucaoEstado>>({})
  const [resolucaoLoading, setResolucaoLoading] = useState(false)

  // Super admin (Fase 04)
  const { participante: currentUser } = useCurrentParticipante();
  const canSuperAdmin = isSuperAdmin(currentUser);
  // Secretária vê a reunião como agenda (calendário + participantes), mas
  // não tem acesso a ata, pendências, resumo, quadro de atribuições. Backend
  // já bloqueia esses endpoints com 403 — esta flag esconde a UI correspondente.
  const hideAtaSections = isSecretaria(currentUser);

  useEffect(() => { setMounted(true); }, []);

  const getToken = async () => {
    const supabase = createClient();
    // getSession() já dispara refresh automático se o access_token expirou —
    // não chamamos getUser() antes pra não perder o header Authorization quando
    // o JWT ainda é válido só que está expirado no cache do cliente.
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token;
  };

  const loadReuniao = async () => {
    try {
      const token = await getToken();
      const res = await fetch(`/api/reunioes/${id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Reunião não encontrada");
      setReuniao(await res.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao carregar");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadReuniao(); }, [id]);

  // Load all participants for search (only when PROGRAMADA)
  useEffect(() => {
    if (reuniao?.status_ata !== "PROGRAMADA") return;
    const load = async () => {
      const token = await getToken();
      const res = await fetch("/api/participantes", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) setAllParticipantes(await res.json());
    };
    load();
  }, [reuniao?.status_ata]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowParticipanteSearch(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Inicializa resoluções quando entra em AGUARDANDO_RESOLUCAO: cada nome começa pendente.
  useEffect(() => {
    if (reuniao?.status_ata === "AGUARDANDO_RESOLUCAO" && reuniao?.participantes_nao_reconhecidos) {
      const inicial: Record<string, ResolucaoEstado> = {}
      for (const p of reuniao.participantes_nao_reconhecidos) {
        if (p?.nome) inicial[p.nome] = { tipo: "pendente" }
      }
      setResolucoes(inicial)
    }
  }, [reuniao?.status_ata, reuniao?.participantes_nao_reconhecidos])

  // Polling for PROCESSANDO status
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    const currentStatus = reuniao?.status_ata;
    const poll = async () => {
      const token = await getToken();
      const res = await fetch(`/api/reunioes/${id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status_ata !== currentStatus) {
          await loadReuniao();
        }
      }
    };
    if (reuniao?.status_ata === "PROCESSANDO" || reuniao?.status_ata === "AGUARDANDO_RESOLUCAO") {
      interval = setInterval(poll, 4000);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [id, reuniao?.status_ata]);

  // ── Handlers: resolução de participantes ──
  const handleResolverParticipantes = async () => {
    if (!reuniao) return
    const naoReconhecidos = reuniao.participantes_nao_reconhecidos ?? []
    const pendente = naoReconhecidos.find(
      (p) => !p.nome || resolucoes[p.nome]?.tipo === "pendente" || !resolucoes[p.nome],
    )
    if (pendente) {
      toast(`Resolva "${pendente.nome}" antes de continuar`, "error")
      return
    }

    const resolucoesPayload = naoReconhecidos
      .filter((p) => p.nome)
      .map((p) => {
        const estado = resolucoes[p.nome]
        if (estado?.tipo === "vinculado") {
          return {
            nome_identificado: p.nome,
            acao: "vincular" as const,
            participante_id: estado.participante.id,
          }
        }
        if (estado?.tipo === "cadastrar_externo") {
          return {
            nome_identificado: p.nome,
            acao: "cadastrar_externo" as const,
            novo_externo: estado.dados,
          }
        }
        return { nome_identificado: p.nome, acao: "ignorar" as const }
      })

    setResolucaoLoading(true)
    try {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch(`/api/reunioes/${reuniao.id_reuniao}/resolver-participantes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ resolucoes: resolucoesPayload }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Erro ao resolver participantes")
      }
      toast("Participantes resolvidos! Gerando PDF...", "success")
    } catch (err) {
      toast(getErrorMessage(err) || "Erro ao resolver participantes", "error")
    } finally {
      setResolucaoLoading(false)
    }
  }

  const handlePularResolucao = async () => {
    if (!reuniao) return
    setResolucaoLoading(true)
    try {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch(`/api/reunioes/${reuniao.id_reuniao}/pular-resolucao`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session?.access_token}` },
      })
      if (!res.ok) throw new Error("Erro ao pular resolução")
      toast("Continuando sem cadastrar participantes...", "success")
    } catch (err) {
      toast(getErrorMessage(err) || "Erro", "error")
    } finally {
      setResolucaoLoading(false)
    }
  }

  // ── Handlers: standard flow ──
  async function handleAprovar() {
    setActionLoading(true);
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}/aprovar`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) { toast("Erro ao aprovar a ata", "error"); setActionLoading(false); return; }
    window.location.reload();
  }

  async function handleAprovarSemAssinatura() {
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}/aprovar-sem-assinatura`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      toast("Erro ao finalizar a ata sem assinatura", "error");
      throw new Error("falha ao finalizar sem assinatura"); // mantém o ConfirmDialog aberto
    }
    const body = await res.json();
    toast(`Ata aprovada — ${body.total_pendencias} pendência(s) criada(s).`, "success");
    window.location.reload();
  }

  async function handleApplyCorrections(planText: string) {
    setActionLoading(true);
    try {
      const token = await getToken();
      const res = await fetch(`/api/reunioes/${id}/corrigir`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ texto: planText }),
      });
      if (!res.ok) {
        const b = await res.json();
        toast(b.detail || "Erro ao aplicar correções", "error");
        return;
      }
      setCorrectionMode(false);
      setSectionContext(null);
      await loadReuniao();
    } finally {
      setActionLoading(false);
    }
  }

  function handleAtribuicaoResponsavelAtualizado(
    index: number,
    novo: { responsavel: string; cargo: string },
  ) {
    setReuniao((prev) => {
      if (!prev || !prev.json_ata?.quadro_atribuicoes) return prev;
      const quadro = prev.json_ata.quadro_atribuicoes;
      if (index < 0 || index >= quadro.length) return prev;
      const novoQuadro = quadro.map((item, i) =>
        i === index ? { ...item, responsavel: novo.responsavel, cargo: novo.cargo } : item,
      );
      return {
        ...prev,
        json_ata: { ...prev.json_ata, quadro_atribuicoes: novoQuadro },
      };
    });
    void loadReuniao();
  }

  // ── Handlers: PROGRAMADA editing ──
  async function handlePatch(fields: Record<string, string | null>) {
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(fields),
    });
    if (!res.ok) throw new Error("Erro ao salvar");
    await loadReuniao();
  }

  async function handleTrocarFacilitador(novoFacilitadorId: string) {
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}/transferir-facilitador`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ novo_facilitador_id: novoFacilitadorId }),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      toast(b.detail || "Erro ao trocar facilitador", "error");
      throw new Error(b.detail || "Erro");
    }
    toast("Facilitador trocado com sucesso.", "success");
    await loadReuniao();
  }

  async function handleDesmarcar() {
    setDesmarcando(true);
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    setDesmarcando(false);
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      toast(b.detail || "Erro ao desmarcar a reunião", "error");
      return;
    }
    setShowDesmarcarModal(false);
    // Redireciona de volta ao calendário
    window.location.href = backHref;
  }

  const handleDesmarcarAttempt = () => {
    if (reuniao?.status_ata !== "PROGRAMADA" && reuniao?.status_ata !== "ERRO") {
      toast("Essa reunião não pode ser apagada", "warning");
      return;
    }
    setShowDesmarcarModal(true);
  };

  // ── Super admin (Fase 04): force delete + force status ──
  async function handleForceDelete(reason?: string) {
    const token = await getToken();
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
      const b = await res.json().catch(() => ({}));
      toast(b.detail || "Erro ao excluir", "error");
      throw new Error(b.detail || "Erro");
    }
    toast("Reunião excluída (super admin).", "success");
    window.location.href = backHref;
  }

  async function handleAddParticipante(participante_id: string) {
    setAddingParticipante(true);
    const token = await getToken();
    const res = await fetch(`/api/reunioes/${id}/participantes`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ participante_ids: [participante_id] }),
    });
    setAddingParticipante(false);
    setShowParticipanteSearch(false);
    setSearchTerm("");
    if (res.ok) {
      toast("Participante adicionado. Um convite por email foi enviado.", "success");
    } else {
      const b = await res.json().catch(() => ({}));
      toast(b.detail || "Não foi possível adicionar o participante.", "error");
    }
    await loadReuniao();
  }

  async function handleRemoveParticipante(participante_id: string) {
    setRemovingId(participante_id);
    const token = await getToken();
    await fetch(`/api/reunioes/${id}/participantes/${participante_id}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    setRemovingId(null);
    await loadReuniao();
  }

  async function handleAnexarTranscricao(file: File) {
    setUploadLoading(true);
    const token = await getToken();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/reunioes/${id}/anexar-transcricao`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const b = await res.json();
      toast(b.detail || "Erro ao enviar transcrição", "error");
      setUploadLoading(false);
      return;
    }
    window.location.reload();
  }

  // ── Helpers ──
  const participanteIds = new Set((reuniao?.participantes_programada ?? []).map((p) => p.id));
  const filteredParticipantes = allParticipantes.filter(
    (p) => !participanteIds.has(p.id) &&
      (p.nome_completo.toLowerCase().includes(searchTerm.toLowerCase()) ||
       (p.cargo ?? "").toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const TIPOS = [
    { label: "Diretoria", value: "Diretoria" },
    { label: "Gerencial", value: "Gerencial" },
    { label: "Coordenação", value: "Coordenação" },
    { label: "Mensal", value: "Mensal" },
    { label: "Extraordinária", value: "Extraordinária" },
  ];

  // ── Render guards ──
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400 text-sm gap-2">
        <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
        Carregando...
      </div>
    );
  }

  if (error || !reuniao) {
    return (
      <div className="text-center py-16">
        <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
          <FileText className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
        </div>
        <p className="text-slate-600">{error ?? "Reunião não encontrada"}</p>
        <Link href="/reunioes/calendario" className="text-primary text-sm mt-2 inline-block hover:underline">
          ← Voltar para reuniões
        </Link>
      </div>
    );
  }

  const ata = reuniao.json_ata;
  const isProgramada = reuniao.status_ata === "PROGRAMADA";
  // Ata Guiada (ADR 0005): nasce sem Transcrição/PDF. Esconde as ações do fluxo por
  // Transcrição (Solicitar Correção baixa a Transcrição; Enviar para assinatura cria
  // Envelope a partir do PDF — ambos inexistentes aqui) e mostra um badge do método.
  const isGuiada = reuniao.metodo_geracao === "GUIADA";

  // ══════════════════════════════════════════
  // PROGRAMADA MODE
  // ══════════════════════════════════════════
  if (isProgramada) {
    return (
      <div className="space-y-6 max-w-4xl animate-fade-in-up">
        {/* Modal de troca de facilitador (super admin) */}
        <TrocarFacilitadorModal
          open={showTrocarFacilitador}
          onClose={() => setShowTrocarFacilitador(false)}
          facilitadorAtualId={reuniao.facilitador_id ?? null}
          onConfirm={handleTrocarFacilitador}
        />

        {/* Modal de confirmação — Desmarcar */}
        {showDesmarcarModal && (
          <div className="modal-backdrop z-[200] flex items-center justify-center px-4">
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
                  onClick={() => setShowDesmarcarModal(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleDesmarcar}
                  disabled={desmarcando}
                  className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
                >
                  {desmarcando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  {desmarcando ? "Desmarcando..." : "Sim, Desmarcar"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Header */}
        <div>
          <Link
            href={backHref}
            className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-600 transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            {backLabel}
          </Link>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                  <CalendarDays className="w-3 h-3" />
                  Programada
                </span>
              </div>
              <h1 className="text-2xl font-bold text-slate-900">
                {reuniao.tipo ?? "Reunião"} —{" "}
                {mounted ? new Date(reuniao.data + "T12:00:00").toLocaleDateString("pt-BR", {
                  day: "2-digit", month: "long", year: "numeric",
                }) : "—"}
              </h1>
              <p className="font-mono text-xs text-slate-400 mt-0.5">{reuniao.id_reuniao}</p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {/* Super admin: Excluir em qualquer status */}
              <DeleteButton
                visible={canSuperAdmin}
                confirmTitle="Excluir reunião em qualquer status?"
                confirmDescription={
                  reuniao.status_ata === "ASSINADA"
                    ? "ATENÇÃO: esta ATA está ASSINADA digitalmente. Ao confirmar, o registro será removido permanentemente. Ação registrada no audit log."
                    : "A reunião será removida permanentemente em qualquer status. Ação registrada no audit log."
                }
                onDelete={handleForceDelete}
                label="Excluir"
              />
              {/* Botão Desmarcar (regra normal) */}
              <button
                onClick={handleDesmarcarAttempt}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50 hover:border-red-300 transition-all"
              >
                <Trash2 className="w-4 h-4" />
                Desmarcar
              </button>
            </div>
          </div>
        </div>

        {/* 2-col layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column — main fields */}
          <div className="lg:col-span-2 space-y-5">

            {/* Detalhes Editáveis */}
            <div className="bg-white rounded-2xl border border-border shadow-premium">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2.5">
                <Edit3 className="w-4 h-4 text-primary" strokeWidth={1.5} />
                <h2 className="font-semibold text-slate-900">Detalhes da Reunião</h2>
                <span className="ml-auto text-xs text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-200">
                  Clique em qualquer campo para editar
                </span>
              </div>
              <div className="px-6 py-5 space-y-4">
                {/* Título — full width, destaque */}
                <div>
                  <InlineEditField
                    label="Título da Reunião"
                    value={reuniao.titulo ?? ""}
                    icon={FileText}
                    type="text"
                    onSave={(v) => handlePatch({ titulo: v || null })}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <InlineEditField
                  label="Tipo de Reunião"
                  value={reuniao.tipo ?? ""}
                  icon={FileText}
                  type="select"
                  options={TIPOS}
                  onSave={(v) => handlePatch({ tipo: v || null })}
                />
                <InlineEditField
                  label="Horário de Início"
                  value={reuniao.hora_inicio ?? ""}
                  icon={Clock}
                  type="time"
                  onSave={(v) => handlePatch({ hora_inicio: v || null })}
                />
                <InlineEditField
                  label="Data"
                  value={reuniao.data}
                  icon={CalendarDays}
                  type="date"
                  onSave={(v) => handlePatch({ data: v || null })}
                />

                {/* Pauta — full width */}
                <div className="col-span-full">
                  <InlineEditField
                    label="Pauta"
                    value={reuniao.objetivo ?? ""}
                    icon={FileText}
                    type="textarea"
                    onSave={(v) => handlePatch({ objetivo: v || null })}
                  />
                </div>
                </div>
              </div>
            </div>

            {/* Participantes */}
            <div className="bg-white rounded-2xl border border-border shadow-premium">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2.5">
                <Users className="w-4 h-4 text-primary" strokeWidth={1.5} />
                <h2 className="font-semibold text-slate-900">
                  Participantes
                  {(reuniao.participantes_programada?.length ?? 0) > 0 && (
                    <span className="ml-2 text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                      {reuniao.participantes_programada?.length ?? 0}
                    </span>
                  )}
                </h2>
              </div>
              <div className="px-6 py-5 space-y-4">
                {/* List */}
                {(reuniao.participantes_programada?.length ?? 0) === 0 ? (
                  <p className="text-sm text-slate-400 italic">Nenhum participante adicionado ainda.</p>
                ) : (
                  <div className="space-y-2">
                    {(reuniao.participantes_programada ?? []).map((p) => {
                      const isFacilitador = p.id === reuniao.facilitador_id;
                      return (
                        <div key={p.id} className={`flex items-center gap-3 px-3 py-2 rounded-xl group ${
                          isFacilitador ? "bg-amber-50 border border-amber-100" : "bg-slate-50"
                        }`}>
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 ${
                            isFacilitador
                              ? "bg-gradient-to-br from-amber-200 to-amber-300 text-amber-800"
                              : "bg-gradient-to-br from-primary/20 to-primary-light/20 text-primary"
                          }`}>
                            {p.nome.charAt(0).toUpperCase()}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <p className="text-sm font-medium text-slate-800 truncate">{p.nome}</p>
                              {isFacilitador && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold flex-shrink-0">
                                  <Crown className="w-2.5 h-2.5" />
                                  Facilitador
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 truncate">{p.cargo}{p.area ? ` · ${p.area}` : ""}</p>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {isFacilitador && canSuperAdmin && (
                              <button
                                onClick={() => setShowTrocarFacilitador(true)}
                                title="Trocar facilitador"
                                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-amber-100 text-slate-400 hover:text-amber-700"
                              >
                                <ArrowRightLeft className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              onClick={() => handleRemoveParticipante(p.id)}
                              disabled={removingId === p.id || isFacilitador}
                              title={isFacilitador ? "O facilitador não pode ser removido" : "Remover participante"}
                              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-red-100 text-slate-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                            >
                              {removingId === p.id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <X className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Add participant */}
                <div className="relative" ref={searchRef}>
                  <button
                    onClick={() => setShowParticipanteSearch(!showParticipanteSearch)}
                    className="flex items-center gap-2 w-full px-4 py-2.5 rounded-xl border-2 border-dashed border-slate-200 hover:border-primary/40 hover:bg-primary/5 text-slate-400 hover:text-primary text-sm font-medium transition-all"
                  >
                    <Plus className="w-4 h-4" />
                    Adicionar participante
                  </button>
                  <p className="text-xs text-slate-500 mt-2">
                    Novos participantes recebem um email de convite na hora.
                  </p>
                  {showParticipanteSearch && (
                    <div className="absolute top-full mt-2 left-0 right-0 bg-white rounded-2xl border border-border shadow-premium-strong z-20 overflow-hidden">
                      <div className="p-3 border-b border-slate-100">
                        <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-xl">
                          <Search className="w-3.5 h-3.5 text-slate-400" />
                          <input
                            type="text"
                            placeholder="Buscar por nome ou cargo..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="flex-1 bg-transparent text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none"
                            autoFocus
                          />
                        </div>
                      </div>
                      <div className="max-h-52 overflow-y-auto">
                        {filteredParticipantes.length === 0 ? (
                          <p className="text-center text-sm text-slate-400 py-4">Nenhum resultado</p>
                        ) : (
                          filteredParticipantes.slice(0, 8).map((p) => (
                            <button
                              key={p.id}
                              onClick={() => handleAddParticipante(p.id)}
                              disabled={addingParticipante}
                              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left transition-colors"
                            >
                              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/15 to-primary-light/15 flex items-center justify-center text-primary font-semibold text-xs flex-shrink-0">
                                {p.nome_completo.charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <p className="text-sm font-medium text-slate-800">{p.nome_completo}</p>
                                <p className="text-xs text-slate-400">{p.cargo}</p>
                              </div>
                              {addingParticipante && <Loader2 className="w-3.5 h-3.5 animate-spin ml-auto text-primary" />}
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Anexar Transcrição — secretária não tem acesso ao pipeline de ata (backend 403) */}
            {!hideAtaSections && (
              <div className="bg-white rounded-2xl border border-border shadow-premium">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2.5">
                  <Upload className="w-4 h-4 text-primary" strokeWidth={1.5} />
                  <h2 className="font-semibold text-slate-900">Transcrição</h2>
                </div>
                <div className="px-6 py-5">
                  <p className="text-sm text-slate-600 mb-4">
                    Após a reunião, anexe o arquivo de transcrição (<span className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">.txt</span>, <span className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">.md</span>, <span className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">.pdf</span> ou <span className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">.docx</span>) para que a IA processe e gere a ata automaticamente.
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.md,.pdf,.docx"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleAnexarTranscricao(file);
                    }}
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadLoading}
                    className="flex items-center gap-2.5 px-5 py-3 bg-gradient-to-r from-primary to-primary-dark text-white font-medium rounded-xl hover:shadow-lg hover:shadow-primary/20 transition-all disabled:opacity-60 cursor-pointer"
                  >
                    {uploadLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Enviando e iniciando IA...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4" />
                        Anexar Transcrição e Processar com IA
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Ata Guiada — registrar reunião sem transcrição (ADR 0005) */}
            {!hideAtaSections && (
              <div className="bg-white rounded-2xl border border-border shadow-premium">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2.5">
                  <Sparkles className="w-4 h-4 text-primary" strokeWidth={1.5} />
                  <h2 className="font-semibold text-slate-900">Ata Guiada</h2>
                </div>
                <div className="px-6 py-5">
                  {ataGuiadaAberta ? (
                    <ChatAtaGuiada
                      idReuniao={reuniao.id_reuniao}
                      onConcluido={() => window.location.reload()}
                      onClose={() => setAtaGuiadaAberta(false)}
                    />
                  ) : (
                    <>
                      <p className="text-sm text-slate-600 mb-4">
                        Reunião rápida, sem transcrição? Monte a ata conversando (por texto) com um
                        assistente — ele organiza um resumo e o quadro de ações. Você revisa e finaliza
                        sem assinatura.
                      </p>
                      <button
                        onClick={() => setAtaGuiadaAberta(true)}
                        className="flex items-center gap-2.5 px-5 py-3 border-2 border-primary/30 text-primary font-medium rounded-xl hover:bg-primary/5 transition-all cursor-pointer"
                      >
                        <MessageSquare className="w-4 h-4" />
                        Iniciar Ata Guiada
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Recorrência */}
            <RecorrenciaPanel reuniao={reuniao} getToken={getToken} />

          </div>

          {/* Right column — preparation */}
          <div className="space-y-5">
            <div className="bg-white rounded-2xl border border-border shadow-premium">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2.5">
                <Sparkles className="w-4 h-4 text-amber-500" strokeWidth={1.5} />
                <h2 className="font-semibold text-slate-900">Preparação</h2>
              </div>
              <div className="px-5 py-4">
                <PreparacaoChecklist reuniao={reuniao} />
              </div>
            </div>

            {/* Quick info card */}
            <div className="bg-slate-50 rounded-2xl border border-border px-5 py-4 space-y-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Resumo</p>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Data</span>
                  <span className="font-medium text-slate-800">
                    {mounted ? new Date(reuniao.data + "T12:00:00").toLocaleDateString("pt-BR") : "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Horário</span>
                  <span className="font-medium text-slate-800">{reuniao.hora_inicio ?? "—"}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Tipo</span>
                  <span className="font-medium text-slate-800">{reuniao.tipo ?? "—"}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Participantes</span>
                  <span className="font-medium text-slate-800">{reuniao.participantes_programada?.length ?? 0}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════
  // STANDARD FLOW (PROCESSANDO, VALIDACAO, etc.)
  // ══════════════════════════════════════════
  return (
    <div className="space-y-6 max-w-4xl animate-fade-in-up">
      {/* Header */}
      <div>
        <Link
          href={backHref}
          className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-600 transition-colors mb-2"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          {backLabel}
        </Link>
        <div className="flex items-start justify-between gap-4">
          <div>
            {isGuiada && (
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                  <Sparkles className="w-3 h-3" />
                  Ata Guiada
                </span>
              </div>
            )}
            <h1 className="text-2xl font-bold text-slate-900">
              {reuniao.tipo ?? "Reunião"} —{" "}
              {mounted ? new Date(reuniao.data + "T12:00:00").toLocaleDateString("pt-BR", {
                day: "2-digit", month: "long", year: "numeric",
              }) : "—"}
            </h1>
            <p className="font-mono text-xs text-slate-400 mt-0.5">{reuniao.id_reuniao}</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Super admin: Excluir em qualquer status (inclui ATA assinada) */}
            <DeleteButton
              visible={canSuperAdmin}
              confirmTitle="Excluir reunião em qualquer status?"
              confirmDescription={
                reuniao.status_ata === "ASSINADA"
                  ? "ATENÇÃO: esta ATA está ASSINADA digitalmente. Ao confirmar, o registro será removido permanentemente. Ação registrada no audit log."
                  : "A reunião será removida permanentemente em qualquer status. Ação registrada no audit log."
              }
              onDelete={handleForceDelete}
              label="Excluir"
            />
            {/* Desmarcar só faz sentido em PROGRAMADA/ERRO (backend recusa nos demais).
                Pra secretária, nessas status_ata ela não chega no STANDARD FLOW, então
                o botão fica oculto aqui pra não confundir. */}
            {!hideAtaSections && (
              <button
                onClick={handleDesmarcarAttempt}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50 hover:border-red-300 transition-all flex-shrink-0"
              >
                <Trash2 className="w-4 h-4" />
                Desmarcar
              </button>
            )}
            {reuniao.url_pdf_preliminar && !hideAtaSections && (
              <a
                href={reuniao.url_pdf_preliminar}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-medium rounded-xl hover:shadow-premium-strong transition-all whitespace-nowrap cursor-pointer"
              >
                <Download className="w-4 h-4" />
                Baixar PDF
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="bg-white rounded-2xl border border-border shadow-premium px-6 py-4 overflow-x-auto">
        <StatusTimeline current={reuniao.status_ata} />
      </div>

      {/* Card: status live dos signatarios (polling 30s + botao Atualizar + Lembrar por linha) */}
      {reuniao.status_ata === "AGUARDANDO_ASSINATURA" && !hideAtaSections && (
        <SignatariosCard
          idReuniao={reuniao.id_reuniao}
          envelopeKey={reuniao.envelope_key_clicksign || ""}
          enabled={reuniao.status_ata === "AGUARDANDO_ASSINATURA"}
        />
      )}

      {/* Banner: Ata Assinada */}
      {reuniao.status_ata === "ASSINADA" && !hideAtaSections && (
        <div className="flex items-center justify-between gap-4 bg-emerald-50 border border-emerald-200 rounded-2xl px-6 py-4">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <BadgeCheck className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <p className="font-semibold text-emerald-800 text-sm">Ata Assinada Digitalmente</p>
              {reuniao.data_assinatura && (
                <p className="text-emerald-700 text-xs mt-1">
                  Assinada em{" "}
                  {mounted ? new Date(reuniao.data_assinatura + "T12:00:00").toLocaleDateString("pt-BR", {
                    day: "2-digit", month: "long", year: "numeric",
                  }) : "—"}
                </p>
              )}
            </div>
          </div>
          {reuniao.url_pdf_assinado && (
            <a
              href={reuniao.url_pdf_assinado}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-xl hover:bg-emerald-700 transition-colors whitespace-nowrap cursor-pointer"
            >
              <Download className="w-4 h-4" />
              PDF Assinado
            </a>
          )}
        </div>
      )}

      {/* Banner: Ata Aprovada (finalizada sem assinatura digital) */}
      {reuniao.status_ata === "APROVADA" && !hideAtaSections && (
        <div className="flex items-center justify-between gap-4 bg-sky-50 border border-sky-200 rounded-2xl px-6 py-4">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-sky-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle className="w-5 h-5 text-sky-600" />
            </div>
            <div>
              <p className="font-semibold text-sky-800 text-sm">Ata Aprovada</p>
              <p className="text-sky-700 text-xs mt-1">
                Finalizada sem assinatura digital. As Pendências foram criadas — confira no painel.
              </p>
            </div>
          </div>
          <Link
            href="/pendencias"
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white text-sm font-medium rounded-xl hover:bg-sky-700 transition-colors whitespace-nowrap cursor-pointer"
          >
            <ListChecks className="w-4 h-4" />
            Ver Pendências
          </Link>
        </div>
      )}

      {/* Meta info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Data", value: mounted ? new Date(reuniao.data + "T12:00:00").toLocaleDateString("pt-BR") : "—", icon: CalendarDays },
          {
            label: "Horário",
            value:
              reuniao.hora_inicio && reuniao.hora_fim
                ? `${reuniao.hora_inicio} – ${reuniao.hora_fim}`
                : ata?.hora_inicio
                ? `${ata.hora_inicio}${ata.hora_fim ? " – " + ata.hora_fim : ""}`
                : "—",
            icon: Clock,
          },
          { label: "Tipo", value: reuniao.tipo ?? "—", icon: FileText },
          ...(hideAtaSections
            ? []
            : [{ label: "Ações", value: `${reuniao.total_acoes} total`, icon: ListChecks }]),
        ].map((m) => {
          const Icon = m.icon;
          return (
            <div key={m.label} className="bg-white rounded-xl border border-border shadow-premium px-4 py-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Icon className="w-3.5 h-3.5 text-slate-400" strokeWidth={1.5} />
                <p className="text-xs text-slate-400 font-medium">{m.label}</p>
              </div>
              <p className="text-slate-900 font-semibold text-sm">{m.value}</p>
            </div>
          );
        })}
      </div>

      {/* Resolução de Participantes Não Reconhecidos */}
      {reuniao.status_ata === "AGUARDANDO_RESOLUCAO" && !hideAtaSections && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <Users className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h3 className="font-semibold text-amber-900">Participantes Não Cadastrados</h3>
              <p className="text-sm text-amber-700">
                A IA identificou {reuniao.participantes_nao_reconhecidos?.length || 0} participante(s) que não bateram com internos cadastrados.
                Para cada um, aponte um participante existente (interno ou externo já cadastrado), cadastre como novo externo, ou ignore.
              </p>
            </div>
          </div>

          <div className="space-y-3">
            {reuniao.participantes_nao_reconhecidos?.map((p) => {
              const estado = resolucoes[p.nome] ?? { tipo: "pendente" as const }
              return (
                <div key={p.nome} className="bg-white border border-amber-200 rounded-lg p-4">
                  <div className="flex items-baseline justify-between gap-3 mb-3">
                    <div className="font-medium text-slate-800 truncate">{p.nome}</div>
                    {(p.cargo || p.setor) && (
                      <div className="text-xs text-slate-500 truncate">
                        {[p.cargo, p.setor].filter(Boolean).join(" • ")}
                      </div>
                    )}
                  </div>
                  <ParticipanteCombobox
                    nomeSugerido={p.nome}
                    cargoSugerido={p.cargo}
                    estado={estado}
                    onSelecionarExistente={(participante) => {
                      setResolucoes((prev) => ({
                        ...prev,
                        [p.nome]: { tipo: "vinculado", participante },
                      }))
                    }}
                    onCadastrarExterno={(dados) => {
                      setResolucoes((prev) => ({
                        ...prev,
                        [p.nome]: { tipo: "cadastrar_externo", dados },
                      }))
                    }}
                    onIgnorar={() => {
                      setResolucoes((prev) => ({
                        ...prev,
                        [p.nome]: { tipo: "ignorar" },
                      }))
                    }}
                    onAlterar={() => {
                      setResolucoes((prev) => ({
                        ...prev,
                        [p.nome]: { tipo: "pendente" },
                      }))
                    }}
                  />
                </div>
              )
            })}
          </div>

          <div className="flex gap-3 mt-5">
            <button
              onClick={handleResolverParticipantes}
              disabled={resolucaoLoading}
              className="flex-1 bg-amber-500 text-white py-2.5 px-4 rounded-lg font-medium hover:bg-amber-600 disabled:opacity-50 transition-colors"
            >
              {resolucaoLoading ? "Processando..." : "Confirmar e Continuar"}
            </button>
            <button
              onClick={handlePularResolucao}
              disabled={resolucaoLoading}
              className="px-4 py-2.5 border border-amber-300 text-amber-700 rounded-lg font-medium hover:bg-amber-50 disabled:opacity-50 transition-colors"
            >
              Ignorar Todos
            </button>
          </div>
        </div>
      )}

      {/* Ações de Validação */}
      {reuniao.status_ata === "AGUARDANDO_VALIDACAO" && !hideAtaSections && (
        <div className="bg-white rounded-2xl border border-primary/30 shadow-premium p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-warning" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Validação Necessária</h2>
              <p className="text-sm text-slate-600">
                {isGuiada
                  ? "Revise o resumo e o quadro de ações antes de finalizar."
                  : "Por favor, revise o PDF da ata antes de prosseguir com a assinatura."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            {!isGuiada && (
              <button onClick={handleAprovar} disabled={actionLoading} className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-primary to-primary-dark text-white font-medium rounded-xl hover:shadow-lg transition-all cursor-pointer">
                <PenLine className="w-4 h-4" />
                {actionLoading ? "Enviando..." : "Enviar para assinatura"}
              </button>
            )}
            <button
              onClick={() => setConfirmSemAssinatura(true)}
              disabled={actionLoading}
              className="flex items-center gap-2 px-6 py-2.5 border border-primary/30 text-primary font-medium rounded-xl hover:bg-primary/5 transition-colors cursor-pointer"
            >
              <CheckCircle className="w-4 h-4" />
              Finalizar sem assinatura
            </button>
            {!isGuiada && (
              <button
                onClick={() => { setCorrectionMode(!correctionMode); setSectionContext(null); }}
                disabled={actionLoading}
                className="flex items-center gap-2 px-6 py-2.5 bg-amber-100 text-amber-800 font-medium rounded-xl hover:bg-amber-200 transition-colors cursor-pointer"
              >
                <Pen className="w-4 h-4" />
                {correctionMode ? "Fechar Chat" : "Solicitar Correção"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Confirmação: finalizar sem assinatura (cria as Pendências na hora) */}
      <ConfirmDialog
        open={confirmSemAssinatura}
        onClose={() => setConfirmSemAssinatura(false)}
        onConfirm={handleAprovarSemAssinatura}
        title="Finalizar sem assinatura?"
        description={
          `Isto criará ${ata?.quadro_atribuicoes?.length ?? 0} pendência(s) imediatamente e marcará a Ata como APROVADA.\n\n` +
          "A Ata não terá assinatura digital — você abre mão da formalidade do ClickSign. Esta ação é definitiva."
        }
        confirmLabel="Finalizar sem assinatura"
      />

      {correctionMode && reuniao && ata && !hideAtaSections && !isGuiada && (
        <ChatCorrecao
          idReuniao={reuniao.id_reuniao}
          sectionContext={sectionContext}
          onClearSectionContext={() => setSectionContext(null)}
          onApplyCorrections={handleApplyCorrections}
          onClose={() => { setCorrectionMode(false); setSectionContext(null); }}
        />
      )}

      {/* Pauta */}
      {reuniao.objetivo && (
        <Section title="Pauta" icon={FileText}>
          <p className="text-slate-600 text-sm leading-relaxed">{reuniao.objetivo}</p>
        </Section>
      )}

      {/* Erro */}
      {reuniao.status_ata === "ERRO" && ata?.error && !hideAtaSections && (
        <div className="flex items-start gap-3 px-5 py-4 rounded-2xl bg-red-50 border border-red-100 text-red-700 text-sm">
          <XCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div><strong>Erro no processamento:</strong> {ata.error}</div>
        </div>
      )}

      {/* Processando */}
      {reuniao.status_ata === "PROCESSANDO" && (
        <div className="px-5 py-8 rounded-2xl bg-stone-50 border border-stone-200 text-center">
          <div className="w-14 h-14 rounded-2xl bg-stone-100 flex items-center justify-center mx-auto mb-3">
            <Bot className="w-7 h-7 text-slate-600 animate-pulse" />
          </div>
          <p className="text-slate-900 font-medium text-sm">A IA está processando a transcrição...</p>
          <p className="text-slate-500 text-xs mt-1">Isso pode levar até 30 segundos. Recarregue a página em instantes.</p>
        </div>
      )}

      {/* Mock indicator */}
      {ata?._mock && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-100 text-amber-700 text-xs">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span><strong>Modo Mock:</strong> Configure OPENROUTER_API_KEY no .env para processar com IA real.</span>
        </div>
      )}

      {ata && !ata.error && reuniao.status_ata !== "PROCESSANDO" && !hideAtaSections && (
        <>
          {ata.resumo_executivo && (
            <Section
              title="Resumo Executivo"
              icon={FileText}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Resumo Executivo")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Resumo Executivo" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <p className="text-slate-700 text-sm leading-relaxed italic">&quot;{ata.resumo_executivo}&quot;</p>
            </Section>
          )}

          {ata.participantes && ata.participantes.length > 0 && (
            <Section
              title={`Participantes (${ata.participantes.length})`}
              icon={Users}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Participantes")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Participantes" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {ata.participantes.map((p, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-50 ${correctionMode ? "cursor-pointer hover:bg-primary/5 border border-transparent hover:border-primary/20" : ""}`}
                    onClick={correctionMode ? () => setSectionContext(`Participantes, item ${i + 1}: "${p.nome}"`) : undefined}
                  >
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 to-primary-light/20 flex items-center justify-center text-primary font-semibold text-xs flex-shrink-0">
                      {p.nome.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">{p.nome}</p>
                      <p className="text-xs text-slate-400">{p.cargo}</p>
                    </div>
                    {p.presente && <span className="ml-auto"><CheckCircle className="w-4 h-4 text-success" /></span>}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Pauta da Reunião (HSM) */}
          {(ata.objetivo || reuniao.objetivo) && (
            <Section
              title="Pauta da Reunião"
              icon={Target}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Objetivo")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Objetivo" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <p className="text-slate-700 text-sm leading-relaxed whitespace-pre-line">
                {ata.objetivo || reuniao.objetivo}
              </p>
            </Section>
          )}

          {/* Discussão dos Pontos (HSM) com fallback para registro_narrativo legado */}
          {ata.discussao && ata.discussao.length > 0 ? (
            <Section
              title={`Discussão dos Pontos (${ata.discussao.length})`}
              icon={MessageSquare}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Discussão")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Discussão" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <div className="space-y-4">
                {ata.discussao.map((topico, i) => (
                  <div
                    key={i}
                    className={`border-l-4 border-primary/40 bg-slate-50 rounded-r-xl px-4 py-3 ${correctionMode ? "cursor-pointer hover:bg-primary/5" : ""}`}
                    onClick={correctionMode ? () => setSectionContext(`Discussão, item ${i + 1}: "${topico.titulo}"`) : undefined}
                  >
                    <p className="text-sm font-semibold text-primary">4.{i + 1} {topico.titulo}</p>
                    {topico.descricao && (
                      <p className="mt-2 text-sm text-slate-700 leading-relaxed whitespace-pre-line">{topico.descricao}</p>
                    )}
                    {topico.contribuicoes && topico.contribuicoes.length > 0 && (
                      <div className="mt-3">
                        <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">Contribuições</p>
                        <ul className="mt-1 space-y-1">
                          {topico.contribuicoes.map((c, j) => {
                            const autor = c.nome && c.funcao
                              ? `${c.nome} (${c.funcao})`
                              : c.nome || c.funcao || "Participante";
                            return (
                              <li key={j} className="text-sm text-slate-700">
                                <strong className="text-slate-800">{autor}:</strong> {c.conteudo}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                    {topico.divergencias && topico.divergencias.length > 0 && (
                      <div className="mt-3">
                        <p className="text-[10px] uppercase tracking-wider font-semibold text-red-700">Divergências / Ressalvas</p>
                        <ul className="mt-1 space-y-1 list-disc list-inside">
                          {topico.divergencias.map((d, j) => (
                            <li key={j} className="text-sm text-red-800">{d}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {topico.decisao && (
                      <div className="mt-3 px-3 py-2 rounded-lg bg-cyan-50 border-l-2 border-cyan-500 text-sm">
                        <strong className="text-cyan-900">Decisão:</strong>{" "}
                        <span className="text-slate-800">{topico.decisao}</span>
                        {topico.responsavel && (
                          <span className="block mt-0.5 text-xs text-slate-600 italic">Responsável: {topico.responsavel}</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          ) : ata.registro_narrativo ? (
            <Section
              title="Registro Narrativo"
              icon={FileText}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Registro Narrativo")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Registro Narrativo" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <p className="text-slate-600 text-sm leading-relaxed whitespace-pre-line">{ata.registro_narrativo}</p>
            </Section>
          ) : null}

          {ata.quadro_atribuicoes && ata.quadro_atribuicoes.length > 0 && (
            <Section
              title={`Quadro de Atribuições (${ata.quadro_atribuicoes.length} ações)`}
              icon={ListChecks}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Quadro de Atribuições")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Quadro de Atribuições" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100">
                      {["Ação", "Responsável", "Objetivo / Meta", "Prazo", "Status"].map((h) => (
                        <th key={h} className="text-left pb-2 text-xs font-semibold text-slate-400 uppercase tracking-wide pr-4">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {ata.quadro_atribuicoes.map((a, i) => (
                      <tr
                        key={i}
                        className={correctionMode ? "cursor-pointer hover:bg-primary/5" : ""}
                        onClick={correctionMode ? () => setSectionContext(`Quadro de Atribuições, item ${i + 1}: "${a.acao}"`) : undefined}
                      >
                        <td className="py-3 pr-4 text-slate-800 font-medium align-top">{a.acao}</td>
                        <td className="py-3 pr-4 align-top min-w-[180px]">
                          {correctionMode ? (
                            <ResponsavelInlineCombobox
                              reuniaoId={reuniao.id_reuniao}
                              atribuicaoIndex={i}
                              participantes={(reuniao.participantes_programada ?? []).map((p) => ({
                                id: p.id,
                                nome: p.nome,
                                cargo: p.cargo ?? "",
                              }))}
                              valorAtual={{ responsavel: a.responsavel ?? "", cargo: a.cargo ?? "" }}
                              onAtualizado={(novo) => handleAtribuicaoResponsavelAtualizado(i, novo)}
                            />
                          ) : (
                            <>
                              <p className="text-slate-700">{a.responsavel}</p>
                              <p className="text-xs text-slate-400">{a.cargo}</p>
                            </>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-slate-600 text-xs align-top max-w-[180px]">
                          {a.objetivo_meta || a.entregavel || <span className="text-slate-300">—</span>}
                        </td>
                        <td className="py-3 pr-4 text-slate-600 align-top whitespace-nowrap">
                          {(() => {
                            if (!a.prazo) return <span className="text-slate-300">A definir</span>;
                            if (a.prazo === "Fluxo contínuo") return <span className="italic text-slate-500">Fluxo contínuo</span>;
                            let date = new Date(a.prazo + "T12:00:00");
                            if (isNaN(date.getTime()) && a.prazo.includes("/")) {
                              const [d, m, y] = a.prazo.split("/");
                              date = new Date(`${y}-${m}-${d}T12:00:00`);
                            }
                            return isNaN(date.getTime()) || !mounted ? a.prazo : date.toLocaleDateString("pt-BR");
                          })()}
                        </td>
                        <td className="py-3 align-top">
                          {(() => {
                            const st = (a.status || "ABERTO").toUpperCase();
                            const cls =
                              st === "CONCLUIDO"
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                : st === "EM_ANDAMENTO"
                                ? "bg-blue-50 text-blue-700 border-blue-200"
                                : "bg-amber-50 text-amber-700 border-amber-200";
                            const label = st === "CONCLUIDO" ? "Concluído" : st === "EM_ANDAMENTO" ? "Em andamento" : "Aberto";
                            return (
                              <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}>
                                {label}
                              </span>
                            );
                          })()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {/* Lacunas Identificadas (HSM) */}
          {ata.lacunas_identificadas && ata.lacunas_identificadas.length > 0 && (
            <Section
              title={`Pontos para Esclarecimento (${ata.lacunas_identificadas.length})`}
              icon={AlertTriangle}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Lacunas Identificadas")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Lacunas Identificadas" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <div className="rounded-xl bg-amber-50 border border-amber-100 p-3">
                <p className="text-xs text-amber-900 mb-2">A IA identificou os pontos abaixo como ambíguos ou incompletos — revise antes de assinar:</p>
                <ul className="list-disc list-inside space-y-1">
                  {ata.lacunas_identificadas.map((l, i) => (
                    <li key={i} className="text-sm text-amber-900">{l}</li>
                  ))}
                </ul>
              </div>
            </Section>
          )}

          {ata.proxima_reuniao && (
            <Section
              title="Próxima Reunião"
              icon={CalendarDays}
              action={
                correctionMode ? (
                  <button
                    onClick={() => setSectionContext("Próxima Reunião")}
                    className={`p-1.5 rounded-lg transition-colors ${sectionContext === "Próxima Reunião" ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"}`}
                    title="Apontar para esta seção"
                  >
                    <Crosshair className="w-4 h-4" />
                  </button>
                ) : undefined
              }
            >
              <p className="text-slate-700 text-sm">{ata.proxima_reuniao}</p>
            </Section>
          )}
        </>
      )}
    </div>
  );
}
