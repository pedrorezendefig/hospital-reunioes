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
 * iniciais do Responsável, partes do PRD, a versão em Em produção, o selo
 * "Envio falhou" e o botão do vídeo da Demonstração. Data, quem pediu e o
 * "Conversar" ficam na Demanda aberta.
 */

import { Play } from "lucide-react";
import { useId } from "react";

import { ASSISTIR_A_DEMONSTRACAO } from "./DocumentoDoCard";

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
} from "./demandas";

const COLUNA_VAZIA = "Nenhum pedido.";
/** O pé da coluna Entregue: as Entregas guardam também o que passou dos 30 dias (issue #1644). */
export const VER_TODOS_NAS_ENTREGAS = "Ver todos nas Entregas";

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
        <span
          className="block h-full rounded-full bg-emerald-500"
          style={{ width: largura }}
        />
      </span>
      <span className="normal-case text-[11px] font-medium text-text-secondary whitespace-nowrap">
        {partes.entregues} de {partes.total} partes
      </span>
    </span>
  );
}

/**
 * O vídeo da Demonstração direto do card, sem abrir a Demanda: um botão
 * redondo com o play, num brilho que passa devagar (não pisca). Fica fora do
 * botão do card, porque link dentro de botão não é HTML válido; por isso vem
 * por cima, no canto de baixo.
 */
function VideoDaDemonstracao({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={ASSISTIR_A_DEMONSTRACAO}
      title={ASSISTIR_A_DEMONSTRACAO}
      className="brilho-da-demonstracao absolute bottom-2.5 right-2.5 w-8 h-8 rounded-full flex items-center justify-center bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-md shadow-violet-500/40 ring-2 ring-violet-200 transition duration-150 ease-out motion-reduce:transition-none hover:scale-110 hover:shadow-lg hover:shadow-violet-500/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
    >
      <Play
        aria-hidden="true"
        className="w-3.5 h-3.5 ml-0.5"
        fill="currentColor"
      />
    </a>
  );
}

/**
 * Um card do Quadro: um botão que abre a Demanda e, quando há vídeo, o botão
 * da Demonstração ao lado, que abre o vídeo direto. O `data-demanda` é por
 * onde o painel devolve o foco ao card quando fecha (issue #1643).
 */
function CardDoQuadro({
  demanda,
  onAbrir,
}: {
  demanda: Demanda;
  onAbrir: () => void;
}) {
  const idDosDetalhes = useId();
  const numero = nomeDoNumero(demanda);
  const classificacao = demanda.classificacao;
  const versao = demanda.etapa === "em_producao" ? demanda.versao : null;
  const demonstracao = linkDaDemonstracao(demanda);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onAbrir}
        data-demanda={demanda.id}
        aria-label={nomeDoCard(demanda)}
        aria-describedby={idDosDetalhes}
        className="w-full flex flex-col gap-2 p-3 rounded-xl border border-border bg-white text-left shadow-sm transition duration-150 ease-out motion-reduce:transition-none hover:border-primary/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="flex items-center justify-between gap-2 min-h-6">
          <span className="normal-case text-[11px] font-medium text-text-secondary">
            {numero}
          </span>
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
        <span
          id={idDosDetalhes}
          className={`flex flex-wrap items-center gap-1 ${demonstracao ? "min-h-6 pr-10" : ""}`}
        >
          {classificacao && (
            <span
              className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${CLASSIFICACAO_CLASSE[classificacao]}`}
            >
              {CLASSIFICACAO_ROTULO[classificacao]}
            </span>
          )}
          {versao && (
            <span className="normal-case px-1.5 py-0.5 rounded text-[11px] font-medium bg-emerald-100 text-emerald-800">
              {versao}
            </span>
          )}
          {demanda.envio_falhou && (
            <span className="px-1.5 py-0.5 rounded text-[11px] font-medium bg-red-50 text-red-700">
              {ENVIO_FALHOU}
            </span>
          )}
          {demanda.responsavel && (
            <span className="sr-only">Responsável: {demanda.responsavel}</span>
          )}
        </span>
      </button>
      {demonstracao && <VideoDaDemonstracao url={demonstracao} />}
    </div>
  );
}

/**
 * Uma coluna: o cabeçalho fixo no topo da página e os cards, sem rolagem
 * própria. A Entregue tem no pé o "Ver todos nas Entregas", sempre à vista.
 */
function ColunaDoQuadroNaTela({
  coluna,
  onAbrir,
  onVerEntregas,
}: {
  coluna: ColunaDoQuadro;
  onAbrir: (demanda: Demanda) => void;
  onVerEntregas?: () => void;
}) {
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
              <CardDoQuadro
                demanda={demanda}
                onAbrir={() => onAbrir(demanda)}
              />
            </li>
          ))}
        </ul>
      )}
      {coluna.etapa === "entregue" && onVerEntregas && (
        <button
          type="button"
          onClick={onVerEntregas}
          className="self-start px-1 text-xs font-semibold text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
        >
          {VER_TODOS_NAS_ENTREGAS}
        </button>
      )}
    </section>
  );
}

export function QuadroDaTecnologia({
  demandas,
  comNaoSeraFeita,
  onAbrir,
  onVerEntregas,
}: {
  demandas: Demanda[];
  /** O interruptor "Mostrar as que não serão feitas" da barra: a sexta coluna, no fim. */
  comNaoSeraFeita: boolean;
  onAbrir: (demanda: Demanda) => void;
  /** Troca para a aba Entregas; quem passa é o módulo da aba. */
  onVerEntregas?: () => void;
}) {
  const colunas = colunasDoQuadro(demandas, comNaoSeraFeita, new Date());
  return (
    <section
      aria-label="Quadro"
      data-quadro=""
      className={`grid gap-4 ${colunas.length > 5 ? "grid-cols-6" : "grid-cols-5"}`}
    >
      {colunas.map((coluna) => (
        <ColunaDoQuadroNaTela
          key={coluna.etapa}
          coluna={coluna}
          onAbrir={onAbrir}
          onVerEntregas={onVerEntregas}
        />
      ))}
    </section>
  );
}
