import {
  Baby,
  FlaskConical,
  MapPin,
  ScanLine,
  Siren,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";

import { formatarInteiro, formatarPercentual } from "@/lib/central-de-comando/formato";
import { COR_DA_BARRA, COR_DO_TRILHO, larguraNaProporcaoDoMaior } from "@/lib/central-de-comando/graficos";

/**
 * Uma Área do site do bloco `areas_do_site` do payload de Dados do Google:
 * o nome e o que ela reúne (do catálogo da Central), as Visitas às páginas
 * dela no período e no anterior, e a variação de um para o outro, já
 * calculada no backend (nula quando o anterior não teve visita). O backend
 * manda as cinco, da mais visitada para a menos.
 */
export type AreaDoPayload = {
  chave: string;
  nome: string;
  descricao: string;
  visitas: number;
  visitas_anterior: number;
  variacao: number | null;
};

/** Um ícone por Área do site; Área que a tela ainda não conhece ganha o genérico. */
const ICONE_DA_AREA: Record<string, LucideIcon> = {
  maternidade: Baby,
  emergencia: Siren,
  "centro-de-imagem": ScanLine,
  "centro-medico": Stethoscope,
  laboratorio: FlaskConical,
};

/**
 * O ranking das Áreas do site de Dados do Google (issue #818, ADR 0058).
 *
 * Porte do ranking da Central antiga em Tailwind puro, com o nome novo: cada
 * Área com o ícone, o nome, o que ela reúne, a barra na proporção da líder,
 * as Visitas e a seta da variação contra o período anterior. A ordem e a
 * variação vêm prontas do backend. O número fala das páginas do Site, e não
 * da procura pelo serviço: quem diz isso é a dica do bloco.
 */
export function RankingAreasDoSite({ areas }: { areas: AreaDoPayload[] }) {
  if (areas.length === 0) {
    return <p className="py-10 text-center text-sm text-text-secondary">Sem dados de Áreas do site para este período.</p>;
  }

  const lider = Math.max(...areas.map((area) => area.visitas));

  return (
    <ol aria-label="Áreas do site por Visitas" className="divide-y divide-border">
      {areas.map((area) => {
        const Icone = ICONE_DA_AREA[area.chave] ?? MapPin;
        return (
          <li key={area.chave} className="flex items-center gap-4 py-3">
            <span
              aria-hidden="true"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"
            >
              <Icone className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-text">{area.nome}</p>
              <p className="text-xs text-text-secondary">{area.descricao}</p>
              <div
                aria-hidden="true"
                className="mt-2 h-1.5 max-w-xs overflow-hidden rounded-full"
                style={{ backgroundColor: COR_DO_TRILHO }}
              >
                <div
                  data-testid="barra"
                  className="h-full rounded-full"
                  style={{
                    width: `${larguraNaProporcaoDoMaior(area.visitas, lider)}%`,
                    backgroundColor: COR_DA_BARRA,
                  }}
                />
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-lg font-bold tabular-nums text-text">{formatarInteiro(area.visitas)}</p>
              <Variacao variacao={area.variacao} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * A seta da variação contra o período anterior, no molde do número-manchete
 * da Visão Geral: para cima em verde, para baixo em âmbar, a porcentagem sem
 * sinal. Sem base de comparação, ou estável, não há seta (como no ranking da
 * Central antiga).
 */
function Variacao({ variacao }: { variacao: number | null }) {
  if (variacao === null || variacao === 0) return null;
  const subiu = variacao > 0;
  const texto = formatarPercentual(Math.abs(variacao));
  return (
    <p
      aria-label={`${subiu ? "subiu" : "caiu"} ${texto} em relação ao período anterior`}
      className={`text-xs font-semibold tabular-nums ${subiu ? "text-emerald-700" : "text-amber-700"}`}
    >
      {subiu ? "↑" : "↓"} {texto}
    </p>
  );
}
