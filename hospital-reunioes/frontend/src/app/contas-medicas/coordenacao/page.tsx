"use client";

/**
 * A tela Coordenação de Contas médicas (issue #1143, PRD #1129, adendo v1.1).
 *
 * A segunda checagem da coordenadora: três números no topo (lembretes abertos,
 * contas com lembrete, R$ a conferir) e a lista por conta, a do lembrete mais
 * antigo primeiro, com a situação da conta na faturista. Cada lembrete tem
 * Incluído e Não se aplica. A aba Cenários aparece só para quem cadastra.
 * Quem decide o que cada pessoa vê é o servidor: sem a permissão, 403 e nenhum
 * dado de cenário ou de lembrete.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, ClipboardCheck, Loader2 } from "lucide-react";

import { AbaCenarios } from "@/components/contas-medicas/coordenacao/AbaCenarios";
import { CartaoDoLembrete } from "@/components/contas-medicas/coordenacao/CartaoDoLembrete";
import {
  type Conferencia,
  type ContaComLembrete,
  type EstadoDaMarcacao,
  ROTA_COORDENACAO,
  situacaoNaFaturista,
} from "@/lib/contas-medicas/coordenacao";
import { dataCurta, reais } from "@/lib/contas-medicas/guia";
import { createClient } from "@/lib/supabase/client";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const ERRO_DE_CARGA = "Não foi possível carregar a conferência da coordenação.";

type Aba = "lembretes" | "cenarios";

function Numero({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <section aria-label={titulo} className={`${CARTAO} p-5`}>
      <h2 className="text-sm font-semibold text-slate-700">{titulo}</h2>
      <p className="mt-3 text-3xl font-bold tabular-nums text-primary">{valor}</p>
    </section>
  );
}

function complemento(conta: ContaComLembrete): string {
  const periodo =
    conta.periodo_inicio && conta.periodo_fim
      ? `${dataCurta(conta.periodo_inicio)} a ${dataCurta(conta.periodo_fim)}`
      : null;
  return [
    conta.paciente_rotulo,
    conta.operadora,
    conta.numero_conta ? `conta ${conta.numero_conta}` : null,
    periodo,
    situacaoNaFaturista(conta),
  ]
    .filter(Boolean)
    .join(" · ");
}

export default function CoordenacaoPage() {
  const [token, setToken] = useState<string | null>(null);
  const [dados, setDados] = useState<Conferencia | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [semPermissao, setSemPermissao] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("lembretes");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [copiado, setCopiado] = useState<string | null>(null);

  const carregar = useCallback(async (sessao: string) => {
    try {
      const res = await fetch(ROTA_COORDENACAO, { headers: { Authorization: `Bearer ${sessao}` } });
      if (res.status === 403) {
        setSemPermissao(true);
        return;
      }
      if (!res.ok) {
        setErro(ERRO_DE_CARGA);
        return;
      }
      setErro(null);
      setDados(await res.json());
    } catch {
      setErro(ERRO_DE_CARGA);
    }
  }, []);

  useEffect(() => {
    async function iniciar() {
      try {
        const {
          data: { session },
        } = await createClient().auth.getSession();
        const sessao = session?.access_token ?? null;
        setToken(sessao);
        if (sessao) await carregar(sessao);
        else setErro("Sessão expirada. Entre de novo.");
      } finally {
        setCarregando(false);
      }
    }
    iniciar();
  }, [carregar]);

  async function marcar(lembreteId: string, estado: EstadoDaMarcacao, observacao: string | null) {
    if (!token) return;
    setOcupado(lembreteId);
    try {
      const res = await fetch(`${ROTA_COORDENACAO}/lembretes/${lembreteId}/marcacao`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ estado, observacao }),
      });
      if (!res.ok) setErro("Não foi possível marcar o lembrete. Tente de novo.");
      await carregar(token);
    } catch {
      setErro("Não foi possível marcar o lembrete. Tente de novo.");
    } finally {
      setOcupado(null);
    }
  }

  async function copiar(codigo: string) {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiado(codigo);
    } catch {
      setCopiado(null);
    }
  }

  if (carregando) {
    return (
      <p className="flex items-center gap-2 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando a conferência
      </p>
    );
  }

  if (semPermissao) {
    return (
      <div className={`${CARTAO} p-6`}>
        <p className="text-sm text-slate-600">
          Você não tem a permissão de Conferência da coordenação, que é a da segunda checagem das contas.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/contas-medicas"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Contas médicas
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Coordenação</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          A segunda checagem: quando o prontuário mostra um cenário, os insumos que faltam na conta. A faturista não vê
          esta tela.
        </p>
      </div>

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}
      {copiado && (
        <p role="status" className="text-xs text-slate-500">
          Código {copiado} copiado.
        </p>
      )}

      {dados && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Numero titulo="Lembretes abertos" valor={String(dados.numeros.lembretes_abertos)} />
          <Numero titulo="Contas com lembrete" valor={String(dados.numeros.contas_com_lembrete)} />
          <Numero titulo="R$ a conferir" valor={`R$ ${reais(dados.numeros.valor_a_conferir)}`} />
        </div>
      )}

      {dados?.pode_cadastrar && (
        <div className="flex gap-2 border-b border-border" role="tablist">
          {(
            [
              ["lembretes", "Lembretes"],
              ["cenarios", "Cenários"],
            ] as [Aba, string][]
          ).map(([id, rotulo]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={aba === id}
              onClick={() => setAba(id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                aba === id ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text"
              }`}
            >
              {rotulo}
            </button>
          ))}
        </div>
      )}

      {aba === "cenarios" && token ? (
        <AbaCenarios token={token} />
      ) : (
        dados && (
          <div className="space-y-4">
            {dados.contas.length === 0 ? (
              <div className={`${CARTAO} p-10 text-center`}>
                <ClipboardCheck className="w-8 h-8 text-slate-300 mx-auto mb-3" aria-hidden="true" />
                <p className="text-sm text-slate-500">Nenhum lembrete aberto.</p>
              </div>
            ) : (
              dados.contas.map((conta) => (
                <section
                  key={conta.conta_id}
                  aria-label={`Atendimento ${conta.numero_atendimento ?? ""}`}
                  className={`${CARTAO} p-5 space-y-3`}
                >
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Atendimento {conta.numero_atendimento}</h2>
                    <p className="text-xs text-slate-500">{complemento(conta)}</p>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {conta.lembretes.map((lembrete) => (
                      <CartaoDoLembrete
                        key={lembrete.id}
                        lembrete={lembrete}
                        ocupado={ocupado === lembrete.id}
                        onMarcar={(estado, observacao) => marcar(lembrete.id, estado, observacao)}
                        onCopiar={copiar}
                      />
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>
        )
      )}
    </div>
  );
}
