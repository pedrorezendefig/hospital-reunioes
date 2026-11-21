"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { useMovimentoReduzido } from "@/hooks/useMovimentoReduzido";
import { createClient } from "@/lib/supabase/client";

import { Trilho, type ItemDoTrilho } from "./Trilho";

export type GrupoDoInicio = "passou_do_prazo" | "ate_48_horas" | "proximos_7_dias";
/** O grupo do item a que o módulo de origem não dá prazo (issue #1936). */
export type GrupoSemPrazo = "sem_prazo";

/** Um item da Minha Fila, no formato comum de toda fonte (ADR 0104). */
export interface ItemDoInicio {
  tipo: string;
  id: string;
  titulo: string;
  origem: string;
  prazo: string | null;
  chegou_em: string | null;
  area: string;
  acao: string;
  destino: string;
  contexto?: string | null;
  acao_de_um_clique: { rotulo: string; endpoint: string } | null;
  grupo: GrupoDoInicio | GrupoSemPrazo | null;
  dias_de_atraso: number | null;
  /** Só no grupo Sem prazo: há quantos dias o item espera. */
  dias_esperando?: number | null;
}

/** A linha de resumo de uma fila sem responsável nomeado (ADR 0104, decisão 6). */
export interface FilaDoPapel {
  fila: string;
  titulo: string;
  esperam: number;
  vencidas: number;
  resumo: string;
  destino: string;
}

export interface InicioDaPessoa {
  hoje: string;
  frase: { titulo: string; apoio: string };
  /** Nada vencido nem para as próximas 48 horas, como na frase (issue #1946). */
  em_dia?: boolean;
  contadores: Record<GrupoDoInicio, number>;
  itens: ItemDoInicio[];
  avisos: { fonte: string; mensagem: string }[];
  trilho: ItemDoTrilho[];
  filas_do_papel: FilaDoPapel[];
}

const GRUPOS: { chave: GrupoDoInicio | GrupoSemPrazo; titulo: string }[] = [
  { chave: "passou_do_prazo", titulo: "Passou do prazo" },
  { chave: "ate_48_horas", titulo: "Vence em até 48 horas" },
  { chave: "proximos_7_dias", titulo: "Próximos 7 dias" },
  // No fim: o que espera sem prazo não é vencido (PRD #1932).
  { chave: "sem_prazo", titulo: "Sem prazo" },
];

const DIAS_DA_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

// Vermelho só em texto (ADR 0104, decisão 8): nada de fundo nem borda.
const VERMELHO = "text-red-700";

/** "2026-11-20" vira ["sex", "20/11"], sem passar por fuso. */
function diaDaSemanaEData(iso: string): [string, string] {
  const [ano, mes, dia] = iso.slice(0, 10).split("-").map(Number);
  const data = new Date(ano, mes - 1, dia);
  return [DIAS_DA_SEMANA[data.getDay()], `${String(dia).padStart(2, "0")}/${String(mes).padStart(2, "0")}`];
}

function dataPorExtenso(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-").map(Number);
  return new Date(ano, mes - 1, dia).toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function Quando({ item, hoje }: { item: ItemDoInicio; hoje: string }) {
  if (item.grupo === "passou_do_prazo" && item.dias_de_atraso) {
    return (
      <div className={`leading-tight ${VERMELHO}`}>
        <span className="block text-3xl tabular-nums">{item.dias_de_atraso}</span>
        <span className="block text-xs mt-0.5">
          {item.dias_de_atraso === 1 ? "dia de atraso" : "dias de atraso"}
        </span>
      </div>
    );
  }
  if (item.grupo === "sem_prazo" && item.dias_esperando != null) {
    return (
      <div className="leading-tight text-text">
        <span className="block text-3xl tabular-nums">{item.dias_esperando}</span>
        <span className="block text-xs mt-0.5 text-text-secondary">
          {item.dias_esperando === 1 ? "dia esperando" : "dias esperando"}
        </span>
      </div>
    );
  }
  const data = item.prazo ?? item.chegou_em;
  if (!data) return <div />;
  const [semana, diaEMes] = diaDaSemanaEData(data);
  return (
    <div className="leading-tight text-text">
      <span className="block text-xl">{data.slice(0, 10) === hoje ? "Hoje" : semana}</span>
      <span className="block text-xs mt-0.5 text-text-secondary">{diaEMes}</span>
    </div>
  );
}

async function cabecalhoDeAcesso(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

/**
 * A ação de um clique (ADR 0104, decisão 3): chama a rota que o servidor
 * mandou, sem sair do Início, e pede o Início de novo para a linha sair e a
 * frase e os contadores virem refeitos (issue #1939).
 */
function BotaoDeUmClique({
  acao,
  className,
  aoResolver,
}: {
  acao: { rotulo: string; endpoint: string };
  className: string;
  aoResolver: () => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [falhou, setFalhou] = useState(false);

  async function clicar() {
    setEnviando(true);
    setFalhou(false);
    try {
      const res = await fetch(acao.endpoint, { method: "POST", headers: await cabecalhoDeAcesso() });
      if (!res.ok) throw new Error(String(res.status));
      aoResolver();
    } catch {
      setFalhou(true);
      setEnviando(false);
    }
  }

  return (
    <>
      <button type="button" onClick={clicar} disabled={enviando} className={className}>
        {acao.rotulo}
      </button>
      {falhou && (
        <p role="alert" className="text-xs text-text-secondary">
          Não deu para confirmar agora. Tente de novo.
        </p>
      )}
    </>
  );
}

// O botão da linha: preenchido no vencido; nos outros, preenche no hover e no
// foco da linha (issue #1935).
const BOTAO_VENCIDO = "bg-primary text-white group-hover:bg-primary-dark group-focus-within:bg-primary-dark";
const BOTAO_DOS_OUTROS =
  "bg-white text-primary group-hover:bg-primary group-hover:text-white group-focus-within:bg-primary group-focus-within:text-white";

/**
 * Uma linha da fila. No hover e no foco do teclado ganha fundo suave, o botão
 * preenche e a linha de contexto aparece; na tela de toque, que não tem hover,
 * o contexto fica sempre à vista. A linha vencida entra uma vez, ao abrir, uma
 * depois da outra (ADR 0104, decisão 8); com movimento reduzido, nada entra.
 */
function Linha({
  item,
  hoje,
  entrada,
  aoResolver,
}: {
  item: ItemDoInicio;
  hoje: string;
  entrada: number | null;
  aoResolver: () => void;
}) {
  const classeDoBotao = `uppercase tracking-wide text-xs text-center max-w-full sm:whitespace-nowrap rounded-lg px-3.5 py-2 border border-primary motion-safe:transition-colors ${
    item.grupo === "passou_do_prazo" ? BOTAO_VENCIDO : BOTAO_DOS_OUTROS
  }`;
  return (
    <li
      className={`group grid grid-cols-[88px_minmax(0,1fr)] sm:grid-cols-[104px_minmax(0,1fr)_auto] gap-4 items-center py-3.5 px-2 border-b border-border rounded-lg motion-safe:transition-colors hover:bg-slate-50 focus-within:bg-slate-50${
        entrada === null ? "" : " animate-fade-in-up"
      }`}
      style={entrada === null ? undefined : { animationDelay: `${entrada * 70}ms` }}
    >
      <Quando item={item} hoje={hoje} />
      <div className="min-w-0">
        <p className="text-base text-text leading-snug break-words">{item.titulo}</p>
        <p className="text-xs text-text-secondary mt-1 break-words">{item.origem}</p>
        {item.contexto && (
          <p className="hidden group-hover:block group-focus-within:block [@media(hover:none)]:block text-xs text-primary mt-1.5 pl-2.5 border-l-2 border-border break-words">
            {item.contexto}
          </p>
        )}
      </div>
      {/* No celular a coluna é estreita: a etiqueta e o botão descem de linha e
          quebram o texto em vez de passar da borda do cartão (issue #1935). */}
      <div className="col-start-2 sm:col-start-auto flex flex-wrap sm:flex-nowrap sm:flex-col items-center sm:items-end justify-between gap-2">
        <span className="etiqueta text-[11px] text-slate-600 bg-slate-100 rounded-full px-2.5 py-0.5 max-w-full sm:whitespace-nowrap">
          {item.area}
        </span>
        {item.acao_de_um_clique ? (
          <BotaoDeUmClique acao={item.acao_de_um_clique} className={classeDoBotao} aoResolver={aoResolver} />
        ) : (
          <Link href={item.destino} aria-label={`${item.acao}: ${item.titulo}`} className={classeDoBotao}>
            {item.acao}
          </Link>
        )}
      </div>
    </li>
  );
}

/** O título da aba: o número de prazos vencidos quando há, para a aba de
 * início do navegador chamar atenção sem piscar (ADR 0104, decisão 8). */
function tituloDaAba(vencidos: number): string {
  return vencidos > 0 ? `(${vencidos}) Início` : "Início";
}

/**
 * O Início de quem está olhando (issue #1934, ADR 0104): a frase do topo, os
 * três contadores e a Minha Fila em três grupos, do prazo mais vencido para o
 * mais distante. Grupo, atraso e frase vêm prontos do servidor.
 *
 * A frase mora numa região anunciada que já existe enquanto a tela carrega:
 * quando ela chega, o leitor de tela a lê (issue #1935).
 */
export function MinhaFila({ aoCarregar }: { aoCarregar?: (inicio: InicioDaPessoa) => void } = {}) {
  const [inicio, setInicio] = useState<InicioDaPessoa | null>(null);
  const [falhou, setFalhou] = useState(false);
  const movimentoReduzido = useMovimentoReduzido();
  // Quem monta a tela fica sabendo do Início que chegou (se a pessoa está em
  // dia, issue #1946), sem refazer o pedido quando a função muda.
  const avisar = useRef(aoCarregar);
  useEffect(() => {
    avisar.current = aoCarregar;
  });

  // Também roda depois de uma ação de um clique: o servidor refaz a fila, a
  // frase e os contadores.
  const carregar = useCallback(async (vivo: () => boolean = () => true) => {
    try {
      const res = await fetch("/api/inicio", { headers: await cabecalhoDeAcesso() });
      if (!res.ok) throw new Error(String(res.status));
      const corpo = (await res.json()) as InicioDaPessoa;
      if (vivo()) {
        setInicio(corpo);
        avisar.current?.(corpo);
      }
    } catch {
      if (vivo()) setFalhou(true);
    }
  }, []);

  useEffect(() => {
    let vivo = true;
    carregar(() => vivo);
    return () => {
      vivo = false;
    };
  }, [carregar]);

  const vencidos = inicio?.contadores.passou_do_prazo ?? null;
  useEffect(() => {
    if (vencidos === null) return;
    const anterior = document.title;
    document.title = tituloDaAba(vencidos);
    return () => {
      document.title = anterior;
    };
  }, [vencidos]);

  if (falhou) {
    return (
      <p role="alert" className="p-6 text-sm text-text-secondary">
        Não foi possível abrir o seu Início agora. Tente de novo em instantes.
      </p>
    );
  }

  const grupos = inicio
    ? GRUPOS.map((g) => ({ ...g, itens: inicio.itens.filter((i) => i.grupo === g.chave) })).filter(
        (g) => g.itens.length > 0
      )
    : [];
  const contadores: [GrupoDoInicio, number, string][] = inicio
    ? [
        ["passou_do_prazo", inicio.contadores.passou_do_prazo, inicio.contadores.passou_do_prazo === 1 ? "prazo vencido" : "prazos vencidos"],
        ["ate_48_horas", inicio.contadores.ate_48_horas, inicio.contadores.ate_48_horas === 1 ? "vence em até 48 horas" : "vencem em até 48 horas"],
        ["proximos_7_dias", inicio.contadores.proximos_7_dias, "nos próximos 7 dias"],
      ]
    : [];

  return (
    <div className="bg-white rounded-2xl border border-border overflow-hidden">
      <section
        data-testid="abertura"
        className={`px-6 sm:px-8 pt-7 pb-6 ${vencidos ? "bg-primary-dark text-white" : "bg-white text-text"}`}
      >
        {inicio && (
          <div className="flex flex-wrap justify-between gap-4 text-xs opacity-80">
            <h1 className="text-xs">Início</h1>
            <span>{dataPorExtenso(inicio.hoje)}</span>
          </div>
        )}
        <div aria-live="polite">
          {inicio ? (
            <>
              <p className="mt-4 text-3xl sm:text-4xl leading-tight max-w-[22ch] break-words">{inicio.frase.titulo}</p>
              <p className="mt-2.5 text-base max-w-[52ch] opacity-85">{inicio.frase.apoio}</p>
            </>
          ) : (
            <p className="text-sm text-text-secondary">Carregando o seu Início</p>
          )}
        </div>
        {inicio && (
          <ul aria-label="Resumo dos prazos" className="mt-5 flex flex-wrap gap-2">
            {contadores.map(([chave, numero, rotulo]) => {
              const conteudo = (
                <>
                  <b className="font-normal text-xl tabular-nums">{numero}</b>
                  <span className="etiqueta">{rotulo}</span>
                </>
              );
              const caixa = "inline-flex items-baseline gap-2 rounded-lg border border-current px-3.5 py-2 text-xs";
              return (
                <li key={chave} className="flex">
                  {numero > 0 ? (
                    <a href={`#grupo-${chave}`} className={`${caixa} hover:underline underline-offset-4`}>
                      {conteudo}
                    </a>
                  ) : (
                    <span className={caixa}>{conteudo}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {inicio && (
        <div className="px-4 sm:px-8 py-7 grid gap-8 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="min-w-0 space-y-8">
            {inicio.avisos.map((aviso) => (
              <p key={aviso.fonte} role="status" className="text-sm text-text-secondary">
                {aviso.mensagem}
              </p>
            ))}

            {grupos.length === 0 ? (
              <p className="text-base text-text">Nada vencido e nada para os próximos 7 dias.</p>
            ) : (
              grupos.map((grupo) => (
                <section key={grupo.chave} id={`grupo-${grupo.chave}`} aria-label={grupo.titulo} className="scroll-mt-4">
                  <h2
                    className={`flex items-baseline gap-2.5 pb-2 border-b border-border text-xs ${
                      grupo.chave === "passou_do_prazo" ? VERMELHO : "text-text-secondary"
                    }`}
                  >
                    {grupo.titulo}
                    <span className="tabular-nums">{grupo.itens.length}</span>
                  </h2>
                  <ul>
                    {grupo.itens.map((item, indice) => (
                      <Linha
                        key={`${item.tipo}:${item.id}`}
                        item={item}
                        hoje={inicio.hoje}
                        entrada={grupo.chave === "passou_do_prazo" && !movimentoReduzido ? indice : null}
                        aoResolver={() => carregar()}
                      />
                    ))}
                  </ul>
                </section>
              ))
            )}

            {/* A Fila do papel fica à parte e fora da frase e dos contadores
                (ADR 0104, decisão 6): a fila é do papel, não da pessoa. */}
            {inicio.filas_do_papel.length > 0 && (
              <section aria-label="Fila do papel">
                <h2 className="pb-2 border-b border-border text-xs text-text-secondary">Fila do papel</h2>
                <ul>
                  {inicio.filas_do_papel.map((fila) => (
                    <li
                      key={fila.fila}
                      className="flex flex-wrap items-center justify-between gap-3 py-3.5 px-2 border-b border-border"
                    >
                      <div className="min-w-0">
                        <p className="text-base text-text leading-snug">{fila.titulo}</p>
                        <p className="text-xs text-text-secondary mt-1">{fila.resumo}</p>
                      </div>
                      <Link
                        href={fila.destino}
                        className="uppercase tracking-wide text-xs whitespace-nowrap rounded-lg px-3.5 py-2 border border-primary bg-white text-primary"
                      >
                        Abrir a fila
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* O Registro de acesso (issue #1941, ADR 0104 decisão 10). */}
            <p className="text-xs text-text-secondary">O dia em que você abre o Início fica registrado.</p>
          </div>
          <Trilho itens={inicio.trilho} hoje={inicio.hoje} />
        </div>
      )}
    </div>
  );
}
