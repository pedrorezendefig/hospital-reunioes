"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, Search } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { DataTable, type Column } from "@/components/admin/DataTable";

/**
 * Espelho da Global Health (ADR 0038), elo 1: as especialidades publicadas na
 * agenda online, ao vivo.
 *
 * Caminho paralelo às tabelas curadas: aqui não se cria, não se edita e nada
 * é gravado. O navegador fala com o backend do app, e só o backend fala com a
 * Global Health (o token da integração nunca chega até aqui).
 *
 * A busca é da própria Global Health (parâmetro `pesquisa`), aplicada ao
 * enviar o campo ou ao clicar em Atualizar, e não um filtro sobre uma cópia
 * velha.
 *
 * Três estados explícitos, porque a honestidade é o valor da tela:
 * carregando, erro (com a mensagem da falha) e vazio com o motivo. Falha da
 * Global Health nunca aparece como lista vazia.
 */

type Especialidade = {
  id: number;
  nome: string;
  bloqueado: boolean;
};

type EspelhoResponse = {
  data: Especialidade[];
  total: number;
  motivo_vazio: string | null;
};

const ENDPOINT = "/api/admin/espelho-global-health/especialidades";

export function EspelhoGlobalHealth() {
  const { token, loading: authLoading } = useAuth();

  const [linhas, setLinhas] = useState<Especialidade[]>([]);
  const [motivoVazio, setMotivoVazio] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  // O termo que foi de fato para a Global Health (o campo digitado só vale
  // depois de enviado).
  const [buscaAplicada, setBuscaAplicada] = useState("");
  // Incrementado a cada envio: mesmo com o termo igual, o clique em Atualizar
  // busca a resposta fresca.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (authLoading || !token) return;
    let cancelled = false;
    setLoading(true);
    setErro(null);
    (async () => {
      try {
        const url = buscaAplicada
          ? `${ENDPOINT}?pesquisa=${encodeURIComponent(buscaAplicada)}`
          : ENDPOINT;
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (!res.ok) {
          setLinhas([]);
          setMotivoVazio(null);
          setErro(mensagemDeErro(body, res.statusText));
          return;
        }
        const dados = body as EspelhoResponse;
        setLinhas(dados.data ?? []);
        setMotivoVazio(dados.motivo_vazio ?? null);
      } catch {
        if (cancelled) return;
        setLinhas([]);
        setMotivoVazio(null);
        setErro(
          "Não foi possível falar com o servidor para consultar a Global Health.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, token, buscaAplicada, reloadKey]);

  function atualizar(evento?: React.FormEvent) {
    evento?.preventDefault();
    setBuscaAplicada(busca.trim());
    setReloadKey((k) => k + 1);
  }

  // Cada vazio diz por que está vazio: falha na consulta, busca sem resultado
  // ou agenda sem nada publicado (o motivo vem do backend).
  const estadoVazio = erro
    ? {
        title: "Nada a mostrar enquanto a consulta falhar",
        hint: "Clique em Atualizar para tentar de novo.",
      }
    : buscaAplicada
      ? {
          title: `Nenhuma especialidade publicada com "${buscaAplicada}" no nome`,
          hint: "Limpe a busca e atualize para ver tudo o que a agenda publica.",
        }
      : {
          title: motivoVazio ?? "Nenhuma especialidade encontrada",
          hint: "Publique a especialidade no Painel de Controle da Global Health para ela aparecer aqui.",
        };

  const columns: Column<Especialidade>[] = [
    {
      key: "id",
      header: "ID na Global Health",
      width: "160px",
      render: (linha) => (
        <span className="font-mono text-xs text-slate-500">{linha.id}</span>
      ),
    },
    {
      key: "nome",
      header: "Especialidade",
      render: (linha) => <span className="text-text">{linha.nome ?? "-"}</span>,
    },
    {
      key: "bloqueado",
      header: "Situação",
      width: "150px",
      render: (linha) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
            linha.bloqueado
              ? "bg-amber-50 text-amber-700"
              : "bg-emerald-50 text-emerald-600"
          }`}
        >
          {linha.bloqueado ? "Bloqueada" : "Publicada"}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        O que a agenda online da Global Health publica agora. Esta seção é uma
        janela, não um caderno: nada fica gravado, e cada clique em Atualizar
        busca a resposta fresca.
      </p>

      {erro && (
        <div
          role="alert"
          className="flex items-start gap-3 p-4 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700"
        >
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">
              A consulta à Global Health falhou. A lista está vazia por causa da
              falha, não por falta de especialidade publicada.
            </p>
            <p className="mt-1">{erro}</p>
          </div>
        </div>
      )}

      <DataTable
        data={erro ? [] : linhas}
        loading={loading || authLoading}
        columns={columns}
        getRowKey={(linha) => String(linha.id)}
        emptyState={estadoVazio}
        toolbar={
          <form
            onSubmit={atualizar}
            className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-center"
          >
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar especialidade na agenda..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-border bg-white text-text-secondary hover:bg-primary/5 hover:text-text transition-colors disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw
                className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
              />
              Atualizar
            </button>
          </form>
        }
      />
    </div>
  );
}

function mensagemDeErro(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return fallback || "Falha desconhecida ao consultar a Global Health.";
}
