"use client";

import { useState } from "react";
import { Repeat2, CheckCircle, Loader2 } from "lucide-react";

interface RecorrenciaReuniao {
  data: string;
  titulo: string | null;
  tipo: string | null;
  objetivo: string | null;
  local: string | null;
  hora_inicio: string | null;
  participantes_programada?: Array<{ id: string }>;
}

interface RecorrenciaPanelProps {
  reuniao: RecorrenciaReuniao;
  getToken: () => Promise<string | undefined>;
}

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

export default function RecorrenciaPanel({ reuniao, getToken }: RecorrenciaPanelProps) {
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
        tipo: reuniao.tipo || null,
        objetivo: reuniao.objetivo || null,
        local: reuniao.local || null,
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
