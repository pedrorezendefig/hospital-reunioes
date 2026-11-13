"use client";

/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319; redesenho da issue
 * #1628, seção 4.11 do anexo da Demanda #1527).
 *
 * O que precisa de atenção agora, em seis faixas, da mais urgente para a menos
 * urgente, na mesma ordem no computador e no celular: críticos, números do
 * agora, atrasos das áreas (com Cobrar), atrasos da Ouvidoria, próximos
 * vencimentos e a tabela por área. Todo caso sai no card padrão (seção 4.12),
 * com o assunto do agente e nunca o começo do relato (regra T3).
 *
 * Três fontes, sem mistura. As contagens de área vêm do módulo de métricas, a
 * MESMA função que o relatório em PDF consome, e por isso os dois nunca
 * divergem. Os casos vêm da listagem, porque o módulo de métricas não
 * identifica caso nenhum (contrato da issue #341). O contador Para revisar vem
 * da porta própria dele, que devolve só o número.
 *
 * A regra que rege esta tela inteira: ela nunca afirma o que não sabe. Faixa
 * que não carregou diz que não carregou, e não desenha zero; número em dias
 * úteis calculado sem o calendário sai marcado; perda de acesso apaga o que
 * está na tela em vez de manter a foto antiga.
 *
 * A régua de quem entra em cada faixa mora em `lib/ouvidoria/painel.ts`, com
 * testes próprios. Aqui só há tela.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, AlertTriangle, ArrowLeft, Loader2, RefreshCw, Send } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { FRASE_DO_TOPO } from "@/lib/ouvidoria/orientacao";
import { usePolling } from "@/hooks/usePolling";
import { Ajuda } from "@/components/ouvidoria/Ajuda";
import { CardDeCaso, GravidadeDoCaso, type CasoDoCard } from "@/components/ouvidoria/CardDeCaso";
import {
  cobrarOSetor,
  textoDaCobranca,
  tomDaCobranca,
  type ResultadoDaCobranca,
} from "@/lib/ouvidoria/cobranca";
import { ASSUNTO_NAO_GERADO } from "@/lib/ouvidoria/fila";
import { ALTURA_DE_TOQUE } from "@/lib/toque";
import {
  atrasosDaOuvidoria,
  atrasosDasAreas,
  avisosDeDegradacao,
  calendarioUtilFoiLido,
  casosDoNumero,
  classificarFalha,
  classificarJanela,
  criticosAbertos,
  hojeNoHospital,
  idadeDoMaisAntigo,
  intervaloDeAtualizacao,
  LIMITE_DE_PROXIMOS_VENCIMENTOS,
  linhasPorArea,
  percentualRespondidoNoPrazo,
  podeVerPainel,
  proximosVencimentos,
  rotuloDaContagemParcial,
  rotuloDoResponsavel,
  rotuloDoSetor,
  type FalhaDeCarga,
  type LinhaPorArea,
  type NumeroDoAgora,
  type PendenciaDeArea,
  type PrazoDaArea,
  type TrechoDoPrazo,
} from "@/lib/ouvidoria/painel";

interface CasoDaListagem extends CasoDoCard {
  prazo_area_em: string | null;
  prazo_resposta: string;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  sigilo_reforcado: boolean;
  minutos_uteis_restantes?: number | null;
  data_abertura?: string | null;
}

interface Metricas {
  degradado: string[];
  pendencias_por_area: PendenciaDeArea[];
  prazo_por_area: PrazoDaArea[];
  prazo: { trechos?: TrechoDoPrazo[] } | null;
}

type Leitura<T> = { ok: true; corpo: T } | { ok: false; status: number };

/** O endereço da aba Avaliações já filtrada no Para revisar (seção 4.6). */
const AVALIACOES_PARA_REVISAR = "/ouvidoria/avaliacoes?revisar=1";

/**
 * Uma leitura, com o resultado em vez da exceção. `status: 0` é a falha que nem
 * chegou a ter resposta (rede, DNS, aba offline).
 *
 * `no-store` nas duas pontas: o corpo carrega protocolo, setor e assunto do
 * caso, e a leitura se repete a cada minuto. Sem o cabeçalho, a garantia de
 * que nada disso fica guardado no caminho seria comportamento de terceiro, e
 * não decisão do código.
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

/**
 * O prazo ou o atraso de um caso, como a linha 3 do card escreve.
 *
 * O caso ainda na triagem não tem prazo da área, e o que o servidor manda
 * sobre ele fala de um vencimento que não existe (`rotulo_prazo` vem "sem
 * prazo definido"): ali vale o prazo de referência, dito como tal.
 *
 * O vencimento persistido pode ser mostrado sempre: é dado, não conta. O
 * rótulo ("vencido há 3 dias úteis") é calculado com a tabela de feriados, e
 * sem o calendário confirmado a frase sai da tela em vez de sair errada.
 */
function textoDoPrazo(caso: CasoDaListagem, calendarioConfiavel: boolean): string | null {
  const vencimento = caso.prazo_area_em
    ? formatarHora(caso.prazo_area_em)
    : caso.prazo_resposta
      ? formatarDia(caso.prazo_resposta)
      : null;
  if (!vencimento) return null;
  const complemento = !caso.prazo_area_em
    ? " (prazo de referência, ainda sem triagem)"
    : calendarioConfiavel
      ? caso.rotulo_prazo
        ? ` (${caso.rotulo_prazo})`
        : ""
      : " (sem confirmação do calendário)";
  return `${vencimento}${complemento}`;
}

/** Não carregado. Nunca pode ser confundido com vazio. */
function NaoCarregou() {
  return (
    <p className="flex items-center gap-2 px-4 md:px-5 py-4 text-sm text-amber-700 bg-amber-50">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      Não foi possível carregar. Esta faixa não está dizendo que não há nada.
    </p>
  );
}

/** Vazio de verdade, que explica por quê (regra T7). */
function Vazio({ texto }: { texto: string }) {
  return <p className="px-4 md:px-5 py-4 text-sm text-slate-400">{texto}</p>;
}

/** Uma faixa do Painel: o título, uma linha que diz o que ela é e o "?". */
function Faixa({
  titulo,
  linha,
  explicacao,
  destaque,
  children,
}: {
  titulo: string;
  linha: string;
  explicacao: string;
  destaque?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`bg-white rounded-2xl border shadow-premium overflow-hidden ${destaque ? "border-[#B3352B]" : "border-border"}`}
    >
      <header className={`px-4 md:px-5 py-3 border-b ${destaque ? "bg-red-50 border-red-100" : "bg-slate-50 border-slate-100"}`}>
        <div className="flex flex-wrap items-center gap-x-2">
          <h2
            className={`font-bold text-sm uppercase tracking-[0.04em] ${destaque ? "text-[#B3352B]" : "text-slate-800"}`}
          >
            {titulo}
          </h2>
          <Ajuda assunto={titulo} explicacao={explicacao} />
          <p className={`basis-full text-xs ${destaque ? "text-[#B3352B]" : "text-slate-400"}`}>{linha}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

/** Um número da faixa 2. Os que viram lista são botão; os outros, só número. */
function Numero({
  rotulo,
  valor,
  detalhe,
  selecionado,
  onTocar,
}: {
  rotulo: string;
  valor: string;
  detalhe?: string | null;
  selecionado?: boolean;
  onTocar?: () => void;
}) {
  const conteudo = (
    <>
      <span className="block text-2xl font-bold text-slate-900">{valor}</span>
      <span className="block text-xs text-slate-500 mt-0.5">{rotulo}</span>
      {detalhe && <span className="block text-[11px] text-slate-400 mt-0.5">{detalhe}</span>}
    </>
  );
  const caixa = `text-left rounded-xl border px-3 py-2.5 ${ALTURA_DE_TOQUE}`;
  if (!onTocar) return <div className={`${caixa} border-border`}>{conteudo}</div>;
  return (
    <button
      type="button"
      aria-pressed={selecionado}
      onClick={onTocar}
      className={`${caixa} ${selecionado ? "border-[#282760] bg-[#EAEAF0]" : "border-border hover:bg-slate-50"}`}
    >
      {conteudo}
    </button>
  );
}

const ROTULO_DO_NUMERO: Record<NumeroDoAgora, string> = {
  atrasados: "Atrasados",
  vencem: "Vencem em até 2 dias úteis",
  triagem: "Aguardando triagem da Ouvidoria",
};

function formatarPorcentagem(valor: number | null): string {
  return valor === null ? "-" : `${Math.round(valor)}%`;
}

function formatarAtraso(dias: number): string {
  return `${dias.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${
    dias === 1 ? "dia útil" : "dias úteis"
  }`;
}

/** A tabela por área: tabela do `md` para cima, lista empilhada no celular. */
function TabelaPorArea({
  linhas,
  degradado,
  calendarioConfiavel,
}: {
  linhas: LinhaPorArea[];
  degradado: string[];
  calendarioConfiavel: boolean;
}) {
  const semCalendario = !calendarioConfiavel && (
    <span className="ml-1.5 text-[11px] text-amber-600">(sem o calendário)</span>
  );
  return (
    <>
      <table className="hidden md:table w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-100 text-left">
            <th className="px-5 py-2.5 font-semibold text-slate-600">Setor</th>
            <th className="px-5 py-2.5 font-semibold text-slate-600">Responsável</th>
            <th className="px-5 py-2.5 font-semibold text-slate-600">Pendentes</th>
            <th className="px-5 py-2.5 font-semibold text-slate-600">Vencidas</th>
            <th className="px-5 py-2.5 font-semibold text-slate-600">Atraso do pior caso</th>
            <th className="px-5 py-2.5 font-semibold text-slate-600">% no prazo no mês</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {linhas.map((area) => (
            <tr key={area.setor}>
              <td className="px-5 py-3 text-slate-800 font-medium">{rotuloDoSetor(area.setor)}</td>
              <td className={`px-5 py-3 ${area.responsavel ? "text-slate-600" : "text-slate-400"}`}>
                {rotuloDoResponsavel(area.responsavel, degradado)}
              </td>
              <td className="px-5 py-3 text-slate-600">{area.pendentes}</td>
              <td className={`px-5 py-3 ${area.vencidas > 0 ? "text-[#B3352B] font-semibold" : "text-slate-600"}`}>
                {area.vencidas}
              </td>
              <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                {formatarAtraso(area.dias_uteis_de_atraso)}
                {semCalendario}
              </td>
              <td className="px-5 py-3 text-slate-600">{formatarPorcentagem(area.percentual_no_prazo)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="md:hidden divide-y divide-slate-50">
        {linhas.map((area) => (
          <li key={area.setor} className="px-4 py-3 text-sm">
            <p className="font-medium text-slate-800">{rotuloDoSetor(area.setor)}</p>
            <p className="text-xs text-slate-500">{rotuloDoResponsavel(area.responsavel, degradado)}</p>
            <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-slate-400">Pendentes</dt>
              <dd className="text-slate-700">{area.pendentes}</dd>
              <dt className="text-slate-400">Vencidas</dt>
              <dd className={area.vencidas > 0 ? "text-[#B3352B] font-semibold" : "text-slate-700"}>
                {area.vencidas}
              </dd>
              <dt className="text-slate-400">Atraso do pior caso</dt>
              <dd className="text-slate-700">
                {formatarAtraso(area.dias_uteis_de_atraso)}
                {semCalendario}
              </dd>
              <dt className="text-slate-400">% no prazo no mês</dt>
              <dd className="text-slate-700">{formatarPorcentagem(area.percentual_no_prazo)}</dd>
            </dl>
          </li>
        ))}
      </ul>
    </>
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
  // diferentes: uma pode falhar sozinha.
  const [degradadoDosCasos, setDegradadoDosCasos] = useState<string[] | null>(null);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [paraRevisar, setParaRevisar] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [falha, setFalha] = useState<FalhaDeCarga | null>(null);
  const [semSessao, setSemSessao] = useState(false);
  const [falhasSeguidas, setFalhasSeguidas] = useState(0);
  const [atualizadoEm, setAtualizadoEm] = useState<string | null>(null);
  const [abaVisivel, setAbaVisivel] = useState(true);
  // O dia civil no fuso do hospital, calculado só depois de montar, para o
  // servidor e o navegador não renderizarem janelas diferentes.
  const [hoje, setHoje] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  // O número da faixa 2 que o ouvidor tocou, e cuja lista aparece abaixo.
  const [numero, setNumero] = useState<NumeroDoAgora | null>(null);
  const [cobrancas, setCobrancas] = useState<Record<string, ResultadoDaCobranca>>({});

  const carregar = useCallback(async () => {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const acesso = session?.access_token;
    if (!acesso) {
      // Sessão expirada não pode virar painel zerado e silencioso.
      setSemSessao(true);
      setCasos(null);
      setDegradadoDosCasos(null);
      setMetricas(null);
      setParaRevisar(null);
      return;
    }
    setSemSessao(false);
    setToken(acesso);

    const [lidoMetricas, lidoCasos, lidoRevisar] = await Promise.all([
      ler<Metricas>("/api/ouvidoria/metricas", acesso),
      // `arquivados=todos` e não a lista de trabalho (issue #592, ADR 0047): o
      // painel CONTA em vez de trabalhar, e arquivar é organização da lista e
      // não fato do caso.
      ler<{ protocolos: CasoDaListagem[]; degradado?: string[] }>(
        "/api/ouvidoria/protocolos?arquivados=todos",
        acesso
      ),
      ler<{ total: number }>("/api/ouvidoria/avaliacoes/para-revisar", acesso),
    ]);

    // Perder o perfil com a tela aberta apaga a tela. O que está nela é
    // protocolo, setor e assunto de manifestação, e o polling manteria a foto
    // antiga no ar por tempo indeterminado (RN-40).
    const perdeuAcesso = [lidoMetricas, lidoCasos, lidoRevisar].some(
      (lido) => !lido.ok && classificarFalha(lido.status) === "sem_acesso"
    );
    if (perdeuAcesso) {
      setCasos(null);
      setDegradadoDosCasos(null);
      setMetricas(null);
      setParaRevisar(null);
      setAtualizadoEm(null);
      setFalha("sem_acesso");
      return;
    }

    // Cada porta é aplicada por si: a que veio boa não é descartada porque a
    // outra caiu, e a que caiu deixa a faixa dela dizendo que não carregou.
    if (lidoMetricas.ok) {
      setMetricas({
        degradado: lidoMetricas.corpo.degradado ?? [],
        pendencias_por_area: lidoMetricas.corpo.pendencias_por_area ?? [],
        prazo_por_area: lidoMetricas.corpo.prazo_por_area ?? [],
        prazo: lidoMetricas.corpo.prazo ?? null,
      });
    } else {
      setMetricas(null);
    }
    if (lidoCasos.ok) {
      // O dia é relido a cada atualização: painel aberto na virada da
      // meia-noite continuaria chamando de "vence hoje" o que venceu ontem.
      setHoje(hojeNoHospital());
      setCasos(lidoCasos.corpo.protocolos ?? []);
      // Backend uma versão atrás não manda o campo, e "ausente" não pode virar
      // "nada degradou".
      setDegradadoDosCasos(lidoCasos.corpo.degradado ?? null);
    } else {
      setCasos(null);
      setDegradadoDosCasos(null);
    }
    setParaRevisar(lidoRevisar.ok ? lidoRevisar.corpo.total : null);

    if (lidoMetricas.ok && lidoCasos.ok && lidoRevisar.ok) {
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

  // Painel esquecido aberto numa estação compartilhada não fica repuxando a
  // cada minuto. A volta recarrega na hora: o `usePolling` é um `setInterval`
  // sem chamada imediata, e quem volta esperaria um intervalo INTEIRO.
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

  /**
   * O Cobrar do card (seção 4.11, faixa 3): a mesma porta da fila, que manda
   * o acionamento de novo a quem responde pelo setor hoje e grava a cobrança
   * na trilha do caso. O Painel não recarrega: cobrar não muda o estado.
   */
  async function cobrar(caso: CasoDaListagem) {
    if (!token) return;
    const anotar = (resultado: ResultadoDaCobranca) =>
      setCobrancas((antes) => ({ ...antes, [caso.id]: resultado }));
    anotar({ fase: "enviando" });
    anotar(await cobrarOSetor(caso.id, token));
  }

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
  const avisos = avisosDeDegradacao([...new Set([...(degradado ?? []), ...(degradadoDosCasos ?? [])])]);
  // As duas leituras do mesmo calendário: basta uma acusar para a frase em
  // dias úteis sair da tela (issue #449).
  const calendarioConfiavel = calendarioUtilFoiLido(degradado) && calendarioUtilFoiLido(degradadoDosCasos);
  const prontos = casos && hoje ? { casos, hoje } : null;
  const criticos = prontos && criticosAbertos(prontos.casos);
  const daArea = prontos && atrasosDasAreas(prontos.casos, prontos.hoje);
  const daOuvidoria = prontos && atrasosDaOuvidoria(prontos.casos, prontos.hoje);
  const proximos = prontos && proximosVencimentos(prontos.casos, prontos.hoje);
  const listaDoNumero = prontos && numero ? casosDoNumero(numero, prontos.casos, prontos.hoje) : null;
  const areas = metricas && linhasPorArea(metricas.pendencias_por_area, metricas.prazo_por_area);
  const responsavelPorSetor = new Map(
    (metricas?.pendencias_por_area ?? []).map((linha) => [linha.setor, linha.responsavel])
  );

  /** O responsável na linha 3: só do caso que está com a área. */
  function responsavelDoCaso(caso: CasoDaListagem): string | null {
    if (caso.status !== "aguardando_area" || !metricas) return null;
    return rotuloDoResponsavel(responsavelPorSetor.get(caso.setor) ?? null, degradado ?? []);
  }

  function card(caso: CasoDaListagem, opcoes: { cobrar?: boolean } = {}) {
    const cobranca = cobrancas[caso.id];
    const atrasado = prontos ? classificarJanela(caso, prontos.hoje) === "vencido" : false;
    return (
      <CardDeCaso
        key={caso.id}
        caso={caso}
        prazo={textoDoPrazo(caso, calendarioConfiavel)}
        atrasado={atrasado}
        responsavel={responsavelDoCaso(caso)}
        acao={
          opcoes.cobrar ? (
            <button
              type="button"
              disabled={cobranca?.fase === "enviando" || cobranca?.fase === "reenviada"}
              onClick={() => cobrar(caso)}
              className={`inline-flex w-full md:w-auto items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-[#282760] text-white hover:bg-[#282760]/90 disabled:opacity-60 ${ALTURA_DE_TOQUE}`}
            >
              <Send className="w-3.5 h-3.5" />
              Cobrar
            </button>
          ) : undefined
        }
        aviso={
          cobranca && (
            <p
              role="status"
              className={`mt-1.5 text-xs ${
                { ok: "text-emerald-700", alerta: "text-amber-700", neutro: "text-slate-500" }[tomDaCobranca(cobranca)]
              }`}
            >
              {textoDaCobranca(cobranca)}
            </p>
          )
        }
      />
    );
  }

  function listaDeCasos(lista: CasoDaListagem[] | null, vazio: string, opcoes: { cobrar?: boolean } = {}) {
    if (lista === null) return <NaoCarregou />;
    if (lista.length === 0) return <Vazio texto={vazio} />;
    return <ul className="divide-y divide-slate-100">{lista.map((caso) => card(caso, opcoes))}</ul>;
  }

  const idade = prontos ? idadeDoMaisAntigo(prontos.casos, prontos.hoje) : null;
  const percentual = metricas ? percentualRespondidoNoPrazo(metricas.prazo) : null;
  const contagem = (chave: NumeroDoAgora) =>
    prontos ? String(casosDoNumero(chave, prontos.casos, prontos.hoje).length) : "?";

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-slate-900">Painel em tempo real</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {FRASE_DO_TOPO.painel}
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
            Parte do painel não pôde ser atualizada. As faixas que não carregaram estão marcadas; as
            demais podem estar desatualizadas. A próxima tentativa vai ficando mais espaçada.
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

      <div className="space-y-4 md:space-y-5">
        {/* Faixa 1. Vermelha só quando há crítico; sem nenhum, uma linha
            discreta (seção 4.11), e não um terço da tela vazio. */}
        {criticos && criticos.length === 0 ? (
          <section className="rounded-2xl border border-border bg-white px-4 md:px-5 py-2.5 flex flex-wrap items-baseline gap-x-2">
            <h2 className="font-bold text-sm uppercase tracking-[0.04em] text-slate-500">Críticos</h2>
            <p className="text-sm text-slate-400">Nenhum caso crítico aberto.</p>
          </section>
        ) : (
          <Faixa
            titulo="Críticos"
            linha="Casos críticos ainda não encerrados, inclusive os que foram ao Núcleo."
            explicacao="Risco à vida, à segurança ou à imagem. O caso sai daqui quando a Ouvidoria encerra, e não quando a área responde. O que foi ao Núcleo de Segurança do Paciente leva o selo Em análise pelo NSP."
            destaque
          >
            {listaDeCasos(criticos, "Nenhum caso crítico aberto.")}
          </Faixa>
        )}

        {/* Faixa 2. Cada número que é lista vira botão e mostra os casos logo
            abaixo; a porcentagem e o Para revisar não são lista desta tela. */}
        <Faixa
          titulo="Números do agora"
          linha="Toque num número para ver os casos."
          explicacao="Atrasados soma os atrasos das áreas e os da Ouvidoria. Vencem em até 2 dias úteis conta o que ainda não venceu. Aguardando triagem é o que a Ouvidoria ainda não validou, com a idade do mais antigo. A porcentagem é a parte dos casos que entraram no mês e que a área respondeu no prazo. Para revisar são as notas do QR que o agente marcou e ainda esperam revisão, de qualquer data."
        >
          <div className="p-3 md:p-4">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 md:gap-3">
              {(Object.keys(ROTULO_DO_NUMERO) as NumeroDoAgora[]).map((chave) => (
                <Numero
                  key={chave}
                  rotulo={ROTULO_DO_NUMERO[chave]}
                  valor={contagem(chave)}
                  detalhe={
                    chave === "triagem" && idade !== null
                      ? `O mais antigo há ${idade} ${idade === 1 ? "dia" : "dias"}`
                      : null
                  }
                  selecionado={numero === chave}
                  onTocar={() => setNumero((antes) => (antes === chave ? null : chave))}
                />
              ))}
              <Numero
                rotulo="Respondido no prazo no mês"
                valor={metricas ? formatarPorcentagem(percentual) : "?"}
              />
              <Link
                href={AVALIACOES_PARA_REVISAR}
                className={`col-span-2 lg:col-span-1 text-left rounded-xl border border-border px-3 py-2.5 hover:bg-slate-50 ${ALTURA_DE_TOQUE}`}
              >
                <span className="block text-2xl font-bold text-slate-900">
                  {paraRevisar === null ? "?" : paraRevisar}
                </span>
                <span className="block text-xs text-slate-500 mt-0.5">Para revisar</span>
              </Link>
            </div>
            {numero && (
              <div className="mt-3 rounded-xl border border-border overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 bg-slate-50 border-b border-slate-100">
                  <p className="text-xs font-semibold text-slate-600">{ROTULO_DO_NUMERO[numero]}</p>
                  <button
                    type="button"
                    onClick={() => setNumero(null)}
                    className={`text-xs text-primary hover:underline ${ALTURA_DE_TOQUE}`}
                  >
                    Fechar a lista
                  </button>
                </div>
                {listaDeCasos(listaDoNumero, "Nenhum caso neste número agora.")}
              </div>
            )}
          </div>
        </Faixa>

        <Faixa
          titulo="Atrasos das áreas"
          linha="Respostas vencidas, da gravidade maior para a menor e do maior atraso para o menor."
          explicacao="O caso que está com a área e já passou do prazo. O botão Cobrar manda a cobrança de novo a quem responde pelo setor hoje e grava no histórico do caso quem foi cobrado. O elogio fica de fora porque não tem prazo de resposta."
        >
          {listaDeCasos(daArea, "Nenhuma área com resposta vencida agora.", { cobrar: true })}
        </Faixa>

        <Faixa
          titulo="Atrasos da Ouvidoria"
          linha="Casos vencidos ainda na triagem, na mesma ordem."
          explicacao="O caso que a Ouvidoria ainda não validou e já passou do prazo de referência. Fica separado dos atrasos das áreas porque quem deve a resposta é a própria Ouvidoria."
        >
          {listaDeCasos(daOuvidoria, "Nenhuma triagem vencida agora.")}
        </Faixa>

        <Faixa
          titulo="Próximos vencimentos"
          linha={`Os ${LIMITE_DE_PROXIMOS_VENCIMENTOS} próximos a vencer${
            proximos ? `: ${rotuloDaContagemParcial(proximos.casos.length, proximos.total)}` : ""
          }.`}
          explicacao="Os casos mais próximos de vencer, em qualquer dia, inclusive o que vence hoje e ainda não venceu. Na sexta-feira mostra o que vence na segunda."
        >
          {proximos === null ? (
            <NaoCarregou />
          ) : proximos.casos.length === 0 ? (
            <Vazio texto="Nenhum caso aberto com prazo correndo agora." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {proximos.casos.map((caso) => (
                <li key={caso.id} className="flex items-center gap-2 px-4 md:px-5 py-2 min-w-0 text-sm">
                  <Link
                    href={`/ouvidoria/m/${caso.protocolo}`}
                    className="font-mono font-semibold text-slate-800 hover:underline shrink-0"
                  >
                    {caso.protocolo}
                  </Link>
                  <GravidadeDoCaso gravidade={caso.gravidade} />
                  <span className={`truncate min-w-0 flex-1 ${caso.assunto ? "text-slate-600" : "italic text-slate-400"}`}>
                    {caso.assunto || ASSUNTO_NAO_GERADO}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {caso.prazo_area_em ? formatarHora(caso.prazo_area_em) : formatarDia(caso.prazo_resposta)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Faixa>

        <Faixa
          titulo="Por área"
          linha="O que cada área deve agora e quanto respondeu no prazo no mês."
          explicacao="Pendentes conta o que está com a área aguardando resposta, sem recorte de data, e Vencidas conta só o caso já entregue à área. A porcentagem é dos casos que entraram no mês e que a área respondeu dentro do prazo. Vem do módulo de métricas, a mesma fonte do relatório da Diretoria."
        >
          {areas === null ? (
            <NaoCarregou />
          ) : areas.length === 0 ? (
            <Vazio texto="Nenhuma área com caso pendente ou medido no mês." />
          ) : (
            <TabelaPorArea linhas={areas} degradado={degradado ?? []} calendarioConfiavel={calendarioConfiavel} />
          )}
        </Faixa>
      </div>
    </div>
  );
}
