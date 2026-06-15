"use client";

import type { ReactNode } from "react";
import { FileText, ListChecks, Crosshair, Check } from "lucide-react";
import { Section } from "@/components/ui/Section";

/** Item do quadro de ações montado pelo agente (shape consumido por liberar_pendencias). */
export interface AcaoEnxuta {
  acao?: string;
  responsavel?: string | null;
  /** Vínculo da Resolução (ADR 0008, #79): id do Colaborador do cadastro quando
   * o nome casou; null/ausente = nome livre (externo, ambíguo ou ata antiga). */
  responsavel_id?: string | null;
  cargo?: string | null;
  prazo?: string | null;
  entregavel?: string | null;
  objetivo_meta?: string | null;
  status?: string;
}

/** Rascunho enxuto da Ata Guiada (ADR 0005/0006): só resumo + quadro de ações. */
export interface RascunhoAta {
  resumo_executivo?: string;
  quadro_atribuicoes?: AcaoEnxuta[];
}

interface AtaEnxutaViewProps {
  resumoExecutivo?: string;
  quadro?: AcaoEnxuta[];
  /**
   * Quais seções renderizar. O detalhe da Reunião usa "resumo" e "quadro" SEPARADAS
   * (preserva a ordem com as demais seções da Ata por Transcrição); a tela dedicada
   * da Ata Guiada usa "ambas" (resumo em cima, quadro embaixo — a ata viva).
   */
  secoes?: "resumo" | "quadro" | "ambas";
  /** Modo correção (detalhe): mostra o alvo ⌖ e torna a seção/linha clicável. */
  correctionMode?: boolean;
  sectionContext?: string | null;
  onSectionContext?: (ctx: string) => void;
  /**
   * Quando true, CADA ação do quadro ganha seu próprio ícone-alvo (⌖). A Ata
   * Guiada aponta o Resumo e cada ação individualmente (#58). No detalhe (correção
   * de transcrição) fica false: lá a linha já é clicável e o quadro tem o alvo só
   * no cabeçalho — comportamento preservado.
   */
  alvoPorAcao?: boolean;
  /** Render custom da célula Responsável (o detalhe injeta o combobox inline). */
  renderResponsavel?: (acao: AcaoEnxuta, index: number) => ReactNode;
  /**
   * Quadro ao vivo da Guiada (#79): exibe o indicador de vínculo da Resolução —
   * ✓ quando o responsável casou com o cadastro, "sem vínculo" quando ficou só o
   * nome. O detalhe (atas por Transcrição, sem Resolução ao vivo) não liga isso.
   */
  mostrarVinculo?: boolean;
  /** true quando já montou no client — habilita a formatação de data pt-BR. */
  mounted?: boolean;
  /** Mostrado quando secoes="ambas" e ainda não há nada (início da montagem). */
  placeholderVazio?: ReactNode;
}

/** Botão-alvo (⌖) de "apontar seção" — reaproveita o padrão de UX da correção de transcrição. */
function AlvoSecao({ ativo, onClick }: { ativo: boolean; onClick: () => void }) {
  return (
    <button
      // stopPropagation: quando o alvo vive dentro de uma linha clicável (⌖ por ação),
      // não dispara também o onClick da linha. Inofensivo nos cabeçalhos de seção.
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`p-1.5 rounded-lg transition-colors ${
        ativo ? "bg-primary/10 text-primary" : "hover:bg-slate-100 text-slate-400"
      }`}
      title="Apontar para esta seção"
    >
      <Crosshair className="w-4 h-4" />
    </button>
  );
}

/**
 * Renderiza o Resumo Executivo e o Quadro de Atribuições de uma Ata **enxuta**
 * (resumo + quadro), com o mesmo visual da Ata final. Componente apresentacional:
 * dados entram, eventos de "apontar seção" (⌖) saem. Extraído do detalhe da Reunião
 * (ADR 0006) e reusado na tela dedicada da Ata Guiada — fonte única do visual.
 */
export default function AtaEnxutaView({
  resumoExecutivo,
  quadro,
  secoes = "ambas",
  correctionMode = false,
  sectionContext = null,
  onSectionContext,
  alvoPorAcao = false,
  renderResponsavel,
  mostrarVinculo = false,
  mounted = true,
  placeholderVazio,
}: AtaEnxutaViewProps) {
  const acoes = quadro ?? [];
  const temResumo = Boolean((resumoExecutivo || "").trim());
  const temQuadro = acoes.length > 0;
  const mostrarResumo = secoes === "ambas" || secoes === "resumo";
  const mostrarQuadro = secoes === "ambas" || secoes === "quadro";
  // ⌖ por ação (Guiada, #58): cada linha ganha seu alvo. Exige o trio
  // correctionMode + onSectionContext + alvoPorAcao (o detalhe não passa o último).
  const mostrarAlvoAcao = correctionMode && Boolean(onSectionContext) && alvoPorAcao;

  // Tela dedicada no início da montagem: nada ainda → placeholder (não cards vazios).
  if (secoes === "ambas" && !temResumo && !temQuadro && placeholderVazio) {
    return <>{placeholderVazio}</>;
  }

  return (
    <>
      {mostrarResumo && temResumo && (
        <Section
          title="Resumo Executivo"
          icon={FileText}
          action={
            correctionMode && onSectionContext ? (
              <AlvoSecao
                ativo={sectionContext === "Resumo Executivo"}
                onClick={() => onSectionContext("Resumo Executivo")}
              />
            ) : undefined
          }
        >
          <p className="text-slate-700 text-sm leading-relaxed italic">&quot;{resumoExecutivo}&quot;</p>
        </Section>
      )}

      {mostrarQuadro && temQuadro && (
        <Section
          title={`Quadro de Atribuições (${acoes.length} ações)`}
          icon={ListChecks}
          action={
            correctionMode && onSectionContext ? (
              <AlvoSecao
                ativo={sectionContext === "Quadro de Atribuições"}
                onClick={() => onSectionContext("Quadro de Atribuições")}
              />
            ) : undefined
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {["Ação", "Responsável", "Objetivo / Meta", "Prazo", "Status"].map((h) => (
                    <th
                      key={h}
                      className="text-left pb-2 text-xs font-semibold text-slate-400 uppercase tracking-wide pr-4"
                    >
                      {h}
                    </th>
                  ))}
                  {mostrarAlvoAcao && <th className="pb-2 w-9" aria-label="Apontar ação" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {acoes.map((a, i) => {
                  const ctxAcao = `Quadro de Atribuições, item ${i + 1}: "${a.acao}"`;
                  return (
                  <tr
                    key={i}
                    className={correctionMode ? "cursor-pointer hover:bg-primary/5" : ""}
                    onClick={correctionMode && onSectionContext ? () => onSectionContext(ctxAcao) : undefined}
                  >
                    <td className="py-3 pr-4 text-slate-800 font-medium align-top">{a.acao}</td>
                    <td className="py-3 pr-4 align-top min-w-[180px]">
                      {renderResponsavel ? (
                        renderResponsavel(a, i)
                      ) : (
                        <>
                          <p className="text-slate-700 flex items-center gap-1.5">
                            {a.responsavel || <span className="text-slate-300">A definir</span>}
                            {mostrarVinculo && a.responsavel && a.responsavel_id && (
                              <Check
                                className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0"
                                aria-label="Vinculado ao cadastro"
                              />
                            )}
                          </p>
                          {a.cargo && <p className="text-xs text-slate-400">{a.cargo}</p>}
                          {mostrarVinculo && a.responsavel && !a.responsavel_id && (
                            <p className="text-[10px] text-slate-400 italic">sem vínculo</p>
                          )}
                        </>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-slate-600 text-xs align-top max-w-[180px]">
                      {a.objetivo_meta || a.entregavel || <span className="text-slate-300">-</span>}
                    </td>
                    <td className="py-3 pr-4 text-slate-600 align-top whitespace-nowrap">
                      {(() => {
                        if (!a.prazo) return <span className="text-slate-300">A definir</span>;
                        if (a.prazo === "Fluxo contínuo")
                          return <span className="italic text-slate-500">Fluxo contínuo</span>;
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
                        const label =
                          st === "CONCLUIDO" ? "Concluído" : st === "EM_ANDAMENTO" ? "Em andamento" : "Aberto";
                        return (
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}
                          >
                            {label}
                          </span>
                        );
                      })()}
                    </td>
                    {mostrarAlvoAcao && (
                      <td className="py-3 align-top">
                        <AlvoSecao ativo={sectionContext === ctxAcao} onClick={() => onSectionContext?.(ctxAcao)} />
                      </td>
                    )}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </>
  );
}
