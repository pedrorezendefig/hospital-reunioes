"use client";

/**
 * O Quadro da Tecnologia na tela larga (issue #1642, PRD #1641, ADR 0090).
 *
 * As Demandas em colunas pela Etapa, lida do GitHub: ninguém arrasta card nem
 * muda Etapa aqui. A regra das colunas (o que entra em cada uma, a ordem, o
 * teto de Entregue) é o `colunasDoQuadro`; esta tela só desenha.
 *
 * A página rola inteira: as colunas não têm rolagem própria, e o cabeçalho de
 * cada uma (Etapa e contagem) fica fixo no topo. As colunas esticam até a
 * altura da maior, para o cabeçalho da coluna curta não sair da tela antes
 * das outras. O `data-quadro` é a marca que o `globals.css` procura para o
 * `<main>` do AppShell deixar o `sticky` valer na rolagem da página.
 *
 * O card é compacto (decisão 4): Número da Demanda, título, Bug ou Melhoria,
 * iniciais do Responsável, partes do PRD, a versão em Em produção e os selos
 * "Tem demonstração" e "Envio falhou". Data, quem pediu e o "Conversar" ficam
 * na Demanda aberta.
 */

import { useId } from "react";

import {
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  ColunaDoQuadro,
  colunasDoQuadro,
  Demanda,
  ENVIO_FALHOU,
  iniciais,
  linkDaDemonstracao,
  nomeDoNumero,
  partesDoCard,
  TEM_DEMONSTRACAO,
} from "./demandas";

const COLUNA_VAZIA = "Nenhum pedido.";

/** O nome que o leitor de tela diz do card: o Número e o título. */
function nomeDoCard(demanda: Demanda): string {
  const numero = nomeDoNumero(demanda);
  return numero ? `${numero}: ${demanda.titulo}` : demanda.titulo;
}

/** As partes do PRD numa barra fina. A issue simples não tem barra. */
function PartesNoCardCompacto({ demanda }: { demanda: Demanda }) {
  const partes = partesDoCard(demanda);
  if (!partes) return null;
  const largura = `${Math.round((partes.entregues / partes.total) * 100)}%`;
  return (
    <span className="flex items-center gap-2">
      <span
        role="progressbar"
        aria-label="Partes entregues"
        aria-valuemin={0}
        aria-valuemax={partes.total}
        aria-valuenow={partes.entregues}
        className="h-1 flex-1 rounded-full bg-slate-100 overflow-hidden"
      >
        <span className="block h-full rounded-full bg-emerald-500" style={{ width: largura }} />
      </span>
      <span className="normal-case text-[11px] font-medium text-text-secondary whitespace-nowrap">
        {partes.entregues} de {partes.total} partes
      </span>
    </span>
  );
}

/** Um card do Quadro: um botão só, que abre a Demanda. */
function CardDoQuadro({ demanda, onAbrir }: { demanda: Demanda; onAbrir: () => void }) {
  const idDosDetalhes = useId();
  const numero = nomeDoNumero(demanda);
  const classificacao = demanda.classificacao;
  const versao = demanda.etapa === "em_producao" ? demanda.versao : null;
  return (
    <button
      type="button"
      onClick={onAbrir}
      aria-label={nomeDoCard(demanda)}
      aria-describedby={idDosDetalhes}
      className="w-full flex flex-col gap-2 p-3 rounded-xl border border-border bg-white text-left shadow-sm transition duration-150 ease-out motion-reduce:transition-none hover:border-primary/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span className="flex items-center justify-between gap-2 min-h-6">
        <span className="normal-case text-[11px] font-medium text-text-secondary">{numero}</span>
        {demanda.responsavel && (
          <span
            aria-hidden="true"
            title={demanda.responsavel}
            className="w-6 h-6 shrink-0 rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center"
          >
            {iniciais(demanda.responsavel)}
          </span>
        )}
      </span>
      <span className="normal-case text-sm font-semibold leading-snug text-text-primary line-clamp-3">
        {demanda.titulo}
      </span>
      <PartesNoCardCompacto demanda={demanda} />
      <span id={idDosDetalhes} className="flex flex-wrap items-center gap-1">
        {classificacao && (
          <span className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${CLASSIFICACAO_CLASSE[classificacao]}`}>
            {CLASSIFICACAO_ROTULO[classificacao]}
          </span>
        )}
        {versao && (
          <span className="normal-case px-1.5 py-0.5 rounded text-[11px] font-medium bg-emerald-100 text-emerald-800">
            {versao}
          </span>
        )}
        {linkDaDemonstracao(demanda) && (
          <span className="px-1.5 py-0.5 rounded text-[11px] font-medium bg-violet-50 text-violet-700">
            {TEM_DEMONSTRACAO}
          </span>
        )}
        {demanda.envio_falhou && (
          <span className="px-1.5 py-0.5 rounded text-[11px] font-medium bg-red-50 text-red-700">{ENVIO_FALHOU}</span>
        )}
        {demanda.responsavel && <span className="sr-only">Responsável: {demanda.responsavel}</span>}
      </span>
    </button>
  );
}

/** Uma coluna: o cabeçalho fixo no topo da página e os cards, sem rolagem própria. */
function ColunaDoQuadroNaTela({ coluna, onAbrir }: { coluna: ColunaDoQuadro; onAbrir: (demanda: Demanda) => void }) {
  return (
    <section aria-label={coluna.rotulo} className="min-w-0 flex flex-col gap-2">
      <h3 className="sticky top-0 z-10 flex items-center justify-between gap-2 py-2 bg-bg text-xs font-semibold text-text-secondary">
        <span>{coluna.rotulo}</span>
        <span className="min-w-6 px-2 py-0.5 rounded-full bg-slate-200 text-center text-text-primary">
          {coluna.contagem}
        </span>
      </h3>
      {coluna.cards.length === 0 ? (
        <p className="px-1 text-xs text-slate-400">{COLUNA_VAZIA}</p>
      ) : (
        <ul className="space-y-2">
          {coluna.cards.map((demanda) => (
            <li key={demanda.id}>
              <CardDoQuadro demanda={demanda} onAbrir={() => onAbrir(demanda)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function QuadroDaTecnologia({
  demandas,
  onAbrir,
}: {
  demandas: Demanda[];
  onAbrir: (demanda: Demanda) => void;
}) {
  // O interruptor de Não será feita vem com a barra do Quadro (issue #1644): aqui, desligado.
  const colunas = colunasDoQuadro(demandas, false, new Date());
  return (
    <section
      aria-label="Quadro"
      data-quadro=""
      className={`grid gap-4 ${colunas.length > 5 ? "grid-cols-6" : "grid-cols-5"}`}
    >
      {colunas.map((coluna) => (
        <ColunaDoQuadroNaTela key={coluna.etapa} coluna={coluna} onAbrir={onAbrir} />
      ))}
    </section>
  );
}
