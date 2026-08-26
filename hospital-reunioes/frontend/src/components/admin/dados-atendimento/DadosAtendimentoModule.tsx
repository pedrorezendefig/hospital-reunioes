"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  ArchiveRestore,
  HeartPulse,
  Pencil,
  Plus,
  Search,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSecretaria, isSuperAdmin } from "@/lib/auth";
import { useToast } from "@/components/ui/Toast";
import { Select } from "@/components/ui/Select";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { RegistroFormModal } from "./RegistroFormModal";
import { EspelhoGlobalHealth } from "./EspelhoGlobalHealth";
import { TABELAS, type Registro, type TabelaSpec } from "./config";

type AtivoFilter = "todos" | "ativos" | "desativados";

type ListResponse = {
  data: Registro[];
  total: number;
  ultima_atualizacao: string | null;
};

const MOEDA = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

function formatarData(iso: string | null): string {
  if (!iso) return "-";
  const [ano, mes, dia] = iso.split("-");
  if (!ano || !mes || !dia) return iso;
  return `${dia}/${mes}/${ano}`;
}

/**
 * Módulo Dados do Atendimento (ADR 0031): as quatro tabelas de valores que
 * alimentam a Ana, em abas. Super admin e secretária editam; facilitador lê.
 * A edição vale imediatamente para a Ana (sem cache).
 */
export function DadosAtendimentoModule() {
  const { token, loading: authLoading } = useAuth();
  const { participante } = useCurrentParticipante();
  const { toast } = useToast();

  const [spec, setSpec] = useState<TabelaSpec>(TABELAS[0]);
  // O Espelho da Global Health (ADR 0038) é uma opção ao lado das tabelas
  // curadas, fora da factory: leitura ao vivo da agenda, sem CRUD.
  const [espelhoAberto, setEspelhoAberto] = useState(false);
  const [rows, setRows] = useState<Registro[]>([]);
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [ativoFilter, setAtivoFilter] = useState<AtivoFilter>("ativos");

  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<Registro | null>(null);

  // Mesmos helpers do backend (access_profile primeiro, flag legada como
  // fallback): frontend e backend concordam sobre quem edita.
  const podeEditar = isSuperAdmin(participante) || isSecretaria(participante);

  // Incrementado após cada escrita para recarregar a listagem.
  const [reloadKey, setReloadKey] = useState(0);

  const endpoint = `/api/admin/dados-atendimento/${spec.slug}`;

  // Guard de resposta velha (`cancelled`): trocar de aba dispara um fetch
  // novo e a resposta atrasada da aba anterior não pode vencer a atual.
  useEffect(() => {
    if (authLoading || !token) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await fetch(endpoint, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(await res.text());
        const body: ListResponse = await res.json();
        if (cancelled) return;
        setRows(body.data);
        setUltimaAtualizacao(body.ultima_atualizacao);
      } catch (e) {
        if (cancelled) return;
        console.error(e);
        toast("Erro ao carregar a tabela", "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, token, endpoint, reloadKey, toast]);

  const visiveis = useMemo(() => {
    let filtradas = rows;
    if (ativoFilter === "ativos") filtradas = filtradas.filter((r) => r.ativo);
    if (ativoFilter === "desativados")
      filtradas = filtradas.filter((r) => !r.ativo);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      filtradas = filtradas.filter((r) =>
        spec.colunas.some((c) =>
          String(r[c.key] ?? "")
            .toLowerCase()
            .includes(needle),
        ),
      );
    }
    return filtradas;
  }, [rows, ativoFilter, q, spec]);

  async function enviar(
    metodo: "POST" | "PATCH",
    url: string,
    payload: Record<string, unknown>,
    mensagemOk: string,
  ): Promise<boolean> {
    if (!token) return false;
    const res = await fetch(url, {
      method: metodo,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const msg = await parseErrorMessage(res);
      toast(`Erro: ${msg}`, "error");
      return false;
    }
    toast(mensagemOk, "success");
    setReloadKey((k) => k + 1);
    return true;
  }

  async function handleCreate(payload: Record<string, unknown>) {
    const ok = await enviar(
      "POST",
      endpoint,
      payload,
      `${spec.artigo === "a" ? "Nova" : "Novo"} ${spec.itemNoun} ${
        spec.artigo === "a" ? "criada" : "criado"
      }`,
    );
    if (ok) setShowCreate(false);
    return ok;
  }

  async function handleEdit(payload: Record<string, unknown>) {
    if (!editTarget) return false;
    const ok = await enviar(
      "PATCH",
      `${endpoint}/${editTarget.id}`,
      payload,
      "Registro atualizado",
    );
    if (ok) setEditTarget(null);
    return ok;
  }

  async function handleToggleAtivo(row: Registro) {
    const acao = row.ativo ? "desativar" : "reativar";
    const rotulo = String(row[spec.colunas[0].key] ?? spec.itemNoun);
    if (!confirm(`Tem certeza que deseja ${acao} "${rotulo}"?`)) return;
    await enviar(
      "PATCH",
      `${endpoint}/${row.id}`,
      { ativo: !row.ativo },
      row.ativo
        ? "Registro desativado; sai da resposta da Ana"
        : "Registro reativado",
    );
  }

  const columns: Column<Registro>[] = [
    ...spec.colunas.map(
      (c): Column<Registro> => ({
        key: c.key,
        header: c.header,
        width: c.width,
        render: (r) => {
          const valor = r[c.key];
          if (c.formato === "moeda")
            return (
              <span className="font-medium text-text">
                {typeof valor === "number" ? MOEDA.format(valor) : "-"}
              </span>
            );
          if (c.formato === "simnao")
            return (
              <span className="text-slate-600">{valor ? "Sim" : "Não"}</span>
            );
          return <span className="text-text">{String(valor ?? "-")}</span>;
        },
      }),
    ),
    {
      key: "ativo",
      header: "Status",
      width: "120px",
      render: (r) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
            r.ativo
              ? "bg-emerald-50 text-emerald-600"
              : "bg-slate-100 text-slate-500"
          }`}
        >
          {r.ativo ? "Ativo" : "Desativado"}
        </span>
      ),
    },
    {
      key: "ultima_atualizacao",
      header: "Atualizado",
      width: "120px",
      render: (r) => (
        <span className="text-slate-500 text-xs">
          {formatarData(r.ultima_atualizacao)}
        </span>
      ),
    },
  ];

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10 text-primary">
            <HeartPulse className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">
              Dados do Atendimento
            </h1>
            <p className="text-sm text-text-secondary">
              Tabelas de valores que alimentam a Ana. Editou, valeu: a resposta
              seguinte já usa o dado novo.
            </p>
          </div>
        </div>
        {podeEditar && !espelhoAberto && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
          >
            <Plus className="w-4 h-4" />
            {spec.artigo === "a" ? "Nova" : "Novo"} {spec.itemNoun}
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {TABELAS.map((t) => (
          <button
            key={t.slug}
            onClick={() => {
              setSpec(t);
              setQ("");
              setEspelhoAberto(false);
              // Zera a listagem na troca de aba: linha da tabela anterior
              // nunca renderiza (nem recebe ação) sob as colunas da nova.
              setRows([]);
              setUltimaAtualizacao(null);
            }}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer ${
              !espelhoAberto && t.slug === spec.slug
                ? "bg-primary/10 text-primary border border-primary/30"
                : "bg-white text-text-secondary border border-border hover:bg-primary/5 hover:text-text"
            }`}
          >
            {t.titulo}
          </button>
        ))}
        <button
          onClick={() => setEspelhoAberto(true)}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer ${
            espelhoAberto
              ? "bg-primary/10 text-primary border border-primary/30"
              : "bg-white text-text-secondary border border-border hover:bg-primary/5 hover:text-text"
          }`}
        >
          Espelho da Global Health
        </button>
      </div>

      {espelhoAberto ? (
        <EspelhoGlobalHealth />
      ) : (
        <DataTable
          data={visiveis}
          loading={loading || authLoading}
          columns={columns}
          getRowKey={(r) => r.id}
          emptyState={{
            title: `Nenhum registro de ${spec.titulo.toLowerCase()} encontrado`,
            hint: podeEditar
              ? "Ajuste os filtros ou crie um novo registro."
              : "Ajuste os filtros.",
          }}
          toolbar={
            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-center">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder={`Buscar em ${spec.titulo.toLowerCase()}...`}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
                />
              </div>
              <Select
                value={ativoFilter}
                onChange={(v) => setAtivoFilter(v as AtivoFilter)}
                options={[
                  { value: "ativos", label: "Apenas ativos" },
                  { value: "desativados", label: "Apenas desativados" },
                  { value: "todos", label: "Todos" },
                ]}
              />
              <span className="text-xs text-slate-500 whitespace-nowrap">
                Última atualização: {formatarData(ultimaAtualizacao)}
              </span>
            </div>
          }
          rowActions={
            podeEditar
              ? (r) => (
                  <>
                    <button
                      onClick={() => setEditTarget(r)}
                      title="Editar"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleToggleAtivo(r)}
                      title={r.ativo ? "Desativar" : "Reativar"}
                      className={`p-1.5 rounded-lg transition-colors ${
                        r.ativo
                          ? "text-slate-500 hover:text-red-600 hover:bg-red-50"
                          : "text-slate-500 hover:text-emerald-600 hover:bg-emerald-50"
                      }`}
                    >
                      {r.ativo ? (
                        <Archive className="w-4 h-4" />
                      ) : (
                        <ArchiveRestore className="w-4 h-4" />
                      )}
                    </button>
                  </>
                )
              : undefined
          }
        />
      )}

      {showCreate && (
        <RegistroFormModal
          spec={spec}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        />
      )}
      {editTarget && (
        <RegistroFormModal
          spec={spec}
          initial={editTarget}
          onClose={() => setEditTarget(null)}
          onSubmit={handleEdit}
        />
      )}
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
