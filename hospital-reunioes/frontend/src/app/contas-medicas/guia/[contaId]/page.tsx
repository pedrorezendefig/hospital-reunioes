"use client";

/**
 * O Guia da faturista (issue #1121, PRD #1113, ADR 0070).
 *
 * A tela que cabe ao lado do MV (720 px): cabeçalho da conta, os três números
 * (Nota de entrada, R$ a ajustar, Itens feitos), as linhas por dia e setor e o
 * rodapé com a observação e o "Concluir e abrir a próxima", sempre habilitado.
 * Na conta concluída, o rodapé tem o "Reenviar conta corrigida" (issue #1136):
 * a nota de saída vai ao lado da de entrada e cada linha Feito ganha a marca.
 *
 * Quem decide tudo é o servidor: a faturista só abre a própria conta, abrir
 * muda A fazer para Em correção, e concluída não aceita marcação. Depois de
 * cada clique a tela relê o Guia, para os números nunca saírem da conta.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, RefreshCw, Upload } from "lucide-react";

import { LinhaDoGuia, type Marcacao } from "@/components/contas-medicas/LinhaDoGuia";
import { useToast } from "@/components/ui/Toast";
import {
  CONCLUIDAS,
  type GrupoGuia,
  type Guia,
  ROTULO_SITUACAO,
  dataCurta,
  perguntaDeConclusao,
  reais,
  resumoDoReenvio,
  rotuloDoGrupo,
} from "@/lib/contas-medicas/guia";
import { createClient } from "@/lib/supabase/client";

const COR_DA_SITUACAO: Record<string, string> = {
  A_FAZER: "bg-[#FEE2E2] text-[#991B1B]",
  EM_CORRECAO: "bg-[#FEF3C7] text-[#92400E]",
  CONCLUIDA: "bg-[#DCFCE7] text-[#166534]",
  CONCLUIDA_COM_PENDENCIA: "bg-[#FEF3C7] text-[#92400E]",
  RETORNO: "bg-[#FEF3C7] text-[#92400E]",
};

const TITULO = "text-xs font-semibold uppercase tracking-[0.04em] text-slate-500";

function coluna(valor: string): string {
  return valor.charAt(0).toUpperCase() + valor.slice(1).toLowerCase();
}

function subtitulo(guia: Guia): string {
  const c = guia.cabecalho;
  const parcial =
    c.periodo_inicio && c.periodo_fim
      ? `parcial de ${dataCurta(c.periodo_inicio)} a ${dataCurta(c.periodo_fim)}`
      : null;
  return [
    c.paciente_rotulo,
    c.numero_conta ? `conta ${c.numero_conta}` : null,
    c.operadora,
    c.coluna_preco ? `coluna ${coluna(c.coluna_preco)}` : null,
    parcial,
  ]
    .filter(Boolean)
    .join(" · ");
}

function temAberta(grupo: GrupoGuia): boolean {
  return grupo.linhas.some((linha) => linha.estado === "ABERTA" && linha.acao !== "VALIDAR");
}

async function detalhe(resposta: Response, padrao: string): Promise<string> {
  try {
    const corpo = await resposta.json();
    return typeof corpo?.detail === "string" ? corpo.detail : padrao;
  } catch {
    return padrao;
  }
}

export default function GuiaPage() {
  const params = useParams<{ contaId: string }>();
  const bruto = params?.contaId;
  const contaId = Array.isArray(bruto) ? bruto[0] : (bruto ?? "");
  const router = useRouter();
  const { toast } = useToast();

  const [token, setToken] = useState<string | null>(null);
  const [guia, setGuia] = useState<Guia | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [resultadoDoReenvio, setResultadoDoReenvio] = useState<string | null>(null);
  const seletorDoPdf = useRef<HTMLInputElement>(null);

  const base = `/api/contas-medicas/contas/${contaId}/guia`;

  const carregar = useCallback(
    async (tk: string) => {
      const resposta = await fetch(base, { headers: { Authorization: `Bearer ${tk}` } });
      if (!resposta.ok) {
        setErro(await detalhe(resposta, "Não consegui abrir o guia desta conta."));
        return;
      }
      setErro(null);
      setGuia(await resposta.json());
    },
    [base],
  );

  useEffect(() => {
    let vivo = true;
    async function iniciar() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const tk = session?.access_token ?? null;
      if (!vivo) return;
      setToken(tk);
      setGuia(null);
      setObservacao("");
      setResultadoDoReenvio(null);
      if (tk) await carregar(tk);
      else setErro("Sessão expirada. Entre de novo.");
    }
    iniciar();
    return () => {
      vivo = false;
    };
  }, [carregar]);

  async function enviar(caminho: string, metodo: string, corpo?: unknown): Promise<Response | null> {
    if (!token) return null;
    setOcupado(true);
    try {
      const resposta = await fetch(`${base}${caminho}`, {
        method: metodo,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(corpo !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(corpo !== undefined ? { body: JSON.stringify(corpo) } : {}),
      });
      if (!resposta.ok) {
        toast(await detalhe(resposta, "Não deu certo. Tente de novo."), "error");
        return null;
      }
      return resposta;
    } finally {
      setOcupado(false);
    }
  }

  async function marcar(linhaId: string, marcacao: Marcacao) {
    if (await enviar(`/linhas/${linhaId}/marcacao`, "POST", marcacao)) await carregar(token as string);
  }

  async function desfazer(linhaId: string) {
    if (await enviar(`/linhas/${linhaId}/marcacao`, "DELETE")) await carregar(token as string);
  }

  async function marcarODia(grupo: GrupoGuia) {
    if (await enviar("/dia/feito", "POST", { data: grupo.data, setor: grupo.setor })) {
      await carregar(token as string);
    }
  }

  function copiar(codigo: string) {
    if (!navigator.clipboard) {
      toast("Não consegui copiar o código", "error");
      return;
    }
    navigator.clipboard.writeText(codigo).then(
      () => toast("Código copiado", "success"),
      () => toast("Não consegui copiar o código", "error"),
    );
  }

  async function reanalisar() {
    if (!token) return;
    setOcupado(true);
    try {
      const resposta = await fetch(`/api/contas-medicas/contas/${contaId}/reanalisar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        toast(await detalhe(resposta, "Não deu certo. Tente de novo."), "error");
        return;
      }
      toast("A conta voltou para a análise", "success");
      router.push("/contas-medicas");
    } finally {
      setOcupado(false);
    }
  }

  async function reenviar(arquivo: File | undefined) {
    if (!token || !arquivo) return;
    const corpo = new FormData();
    corpo.append("arquivo", arquivo, arquivo.name);
    setOcupado(true);
    try {
      const resposta = await fetch(`/api/contas-medicas/contas/${contaId}/reenvio`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: corpo,
      });
      if (!resposta.ok) {
        toast(await detalhe(resposta, "Não consegui ler a conta corrigida. Envie de novo."), "error");
        return;
      }
      setResultadoDoReenvio(resumoDoReenvio(await resposta.json()));
    } finally {
      setOcupado(false);
      if (seletorDoPdf.current) seletorDoPdf.current.value = "";
    }
    await carregar(token);
  }

  async function concluir() {
    if (!guia) return;
    const pergunta = perguntaDeConclusao(guia.numeros.itens_sem_marcacao);
    if (pergunta && !window.confirm(pergunta)) return;
    const texto = observacao.trim();
    const resposta = await enviar("/concluir", "POST", texto ? { observacao: texto } : {});
    if (!resposta) return;
    const { proxima_conta_id: proxima } = await resposta.json();
    toast("Conta concluída", "success");
    router.push(proxima ? `/contas-medicas/guia/${proxima}` : "/contas-medicas");
  }

  if (erro) {
    return (
      <div className="max-w-3xl mx-auto">
        <VoltarParaContas />
        <p className="bg-white rounded-2xl border border-border p-6 text-sm text-slate-600">{erro}</p>
      </div>
    );
  }

  if (!guia) {
    return (
      <div className="max-w-3xl mx-auto">
        <VoltarParaContas />
        <p className="text-sm text-slate-500">Abrindo o guia...</p>
      </div>
    );
  }

  const { cabecalho, numeros } = guia;
  const concluida = CONCLUIDAS.includes(cabecalho.situacao);
  const resumoDoAjuste =
    numeros.valor_em_validacao > 0
      ? `em ${numeros.itens_a_ajustar} itens, mais ${reais(numeros.valor_em_validacao)} em validação`
      : `em ${numeros.itens_a_ajustar} itens`;

  return (
    <div className="max-w-3xl mx-auto space-y-5 min-w-0">
      <VoltarParaContas />

      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-slate-900">Atendimento {cabecalho.numero_atendimento}</h1>
          <span
            className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${
              COR_DA_SITUACAO[cabecalho.situacao] ?? "bg-[#F1F5F9] text-[#475569]"
            }`}
          >
            {ROTULO_SITUACAO[cabecalho.situacao] ?? cabecalho.situacao}
          </span>
          {guia.pode_reanalisar && (
            <button
              type="button"
              onClick={reanalisar}
              disabled={ocupado}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              Reanalisar
            </button>
          )}
        </div>
        <p className="text-sm text-slate-500 break-words">{subtitulo(guia)}</p>
      </header>

      {cabecalho.parecer_parcial && (
        <div
          role="note"
          aria-label="Parecer parcial"
          className="rounded-xl border border-[#FDE68A] bg-[#FEF3C7] px-4 py-3 text-sm text-[#92400E]"
        >
          <p className="font-semibold uppercase tracking-[0.04em]">PARECER PARCIAL</p>
          {cabecalho.faltantes.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {cabecalho.faltantes.map((faltante, indice) => (
                <li key={indice}>{String(faltante)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {(guia.respostas ?? []).length > 0 && (
        <div
          role="note"
          aria-label="Resposta da Validação"
          className="rounded-xl border border-border bg-[#EEEEF6] px-4 py-3 text-sm text-slate-700 space-y-2"
        >
          <p className="font-semibold uppercase tracking-[0.04em] text-primary">Resposta da Validação</p>
          {(guia.respostas ?? []).map((resposta, indice) => (
            <div key={indice}>
              <p className="text-xs text-slate-500">
                {resposta.regra_codigo ? `Regra ${resposta.regra_codigo}` : resposta.titulo}
              </p>
              <p className="whitespace-pre-line break-words">{resposta.resposta}</p>
            </div>
          ))}
        </div>
      )}

      <section aria-label="Números do guia" className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-white rounded-2xl border border-border shadow-premium p-4 flex flex-wrap gap-x-6 gap-y-2">
          <div>
            <p className={TITULO}>Nota de entrada</p>
            <p className="text-3xl font-bold text-primary">{numeros.nota_entrada}</p>
          </div>
          {guia.reenvio?.nota_saida != null && (
            <div>
              <p className={TITULO}>Nota de saída</p>
              <p className="text-3xl font-bold text-primary">{guia.reenvio.nota_saida}</p>
            </div>
          )}
        </div>
        <div className="bg-white rounded-2xl border border-border shadow-premium p-4">
          <p className={TITULO}>R$ a ajustar</p>
          <p className="text-3xl font-bold text-primary">R$ {reais(numeros.valor_a_ajustar)}</p>
          <p className="text-xs text-slate-500">{resumoDoAjuste}</p>
        </div>
        <div className="bg-white rounded-2xl border border-border shadow-premium p-4">
          <p className={TITULO}>Itens feitos</p>
          <p className="text-3xl font-bold text-primary">
            {numeros.itens_feitos} de {numeros.itens_total}
          </p>
        </div>
      </section>

      {guia.grupos.length === 0 && (
        <p className="bg-white rounded-2xl border border-border p-6 text-sm text-slate-500 text-center">
          Nada a corrigir nesta conta.
        </p>
      )}

      {guia.grupos.map((grupo) => {
        const rotulo = rotuloDoGrupo(grupo);
        return (
          <section key={rotulo} aria-label={rotulo} className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className={TITULO}>{rotulo}</h2>
              {!concluida && temAberta(grupo) && (
                <button
                  type="button"
                  onClick={() => marcarODia(grupo)}
                  disabled={ocupado}
                  className="text-xs font-semibold text-primary hover:underline disabled:opacity-50"
                >
                  Marcar o dia como feito
                </button>
              )}
            </div>
            <div className="space-y-2">
              {grupo.linhas.map((linha) => (
                <LinhaDoGuia
                  key={linha.id}
                  linha={linha}
                  concluida={concluida}
                  ocupado={ocupado}
                  onMarcar={(marcacao) => marcar(linha.id, marcacao)}
                  onDesfazer={() => desfazer(linha.id)}
                  onCopiar={copiar}
                />
              ))}
            </div>
          </section>
        );
      })}

      {concluida ? (
        <footer className="bg-white rounded-2xl border border-border p-4 space-y-3">
          <p className="text-sm text-slate-600">Conta concluída. As marcações não mudam mais.</p>
          {guia.pode_reenviar && (
            <div className="space-y-2">
              <input
                ref={seletorDoPdf}
                type="file"
                accept="application/pdf"
                aria-label="PDF da conta corrigida"
                className="hidden"
                onChange={(evento) => reenviar(evento.target.files?.[0])}
              />
              <button
                type="button"
                onClick={() => seletorDoPdf.current?.click()}
                disabled={ocupado}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 hover:border-slate-300 disabled:opacity-50"
              >
                <Upload className="w-4 h-4" aria-hidden="true" />
                Reenviar conta corrigida
              </button>
              {resultadoDoReenvio && (
                <p role="status" className="text-sm font-semibold text-slate-700">
                  {resultadoDoReenvio}
                </p>
              )}
              <p className="text-xs text-slate-500">
                Opcional. Depois de corrigir no MV, envie só o PDF da conta para ver se a correção pegou. A conta já
                está na sua produção.
              </p>
            </div>
          )}
        </footer>
      ) : (
        <footer className="bg-white rounded-2xl border border-border shadow-premium p-4 space-y-3">
          <label htmlFor="observacao-gestao" className={`block ${TITULO}`}>
            Observação para a gestão de contas médicas
          </label>
          <textarea
            id="observacao-gestao"
            value={observacao}
            onChange={(evento) => setObservacao(evento.target.value)}
            rows={2}
            placeholder="Opcional"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={concluir}
            className="w-full sm:w-auto px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold uppercase tracking-[0.04em]"
          >
            Concluir e abrir a próxima
          </button>
          <p className="text-xs text-slate-500">
            Você pode concluir com pendência. Os itens em validação e os bloqueados seguem para a gestão, e a
            conta já entra na sua produção.
          </p>
        </footer>
      )}
    </div>
  );
}

function VoltarParaContas() {
  return (
    <Link
      href="/contas-medicas"
      className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-2"
    >
      <ArrowLeft className="w-4 h-4" />
      Contas médicas
    </Link>
  );
}
