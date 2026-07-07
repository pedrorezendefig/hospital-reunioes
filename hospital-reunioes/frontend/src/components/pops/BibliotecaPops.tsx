"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileText, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { DataTable, type Column } from "@/components/admin/DataTable";
import {
  CRITICIDADE_POP_LABELS,
  PERIODICIDADE_REVISAO_POP_LABELS,
  type CriticidadePop,
  type PeriodicidadeRevisaoPop,
} from "@/types";

export type BibliotecaItem = {
  pop_id: string;
  codigo: string;
  nome: string;
  setor_id: string;
  setor_nome: string | null;
  setor_sigla: string | null;
  numero_versao: string;
  criticidade: CriticidadePop;
  periodicidade_revisao: PeriodicidadeRevisaoPop;
  elaborador_nome: string | null;
  revisor_nome: string | null;
  validador_nome: string | null;
  criado_em: string | null;
  elaboracao_concluida_em: string | null;
  revisao_aprovada_em: string | null;
  validacao_aprovada_em: string | null;
  publicado_em: string | null;
};

function formatarData(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "-" : d.toLocaleDateString("pt-BR");
}

/**
 * Biblioteca (issue #87): o repositório oficial dos POPs com Versão
 * Publicada, organizado por Setor — código, nome, versão vigente, ficha com
 * as datas de cada etapa e responsáveis, e download do PDF assinado. O
 * escopo (Coordenador: seu Setor; Gerente: seus Setores; Gestor de
 * Qualidade/Superadmin: todos) é decidido pelo backend.
 */
export function BibliotecaPops() {
  const { token } = useAuth();
  const { toast } = useToast();

  const [itens, setItens] = useState<BibliotecaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [ficha, setFicha] = useState<BibliotecaItem | null>(null);

  const fetchItens = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch("/api/pops/biblioteca", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(await res.text());
      setItens(await res.json());
    } catch (e) {
      console.error(e);
      toast("Erro ao carregar a Biblioteca", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    void fetchItens();
  }, [fetchItens]);

  // Download do PDF ASSINADO — mesmo endpoint do documento (o backend serve
  // o arquivo do storage para PUBLICADO), mesmo padrão blob do PopsManager.
  const handleDownload = useCallback(
    async (item: BibliotecaItem) => {
      if (!token) return;
      try {
        const res = await fetch(`/api/pops/${item.pop_id}/documento?download=1`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        const match = (res.headers.get("content-disposition") || "").match(/filename="([^"]+)"/);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = match?.[1] || `${item.codigo}_ASSINADO.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        console.error(e);
        toast("Erro ao baixar o PDF assinado", "error");
      }
    },
    [token, toast]
  );

  const porSetor = useMemo(() => {
    const grupos = new Map<string, { titulo: string; itens: BibliotecaItem[] }>();
    for (const item of itens) {
      const chave = item.setor_id;
      const titulo = item.setor_nome
        ? `${item.setor_nome}${item.setor_sigla ? ` · ${item.setor_sigla}` : ""}`
        : "Setor não identificado";
      if (!grupos.has(chave)) grupos.set(chave, { titulo, itens: [] });
      grupos.get(chave)!.itens.push(item);
    }
    return [...grupos.values()].sort((a, b) => a.titulo.localeCompare(b.titulo, "pt-BR"));
  }, [itens]);

  const columns: Column<BibliotecaItem>[] = [
    {
      key: "codigo",
      header: "Código",
      width: "150px",
      render: (item) => <span className="font-mono text-xs font-semibold text-text">{item.codigo}</span>,
    },
    { key: "nome", header: "Procedimento" },
    {
      key: "numero_versao",
      header: "Versão",
      width: "90px",
      render: (item) => <span className="text-text-secondary">v{item.numero_versao}</span>,
    },
    {
      key: "criticidade",
      header: "Criticidade",
      width: "110px",
      render: (item) => CRITICIDADE_POP_LABELS[item.criticidade] ?? item.criticidade,
    },
    {
      key: "publicado_em",
      header: "Publicado em",
      width: "120px",
      render: (item) => formatarData(item.publicado_em),
    },
  ];

  return (
    <section className="space-y-6">
      {loading || itens.length === 0 ? (
        <DataTable<BibliotecaItem>
          columns={columns}
          data={[]}
          loading={loading}
          emptyState={{
            title: "Nenhum POP publicado ainda",
            hint: "Quando um POP completar o ciclo de assinaturas, ele aparece aqui como a versão oficial do seu Setor.",
          }}
        />
      ) : (
        porSetor.map((grupo) => (
          <div key={grupo.titulo} className="space-y-2">
            <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide px-1">
              {grupo.titulo}
            </h2>
            <DataTable<BibliotecaItem>
              columns={columns}
              data={grupo.itens}
              getRowKey={(item) => item.pop_id}
              onRowClick={(item) => setFicha(item)}
              rowActions={(item) => (
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFicha(item);
                    }}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10"
                    title="Ficha do POP"
                  >
                    <FileText className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDownload(item);
                    }}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10"
                    title="Baixar o PDF assinado"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              )}
            />
          </div>
        ))
      )}

      {ficha && <FichaPopModal item={ficha} onClose={() => setFicha(null)} onDownload={handleDownload} />}
    </section>
  );
}

function FichaPopModal({
  item,
  onClose,
  onDownload,
}: {
  item: BibliotecaItem;
  onClose: () => void;
  onDownload: (item: BibliotecaItem) => Promise<void>;
}) {
  const etapas = [
    { label: "Criação do POP", data: item.criado_em },
    { label: "Elaboração concluída", data: item.elaboracao_concluida_em },
    { label: "Revisão aprovada", data: item.revisao_aprovada_em },
    { label: "Validação aprovada", data: item.validacao_aprovada_em },
    { label: "Publicado (todas as assinaturas)", data: item.publicado_em },
  ];
  const responsaveis = [
    { papel: "Elaborador", nome: item.elaborador_nome },
    { papel: "Revisor", nome: item.revisor_nome },
    { papel: "Validador", nome: item.validador_nome },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px] animate-fade-in"
        aria-hidden="true"
      />
      <div className="relative bg-white rounded-2xl shadow-premium-strong animate-scale-in w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-mono text-xs font-semibold text-text-secondary">{item.codigo}</p>
            <h3 className="text-lg font-bold text-text">{item.nome}</h3>
            <p className="text-xs text-text-secondary">
              {item.setor_nome}
              {item.setor_sigla ? ` · ${item.setor_sigla}` : ""} · v{item.numero_versao} ·{" "}
              {CRITICIDADE_POP_LABELS[item.criticidade] ?? item.criticidade} · Revisão a cada{" "}
              {PERIODICIDADE_REVISAO_POP_LABELS[item.periodicidade_revisao] ?? item.periodicidade_revisao}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-slate-50 rounded-xl border border-slate-100 p-4">
            <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">
              Datas de cada etapa
            </h4>
            <ul className="space-y-2">
              {etapas.map(({ label, data }) => (
                <li key={label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-text-secondary">{label}</span>
                  <span className="font-medium text-text whitespace-nowrap">{formatarData(data)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-slate-50 rounded-xl border border-slate-100 p-4">
            <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">
              Responsáveis
            </h4>
            <ul className="space-y-2">
              {responsaveis.map(({ papel, nome }) => (
                <li key={papel} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-text-secondary">{papel}</span>
                  <span className="font-medium text-text">{nome || "-"}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={() => void onDownload(item)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold hover:opacity-90"
          >
            <Download className="w-4 h-4" />
            Baixar PDF assinado
          </button>
        </div>
      </div>
    </div>
  );
}
