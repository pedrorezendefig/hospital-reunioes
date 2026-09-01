"use client";

/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319, histórias 11 a 14).
 *
 * O retrato de AGORA para o ouvidor e para a Diretoria: a fila por situação, o
 * que já venceu, o que vence hoje e amanhã, o que cada área deve e os críticos
 * abertos.
 *
 * Duas fontes, sem mistura. As contagens de área vêm do módulo de métricas, a
 * MESMA função que o relatório em PDF consome, e por isso os dois nunca
 * divergem. Os casos com nome vêm da listagem, porque o módulo de métricas não
 * identifica caso nenhum (contrato da issue #341).
 *
 * A regra que rege esta tela inteira: ela nunca afirma o que não sabe. Bloco
 * que não carregou diz que não carregou, e não desenha zero; número em dias
 * úteis calculado sem o calendário sai marcado; perda de acesso apaga o que
 * está na tela em vez de manter a foto antiga.
 *
 * A régua de quem entra em cada bloco mora em `lib/ouvidoria/painel.ts`, com
 * testes próprios. Aqui só há tela.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  CalendarPlus,
  CalendarX,
  Loader2,
  Lock,
  RefreshCw,
  ShieldAlert,
  UserX,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { usePolling } from "@/hooks/usePolling";
import { classeDoStatus, rotuloDoStatus } from "@/lib/ouvidoria/fila";
import { CLASSE_GRAVIDADE, LABEL_GRAVIDADE, type Gravidade } from "@/lib/ouvidoria/validacao";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import {
  areasComVencidas,
  avisosDeDegradacao,
  calendarioUtilFoiLido,
  classificarFalha,
  classificarJanela,
  contarPorStatus,
  criticosAbertos,
  hojeNoHospital,
  intervaloDeAtualizacao,
  LIMITE_DE_PROXIMOS_VENCIMENTOS,
  podeVerPainel,
  precisaDaMarcaDeSigilo,
  proximosVencimentos,
  rotuloDaContagemParcial,
  rotuloDoResponsavel,
  rotuloDoSetor,
  vencendoEm,
  type FalhaDeCarga,
  type PendenciaDeArea,
} from "@/lib/ouvidoria/painel";

interface CasoDaListagem {
  id: string;
  protocolo: string;
  status: StatusManifestacao;
  setor: string;
  resumo: string;
  gravidade: string | null;
  prazo_area_em: string | null;
  prazo_resposta: string;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  sigilo_reforcado: boolean;
}

interface Metricas {
  degradado: string[];
  pendencias_por_area: PendenciaDeArea[];
}

type Leitura<T> = { ok: true; corpo: T } | { ok: false; status: number };

/**
 * Uma leitura, com o resultado em vez da exceção. `status: 0` é a falha que nem
 * chegou a ter resposta (rede, DNS, aba offline).
 *
 * `no-store` nas duas pontas: o corpo carrega protocolo, setor e resumo do
 * relato, e o par se repete a cada minuto. Sem o cabeçalho, a garantia de que
 * nada disso fica guardado no caminho seria comportamento de terceiro, e não
 * decisão do código.
 */
async function ler<T>(url: string, token: string): Promise<Leitura<T>> {
  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, corpo: (await res.json()) as T };
  } catch {
    // Sem o objeto de erro: a mensagem de um JSON malformado carrega um trecho
    // do corpo, e o corpo aqui é a lista de manifestações.
    console.error("Falha ao ler o painel da Ouvidoria.");
    return { ok: false, status: 0 };
  }
}

function formatarHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatarDia(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function EtiquetaDeGravidade({ gravidade }: { gravidade: string | null }) {
  if (!gravidade) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border bg-slate-100 text-slate-500 border-slate-200">
        A classificar
      </span>
    );
  }
  const classe = CLASSE_GRAVIDADE[gravidade as Gravidade] ?? "bg-slate-100 text-slate-600 border-slate-200";
  const label = LABEL_GRAVIDADE[gravidade as Gravidade] ?? gravidade;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${classe}`}>
      {label}
    </span>
  );
}

function LinhaDeCaso({
  caso,
  calendarioConfiavel,
  hoje,
}: {
  caso: CasoDaListagem;
  calendarioConfiavel: boolean;
  hoje: string | null;
}) {
  // O caso ainda na triagem não tem prazo da área, e o que o servidor manda
  // sobre ele fala de um vencimento que não existe: `rotulo_prazo` vem
  // literalmente "sem prazo definido" e `prazo_estourado` vem falso, porque os
  // dois olham `prazo_area_em`. Dentro de um bloco chamado "Já venceu", isso
  // punha a linha cinza dizendo o contrário do título logo acima dela.
  //
  // Quem sabe se esse caso venceu é a mesma régua que decidiu em que bloco ele
  // entrou, e é ela que decide a cor aqui.
  const naTriagem = !caso.prazo_area_em;
  const janela = hoje ? classificarJanela(caso, hoje) : null;
  const venceu = naTriagem ? janela === "vencido" : caso.prazo_estourado;

  // O vencimento persistido pode ser mostrado sempre: é dado, não conta. O
  // rótulo ("vencido há 3 dias úteis") é calculado com a tabela de feriados,
  // que a listagem lê em silêncio e sem avisar quando falha. Sem calendário, a
  // frase sai da tela em vez de sair errada.
  //
  // "Sem confirmação", e não "sem o calendário": a marca cobre dois estados, o
  // de saber que os feriados falharam e o de não ter como saber (métricas fora,
  // que é quem declara o degradado). Afirmar a causa no segundo seria a mesma
  // presunção que este bloco existe para evitar.
  const vencimento = caso.prazo_area_em
    ? formatarHora(caso.prazo_area_em)
    : caso.prazo_resposta
      ? formatarDia(caso.prazo_resposta)
      : null;
  const complemento = naTriagem
    ? " (prazo de referência, ainda sem triagem)"
    : calendarioConfiavel
      ? caso.rotulo_prazo
        ? ` (${caso.rotulo_prazo})`
        : ""
      : " (sem confirmação do calendário)";
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono font-semibold text-slate-800 text-sm">{caso.protocolo}</span>
        {precisaDaMarcaDeSigilo(caso) && (
          <span
            title="Caso sigiloso: não projete nem compartilhe esta tela"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border bg-slate-800 text-white border-slate-800"
          >
            <Lock className="w-3 h-3" />
            Sigiloso
          </span>
        )}
        <EtiquetaDeGravidade gravidade={caso.gravidade} />
        <span className="text-sm text-slate-600">{caso.setor}</span>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${classeDoStatus(caso.status)}`}
        >
          {rotuloDoStatus(caso.status)}
        </span>
        {vencimento && (
          <span
            className={`text-xs ml-auto whitespace-nowrap ${venceu ? "text-red-600 font-semibold" : "text-slate-500"}`}
          >
            {vencimento}
            {complemento}
          </span>
        )}
      </div>
      {caso.resumo && <p className="text-xs text-slate-500 mt-1 line-clamp-2">{caso.resumo}</p>}
    </li>
  );
}

function Bloco({
  titulo,
  ajuda,
  icone,
  destaque,
  children,
}: {
  titulo: string;
  ajuda: string;
  icone: React.ReactNode;
  destaque?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`bg-white rounded-2xl border shadow-premium overflow-hidden ${destaque ? "border-red-200" : "border-border"}`}
    >
      <header
        className={`px-5 py-3 border-b ${destaque ? "bg-red-50 border-red-100" : "bg-slate-50 border-slate-100"}`}
      >
        <h2 className={`flex items-center gap-2 font-bold text-sm ${destaque ? "text-red-700" : "text-slate-800"}`}>
          {icone}
          {titulo}
        </h2>
        <p className={`text-xs mt-0.5 ${destaque ? "text-red-500" : "text-slate-400"}`}>{ajuda}</p>
      </header>
      {children}
    </section>
  );
}

/** Vazio de verdade. Só aparece quando a leitura chegou e não tinha nada. */
function Vazio({ texto }: { texto: string }) {
  return <p className="px-5 py-6 text-sm text-slate-400">{texto}</p>;
}

/**
 * Não carregado. Nunca pode ser confundido com vazio: "nenhum caso crítico
 * aberto" é uma afirmação, e o ouvidor que a lê fecha a aba sem cobrar ninguém.
 */
function NaoCarregou() {
  return (
    <p className="flex items-center gap-2 px-5 py-6 text-sm text-amber-700 bg-amber-50">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      Não foi possível carregar. Este bloco não está dizendo que não há nada.
    </p>
  );
}

/** Um bloco de casos: sabe a diferença entre não ter caso e não ter carregado. */
function BlocoDeCasos({
  titulo,
  ajuda,
  icone,
  destaque,
  casos,
  contagem,
  vazio,
  calendarioConfiavel,
  hoje,
}: {
  titulo: string;
  ajuda: string;
  icone: React.ReactNode;
  destaque?: boolean;
  casos: CasoDaListagem[] | null;
  /**
   * O que vai entre parênteses, para o bloco que mostra menos do que tem. Sem
   * isto o contador seria o tamanho da lista cortada, e nos blocos vizinhos ele
   * é o total: o mesmo parêntese passaria a significar duas coisas na mesma
   * tela.
   */
  contagem?: string;
  vazio: string;
  calendarioConfiavel: boolean;
  hoje: string | null;
}) {
  return (
    <Bloco
      titulo={casos === null ? titulo : `${titulo} (${contagem ?? casos.length})`}
      ajuda={ajuda}
      icone={icone}
      destaque={destaque}
    >
      {casos === null ? (
        <NaoCarregou />
      ) : casos.length === 0 ? (
        <Vazio texto={vazio} />
      ) : (
        <ul className="divide-y divide-slate-50">
          {casos.map((caso) => (
            <LinhaDeCaso
              key={caso.id}
              caso={caso}
              calendarioConfiavel={calendarioConfiavel}
              hoje={hoje}
            />
          ))}
        </ul>
      )}
    </Bloco>
  );
}

function TelaRestrita({ motivo }: { motivo: string }) {
  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto text-center py-16">
      <p className="text-slate-500 font-medium">{motivo}</p>
      <Link href="/ouvidoria" className="inline-block mt-4 text-sm text-primary hover:underline">
        Voltar à Ouvidoria
      </Link>
    </div>
  );
}

export default function PainelEmTempoRealPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeVer = podeVerPainel(participante?.perfil_ouvidoria);

  // `null` significa "não carregado", e é diferente de lista vazia em todo
  // lugar desta tela.
  const [casos, setCasos] = useState<CasoDaListagem[] | null>(null);
  // O que a LISTAGEM não pôde ler, separado do que as métricas não puderam
  // (issue #449). São duas leituras do mesmo calendário, em momentos
  // diferentes: uma pode falhar sozinha, e antes desta marca a listagem falhava
  // em silêncio, com a tela afirmando o prazo em dias úteis de cada caso.
  const [degradadoDosCasos, setDegradadoDosCasos] = useState<string[] | null>(null);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [loading, setLoading] = useState(true);
  const [falha, setFalha] = useState<FalhaDeCarga | null>(null);
  const [semSessao, setSemSessao] = useState(false);
  const [falhasSeguidas, setFalhasSeguidas] = useState(0);
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  const [abaVisivel, setAbaVisivel] = useState(true);
  // O dia civil no fuso do hospital, calculado só depois de montar, para o
  // servidor e o navegador não renderizarem janelas diferentes.
  const [hoje, setHoje] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) {
      // Sessão expirada não pode virar painel zerado e silencioso.
      setSemSessao(true);
      setCasos(null);
      setDegradadoDosCasos(null);
      setMetricas(null);
      return;
    }
    setSemSessao(false);

    const [lidoMetricas, lidoCasos] = await Promise.all([
      ler<Metricas>("/api/ouvidoria/metricas", token),
      ler<{ protocolos: CasoDaListagem[]; degradado?: string[] }>("/api/ouvidoria/protocolos", token),
    ]);

    // Perder o perfil com a tela aberta apaga a tela. O que está nela é
    // protocolo, setor e resumo de manifestação, e o polling manteria a foto
    // antiga no ar por tempo indeterminado (RN-40).
    const perdeuAcesso = [lidoMetricas, lidoCasos].some(
      (lido) => !lido.ok && classificarFalha(lido.status) === "sem_acesso"
    );
    if (perdeuAcesso) {
      setCasos(null);
      setDegradadoDosCasos(null);
      setMetricas(null);
      setAtualizadoEm(null);
      setFalha("sem_acesso");
      return;
    }

    // Cada porta é aplicada por si: a que veio boa não é descartada porque a
    // outra caiu, e a que caiu deixa o bloco dela dizendo que não carregou.
    if (lidoMetricas.ok) {
      setMetricas({
        degradado: lidoMetricas.corpo.degradado ?? [],
        pendencias_por_area: lidoMetricas.corpo.pendencias_por_area ?? [],
      });
    } else {
      setMetricas(null);
    }
    if (lidoCasos.ok) {
      // O dia é relido a cada atualização: painel aberto na virada da
      // meia-noite continuaria chamando de "vence hoje" o que venceu ontem.
      setHoje(hojeNoHospital());
      setCasos(lidoCasos.corpo.protocolos ?? []);
      // Backend uma versao atras nao manda o campo, e "ausente" nao pode virar
      // "nada degradou": sem a marca, nao ha como saber se o calendario foi
      // lido, e a frase em dias uteis sai da tela do mesmo jeito.
      setDegradadoDosCasos(lidoCasos.corpo.degradado ?? null);
    } else {
      setCasos(null);
      setDegradadoDosCasos(null);
    }

    if (lidoMetricas.ok && lidoCasos.ok) {
      setFalha(null);
      setFalhasSeguidas(0);
      setAtualizadoEm(new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }));
    } else {
      setFalha("instavel");
      setFalhasSeguidas((anteriores) => anteriores + 1);
    }
  }, []);

  useEffect(() => {
    setHoje(hojeNoHospital());
  }, []);

  // Painel esquecido aberto numa estação compartilhada não fica repuxando e
  // repintando manifestação a cada minuto.
  //
  // A volta recarrega na hora. O `usePolling` é um `setInterval` sem chamada
  // imediata: sem isto, quem volta para a aba espera um intervalo INTEIRO antes
  // do primeiro tick, e são até dez minutos se a aba foi escondida no meio de
  // uma sequência de falhas. O ouvidor voltaria e olharia a foto de antes.
  useEffect(() => {
    const aoTrocar = () => {
      const visivel = document.visibilityState === "visible";
      setAbaVisivel(visivel);
      if (visivel && podeVer) carregar();
    };
    setAbaVisivel(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", aoTrocar);
    return () => document.removeEventListener("visibilitychange", aoTrocar);
  }, [podeVer, carregar]);

  useEffect(() => {
    if (carregandoPerfil) return;
    if (!podeVer) {
      setLoading(false);
      return;
    }
    carregar().finally(() => setLoading(false));
  }, [carregandoPerfil, podeVer, carregar]);

  usePolling(
    carregar,
    intervaloDeAtualizacao(falhasSeguidas),
    podeVer && !loading && abaVisivel && falha !== "sem_acesso"
  );

  if (carregandoPerfil || loading) {
    return (
      <div className="flex items-center justify-center h-64 gap-2 text-slate-400 text-sm">
        <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
        Carregando o painel...
      </div>
    );
  }

  if (!podeVer) {
    return <TelaRestrita motivo="O painel em tempo real é restrito ao Ouvidor e à Diretoria Executiva." />;
  }

  if (falha === "sem_acesso") {
    return (
      <TelaRestrita motivo="Seu acesso ao painel da Ouvidoria mudou. Fale com a Diretoria Executiva se precisar dele de volta." />
    );
  }

  if (semSessao) {
    return <TelaRestrita motivo="Sua sessão expirou. Entre de novo para abrir o painel." />;
  }

  // `null` é a leitura de métricas que não chegou, e é diferente de "nada
  // degradou": quem declara o degradado é ela.
  const degradado = metricas?.degradado ?? null;
  // As duas leituras do mesmo calendário, juntas: a das métricas e a da
  // listagem. Uma falha sozinha, e qualquer uma delas basta para tirar a frase
  // em dias úteis da tela (issue #449).
  const avisos = avisosDeDegradacao([...new Set([...(degradado ?? []), ...(degradadoDosCasos ?? [])])]);
  // Sem o bloco de métricas não há como saber se o calendário foi lido, e a
  // frase em dias úteis de cada caso sai da tela em vez de sair afirmada.
  const calendarioConfiavel = calendarioUtilFoiLido(degradado) && calendarioUtilFoiLido(degradadoDosCasos);
  const criticos = casos && criticosAbertos(casos);
  const vencidos = casos && hoje ? vencendoEm(casos, "vencido", hoje) : null;
  const vencemHoje = casos && hoje ? vencendoEm(casos, "hoje", hoje) : null;
  const proximos = casos && hoje ? proximosVencimentos(casos, hoje) : null;
  const areas = metricas && areasComVencidas(metricas.pendencias_por_area);
  const fila = casos && contarPorStatus(casos);

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Painel em tempo real</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            A operação da Ouvidoria agora: o que está na fila, o que já venceu, o que vence e o que é
            grave. Os prazos cobrem tanto a resposta da área quanto a triagem da própria Ouvidoria.
          </p>
        </div>
        {atualizadoEm && (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
            <RefreshCw className="w-3.5 h-3.5" />
            Atualizado às {atualizadoEm}
          </span>
        )}
      </div>

      {falha === "instavel" && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Parte do painel não pôde ser atualizada. Os blocos que não carregaram estão marcados; os
            demais podem estar desatualizados. A próxima tentativa vai ficando mais espaçada.
          </span>
        </div>
      )}

      {/* O que o painel deixou de poder afirmar. Sem este aviso, o número sai
          com cara de bom e ninguém tem como desconfiar. */}
      {avisos.length > 0 && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <p className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Parte dos números não pôde ser medida
          </p>
          <ul className="mt-1.5 space-y-1 list-disc list-inside">
            {avisos.map((aviso) => (
              <li key={aviso.leitura}>{aviso.texto}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Fila por status: a mesma ordem e os mesmos rótulos da listagem. */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {(fila ?? contarPorStatus([])).map((linha) => (
          <div key={linha.status} className="bg-white rounded-2xl border border-border shadow-premium px-4 py-3">
            <p className={`text-2xl font-bold ${fila ? "text-slate-900" : "text-slate-300"}`}>
              {fila ? linha.total : "?"}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">{linha.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-5">
        <BlocoDeCasos
          titulo="Críticos abertos"
          ajuda="Risco à vida, à segurança ou à imagem. Sai daqui quando a Ouvidoria encerra, não quando a área responde."
          icone={<ShieldAlert className="w-4 h-4" />}
          destaque
          casos={criticos}
          vazio="Nenhum caso crítico aberto."
          calendarioConfiavel={calendarioConfiavel}
          hoje={hoje}
        />

        <div className="grid gap-5 lg:grid-cols-3">
          <BlocoDeCasos
            titulo="Já venceu"
            // O número é maior que a coluna Vencidas de propósito, e a
            // diferença tem que estar dita aqui: o rodapé que explica os dois
            // universos mora no bloco de áreas, que some quando o /metricas cai.
            ajuda="Prazo rompido e ainda sem resposta, da área ou da triagem da Ouvidoria. Conta mais que a coluna Vencidas lá embaixo, que só olha o caso já entregue à área."
            icone={<CalendarX className="w-4 h-4" />}
            casos={vencidos}
            vazio="Nenhum prazo rompido em aberto."
            calendarioConfiavel={calendarioConfiavel}
            hoje={hoje}
          />
          <BlocoDeCasos
            titulo="Vence hoje"
            ajuda="Termina hoje e ainda não rompeu. Assim que rompe, o caso passa para Já venceu."
            icone={<CalendarClock className="w-4 h-4" />}
            casos={vencemHoje}
            vazio="Nada vence hoje."
            calendarioConfiavel={calendarioConfiavel}
            hoje={hoje}
          />
          <BlocoDeCasos
            titulo="Próximos vencimentos"
            ajuda={`Os ${LIMITE_DE_PROXIMOS_VENCIMENTOS} casos mais próximos de vencer, em qualquer dia. Na sexta-feira mostra o que vence na segunda.`}
            icone={<CalendarPlus className="w-4 h-4" />}
            casos={proximos?.casos ?? null}
            contagem={
              proximos ? rotuloDaContagemParcial(proximos.casos.length, proximos.total) : undefined
            }
            vazio="Nada a vencer depois de hoje."
            calendarioConfiavel={calendarioConfiavel}
            hoje={hoje}
          />
        </div>

        <Bloco
          titulo={areas === null ? "Vencidos por área" : `Vencidos por área (${areas.length})`}
          ajuda="A fila viva de hoje, com nome de quem responde pelo setor. Vem do módulo de métricas, a mesma fonte do relatório da Diretoria."
          icone={<UserX className="w-4 h-4" />}
        >
          {areas === null ? (
            <NaoCarregou />
          ) : (
            <>
              {areas.length === 0 ? (
                <Vazio texto="Nenhuma área com caso vencido." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100 text-left">
                        <th className="px-5 py-2.5 font-semibold text-slate-600">Setor</th>
                        <th className="px-5 py-2.5 font-semibold text-slate-600">Responsável</th>
                        <th className="px-5 py-2.5 font-semibold text-slate-600">Pendentes</th>
                        <th className="px-5 py-2.5 font-semibold text-slate-600">Vencidas</th>
                        <th className="px-5 py-2.5 font-semibold text-slate-600">Atraso do pior caso</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {areas.map((area) => (
                        <tr key={area.setor}>
                          <td className="px-5 py-3 text-slate-800 font-medium">{rotuloDoSetor(area.setor)}</td>
                          <td className={`px-5 py-3 ${area.responsavel ? "text-slate-600" : "text-slate-400 italic"}`}>
                            {rotuloDoResponsavel(area.responsavel, degradado ?? [])}
                          </td>
                          <td className="px-5 py-3 text-slate-600">{area.pendentes}</td>
                          <td className="px-5 py-3 text-red-600 font-semibold">{area.vencidas}</td>
                          <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                            {area.dias_uteis_de_atraso.toLocaleString("pt-BR", {
                              minimumFractionDigits: 1,
                              maximumFractionDigits: 1,
                            })}{" "}
                            {area.dias_uteis_de_atraso === 1 ? "dia útil" : "dias úteis"}
                            {!calendarioConfiavel && (
                              <span className="ml-1.5 text-[11px] text-amber-600">(sem o calendário)</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {/* Fica fora do ramo da tabela cheia de propósito: é com a tabela
                  vazia que o leitor mais precisa saber o que "Pendentes" conta,
                  e é com ela vazia que "Já venceu (5)" logo acima parece erro. */}
              <p className="px-5 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-400">
                Pendentes conta só o que está com a área aguardando resposta, sem recorte de data. Os
                cartões do topo contam todos os estados, inclusive o que está com a Ouvidoria. E
                Vencidas conta só o caso que já está com a área, enquanto Já venceu conta todo prazo
                rompido em aberto, inclusive o da triagem da própria Ouvidoria: por isso os dois
                números não se somam nem precisam bater.
              </p>
            </>
          )}
        </Bloco>
      </div>
    </div>
  );
}
