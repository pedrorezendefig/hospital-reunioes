"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import {
  caminhoPor,
  desenharFluxo,
  DURACAO_DA_LIGACAO,
  DURACAO_DO_PASSO,
  lerFluxograma,
  ordemDoFluxo,
  tempos,
  type Fluxo,
  type LigacaoDesenhada,
  type Passo,
  type PassoDesenhado,
} from "./fluxo";

/**
 * O Fluxograma do manual (issue #1719, emenda da ADR 0094): o desenho próprio
 * do app, em SVG, com a fonte da casa e os tokens de cor. O formato do bloco
 * está no comentário de `fluxo.ts`.
 *
 * * Entrada: quando o fluxograma entra na tela, os passos aparecem pela ordem
 *   do fluxo e cada ligação se desenha da origem ao destino.
 * * Passar o mouse num passo (no celular, tocar) destaca o caminho dele e
 *   mostra o detalhe embaixo.
 * * "Percorrer" acende um passo de cada vez, com "Anterior" e "Próximo".
 * * Movimento reduzido: tudo aparece pronto, sem animação.
 * * Leitor de tela: o desenho fica escondido, e o mesmo fluxo vai numa lista
 *   numerada, com as decisões e os caminhos escritos.
 * * Celular: a grade desce para uma coluna.
 */

const CONSULTA_DO_MOVIMENTO_REDUZIDO = "(prefers-reduced-motion: reduce)";
const CONSULTA_DO_CELULAR = "(max-width: 767px)";

function useConsulta(consulta: string): boolean {
  return useSyncExternalStore(
    (avisar) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
      const lista = window.matchMedia(consulta);
      lista.addEventListener("change", avisar);
      return () => lista.removeEventListener("change", avisar);
    },
    () => (typeof window.matchMedia === "function" ? window.matchMedia(consulta).matches : false),
    () => false,
  );
}

/** Se o fluxograma já entrou na tela. Sem `IntersectionObserver`, já entrou. */
function useEntrouNaTela(alvo: React.RefObject<Element | null>): boolean {
  const [entrou, setEntrou] = useState(false);
  useEffect(() => {
    const el = alvo.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setEntrou(true);
      return;
    }
    const observador = new IntersectionObserver((entradas) => {
      if (entradas.some((e) => e.isIntersecting)) {
        setEntrou(true);
        observador.disconnect();
      }
    });
    observador.observe(el);
    return () => observador.disconnect();
  }, [alvo]);
  return entrou;
}

export function Fluxograma({ fonte }: { fonte: string }) {
  const leitura = useMemo(() => lerFluxograma(fonte), [fonte]);
  if (!leitura.ok) {
    return (
      <div role="alert" className="my-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
        <p className="font-semibold">Este fluxograma tem erro e não pôde ser desenhado.</p>
        <ul className="mt-1 list-disc pl-5">
          {leitura.erros.map((erro) => (
            <li key={erro}>{erro}</li>
          ))}
        </ul>
      </div>
    );
  }
  return <Desenho fluxo={leitura.fluxo} />;
}

function Desenho({ fluxo }: { fluxo: Fluxo }) {
  const reduzido = useConsulta(CONSULTA_DO_MOVIMENTO_REDUZIDO);
  const celular = useConsulta(CONSULTA_DO_CELULAR);
  const caixa = useRef<HTMLElement>(null);
  const entrou = useEntrouNaTela(caixa);

  const desenho = useMemo(() => desenharFluxo(fluxo, celular), [fluxo, celular]);
  const ordem = useMemo(() => ordemDoFluxo(fluxo), [fluxo]);
  const quando = useMemo(() => tempos(fluxo), [fluxo]);

  const [realce, setRealce] = useState<string | null>(null);
  const [percurso, setPercurso] = useState<number | null>(null);

  const emFoco = percurso !== null ? ordem[percurso].id : realce;
  const caminho = useMemo(() => {
    if (percurso !== null) return { passos: new Set([ordem[percurso].id]), ligacoes: new Set<string>() };
    return realce ? caminhoPor(fluxo, realce) : null;
  }, [fluxo, ordem, percurso, realce]);
  const passoEmFoco = emFoco ? fluxo.passos.find((p) => p.id === emFoco) : undefined;

  const animar = !reduzido;
  const escondido = animar && !entrou;

  return (
    <figure
      ref={caixa}
      data-fluxograma=""
      data-movimento={reduzido ? "reduzido" : "normal"}
      className="my-6 rounded-2xl border border-border bg-surface p-4 shadow-premium"
    >
      <figcaption className="sr-only">Fluxograma em {ordem.length} passos.</figcaption>
      <div className="overflow-x-auto">
        <svg
          aria-hidden="true"
          viewBox={`0 0 ${desenho.largura} ${desenho.altura}`}
          width={desenho.largura}
          height={desenho.altura}
          className="mx-auto block max-w-full h-auto"
          style={{ fontFamily: "inherit" }}
        >
          {desenho.ligacoes.map((l) => (
            <DesenhoDaLigacao
              key={l.chave}
              ligacao={l}
              realcada={caminho?.ligacoes.has(l.chave) ?? false}
              apagada={caminho !== null && !caminho.ligacoes.has(l.chave)}
              atraso={animar ? quando.ligacao.get(l.chave)! : null}
              escondida={escondido}
            />
          ))}
          {desenho.passos.map((p) => (
            <DesenhoDoPasso
              key={p.id}
              passo={p}
              realcado={caminho?.passos.has(p.id) ?? false}
              apagado={caminho !== null && !caminho.passos.has(p.id)}
              atual={percurso !== null && ordem[percurso].id === p.id}
              atraso={animar ? quando.passo.get(p.id)! : null}
              escondido={escondido}
              aoEntrar={() => setRealce(p.id)}
              aoSair={() => setRealce((r) => (r === p.id ? null : r))}
              aoTocar={() => setRealce((r) => (r === p.id ? null : p.id))}
            />
          ))}
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-border pt-3">
        {percurso === null ? (
          <button
            type="button"
            onClick={() => setPercurso(0)}
            className="rounded-xl bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-dark"
          >
            Percorrer
          </button>
        ) : (
          <>
            <button
              type="button"
              disabled={percurso === 0}
              onClick={() => setPercurso((i) => Math.max(0, (i ?? 0) - 1))}
              className="rounded-xl border border-border px-3 py-1.5 text-xs font-semibold text-primary disabled:opacity-40"
            >
              Anterior
            </button>
            <button
              type="button"
              disabled={percurso === ordem.length - 1}
              onClick={() => setPercurso((i) => Math.min(ordem.length - 1, (i ?? 0) + 1))}
              className="rounded-xl bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-dark disabled:opacity-40"
            >
              Próximo
            </button>
            <button
              type="button"
              onClick={() => setPercurso(null)}
              className="rounded-xl px-3 py-1.5 text-xs font-semibold text-text-secondary hover:text-primary"
            >
              Encerrar
            </button>
            <span className="text-xs text-text-secondary" aria-live="polite">
              Passo {percurso + 1} de {ordem.length}
            </span>
          </>
        )}
      </div>

      {passoEmFoco && (
        <div data-detalhe="" className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-text">
          <p className="font-semibold text-primary">{passoEmFoco.rotulo}</p>
          {passoEmFoco.detalhe && <p className="mt-0.5 text-text-secondary">{passoEmFoco.detalhe}</p>}
        </div>
      )}

      <ListaParaLeitor fluxo={fluxo} ordem={ordem} />
    </figure>
  );
}

const COR_DA_FORMA: Record<Passo["forma"], { fundo: string; borda: string; texto: string }> = {
  inicio: { fundo: "var(--color-primary)", borda: "var(--color-primary)", texto: "#ffffff" },
  fim: { fundo: "var(--color-secondary)", borda: "var(--color-secondary)", texto: "var(--color-primary-dark)" },
  passo: { fundo: "var(--color-surface)", borda: "var(--color-border)", texto: "var(--color-text)" },
  decisao: { fundo: "#FFF7EA", borda: "var(--color-accent)", texto: "var(--color-text)" },
};

function DesenhoDoPasso({
  passo,
  realcado,
  apagado,
  atual,
  atraso,
  escondido,
  aoEntrar,
  aoSair,
  aoTocar,
}: {
  passo: PassoDesenhado;
  realcado: boolean;
  apagado: boolean;
  atual: boolean;
  atraso: number | null;
  escondido: boolean;
  aoEntrar: () => void;
  aoSair: () => void;
  aoTocar: () => void;
}) {
  const { x, y, w, h, forma } = passo;
  const cor = COR_DA_FORMA[forma];
  const borda = realcado || atual ? "var(--color-primary-light)" : cor.borda;
  const espessura = realcado || atual ? 2.5 : 1.5;
  const altura = 16;
  const primeira = y - ((passo.linhasDoRotulo.length - 1) * altura) / 2;

  return (
    <g
      data-passo={passo.id}
      data-forma={forma}
      data-x={x}
      data-y={y}
      data-realcado={realcado ? "sim" : "nao"}
      data-atual={atual ? "sim" : "nao"}
      onMouseEnter={aoEntrar}
      onMouseLeave={aoSair}
      onClick={aoTocar}
      style={{
        cursor: "pointer",
        transformOrigin: `${x}px ${y}px`,
        transition: "opacity 200ms ease-out",
        opacity: escondido ? 0 : apagado ? 0.3 : 1,
        animation:
          atraso !== null && !escondido ? `fluxograma-passo ${DURACAO_DO_PASSO}ms ease-out ${atraso}ms both` : undefined,
      }}
    >
      {forma === "decisao" ? (
        <polygon
          points={`${x},${y - h / 2} ${x + w / 2},${y} ${x},${y + h / 2} ${x - w / 2},${y}`}
          fill={cor.fundo}
          stroke={borda}
          strokeWidth={espessura}
          strokeLinejoin="round"
          style={{ filter: "drop-shadow(0 4px 6px rgba(0,0,0,0.08))" }}
        />
      ) : (
        <rect
          x={x - w / 2}
          y={y - h / 2}
          width={w}
          height={h}
          rx={forma === "passo" ? 8 : h / 2}
          fill={cor.fundo}
          stroke={borda}
          strokeWidth={espessura}
          style={{ filter: "drop-shadow(0 4px 6px rgba(0,0,0,0.08))" }}
        />
      )}
      <text
        x={x}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={13}
        fontWeight={forma === "passo" || forma === "decisao" ? 500 : 600}
        fill={cor.texto}
      >
        {passo.linhasDoRotulo.map((linha, i) => (
          <tspan key={i} x={x} y={primeira + i * altura}>
            {linha}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function DesenhoDaLigacao({
  ligacao,
  realcada,
  apagada,
  atraso,
  escondida,
}: {
  ligacao: LigacaoDesenhada;
  realcada: boolean;
  apagada: boolean;
  atraso: number | null;
  escondida: boolean;
}) {
  const { pontos, comprimento, posicaoDoRotulo } = ligacao;
  const d = pontos.map(([x, y], i) => `${i ? "L" : "M"} ${x} ${y}`).join(" ");
  const [xFim, yFim] = pontos[pontos.length - 1];
  const [xAntes, yAntes] = pontos[pontos.length - 2];
  const angulo = (Math.atan2(yFim - yAntes, xFim - xAntes) * 180) / Math.PI;
  const cor = realcada ? "var(--color-primary-light)" : "#94A3B8";
  const anima = atraso !== null && !escondida;
  const surge = anima ? `fluxograma-surge 150ms ease-out ${atraso! + DURACAO_DA_LIGACAO}ms both` : undefined;

  return (
    <g
      data-ligacao={ligacao.chave}
      data-realcada={realcada ? "sim" : "nao"}
      style={{ opacity: escondida ? 0 : apagada ? 0.25 : 1, transition: "opacity 200ms ease-out" }}
    >
      <path
        d={d}
        fill="none"
        stroke={cor}
        strokeWidth={realcada ? 2.5 : 1.75}
        strokeLinejoin="round"
        strokeDasharray={anima ? comprimento : undefined}
        style={
          anima
            ? ({
                "--comprimento": comprimento,
                animation: `fluxograma-ligacao ${DURACAO_DA_LIGACAO}ms ease-in-out ${atraso}ms both`,
              } as React.CSSProperties)
            : undefined
        }
      />
      <path
        data-seta=""
        d="M -9 -5 L 0 0 L -9 5 Z"
        fill={cor}
        transform={`translate(${xFim} ${yFim}) rotate(${angulo})`}
        style={surge ? { animation: surge } : undefined}
      />
      {posicaoDoRotulo && (
        <text
          x={posicaoDoRotulo[0]}
          y={posicaoDoRotulo[1]}
          textAnchor={pontos[1][0] < pontos[0][0] ? "end" : "start"}
          fontSize={12}
          fontWeight={600}
          fill="var(--color-text-secondary)"
          style={surge ? { animation: surge } : undefined}
        >
          {ligacao.rotulo}
        </text>
      )}
    </g>
  );
}

/** O mesmo fluxo, em lista numerada, para o leitor de tela. */
function ListaParaLeitor({ fluxo, ordem }: { fluxo: Fluxo; ordem: Passo[] }) {
  const porId = new Map(fluxo.passos.map((p) => [p.id, p]));
  const frase = (p: Passo) => {
    const saidas = fluxo.ligacoes.filter((l) => l.de === p.id);
    const nome = { inicio: "Início: ", fim: "Fim: ", decisao: "Decisão: ", passo: "" }[p.forma];
    const partes = [`${nome}${p.rotulo}${/[.?!]$/.test(p.rotulo) ? "" : "."}`];
    if (p.detalhe) partes.push(p.detalhe);
    const comRotulo = saidas.filter((l) => l.rotulo);
    const semRotulo = saidas.filter((l) => !l.rotulo);
    for (const l of comRotulo) partes.push(`Se ${l.rotulo}: ${porId.get(l.para)!.rotulo}.`);
    if (semRotulo.length) partes.push(`Depois: ${semRotulo.map((l) => porId.get(l.para)!.rotulo).join(" ou ")}.`);
    return partes.join(" ");
  };
  return (
    <ol className="sr-only">
      {ordem.map((p) => (
        <li key={p.id}>{frase(p)}</li>
      ))}
    </ol>
  );
}
