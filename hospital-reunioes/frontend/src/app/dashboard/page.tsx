"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { fetchParticipantesAtivos } from "@/lib/participantes";
import KpiCards from "@/components/dashboard/KpiCards";
import DashboardFilters from "@/components/dashboard/DashboardFilters";
import StatusPieChart from "@/components/dashboard/StatusPieChart";
import SetorBarChart from "@/components/dashboard/SetorBarChart";
import type { SetorBarEntry } from "@/components/dashboard/SetorBarChart";
import type { PieEntry } from "@/components/dashboard/StatusPieChart";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Stats {
  atasParadas: number;
  aguardamAssinatura: number;
  atrasadas: number;
  vencemEm3Dias: number;
  conformidade: number; // 0-100
  totalPendencias: number;
}

interface PendenciaRaw {
  id_acao: string;
  responsavel_id?: string;
  status: string;
  prazo?: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Pendente: "#FFC067",      // Pastel Orange
  "Em Progresso": "#7CC2F2",// Pastel Blue
  Concluído: "#88D7A4",     // Pastel Green
  Atrasado: "#FC9D9D",      // Pastel Red
  Repactuada: "#C4B5FD",   // Pastel Purple
};

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();

  const [stats, setStats] = useState<Stats | null>(null);
  const [nome, setNome] = useState("Usuário");
  const [loading, setLoading] = useState(false);
  const [participantes, setParticipantes] = useState<
    { id: string; nome_completo: string; setor?: string }[]
  >([]);
  const [userRole, setUserRole] = useState<string>("");
  const [token, setToken] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Filtros (arrays para multisseleção)
  const [filtroResponsaveis, setFiltroResponsaveis] = useState<string[]>([]);
  const [filtroPrazoDe, setFiltroPrazoDe] = useState<string>("");
  const [filtroPrazoAte, setFiltroPrazoAte] = useState<string>("");
  const [filtroSetores, setFiltroSetores] = useState<string[]>([]);

  // Lista de setores
  const [listaSetores, setListaSetores] = useState<string[]>([]);

  // Dados dos gráficos
  const [pieStats, setPieStats] = useState<PieEntry[]>([]);
  const [allPendencias, setAllPendencias] = useState<PendenciaRaw[]>([]);
  const [loadingCharts, setLoadingCharts] = useState(false);

  // Debounce ref
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialLoadDone = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const supabase = createClient();
    // Usa ref (sobrevive ao double-effect do React StrictMode em dev) para
    // evitar que fetchAllData dispare duas vezes quando o listener
    // onAuthStateChange e o getSession() inicial chegam juntos.

    async function init(sessionToken: string, userId: string) {
      setToken(sessionToken);

      // Busca role em background — não bloqueia o fetchAllData inicial
      supabase
        .from("participantes")
        .select("role")
        .eq("auth_user_id", userId)
        .single()
        .then(({ data }) => setUserRole(data?.role || "coordenador"));

      fetchParticipantesAtivos<{ id: string; nome_completo: string; setor?: string }>(sessionToken)
        .then(setParticipantes)
        .catch((e) => console.error("Erro ao carregar participantes:", e));

      fetch(`/api/participantes/setores`, {
        headers: { Authorization: `Bearer ${sessionToken}` },
      })
        .then((res) => res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`)))
        .then((data) => {
          if (Array.isArray(data)) setListaSetores(data);
        })
        .catch((e) => console.error("Erro ao carregar setores:", e));

      return sessionToken;
    }

    // Listener para capturar sessão que pode chegar depois do redirect OAuth
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if ((event === "SIGNED_IN" || event === "TOKEN_REFRESHED") && session?.access_token && !initialLoadDone.current) {
          initialLoadDone.current = true;
          const meta = session.user.user_metadata as Record<string, unknown>;
          setNome(
            (meta?.nome as string) ||
              session.user.email?.split("@")[0] ||
              "Usuário"
          );
          const tk = await init(session.access_token, session.user.id);
          fetchAllData(tk);
        }
      }
    );

    // Tenta inicializar com a sessão atual
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.access_token && !initialLoadDone.current) {
        initialLoadDone.current = true;
        const meta = session.user.user_metadata as Record<string, unknown>;
        setNome(
          (meta?.nome as string) ||
            session.user.email?.split("@")[0] ||
            "Usuário"
        );
        const tk = await init(session.access_token, session.user.id);
        fetchAllData(tk);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Constrói params de query com suporte a múltiplos valores (CSV)
  function buildParams() {
    const params = new URLSearchParams();
    if (filtroResponsaveis.length > 0) params.append("responsavel_id", filtroResponsaveis.join(","));
    if (filtroPrazoDe) params.append("prazo_de", filtroPrazoDe);
    if (filtroPrazoAte) params.append("prazo_ate", filtroPrazoAte);
    if (filtroSetores.length > 0) params.append("setor", filtroSetores.join(","));
    return params;
  }

  const fetchAllData = useCallback(
    async (tk?: string) => {
      const accessToken = tk ?? token;
      if (!accessToken) return;

      setLoadingCharts(true);
      setLoading(true);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        };

        const params = buildParams();
        const queryStr = params.toString() ? `?${params.toString()}` : "";

        const [reunioesRes, statsRes, pendenciasRes] = await Promise.all([
          fetch(`/api/reunioes?limit=200`, { headers }),
          fetch(`/api/pendencias/stats${queryStr}`, { headers }),
          fetch(
            `/api/pendencias?limit=200${queryStr ? "&" + params.toString() : ""}`,
            { headers }
          ),
        ]);

        const reunioes = reunioesRes.ok ? await reunioesRes.json() : [];
        const pStats = statsRes.ok ? await statsRes.json() : {};
        const pendencias: PendenciaRaw[] = pendenciasRes.ok
          ? await pendenciasRes.json()
          : [];

        // Apply setor filter client-side — the reunioes endpoint doesn't support filter params
        const filteredReunioes =
          filtroSetores.length > 0
            ? reunioes.filter(
                (r: { setor?: string }) =>
                  r.setor && filtroSetores.includes(r.setor)
              )
            : reunioes;

        // KPI stats
        // todayLocal: for prazo comparisons (date-only strings, interpreted as local midnight)
        const todayLocal = new Date();
        todayLocal.setHours(0, 0, 0, 0);

        // nowUTC / threeDaysAgoUTC: for updated_at comparisons (UTC ISO-8601 timestamps)
        const nowUTC = new Date();
        nowUTC.setUTCHours(0, 0, 0, 0);
        const threeDaysAgoUTC = new Date(nowUTC);
        threeDaysAgoUTC.setUTCDate(threeDaysAgoUTC.getUTCDate() - 3);

        // Atas paradas: status intermediário e sem atualização há >3 dias
        const atasParadas = filteredReunioes.filter(
          (r: { status_ata: string; updated_at?: string }) => {
            if (
              r.status_ata !== "AGUARDANDO_VALIDACAO" &&
              r.status_ata !== "PROCESSANDO"
            )
              return false;
            if (!r.updated_at) return true; // sem updated_at = conservador, conta como parada
            return new Date(r.updated_at) < threeDaysAgoUTC;
          }
        ).length;

        // Atas aguardando assinatura
        const aguardamAssinatura = filteredReunioes.filter(
          (r: { status_ata: string }) =>
            r.status_ata === "AGUARDANDO_ASSINATURA"
        ).length;

        // Pendências atrasadas
        const atrasadas = pStats.atrasado ?? 0;

        // Pendências que vencem em 3 dias (PENDENTE com prazo entre hoje e hoje+3)
        const vencemEm3Dias = pendencias.filter((p) => {
          if (p.status !== "PENDENTE" || !p.prazo) return false;
          const prazoDate = new Date(p.prazo + "T00:00:00");
          const diffDays = Math.ceil(
            (prazoDate.getTime() - todayLocal.getTime()) / (1000 * 60 * 60 * 24)
          );
          return diffDays >= 0 && diffDays <= 3;
        }).length;

        // Conformidade: % de pendências ativas que NÃO estão atrasadas
        const totalAtivas =
          (pStats.pendente ?? 0) +
          (pStats.em_progresso ?? 0) +
          (pStats.atrasado ?? 0);
        const conformidade =
          totalAtivas > 0
            ? Math.round(((totalAtivas - atrasadas) / totalAtivas) * 100)
            : 100;

        setStats({
          atasParadas,
          aguardamAssinatura,
          atrasadas,
          vencemEm3Dias,
          conformidade,
          totalPendencias: totalAtivas,
        });

        // Pie stats
        const pieData: PieEntry[] = [
          { name: "Pendente", value: pStats.pendente ?? 0, color: STATUS_COLORS.Pendente },
          {
            name: "Em Progresso",
            value: pStats.em_progresso ?? 0,
            color: STATUS_COLORS["Em Progresso"],
          },
          {
            name: "Concluído",
            value: pStats.concluido ?? 0,
            color: STATUS_COLORS.Concluído,
          },
          { name: "Atrasado", value: pStats.atrasado ?? 0, color: STATUS_COLORS.Atrasado },
          { name: "Repactuada", value: pStats.repactuada ?? 0, color: STATUS_COLORS.Repactuada },
        ].filter((item) => item.value > 0);

        setPieStats(pieData);
        setAllPendencias(pendencias);
      } catch (e) {
        console.error("Erro ao carregar dashboard:", e);
      } finally {
        setLoading(false);
        setLoadingCharts(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      filtroResponsaveis,
      filtroPrazoDe,
      filtroPrazoAte,
      filtroSetores,

      token,
      userRole,
    ]
  );

  // Refetch com debounce ao mudar filtros (pula o primeiro trigger do token inicial)
  useEffect(() => {
    if (!token) return;
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchAllData();
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [
    filtroResponsaveis,
    filtroPrazoDe,
    filtroPrazoAte,
    filtroSetores,
    token,
    fetchAllData,
  ]);

  // ─── Dados derivados para os gráficos ──────────────────────────────────────

  // Gráfico 2: Pendências por Setor (stacked bar horizontal)
  const setorBarData = useMemo<SetorBarEntry[]>(() => {
    const map: Record<string, SetorBarEntry> = {};

    allPendencias.forEach((p) => {
      const part = participantes.find((pt) => pt.id === p.responsavel_id);
      const setor = part?.setor || "Sem Setor";

      if (!map[setor]) {
        map[setor] = {
          setor,
          Pendente: 0,
          "Em Progresso": 0,
          Concluído: 0,
          Atrasado: 0,
          Repactuada: 0,
        };
      }

      if (p.status === "PENDENTE") map[setor].Pendente++;
      else if (p.status === "EM_PROGRESSO") map[setor]["Em Progresso"]++;
      else if (p.status === "CONCLUIDO") map[setor].Concluído++;
      else if (p.status === "ATRASADO") map[setor].Atrasado++;
      else if (p.status === "REPACTUADA") map[setor].Repactuada++;
    });

    return Object.values(map).sort(
      (a, b) =>
        b.Pendente +
        b["Em Progresso"] +
        b.Atrasado -
        (a.Pendente + a["Em Progresso"] + a.Atrasado)
    );
  }, [allPendencias, participantes]);

  // ─── Navigation helper ────────────────────────────────────────────────────

  const today = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  function navigateToPendencias(
    statusParam: string | null,
    overrides?: { setor?: string; responsavel_id?: string }
  ) {
    if (!statusParam && !overrides?.responsavel_id) return;

    const params = new URLSearchParams();
    if (statusParam === "CRITICAS") {
      params.append("criticas", "true");
    } else if (statusParam) {
      params.append("status", statusParam);
    }

    if (overrides?.responsavel_id) {
      params.append("responsavel", overrides.responsavel_id);
    } else if (filtroResponsaveis.length > 0) {
      params.append("responsavel", filtroResponsaveis.join(","));
    }

    if (overrides?.setor) {
      params.append("setor", overrides.setor);
    } else if (filtroSetores.length > 0) {
      params.append("setor", filtroSetores.join(","));
    }

    if (filtroPrazoDe) params.append("prazo_de", filtroPrazoDe);
    if (filtroPrazoAte) params.append("prazo_ate", filtroPrazoAte);

    router.push(`/pendencias?${params.toString()}`);
  }

  // Opções do MultiSelect responsável filtradas por setores selecionados
  const participantesFiltrados = useMemo(
    () =>
      participantes.filter(
        (p) =>
          filtroSetores.length === 0 ||
          (p.setor && filtroSetores.includes(p.setor))
      ),
    [participantes, filtroSetores]
  );

  const setoresOptions = useMemo(
    () => listaSetores.map((s) => ({ value: s, label: s })),
    [listaSetores]
  );

  const responsavelOptions = useMemo(
    () =>
      participantesFiltrados.map((p) => ({
        value: p.id,
        label: p.nome_completo,
      })),
    [participantesFiltrados]
  );

  return (
    <div className="max-w-7xl mx-auto animate-fade-in-up pb-10">
      {/* Welcome */}
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-text">Olá, {nome}</h1>
          <p className="text-text-secondary mt-1 capitalize">
            {mounted ? today : ""}
          </p>
        </div>
      </div>

      {/* Alert Cards */}
      <KpiCards
        stats={stats}
        loading={loading}
        onNavigate={(href) => router.push(href)}
      />

      {/* Filtros Dinâmicos */}
      <DashboardFilters
        filtroSetores={filtroSetores}
        filtroResponsaveis={filtroResponsaveis}
        filtroPrazoDe={filtroPrazoDe}
        filtroPrazoAte={filtroPrazoAte}
        userRole={userRole}
        setoresOptions={setoresOptions}
        responsavelOptions={responsavelOptions}
        onSetFiltroSetores={setFiltroSetores}
        onSetFiltroResponsaveis={setFiltroResponsaveis}
        onSetFiltroPrazoDe={setFiltroPrazoDe}
        onSetFiltroPrazoAte={setFiltroPrazoAte}
        onReset={() => {
          setFiltroResponsaveis([]);
          setFiltroPrazoDe("");
          setFiltroPrazoAte("");
          setFiltroSetores([]);
        }}
      />

      {/* Chart Grid 2x2 — Layout A */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Donut — Status das Pendências */}
        <StatusPieChart
          data={pieStats}
          loading={loadingCharts}
          onSliceClick={(statusEnum) => navigateToPendencias(statusEnum)}
        />

        {/* 2. Stacked Bar Horizontal — Pendências por Setor */}
        <SetorBarChart
          data={setorBarData}
          loading={loadingCharts}
          onBarClick={(statusEnum, setor) =>
            navigateToPendencias(statusEnum, { setor })
          }
        />
      </div>
    </div>
  );
}
