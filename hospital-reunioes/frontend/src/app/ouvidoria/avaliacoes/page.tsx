"use client";

/**
 * A aba Avaliações da Ouvidoria (issue #1626, PRD #1527, seção 4.5 da
 * especificação da Diretoria, ADR 0086 decisões 4 e 8).
 *
 * As notas do QR não geram protocolo: aqui elas viram números (nota média, %
 * de 4 e 5, volume, % que pediu retorno), gráficos por ponto, turno, dia da
 * semana e semana, e uma lista com filtros. Duas ações na nota:
 *
 * * Converter em manifestação abre um caso com o comentário como relato, o
 *   cartaz, a ligação, tipo vazio e T0 da avaliação. Pede confirmação, porque
 *   caso não se apaga (ADR 0047).
 * * Arquivar revisão tira a marca Para revisar com um motivo curto.
 *
 * Só os dois perfis da Ouvidoria. O servidor recusa os outros (403) e o layout
 * da rota devolve à fila; aqui a tela só não pede nada a quem não pode.
 * O contador Para revisar do Painel abre esta tela com `?revisar=1`.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle, ArrowLeft, Flag, Loader2, MessageSquareText } from "lucide-react";

import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { createClient } from "@/lib/supabase/client";
import {
  PERIODOS_DA_ABA,
  TAMANHO_DO_MOTIVO,
  caminhoDaLista,
  filtrosIniciais,
  formatarDataHora,
  formatarMedia,
  formatarPorcentagem,
  motivoValido,
  podeVerAvaliacoes,
  rotuloDaSemana,
  rotuloDoMotivo,
  type AvaliacaoDaLista,
  type Barra,
  type FiltrosDaLista,
  type NumerosDaAba,
  type PaginaDaLista,
  type PeriodoDaAba,
} from "@/lib/ouvidoria/avaliacoes";

/** Alvo de toque de 44 px em todo controle (regra T4 da especificação). */
const TOQUE = "min-h-[44px]";
const CAMPO = `w-full ${TOQUE} px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30`;
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";
const BOTAO_SECUNDARIO = `inline-flex items-center justify-center gap-1.5 ${TOQUE} px-3 rounded-lg border border-slate-200 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40`;
const BOTAO_PRINCIPAL = `inline-flex items-center justify-center gap-1.5 ${TOQUE} px-3 rounded-lg bg-primary text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40`;

/**
 * O token do momento, lido a cada chamada: o supabase-js rotaciona o JWT, e
 * uma aba aberta por mais de uma hora mandaria um token vencido.
 */
async function cabecalhos(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {};
}

async function detalheDoErro(res: Response, padrao: string): Promise<string> {
  try {
    const corpo = await res.json();
    return typeof corpo?.detail === "string" ? corpo.detail : padrao;
  } catch {
    return padrao;
  }
}

export default function AvaliacoesPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      }
    >
      <AbaAvaliacoes />
    </Suspense>
  );
}

function AbaAvaliacoes() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const busca = useSearchParams();
  const pode = podeVerAvaliacoes(participante?.perfil_ouvidoria);

  const [filtros, setFiltros] = useState<FiltrosDaLista>(() => filtrosIniciais(busca.get("revisar")));
  const [numeros, setNumeros] = useState<NumerosDaAba | null>(null);
  const [lista, setLista] = useState<PaginaDaLista | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pode) return;
    let vivo = true;
    (async () => {
      const res = await fetch(`/api/ouvidoria/avaliacoes/numeros?periodo=${filtros.periodo}`, {
        headers: await cabecalhos(),
      });
      if (!vivo) return;
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível ler os números agora."));
        return;
      }
      setNumeros(await res.json());
    })();
    return () => {
      vivo = false;
    };
  }, [pode, filtros.periodo]);

  useEffect(() => {
    if (!pode) return;
    let vivo = true;
    (async () => {
      const res = await fetch(caminhoDaLista(filtros), { headers: await cabecalhos() });
      if (!vivo) return;
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível ler as avaliações agora."));
        return;
      }
      setErro(null);
      setLista(await res.json());
    })();
    return () => {
      vivo = false;
    };
  }, [pode, filtros]);

  const mudar = useCallback((mudanca: Partial<FiltrosDaLista>) => {
    setFiltros((antes) => ({ ...antes, pagina: 1, ...mudanca }));
  }, []);

  /** A nota que o ouvidor converteu ou arquivou, sem reler a lista inteira. */
  const atualizar = useCallback((nova: AvaliacaoDaLista) => {
    setLista((antes) => {
      if (!antes) return antes;
      const velha = antes.itens.find((item) => item.id === nova.id);
      const saiuDeRevisar = Boolean(velha?.para_revisar && !nova.para_revisar);
      return {
        ...antes,
        itens: antes.itens.map((item) => (item.id === nova.id ? nova : item)),
        para_revisar_total: antes.para_revisar_total - (saiuDeRevisar ? 1 : 0),
      };
    });
  }, []);

  if (carregandoPerfil) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    );
  }

  if (!pode) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto text-center py-16">
        <p className="text-slate-500 font-medium">Só o ouvidor e a diretoria executiva abrem a aba Avaliações.</p>
        <Link href="/ouvidoria" className="inline-block mt-4 text-sm text-primary hover:underline">
          Voltar à Ouvidoria
        </Link>
      </div>
    );
  }

  const pontos = (numeros?.por_ponto ?? []).filter((p) => p.ponto_id);
  const paginas = lista ? Math.max(1, Math.ceil(lista.total / lista.por_pagina)) : 1;

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-6">
      <div>
        <Link
          href="/ouvidoria"
          className={`inline-flex items-center gap-1 ${TOQUE} text-sm text-slate-500 hover:text-slate-700`}
        >
          <ArrowLeft className="w-4 h-4" />
          Ouvidoria
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Avaliações</h1>
        <p className="text-sm text-slate-500 mt-1">
          Notas deixadas pelo QR. Não geram protocolo, a menos que a pessoa peça retorno ou a Ouvidoria converta.
        </p>
      </div>

      <div className="max-w-xs">
        <label className={ROTULO} htmlFor="periodo">
          Período
        </label>
        <select
          id="periodo"
          className={CAMPO}
          value={filtros.periodo}
          onChange={(e) => mudar({ periodo: e.target.value as PeriodoDaAba })}
        >
          {PERIODOS_DA_ABA.map((p) => (
            <option key={p.valor} value={p.valor}>
              {p.rotulo}
            </option>
          ))}
        </select>
      </div>

      {erro && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erro}</span>
        </div>
      )}

      {numeros && <Numeros numeros={numeros} />}

      <section aria-labelledby="titulo-da-lista" className="space-y-4">
        <h2 id="titulo-da-lista" className="text-lg font-semibold text-slate-800">
          Notas
        </h2>
        <div role="group" aria-label="Filtros da lista" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className={ROTULO} htmlFor="filtro-ponto">
              Ponto
            </label>
            <select
              id="filtro-ponto"
              className={CAMPO}
              value={filtros.pontoId}
              onChange={(e) => mudar({ pontoId: e.target.value })}
            >
              <option value="">Todos os pontos</option>
              {pontos.map((p) => (
                <option key={p.ponto_id} value={p.ponto_id!}>
                  {p.nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={ROTULO} htmlFor="filtro-nota">
              Nota
            </label>
            <select
              id="filtro-nota"
              className={CAMPO}
              value={filtros.nota}
              onChange={(e) => mudar({ nota: e.target.value })}
            >
              <option value="">Todas as notas</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <label className={`flex items-center gap-2 ${TOQUE} text-sm text-slate-700 sm:self-end`}>
            <input
              type="checkbox"
              className="w-4 h-4"
              checked={filtros.comComentario}
              onChange={(e) => mudar({ comComentario: e.target.checked })}
            />
            Só com comentário
          </label>
          <label className={`flex items-center gap-2 ${TOQUE} text-sm text-slate-700 sm:self-end`}>
            <input
              type="checkbox"
              className="w-4 h-4"
              checked={filtros.paraRevisar}
              onChange={(e) => mudar({ paraRevisar: e.target.checked })}
            />
            Para revisar{lista ? ` (${lista.para_revisar_total})` : ""}
          </label>
        </div>

        {!lista ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 text-primary animate-spin" />
          </div>
        ) : lista.itens.length === 0 ? (
          <p className="text-sm text-slate-500 py-6 text-center">
            Nenhuma nota com esses filtros no período. As notas do QR aparecem aqui assim que alguém avalia, e as
            marcadas pelo agente entram em Para revisar.
          </p>
        ) : (
          <ul className="space-y-3">
            {lista.itens.map((item) => (
              <li key={item.id}>
                <CartaoDaAvaliacao item={item} aoMudar={atualizar} />
              </li>
            ))}
          </ul>
        )}

        {lista && paginas > 1 && (
          <nav aria-label="Páginas da lista" className="flex items-center justify-between gap-3">
            <button
              type="button"
              className={BOTAO_SECUNDARIO}
              disabled={filtros.pagina <= 1}
              onClick={() => setFiltros((antes) => ({ ...antes, pagina: antes.pagina - 1 }))}
            >
              Mais novas
            </button>
            <span className="text-sm text-slate-500">
              Página {filtros.pagina} de {paginas}
            </span>
            <button
              type="button"
              className={BOTAO_SECUNDARIO}
              disabled={filtros.pagina >= paginas}
              onClick={() => setFiltros((antes) => ({ ...antes, pagina: antes.pagina + 1 }))}
            >
              Mais antigas
            </button>
          </nav>
        )}
      </section>
    </div>
  );
}

function Numeros({ numeros }: { numeros: NumerosDaAba }) {
  const { indicadores } = numeros;
  const cartoes = [
    { rotulo: "Nota média", valor: formatarMedia(indicadores.nota_media) },
    { rotulo: "Notas 4 e 5", valor: formatarPorcentagem(indicadores.pct_4_e_5) },
    { rotulo: "Avaliações", valor: String(indicadores.volume) },
    { rotulo: "Pediram retorno", valor: formatarPorcentagem(indicadores.pct_pediu_retorno) },
  ];
  return (
    <>
      <section aria-label="Indicadores">
        <dl className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {cartoes.map((c) => (
            <div key={c.rotulo} className="rounded-xl border border-border bg-white p-4">
              <dt className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{c.rotulo}</dt>
              <dd className="text-2xl font-bold text-slate-900 mt-1">{c.valor}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Grafico titulo="Nota média por ponto" barras={numeros.por_ponto.map((p) => ({ ...p, rotulo: p.nome }))} />
        <Grafico
          titulo="Nota média por turno"
          nota="Madrugada da meia-noite às 6h, manhã das 6h ao meio-dia, tarde do meio-dia às 18h e noite das 18h à meia-noite, no relógio do hospital."
          barras={numeros.por_turno}
        />
        <Grafico titulo="Nota média por dia da semana" barras={numeros.por_dia_da_semana} />
        <Grafico
          titulo="Evolução semanal"
          nota="Cada linha é a semana que começa na segunda indicada."
          barras={numeros.por_semana.map((s) => ({ ...s, rotulo: rotuloDaSemana(s.semana) }))}
        />
      </div>
    </>
  );
}

/** Barras horizontais de nota média (0 a 5): cabem a 375 px sem rolagem. */
function Grafico({
  titulo,
  nota,
  barras,
}: {
  titulo: string;
  nota?: string;
  barras: (Barra & { rotulo: string })[];
}) {
  return (
    <section aria-label={titulo} className="rounded-xl border border-border bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-700">{titulo}</h3>
      {nota && <p className="text-xs text-slate-400 mt-1">{nota}</p>}
      {barras.length === 0 ? (
        <p className="text-sm text-slate-500 mt-3">Sem notas no período.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {barras.map((b) => (
            <li key={b.rotulo} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-2 text-sm">
              <span className="truncate text-slate-600" title={b.rotulo}>
                {b.rotulo}
              </span>
              <span className="h-2.5 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
                <span
                  className="block h-full rounded-full bg-primary"
                  style={{ width: `${((b.nota_media ?? 0) / 5) * 100}%` }}
                />
              </span>
              <span className="tabular-nums text-slate-700">
                <span>{formatarMedia(b.nota_media)}</span>
                <span className="text-xs text-slate-400"> ({b.volume})</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CartaoDaAvaliacao({
  item,
  aoMudar,
}: {
  item: AvaliacaoDaLista;
  aoMudar: (nova: AvaliacaoDaLista) => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [arquivando, setArquivando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function converter() {
    setOcupado(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/avaliacoes/${encodeURIComponent(item.id)}/conversao`, {
        method: "POST",
        headers: await cabecalhos(),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível abrir o caso agora."));
        return;
      }
      const caso = (await res.json()) as { id: string; protocolo: string | null };
      setConfirmando(false);
      aoMudar({ ...item, caso, revisao_desfecho: "convertida", para_revisar: false });
    } finally {
      setOcupado(false);
    }
  }

  async function arquivar() {
    setOcupado(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/avaliacoes/${encodeURIComponent(item.id)}/arquivamento`, {
        method: "POST",
        headers: { ...(await cabecalhos()), "Content-Type": "application/json" },
        body: JSON.stringify({ motivo: motivo.trim() }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível arquivar a revisão agora."));
        return;
      }
      const feito = (await res.json()) as { revisao_motivo: string };
      setArquivando(false);
      aoMudar({ ...item, revisao_desfecho: "arquivada", revisao_motivo: feito.revisao_motivo, para_revisar: false });
    } finally {
      setOcupado(false);
    }
  }

  const podeConverter = Boolean(item.comentario) && !item.caso;

  return (
    <article
      aria-label={`Avaliação nota ${item.nota}, ${item.ponto_nome}`}
      className="rounded-xl border border-border bg-white p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-lg font-bold text-slate-900">Nota {item.nota}</span>
        <span className="text-sm text-slate-600">{item.ponto_nome}</span>
        <span className="text-sm text-slate-400">{formatarDataHora(item.criada_em)}</span>
        {item.para_revisar && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold">
            <Flag className="w-3 h-3" />
            Para revisar
          </span>
        )}
      </div>

      {item.motivos.length > 0 && (
        <ul aria-label="Motivos" className="flex flex-wrap gap-1.5">
          {item.motivos.map((m) => (
            <li key={m} className="px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-600">
              {rotuloDoMotivo(m)}
            </li>
          ))}
        </ul>
      )}

      {item.comentario ? (
        <p className="flex items-start gap-2 text-sm text-slate-700 break-words">
          <MessageSquareText className="w-4 h-4 shrink-0 mt-0.5 text-slate-400" />
          <span className="min-w-0">{item.comentario}</span>
        </p>
      ) : (
        <p className="text-sm text-slate-400">Sem comentário.</p>
      )}

      {item.revisar_motivo && (
        <p className="text-xs text-slate-500">Apontada pelo agente: {item.revisar_motivo}</p>
      )}
      {item.revisao_desfecho === "arquivada" && (
        <p className="text-xs text-slate-500">Revisão arquivada: {item.revisao_motivo}</p>
      )}
      {item.caso && (
        <p className="text-sm text-slate-700">
          Virou o caso{" "}
          <Link href={`/ouvidoria/m/${item.caso.protocolo}`} className="font-semibold text-primary hover:underline">
            {item.caso.protocolo}
          </Link>
        </p>
      )}

      {erro && <p className="text-sm text-red-700">{erro}</p>}

      {confirmando ? (
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-2">
          <p className="text-sm text-slate-700">
            Abre um caso com este comentário como relato, sem tipo e com a hora da avaliação. Quem avaliou não deixou
            contato. Caso aberto não tem volta.
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <button type="button" className={BOTAO_PRINCIPAL} disabled={ocupado} onClick={converter}>
              Abrir o caso
            </button>
            <button type="button" className={BOTAO_SECUNDARIO} disabled={ocupado} onClick={() => setConfirmando(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : arquivando ? (
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-2">
          <label className={ROTULO} htmlFor={`motivo-${item.id}`}>
            Motivo do arquivo
          </label>
          <input
            id={`motivo-${item.id}`}
            className={CAMPO}
            maxLength={TAMANHO_DO_MOTIVO}
            placeholder="Ex.: já tratado por telefone"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              className={BOTAO_PRINCIPAL}
              disabled={ocupado || !motivoValido(motivo)}
              onClick={arquivar}
            >
              Confirmar arquivo
            </button>
            <button type="button" className={BOTAO_SECUNDARIO} disabled={ocupado} onClick={() => setArquivando(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        (podeConverter || item.para_revisar) && (
          <div className="flex flex-col sm:flex-row gap-2">
            {podeConverter && (
              <button type="button" className={BOTAO_SECUNDARIO} onClick={() => setConfirmando(true)}>
                Converter em manifestação
              </button>
            )}
            {item.para_revisar && (
              <button type="button" className={BOTAO_SECUNDARIO} onClick={() => setArquivando(true)}>
                Arquivar revisão
              </button>
            )}
          </div>
        )
      )}
    </article>
  );
}
