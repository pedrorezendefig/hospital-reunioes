import { AlertTriangle, Building2, PlugZap, Smartphone } from "lucide-react";

import { formatarData, formatarFatia, formatarInteiro, formatarPercentual } from "@/lib/central-de-comando/formato";
import type { Periodo } from "@/lib/central-de-comando/periodo";

type Intervalo = { inicio: string; fim: string };

/** O bloco `periodo` do payload: o período e as datas dele e do anterior. */
export type PeriodoDoPayload = {
  chave: Periodo;
  dias: number;
  atual: Intervalo;
  anterior: Intervalo;
};

/** Um fato do contexto do número-manchete; nulo quando a fonte não tem o dado. */
type FatoDeArea = { chave: string; nome: string; visitas: number };
type FatoComPercentual = { chave: string; rotulo: string; percentual: number };

export type ContextoDoPayload = {
  area: FatoDeArea | null;
  origem: FatoComPercentual | null;
  dispositivo: FatoComPercentual | null;
};

/**
 * O bloco `visitantes` do payload, por estado (issue #821): `ok` com os números
 * e o contexto (a variação já vem calculada do backend), `nao-configurado`
 * quando falta a credencial e `sem-dado` quando a fonte caiu sem nada guardado.
 */
export type VisitantesDoPayload =
  | { estado: "ok"; atual: number; anterior: number; variacao: number | null; contexto: ContextoDoPayload }
  | { estado: "nao-configurado"; motivo: string }
  | { estado: "sem-dado"; motivo: string };

/**
 * A seta da variação contra o período anterior: para cima em verde, para baixo
 * em âmbar, e nada quando não há base de comparação. O sentido fica na seta, e a
 * porcentagem vai sem sinal (molde da Central antiga).
 */
function Variacao({ variacao }: { variacao: number | null }) {
  if (variacao === null) return null;
  const subiu = variacao >= 0;
  return (
    <span className={`font-semibold ${subiu ? "text-emerald-700" : "text-amber-700"}`}>
      {subiu ? "↑" : "↓"} {formatarPercentual(Math.abs(variacao))}
    </span>
  );
}

/**
 * O número-manchete da Visão Geral e o contexto dele: quantos Visitantes o Site
 * teve no período, e, logo abaixo, a Área do site que mais atrai, a principal
 * Origem do público e o dispositivo mais usado. Cada fato só aparece quando a
 * fonte o tem (ADR 0003 de lá); o bloco degrada sozinho, sem derrubar a tela.
 */
export function BlocoVisitantes({
  periodo,
  visitantes,
}: {
  periodo: PeriodoDoPayload;
  visitantes: VisitantesDoPayload;
}) {
  if (visitantes.estado === "nao-configurado") {
    return (
      <BlocoDeAviso
        icone={PlugZap}
        tom="calmo"
        titulo="Sem ligação com o Google Analytics"
        mensagem={visitantes.motivo}
      />
    );
  }
  if (visitantes.estado === "sem-dado") {
    return (
      <BlocoDeAviso
        icone={AlertTriangle}
        tom="erro"
        titulo="Não foi possível buscar os Visitantes agora."
        mensagem={visitantes.motivo}
      />
    );
  }

  return (
    <section
      aria-labelledby="central-visitantes"
      className="space-y-3 rounded-2xl border border-border bg-white p-6 shadow-premium"
    >
      <h2 id="central-visitantes" className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
        Visitantes · últimos {periodo.dias} dias
      </h2>
      <p className="text-5xl font-bold tabular-nums text-text">{formatarInteiro(visitantes.atual)}</p>
      <p className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
        <Variacao variacao={visitantes.variacao} />
        <span>
          {visitantes.variacao === null
            ? "sem base de comparação com o período anterior"
            : "em relação ao período anterior"}
        </span>
      </p>
      <ContextoDoNumero contexto={visitantes.contexto} />
      <p className="text-xs text-text-secondary">
        De {formatarData(periodo.atual.inicio)} a {formatarData(periodo.atual.fim)}. Período anterior:{" "}
        {formatarData(periodo.anterior.inicio)} a {formatarData(periodo.anterior.fim)}.
      </p>
    </section>
  );
}

/** Os três fatos que dão contexto ao número-manchete, cada um se a fonte o tem. */
function ContextoDoNumero({ contexto }: { contexto: ContextoDoPayload }) {
  const { area, origem, dispositivo } = contexto;
  if (!area && !origem && !dispositivo) return null;
  return (
    <dl className="grid gap-3 border-t border-border pt-3 sm:grid-cols-3">
      {area && (
        <Fato
          icone={Building2}
          rotulo="Área do site que mais atrai"
          destaque={area.nome}
          apoio={`${formatarInteiro(area.visitas)} visitas`}
        />
      )}
      {origem && (
        <Fato
          icone={Building2}
          rotulo="Principal Origem do público"
          destaque={origem.rotulo}
          apoio={formatarFatia(origem.percentual)}
        />
      )}
      {dispositivo && (
        <Fato
          icone={Smartphone}
          rotulo="Dispositivo mais usado"
          destaque={dispositivo.rotulo}
          apoio={formatarFatia(dispositivo.percentual)}
        />
      )}
    </dl>
  );
}

function Fato({
  icone: Icone,
  rotulo,
  destaque,
  apoio,
}: {
  icone: typeof Building2;
  rotulo: string;
  destaque: string;
  apoio: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <Icone aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div>
        <dt className="text-xs text-text-secondary">{rotulo}</dt>
        <dd className="text-sm font-semibold text-text">
          {destaque} <span className="font-normal text-text-secondary">· {apoio}</span>
        </dd>
      </div>
    </div>
  );
}

/** O estado calmo (falta configurar) ou de erro (a fonte caiu) do bloco. */
function BlocoDeAviso({
  icone: Icone,
  tom,
  titulo,
  mensagem,
}: {
  icone: typeof PlugZap;
  tom: "calmo" | "erro";
  titulo: string;
  mensagem: string;
}) {
  const cores = tom === "calmo" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-red-200 bg-red-50 text-red-900";
  return (
    <section aria-labelledby="central-visitantes" className={`flex gap-3 rounded-2xl border p-6 ${cores}`}>
      <Icone className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <div className="space-y-1">
        <h2 id="central-visitantes" className="font-semibold">
          {titulo}
        </h2>
        <p className="text-sm">{mensagem}</p>
      </div>
    </section>
  );
}
