"use client";

/**
 * O card de caso padrão da Ouvidoria (issue #1628, seção 4.12 do anexo da
 * Demanda #1527).
 *
 * Três linhas, e nada sai para o lado em nenhuma largura (regra T4):
 *
 * 1. protocolo, o ponto colorido da gravidade e o setor;
 * 2. o assunto que o agente de triagem escreveu, em uma linha;
 * 3. o prazo ou o atraso, quem responde, os selos e a ação.
 *
 * A gravidade é o único elemento colorido. O vermelho fica para o atraso, e o
 * estado do caso é uma etiqueta neutra.
 *
 * O card nunca mostra o resumo: no canal aberto ele é recorte literal do
 * relato, nome de paciente incluído (regra T3, ADR 0087). Sem o assunto, o
 * card diz que ele não foi gerado.
 */

import Link from "next/link";
import { Lock } from "lucide-react";

import {
  ASSUNTO_NAO_GERADO,
  MARCA_PRONTO_PARA_ENCERRAR,
  prontoParaEncerrar,
  rotuloDoStatus,
} from "@/lib/ouvidoria/fila";
import { estaComONucleo, SELO_DO_NUCLEO } from "@/lib/ouvidoria/nucleo";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import type { TipoManifestacao } from "@/lib/ouvidoria/taxonomia";
import { rotuloDaGravidade } from "@/lib/ouvidoria/validacao";

/** O que o card precisa saber de um caso da listagem. */
export interface CasoDoCard {
  id: string;
  protocolo: string;
  status: StatusManifestacao;
  setor: string;
  gravidade: string | null;
  assunto?: string | null;
  sigilo_reforcado?: boolean;
  nsp_decisao?: string | null;
  tipo_manifestacao?: string | null;
}

/**
 * As cores da gravidade, do design system do hospital (seção 4.12): Crítico
 * `hsm-danger`, Alto `hsm-warning`, Médio `hsm-azul-claro`, Baixo
 * `hsm-gray-40`. O caso ainda sem gravidade fica com o ponto vazado.
 */
const COR_DA_GRAVIDADE: Record<string, string> = {
  critico: "bg-[#B3352B]",
  alto: "bg-[#C78A1A]",
  medio: "bg-[#1E4394]",
  baixo: "bg-[#9BA1AB]",
};

export function GravidadeDoCaso({ gravidade }: { gravidade: string | null }) {
  const rotulo = rotuloDaGravidade(gravidade) ?? "A classificar";
  const cor = gravidade ? (COR_DA_GRAVIDADE[gravidade] ?? "bg-slate-400") : "border border-slate-300 bg-white";
  return (
    <span className="inline-flex items-center gap-1.5 shrink-0 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
      <span aria-hidden="true" className={`inline-block w-2.5 h-2.5 rounded-full ${cor}`} />
      {rotulo}
    </span>
  );
}

/** O estado em etiqueta neutra: fundo `hsm-azul-escuro-10`, texto `hsm-azul-escuro`. */
function EtiquetaDoEstado({ status }: { status: StatusManifestacao }) {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide bg-[#EAEAF0] text-[#282760]">
      {rotuloDoStatus(status)}
    </span>
  );
}

function Selo({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 px-2 py-0.5 rounded-full border border-slate-200 text-[11px] font-semibold text-slate-600">
      {children}
    </span>
  );
}

export function CardDeCaso({
  caso,
  prazo,
  atrasado,
  responsavel,
  acao,
  aviso,
}: {
  caso: CasoDoCard;
  /** O prazo ou o atraso, já escrito por quem sabe a régua. */
  prazo: string | null;
  /** O caso já venceu: o prazo sai em vermelho, o único vermelho do card. */
  atrasado: boolean;
  responsavel?: string | null;
  /** O botão da linha 3, quando o card tem ação. */
  acao?: React.ReactNode;
  /** A frase que a ação deixou (a cobrança, por exemplo). */
  aviso?: React.ReactNode;
}) {
  const pronto = prontoParaEncerrar({
    status: caso.status,
    tipo_manifestacao: (caso.tipo_manifestacao ?? null) as TipoManifestacao | null,
  });
  return (
    <li data-protocolo={caso.protocolo} className="px-4 md:px-5 py-3 min-w-0">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0">
        <Link
          href={`/ouvidoria/m/${caso.protocolo}`}
          className="font-mono font-semibold text-sm text-slate-800 hover:underline shrink-0"
        >
          {caso.protocolo}
        </Link>
        <GravidadeDoCaso gravidade={caso.gravidade} />
        <span className="text-sm text-slate-600 truncate min-w-0">{caso.setor}</span>
        {caso.sigilo_reforcado && (
          <span
            title="Caso sigiloso: não projete nem compartilhe esta tela"
            className="inline-flex items-center gap-1 shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide bg-slate-800 text-white"
          >
            <Lock className="w-3 h-3" />
            Sigiloso
          </span>
        )}
      </div>
      <p
        className={`mt-1 text-sm truncate ${caso.assunto ? "text-slate-800" : "italic text-slate-400"}`}
      >
        {caso.assunto || ASSUNTO_NAO_GERADO}
      </p>
      <div className="mt-1.5 flex flex-col md:flex-row md:items-center gap-1.5 md:gap-2.5 min-w-0">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0 flex-1 text-xs">
          {prazo && (
            <span className={atrasado ? "font-semibold text-[#B3352B]" : "text-slate-500"}>{prazo}</span>
          )}
          {responsavel && <span className="text-slate-500 truncate min-w-0">{responsavel}</span>}
          <EtiquetaDoEstado status={caso.status} />
          {estaComONucleo(caso) && <Selo>{SELO_DO_NUCLEO}</Selo>}
          {pronto && <Selo>{MARCA_PRONTO_PARA_ENCERRAR}</Selo>}
        </div>
        {acao && <div className="w-full md:w-auto shrink-0">{acao}</div>}
      </div>
      {aviso}
    </li>
  );
}
