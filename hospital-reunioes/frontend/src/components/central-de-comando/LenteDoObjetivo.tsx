"use client";

/**
 * A lente de um Objetivo da Central de Comando (issue #820, PRD #809, ADR 0058).
 *
 * Pede ao backend os numeros de um Objetivo no periodo, as sugestoes (cada uma
 * com o porque) e o frescor, e desenha o que veio. A conta e do backend; a tela
 * so escreve. Identificador que o backend nao conhece (404) cai na pagina de
 * nao encontrado (`notFound`).
 *
 * Honestidade do dado, como nas outras telas: sem credencial (503) ou com a
 * fonte fora e nada guardado (502), a lente diz o que houve e nao inventa
 * numero.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertTriangle, ArrowLeft, Loader2, PlugZap } from "lucide-react";
import { useEffect, useState } from "react";

import { getAuthToken } from "@/hooks/useAuth";
import { BASE_CENTRAL, FALHA_DE_CONEXAO, type Frescor, lerRecusa, SEM_SESSAO } from "@/lib/central-de-comando/api";
import { formatarInteiro, formatarPercentual, formatarQuando } from "@/lib/central-de-comando/formato";
import { PERIODOS, PERIODOS_DO_INSTAGRAM, type Periodo } from "@/lib/central-de-comando/periodo";

import { CAMINHO_OBJETIVOS } from "./Objetivos";
import { SeletorDePeriodo } from "./SeletorDePeriodo";

/** Um numero da lente. Fluxo traz `anterior` e `variacao`; estoque, `crescimento`. */
export type NumeroDaLente = {
  chave: string;
  rotulo: string;
  valor: number;
  anterior?: number;
  variacao?: number | null;
  crescimento?: number;
  crescimento_anterior?: number;
};

/** Uma sugestao da lente, sempre com o porque (o dado que a disparou). */
export type SugestaoDaLente = {
  id: string;
  titulo: string;
  detalhe: string;
  porque: string;
  tom: "atencao" | "positivo" | "neutro";
};

/** O que `GET /api/admin/central-de-comando/objetivos/{id}` devolve. */
export type LentePayload = {
  objetivo: { id: string; nome: string; descricao: string };
  periodo: { chave: Periodo; dias: number };
  numeros: NumeroDaLente[];
  sugestoes: SugestaoDaLente[];
  frescor: Frescor;
};

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; dados: LentePayload }
  | { tipo: "nao-encontrado" }
  | { tipo: "nao-configurado"; mensagem: string }
  | { tipo: "falhou"; mensagem: string }
  | { tipo: "sem-conexao"; mensagem: string };

const CORES_DO_TOM: Record<SugestaoDaLente["tom"], string> = {
  atencao: "border-amber-200 bg-amber-50 text-amber-900",
  positivo: "border-emerald-200 bg-emerald-50 text-emerald-900",
  neutro: "border-border bg-white text-text",
};

export function LenteDoObjetivo({ identificador, periodo }: { identificador: string; periodo: Periodo }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const caminho = `${CAMINHO_OBJETIVOS}/${identificador}`;
  const periodos = identificador.startsWith("instagram") ? PERIODOS_DO_INSTAGRAM : PERIODOS;

  useEffect(() => {
    let vivo = true;

    async function carregar() {
      setEstado({ tipo: "carregando" });
      let token: string | undefined;
      try {
        token = await getAuthToken();
      } catch {
        token = undefined;
      }
      if (!token) {
        if (vivo) setEstado({ tipo: "sem-conexao", mensagem: SEM_SESSAO });
        return;
      }
      try {
        const resposta = await fetch(`${BASE_CENTRAL}/objetivos/${identificador}?periodo=${periodo}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (resposta.status === 404) {
          if (vivo) setEstado({ tipo: "nao-encontrado" });
          return;
        }
        if (!resposta.ok) {
          const recusa = await lerRecusa(resposta);
          if (vivo) setEstado(recusa);
          return;
        }
        const dados = (await resposta.json()) as LentePayload;
        if (vivo) setEstado({ tipo: "pronto", dados });
      } catch {
        if (vivo) setEstado({ tipo: "sem-conexao", mensagem: FALHA_DE_CONEXAO });
      }
    }

    carregar();
    return () => {
      vivo = false;
    };
  }, [identificador, periodo]);

  if (estado.tipo === "nao-encontrado") {
    // Em producao, `notFound` lanca e a pagina de nao encontrado assume; o
    // `return null` e defensivo (e o que o teste observa).
    notFound();
    return null;
  }

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Link
          href={CAMINHO_OBJETIVOS}
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text"
        >
          <ArrowLeft className="h-4 w-4" />
          Objetivos
        </Link>
        <SeletorDePeriodo ativo={periodo} caminho={caminho} periodos={periodos} />
      </div>

      {estado.tipo === "carregando" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-2xl border border-border bg-white p-6 text-sm text-text-secondary shadow-premium"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando os números
        </div>
      )}

      {estado.tipo === "pronto" && (
        <div className="space-y-6">
          <header className="space-y-1">
            <h1 className="text-2xl font-bold text-text">{estado.dados.objetivo.nome}</h1>
            <p className="text-sm text-text-secondary">{estado.dados.objetivo.descricao}</p>
            <LinhaDeFrescor frescor={estado.dados.frescor} dias={estado.dados.periodo.dias} />
          </header>

          {estado.dados.numeros.length > 0 ? (
            <ul aria-label="Números do Objetivo" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {estado.dados.numeros.map((numero) => (
                <li key={numero.chave}>
                  <CardNumero numero={numero} />
                </li>
              ))}
            </ul>
          ) : (
            <p role="status" className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-secondary">
              Ainda sem número para este período: a fonte deste Objetivo está em construção.
            </p>
          )}

          {estado.dados.sugestoes.length > 0 && (
            <section aria-label="Sugestões" className="space-y-3">
              <h2 className="text-lg font-bold text-text">Sugestões</h2>
              {estado.dados.sugestoes.map((sugestao) => (
                <CardSugestao key={sugestao.id} sugestao={sugestao} />
              ))}
            </section>
          )}
        </div>
      )}

      {estado.tipo === "nao-configurado" && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Sem ligação com a fonte dos números</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {(estado.tipo === "falhou" || estado.tipo === "sem-conexao") && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível buscar os números agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CardNumero({ numero }: { numero: NumeroDaLente }) {
  return (
    <div className="rounded-2xl border border-border bg-white p-5 shadow-premium">
      <p className="text-xs text-text-secondary">{numero.rotulo}</p>
      <p className="text-3xl font-bold tabular-nums text-text">{formatarInteiro(numero.valor)}</p>
      {numero.crescimento !== undefined ? (
        <p className={`text-sm font-medium ${numero.crescimento >= 0 ? "text-emerald-600" : "text-amber-600"}`}>
          {numero.crescimento >= 0 ? "+" : ""}
          {formatarInteiro(numero.crescimento)} no período
        </p>
      ) : (
        <Variacao variacao={numero.variacao} />
      )}
    </div>
  );
}

function Variacao({ variacao }: { variacao?: number | null }) {
  if (variacao === null || variacao === undefined) {
    return <span className="text-xs text-text-secondary">sem base de comparação com o período anterior</span>;
  }
  const subiu = variacao >= 0;
  return (
    <span className={`text-sm font-medium ${subiu ? "text-emerald-600" : "text-amber-600"}`}>
      {subiu ? "↑" : "↓"} {formatarPercentual(Math.abs(variacao))}
    </span>
  );
}

function CardSugestao({ sugestao }: { sugestao: SugestaoDaLente }) {
  return (
    <div className={`space-y-2 rounded-2xl border p-5 ${CORES_DO_TOM[sugestao.tom]}`}>
      <p className="font-semibold">{sugestao.titulo}</p>
      <p className="text-sm">{sugestao.detalhe}</p>
      <p className="text-xs opacity-80">{sugestao.porque}</p>
    </div>
  );
}

function LinhaDeFrescor({ frescor, dias }: { frescor: Frescor; dias: number }) {
  const partes: string[] = [`últimos ${dias} dias`];
  if (frescor.atualizado_em) {
    partes.push(`números de ${formatarQuando(Date.parse(frescor.atualizado_em), Date.now())}`);
  }
  if (frescor.atualizacao_falhou && frescor.motivo) {
    partes.push(`não foi possível atualizar agora: ${frescor.motivo}`);
  }
  return <p className="text-xs text-text-secondary">{partes.join(" · ")}</p>;
}
