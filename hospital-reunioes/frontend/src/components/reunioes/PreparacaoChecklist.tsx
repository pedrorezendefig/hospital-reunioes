"use client";

import { CheckSquare, Square } from "lucide-react";

interface PreparacaoReuniao {
  objetivo: string | null;
  tipo: string | null;
  hora_inicio: string | null;
  participantes_programada?: Array<{ id: string }>;
}

interface PreparacaoChecklistProps {
  reuniao: PreparacaoReuniao;
}

export default function PreparacaoChecklist({ reuniao }: PreparacaoChecklistProps) {
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
