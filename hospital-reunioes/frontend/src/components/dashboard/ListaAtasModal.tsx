"use client";

import Link from "next/link";
import { AdminModal } from "@/components/admin/AdminModal";
import type { AtaDoDashboard } from "@/lib/reunioes/atasDoDashboard";

const STATUS_ATA_LABEL: Record<string, string> = {
  PROCESSANDO: "Processando IA",
  AGUARDANDO_VALIDACAO: "Aguard. Validação",
  AGUARDANDO_ASSINATURA: "Aguard. Assinatura",
};

const DIA = 24 * 60 * 60 * 1000;

function haQuanto(updatedAt?: string | null): string | null {
  if (!updatedAt) return null;
  const dias = Math.floor((Date.now() - new Date(updatedAt).getTime()) / DIA);
  if (dias <= 0) return "hoje";
  return dias === 1 ? "há 1 dia" : `há ${dias} dias`;
}

function formatarData(data: string): string {
  const [ano, mes, dia] = data.split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : data;
}

export interface ListaAtasModalProps {
  titulo: string;
  atas: AtaDoDashboard[];
  onClose: () => void;
}

export default function ListaAtasModal({ titulo, atas, onClose }: ListaAtasModalProps) {
  return (
    <AdminModal open onClose={onClose} title={titulo} size="lg" scrollable>
      {atas.length === 0 ? (
        <p className="text-sm text-text-secondary">Nenhuma ata nesta situação.</p>
      ) : (
        <ul className="divide-y divide-border">
          {atas.map((ata) => {
            const tempo = haQuanto(ata.updated_at);
            return (
              <li key={ata.id_reuniao}>
                <Link
                  href={`/reunioes/${ata.id_reuniao}`}
                  className="flex items-start justify-between gap-4 py-3 px-2 -mx-2 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-text truncate">
                      {ata.tipo || "Reunião"}
                    </div>
                    {ata.objetivo && (
                      <div className="text-xs text-text-secondary truncate">{ata.objetivo}</div>
                    )}
                    <div className="text-xs text-text-secondary/70 mt-0.5">
                      {formatarData(ata.data)}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                      {STATUS_ATA_LABEL[ata.status_ata] ?? ata.status_ata}
                    </span>
                    {tempo && <span className="text-xs text-text-secondary">{tempo}</span>}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </AdminModal>
  );
}
