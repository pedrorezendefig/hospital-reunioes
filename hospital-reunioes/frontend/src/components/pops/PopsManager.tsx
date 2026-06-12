"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { BookOpenCheck, Download, FileText, Plus, Sparkles, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import {
  CRITICIDADE_POP_LABELS,
  ESTADO_VERSAO_POP_LABELS,
  PERIODICIDADE_REVISAO_POP_LABELS,
  type CriticidadePop,
  type EstadoVersaoPop,
  type PeriodicidadeRevisaoPop,
  type Pop,
  type PopDesignavel,
} from "@/types";
import type { PopsSetor } from "@/components/pops/SetoresManager";

const ESTADOS: EstadoVersaoPop[] = [
  "A_ELABORAR",
  "EM_ELABORACAO",
  "EM_REVISAO",
  "EM_VALIDACAO",
  "EM_ASSINATURA",
  "PUBLICADO",
];

// O documento preliminar em PDF existe da Revisão em diante (issue #86) — o
// backend guarda os estados/escopo; aqui só decidimos exibir os botões.
const ESTADOS_COM_DOCUMENTO: EstadoVersaoPop[] = ["EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO"];

const ESTADO_BADGE: Record<EstadoVersaoPop, string> = {
  A_ELABORAR: "bg-slate-100 text-slate-700",
  EM_ELABORACAO: "bg-blue-100 text-blue-700",
  EM_REVISAO: "bg-amber-100 text-amber-700",
  EM_VALIDACAO: "bg-purple-100 text-purple-700",
  EM_ASSINATURA: "bg-indigo-100 text-indigo-700",
  PUBLICADO: "bg-emerald-100 text-emerald-700",
};

const CRITICIDADE_BADGE: Record<CriticidadePop, string> = {
  CRITICA: "bg-red-100 text-red-700",
  ALTA: "bg-orange-100 text-orange-700",
  MEDIA: "bg-yellow-100 text-yellow-700",
};

/**
 * POPs do escopo do perfil: lista por estado da Versão + criação pelo
 * formulário institucional (DRF §3.2). O Código HSM_[SIGLA]-[NNN] é gerado
 * e travado pelo backend; o escopo (Coordenador: seu Setor; Gerente: seus
 * Setores; Gestor de Qualidade/Superadmin: todos) também é decidido lá.
 */
export function PopsManager() {
  const { token, loading: authLoading } = useAuth();
  const { participante } = useCurrentParticipante();
  const { toast } = useToast();

  const [rows, setRows] = useState<Pop[]>([]);
  const [loading, setLoading] = useState(true);
  const [estado, setEstado] = useState<EstadoVersaoPop | null>(null);
  const [showCriar, setShowCriar] = useState(false);
  const [setores, setSetores] = useState<PopsSetor[]>([]);
  const [designaveis, setDesignaveis] = useState<PopDesignavel[]>([]);

  const fetchRows = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch("/api/pops", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setRows(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar POPs", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  const fetchApoio = useCallback(async () => {
    if (!token) return;
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [resSetores, resDesignaveis] = await Promise.all([
        fetch("/api/pops/setores/meus", { headers }),
        fetch("/api/pops/designaveis", { headers }),
      ]);
      if (resSetores.ok) setSetores(await resSetores.json());
      if (resDesignaveis.ok) setDesignaveis(await resDesignaveis.json());
      if (!resSetores.ok || !resDesignaveis.ok) {
        toast("Erro ao carregar dados do formulário de POP", "error");
      }
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar dados do formulário de POP", "error");
    }
  }, [token, toast]);

  useEffect(() => {
    if (!authLoading && token) {
      fetchRows();
      fetchApoio();
    }
  }, [authLoading, token, fetchRows, fetchApoio]);

  const nomePorId = useMemo(() => {
    const mapa = new Map<string, string>();
    designaveis.forEach((d) => mapa.set(d.id, d.nome_completo || d.id));
    return mapa;
  }, [designaveis]);

  const visiveis = estado ? rows.filter((r) => r.versao?.estado === estado) : rows;

  // Preview/download do documento preliminar (PDF institucional, issue #86).
  // O endpoint exige Bearer token — buscamos o blob e abrimos/baixamos local,
  // preservando o nome travado do DRF que vem no Content-Disposition.
  const fetchDocumento = useCallback(
    async (pop: Pop, download: boolean): Promise<{ blob: Blob; filename: string } | null> => {
      if (!token) return null;
      try {
        const res = await fetch(`/api/pops/${pop.id}/documento${download ? "?download=1" : ""}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        const match = (res.headers.get("content-disposition") || "").match(/filename="([^"]+)"/);
        return { blob, filename: match?.[1] || `${pop.codigo}.pdf` };
      } catch (e) {
        console.error(e);
        toast("Erro ao gerar o PDF do POP", "error");
        return null;
      }
    },
    [token, toast]
  );

  async function handlePreviewPdf(pop: Pop) {
    const doc = await fetchDocumento(pop, false);
    if (!doc) return;
    const url = URL.createObjectURL(doc.blob);
    window.open(url, "_blank");
    // Revogação adiada: o viewer da aba nova precisa da URL durante o load.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  async function handleDownloadPdf(pop: Pop) {
    const doc = await fetchDocumento(pop, true);
    if (!doc) return;
    const url = URL.createObjectURL(doc.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = doc.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  const columns: Column<Pop>[] = [
    {
      key: "codigo",
      header: "Código",
      width: "150px",
      render: (r) => (
        <span className="inline-flex px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-semibold whitespace-nowrap">
          {r.codigo}
        </span>
      ),
    },
    {
      key: "nome",
      header: "Nome",
      render: (r) => <span className="font-medium text-text">{r.nome}</span>,
    },
    {
      key: "setor",
      header: "Setor",
      width: "120px",
      render: (r) => <span className="text-sm text-text-secondary">{r.setor_sigla || "—"}</span>,
    },
    {
      key: "criticidade",
      header: "Criticidade",
      width: "120px",
      render: (r) => (
        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold ${CRITICIDADE_BADGE[r.criticidade]}`}>
          {CRITICIDADE_POP_LABELS[r.criticidade]}
        </span>
      ),
    },
    {
      key: "estado",
      header: "Estado",
      width: "150px",
      render: (r) =>
        r.versao ? (
          <span className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold ${ESTADO_BADGE[r.versao.estado]}`}>
            v{r.versao.numero_versao} · {ESTADO_VERSAO_POP_LABELS[r.versao.estado]}
          </span>
        ) : (
          <span className="text-xs text-text-secondary">—</span>
        ),
    },
    {
      key: "elaborador",
      header: "Elaborador",
      width: "180px",
      render: (r) => (
        <span className="text-sm text-text-secondary">{nomePorId.get(r.elaborador_id) || r.elaborador_id}</span>
      ),
    },
    {
      key: "acoes",
      header: "",
      width: "230px",
      // Ações por papel × estado; o backend garante os 403/400 de qualquer
      // forma. Elaborar (issue #83): exclusivo do Elaborador designado com a
      // Versão nas mãos dele. Da Revisão em diante: link da etapa (Revisar/
      // Validar — issue #85; demais leitores do escopo veem a Versão) + o
      // documento preliminar em PDF (issue #86).
      render: (r) => {
        const estado = r.versao?.estado;
        if (participante?.id === r.elaborador_id && (estado === "A_ELABORAR" || estado === "EM_ELABORACAO")) {
          return (
            <Link
              href={`/pops/${r.id}/elaboracao`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-colors whitespace-nowrap"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Elaborar
            </Link>
          );
        }
        if (r.versao && ESTADOS_COM_DOCUMENTO.includes(r.versao.estado)) {
          const minhaEtapa =
            (participante?.id === r.revisor_id && estado === "EM_REVISAO" && "Revisar") ||
            (participante?.id === r.validador_id && estado === "EM_VALIDACAO" && "Validar") ||
            null;
          return (
            <div className="flex items-center gap-1">
              <Link
                href={`/pops/${r.id}/versao`}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap ${
                  minhaEtapa
                    ? "bg-primary/10 text-primary hover:bg-primary/20"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                <BookOpenCheck className="w-3.5 h-3.5" />
                {minhaEtapa ?? "Ver"}
              </Link>
              <button
                onClick={() => handlePreviewPdf(r)}
                title="Ver o documento (PDF)"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-colors whitespace-nowrap"
              >
                <FileText className="w-3.5 h-3.5" />
                PDF
              </button>
              <button
                onClick={() => handleDownloadPdf(r)}
                title="Baixar o PDF"
                className="inline-flex items-center px-2 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        }
        return null;
      },
    },
  ];

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <div>
            <h2 className="text-lg font-bold text-text">POPs do meu escopo</h2>
            <p className="text-xs text-text-secondary">
              Código travado pelo sistema · Versão 1.0 nasce em A Elaborar
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowCriar(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" />
          Criar novo POP
        </button>
      </div>

      {/* Filtro por estado da Versão */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setEstado(null)}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
            estado === null ? "bg-primary text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Todos
        </button>
        {ESTADOS.map((e) => (
          <button
            key={e}
            onClick={() => setEstado(estado === e ? null : e)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
              estado === e ? "bg-primary text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {ESTADO_VERSAO_POP_LABELS[e]}
          </button>
        ))}
      </div>

      <DataTable
        data={visiveis}
        loading={loading}
        columns={columns}
        getRowKey={(r) => r.id}
        emptyState={{
          title: estado ? "Nenhum POP neste estado" : "Nenhum POP no seu escopo",
          hint: "Crie um POP pelo formulário institucional — o código é gerado e travado automaticamente.",
        }}
      />

      {showCriar && (
        <CriarPopModal
          setores={setores}
          designaveis={designaveis}
          onClose={() => setShowCriar(false)}
          onCreated={async (pop) => {
            setShowCriar(false);
            toast(`POP ${pop.codigo} criado — Elaborador notificado por email`, "success");
            await fetchRows();
          }}
        />
      )}
    </section>
  );
}

function CriarPopModal({
  setores,
  designaveis,
  onClose,
  onCreated,
}: {
  setores: PopsSetor[];
  designaveis: PopDesignavel[];
  onClose: () => void;
  onCreated: (pop: Pop) => Promise<void>;
}) {
  const { token } = useAuth();
  const { toast } = useToast();

  const [setorId, setSetorId] = useState("");
  const [nome, setNome] = useState("");
  const [nomeEditado, setNomeEditado] = useState(false);
  const [elaboradorId, setElaboradorId] = useState("");
  const [revisorId, setRevisorId] = useState("");
  const [validadorId, setValidadorId] = useState("");
  const [criticidade, setCriticidade] = useState<CriticidadePop | "">("");
  const [periodicidade, setPeriodicidade] = useState<PeriodicidadeRevisaoPop | "">("");
  const [prazoElaboracao, setPrazoElaboracao] = useState(15);
  const [prazoRevisao, setPrazoRevisao] = useState(30);
  const [baseNormativa, setBaseNormativa] = useState("");
  const [saving, setSaving] = useState(false);

  // DRF §3.2: o sistema sugere o nome com base no Setor — editável à vontade.
  function handleSetorChange(id: string) {
    setSetorId(id);
    if (!nomeEditado) {
      const setor = setores.find((s) => s.id === id);
      setNome(setor ? `POP ${setor.nome}` : "");
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !setorId || !nome.trim() || !elaboradorId || !revisorId || !validadorId) return;
    if (!criticidade || !periodicidade) return;
    setSaving(true);
    const res = await fetch("/api/pops", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        setor_id: setorId,
        nome: nome.trim(),
        elaborador_id: elaboradorId,
        revisor_id: revisorId,
        validador_id: validadorId,
        criticidade,
        periodicidade_revisao: periodicidade,
        prazo_elaboracao_dias: prazoElaboracao,
        prazo_revisao_dias: prazoRevisao,
        base_normativa: baseNormativa.trim() || null,
      }),
    });
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro ao criar POP: ${msg}`, "error");
      setSaving(false);
      return;
    }
    await onCreated((await res.json()) as Pop);
  }

  const selectClass =
    "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white";
  const inputClass =
    "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary";
  const labelClass = "block text-sm font-medium text-text mb-1";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-text">Criar novo POP</h3>
            <p className="text-xs text-text-secondary">
              O código HSM_[SIGLA]-[NNN] é gerado pelo sistema e travado para sempre
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Setor</label>
              <select value={setorId} onChange={(e) => handleSetorChange(e.target.value)} className={selectClass} required>
                <option value="">Selecione o Setor</option>
                {setores.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nome} ({s.sigla})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>Criticidade</label>
              <select
                value={criticidade}
                onChange={(e) => setCriticidade(e.target.value as CriticidadePop)}
                className={selectClass}
                required
              >
                <option value="">Selecione</option>
                {(Object.keys(CRITICIDADE_POP_LABELS) as CriticidadePop[]).map((c) => (
                  <option key={c} value={c}>
                    {CRITICIDADE_POP_LABELS[c]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className={labelClass}>Nome do POP</label>
            <input
              value={nome}
              onChange={(e) => {
                setNome(e.target.value);
                setNomeEditado(true);
              }}
              placeholder="Ex.: Higienização das Mãos"
              className={inputClass}
              required
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(
              [
                ["Elaborador", elaboradorId, setElaboradorId],
                ["Revisor", revisorId, setRevisorId],
                ["Validador", validadorId, setValidadorId],
              ] as const
            ).map(([papel, valor, setter]) => (
              <div key={papel}>
                <label className={labelClass}>{papel}</label>
                <select value={valor} onChange={(e) => setter(e.target.value)} className={selectClass} required>
                  <option value="">Selecione</option>
                  {designaveis.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nome_completo || d.id}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className={labelClass}>Prazo de elaboração (dias úteis)</label>
              <input
                type="number"
                min={1}
                max={365}
                value={prazoElaboracao}
                onChange={(e) => setPrazoElaboracao(Number(e.target.value))}
                className={inputClass}
                required
              />
            </div>
            <div>
              <label className={labelClass}>Prazo de revisão (dias)</label>
              <input
                type="number"
                min={1}
                max={365}
                value={prazoRevisao}
                onChange={(e) => setPrazoRevisao(Number(e.target.value))}
                className={inputClass}
                required
              />
            </div>
            <div>
              <label className={labelClass}>Periodicidade de revisão</label>
              <select
                value={periodicidade}
                onChange={(e) => setPeriodicidade(e.target.value as PeriodicidadeRevisaoPop)}
                className={selectClass}
                required
              >
                <option value="">Selecione</option>
                {(Object.keys(PERIODICIDADE_REVISAO_POP_LABELS) as PeriodicidadeRevisaoPop[]).map((p) => (
                  <option key={p} value={p}>
                    {PERIODICIDADE_REVISAO_POP_LABELS[p]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className={labelClass}>Base normativa (opcional)</label>
            <input
              value={baseNormativa}
              onChange={(e) => setBaseNormativa(e.target.value)}
              placeholder="Ex.: RDC 63/2011, Manual ONA"
              className={inputClass}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all disabled:opacity-60"
            >
              {saving ? "Criando…" : "Criar POP"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
    return res.statusText;
  } catch {
    return res.statusText;
  }
}
