"use client";

/**
 * A aba Entregas da Tecnologia (issue #1556, PRD #1548; ritmo semanal na issue
 * #1701 e lista por semana na #1703, PRD #1689, ADR 0092).
 *
 * No topo, o ritmo: pedidos e entregas das últimas 4 semanas e o gráfico das
 * últimas 12 (`RitmoDasEntregas`). Embaixo, "O que foi entregue", agrupado por
 * semana, a mais nova em cima. A linha recolhida diz o Tamanho da entrega, o
 * título, o tipo, a versão e a data, com o ícone do vídeo quando há
 * Demonstração. Pela intenção de hover (150 ms para abrir, 180 ms para fechar,
 * o clique fixa, o toque alterna), uma linha por vez abre com o O que muda e
 * os botões Demonstração, Abrir o card e Copiar link. Os filtros de Tipo,
 * Origem e Responsável valem para tudo. Quem conta, filtra e agrupa é o
 * servidor; a tela só desenha e monta a consulta. Nada se move por aqui.
 *
 * O clique numa semana do gráfico mostra na lista só aquela semana e rola até
 * ela, com o botão de desfazer no alto; o segundo clique na barra também
 * desfaz. "Ver semanas anteriores", no fim, pede ao servidor o bloco de 12
 * semanas antes do corte e o põe embaixo; some quando o servidor diz que não
 * há entrega mais antiga. Trocar um filtro recomeça das 12 semanas (issue
 * #1704).
 *
 * Abrir o card mostra o mesmo Documento do card da conversa num painel à
 * direita, como no Quadro: a entrega vem do servidor no formato da lista do
 * chat, e o documento não pede outra coisa.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, Play, X } from "lucide-react";

import { useIntencaoDeHoverDeUmaVez } from "@/hooks/useIntencaoDeHover";
import { useMovimentoReduzido } from "@/hooks/useMovimentoReduzido";

import { Chip, FECHAR_O_PAINEL, GrupoDeChips } from "./ConversasDaTecnologia";
import {
  ASSISTIR_A_DEMONSTRACAO,
  CopiarLink,
  DocumentoDoCard,
  FraseEOQueMuda,
  TITULO_DEMONSTRACAO,
} from "./DocumentoDoCard";
import {
  diaEMes,
  RitmoDasEntregas,
  type SemanaDasEntregas,
  type Tamanho,
  type TopoDasEntregas,
} from "./RitmoDasEntregas";
import {
  BASE_TECNOLOGIA,
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  Classificacao,
  Demanda,
  diaDoHospital,
  FALHA_DE_CONEXAO,
  linkDaDemonstracao,
  Origem,
  ORIGEM_ROTULO,
} from "./demandas";

const URL_DAS_ENTREGAS = `${BASE_TECNOLOGIA}/entregas`;
const ENTREGAS_FALHOU = "Não foi possível carregar as entregas. Tente recarregar a página.";
const NENHUMA_ENTREGA = "Nenhuma entrega com esses filtros.";
const NENHUMA_ENTREGA_NA_SEMANA = "Nenhuma entrega nesta semana.";
const VER_SEMANAS_ANTERIORES = "Ver semanas anteriores";

export const ABRIR_O_CARD = "Abrir o card";

type ResponsavelDasEntregas = { valor: string; nome: string };
/** Uma linha de "O que foi entregue": a Demanda da lista do chat e o Tamanho da entrega. */
type Entrega = Demanda & { tamanho: Tamanho };
/** Uma semana da lista: a segunda-feira (AAAA-MM-DD, dia do hospital) e o que saiu nela. */
type GrupoDasEntregas = { inicio: string; entregas: Entrega[] };
type Entregas = {
  topo: TopoDasEntregas;
  semanas: SemanaDasEntregas[];
  grupos: GrupoDasEntregas[];
  /** O corte do bloco seguinte da lista, `null` quando não há entrega mais antiga. */
  proximo_corte: string | null;
  responsaveis: ResponsavelDasEntregas[];
};

const TAMANHOS: Tamanho[] = ["G", "M", "P"];
const PARTES_DO_TAMANHO: Record<Tamanho, string> = {
  G: "6 partes ou mais",
  M: "de 2 a 5 partes",
  P: "até 1 parte",
};

const CLASSIFICACOES = Object.keys(CLASSIFICACAO_ROTULO) as Classificacao[];
const ORIGENS = Object.keys(ORIGEM_ROTULO) as Origem[];

type Filtros = {
  tipo: Classificacao | null;
  origem: Origem | null;
  responsavel: string | null;
};

function urlDasEntregas(filtros: Filtros, corte: string | null = null): string {
  const consulta = new URLSearchParams();
  if (filtros.tipo) consulta.set("tipo", filtros.tipo);
  if (filtros.origem) consulta.set("origem", filtros.origem);
  if (filtros.responsavel) consulta.set("responsavel", filtros.responsavel);
  if (corte) consulta.set("corte", corte);
  const texto = consulta.toString();
  return texto ? `${URL_DAS_ENTREGAS}?${texto}` : URL_DAS_ENTREGAS;
}

function entregasValidas(corpo: unknown): Entregas | null {
  if (typeof corpo !== "object" || corpo === null) return null;
  const c = corpo as Partial<Entregas>;
  if (typeof c.topo !== "object" || c.topo === null || !Array.isArray(c.semanas) || !Array.isArray(c.grupos)) {
    return null;
  }
  return {
    topo: c.topo,
    semanas: c.semanas,
    grupos: c.grupos
      .filter((g) => typeof g?.inicio === "string" && Array.isArray(g?.entregas))
      .map((g) => ({
        inicio: g.inicio,
        entregas: g.entregas.filter((d) => typeof d?.id === "string" && typeof d?.titulo === "string"),
      }))
      .filter((g) => g.entregas.length > 0),
    proximo_corte: typeof c.proximo_corte === "string" ? c.proximo_corte : null,
    responsaveis: Array.isArray(c.responsaveis) ? c.responsaveis : [],
  };
}

/** "Semana de 09/11: 3 entregas (1 G, 2 P)": o início lido como texto, sem fuso. */
function cabecalhoDaSemana(grupo: GrupoDasEntregas): string {
  const total = grupo.entregas.length;
  const tamanhos = TAMANHOS.map((t) => [t, grupo.entregas.filter((e) => e.tamanho === t).length] as const)
    .filter(([, n]) => n > 0)
    .map(([t, n]) => `${n} ${t}`);
  return `Semana de ${diaEMes(grupo.inicio)}: ${total} ${total === 1 ? "entrega" : "entregas"} (${tamanhos.join(", ")})`;
}

const BOTAO_DA_LINHA =
  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-primary border border-primary/30 hover:bg-primary/5";

type EventosDaLinha = { onMouseEnter: () => void; onMouseLeave: () => void; onClick: () => void };

/**
 * Uma entrega da lista. O mouse entra e sai pelo item inteiro, para o caminho
 * até os botões não fechar a linha; o clique (e o toque) é só no botão da
 * linha, para o clique num botão de dentro não a soltar. O vídeo fica fora
 * do botão: link dentro de botão não é HTML válido.
 */
function LinhaDaEntrega({
  entrega,
  aberta,
  eventos,
  parado,
  onAbrirOCard,
}: {
  entrega: Entrega;
  aberta: boolean;
  eventos: EventosDaLinha;
  parado: boolean;
  onAbrirOCard: () => void;
}) {
  const id = useId();
  const demonstracao = linkDaDemonstracao(entrega);
  const classificacao = entrega.classificacao;
  const dia = diaDoHospital(entrega.fechada_em);
  return (
    <li onMouseEnter={eventos.onMouseEnter} onMouseLeave={eventos.onMouseLeave}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={eventos.onClick}
          aria-expanded={aberta}
          aria-controls={id}
          className={`min-w-0 flex-1 flex flex-wrap items-center gap-2 px-3 py-2 rounded-xl border text-left text-sm transition-colors ${
            aberta ? "border-primary/40 bg-primary/5" : "border-transparent hover:border-border hover:bg-slate-50"
          }`}
        >
          <span
            title={PARTES_DO_TAMANHO[entrega.tamanho]}
            className="w-6 h-6 shrink-0 rounded-md bg-primary/10 text-primary text-xs font-bold flex items-center justify-center"
          >
            {entrega.tamanho}
          </span>
          <span className="normal-case min-w-0 flex-1 font-medium text-text-primary line-clamp-2">{entrega.titulo}</span>
          {classificacao && (
            <span className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${CLASSIFICACAO_CLASSE[classificacao]}`}>
              {CLASSIFICACAO_ROTULO[classificacao]}
            </span>
          )}
          {entrega.versao && (
            <span className="normal-case px-1.5 py-0.5 rounded text-[11px] font-medium bg-emerald-100 text-emerald-800">
              {entrega.versao}
            </span>
          )}
          {dia && <span className="normal-case text-xs text-text-secondary tabular-nums">{dia}</span>}
        </button>
        {demonstracao && (
          <a
            href={demonstracao}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={ASSISTIR_A_DEMONSTRACAO}
            title={ASSISTIR_A_DEMONSTRACAO}
            className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Play aria-hidden="true" className="w-3.5 h-3.5 ml-0.5" fill="currentColor" />
          </a>
        )}
      </div>
      {aberta && (
        <div
          id={id}
          role="region"
          aria-label={`O que mudou: ${entrega.titulo}`}
          className={`mx-3 mt-1 mb-2 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 space-y-2 ${
            parado ? "" : "animate-fade-in-up"
          }`}
        >
          <FraseEOQueMuda texto={entrega.o_que_muda} chave={entrega.id} />
          <div className="flex flex-wrap items-center gap-2">
            {demonstracao && (
              <a href={demonstracao} target="_blank" rel="noopener noreferrer" className={BOTAO_DA_LINHA}>
                <Play aria-hidden="true" className="w-3 h-3" fill="currentColor" />
                {TITULO_DEMONSTRACAO}
              </a>
            )}
            <button type="button" onClick={onAbrirOCard} className={BOTAO_DA_LINHA}>
              {ABRIR_O_CARD}
            </button>
            <CopiarLink demanda={entrega} />
          </div>
        </div>
      )}
    </li>
  );
}

/**
 * O Documento do card num painel à direita, como no Quadro (issue #1643): por
 * cima da aba, fecha pelo X ou pelo Esc. Portal no body, porque o wrapper
 * animado do módulo prenderia o `fixed` à caixa dele.
 */
function PainelDoCard({ demanda, onFechar }: { demanda: Demanda; onFechar: () => void }) {
  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") onFechar();
    }
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [onFechar]);

  return createPortal(
    <aside
      aria-label="Pedido aberto"
      className="fixed top-16 bottom-0 right-0 z-40 w-[min(40rem,100vw)] overflow-y-auto border-l border-border bg-bg shadow-premium-strong p-5 space-y-3 animate-fade-in-right"
    >
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onFechar}
          aria-label={FECHAR_O_PAINEL}
          title={FECHAR_O_PAINEL}
          className="w-9 h-9 inline-flex items-center justify-center rounded-xl text-text-secondary hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <DocumentoDoCard key={demanda.id} demanda={demanda} />
    </aside>,
    document.body,
  );
}

export function EntregasDaTecnologia({ token }: { token: string | null }) {
  const [tipo, setTipo] = useState<Classificacao | null>(null);
  const [origem, setOrigem] = useState<Origem | null>(null);
  const [responsavel, setResponsavel] = useState<string | null>(null);
  const [dados, setDados] = useState<Entregas | null>(null);
  /** Os blocos de "Ver semanas anteriores", embaixo das 12 semanas, e o corte do próximo. */
  const [anteriores, setAnteriores] = useState<GrupoDasEntregas[]>([]);
  const [corte, setCorte] = useState<string | null>(null);
  const [carregandoAnteriores, setCarregandoAnteriores] = useState(false);
  /** A semana que o clique no gráfico marcou; a lista mostra só ela. */
  const [semana, setSemana] = useState<string | null>(null);
  const listaRef = useRef<HTMLElement>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [noPainel, setNoPainel] = useState<Demanda | null>(null);
  const { aberta, alvo } = useIntencaoDeHoverDeUmaVez<string>();
  const parado = useMovimentoReduzido();
  const fecharPainel = useCallback(() => setNoPainel(null), []);
  /** A resposta de um pedido mais velho não sobrescreve a do novo. */
  const ultimoPedido = useRef(0);

  const carregar = useCallback(async () => {
    if (!token) return;
    const pedido = ++ultimoPedido.current;
    try {
      const resposta = await fetch(urlDasEntregas({ tipo, origem, responsavel }), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (pedido !== ultimoPedido.current) return;
      const lidas = resposta.ok ? entregasValidas(await resposta.json()) : null;
      if (pedido !== ultimoPedido.current) return;
      setDados(lidas);
      setAnteriores([]);
      setCorte(lidas?.proximo_corte ?? null);
      setErro(lidas ? null : ENTREGAS_FALHOU);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as entregas", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }, [token, tipo, origem, responsavel]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  /** O bloco seguinte, com os mesmos filtros; descartado se um filtro mudou no meio. */
  async function carregarAnteriores() {
    if (!token || !corte || carregandoAnteriores) return;
    const pedido = ultimoPedido.current;
    setCarregandoAnteriores(true);
    try {
      const resposta = await fetch(urlDasEntregas({ tipo, origem, responsavel }, corte), {
        headers: { Authorization: `Bearer ${token}` },
      });
      const lidas = resposta.ok ? entregasValidas(await resposta.json()) : null;
      if (pedido !== ultimoPedido.current) return;
      if (!lidas) {
        setErro(ENTREGAS_FALHOU);
        return;
      }
      setAnteriores((atuais) => [...atuais, ...lidas.grupos]);
      setCorte(lidas.proximo_corte);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as semanas anteriores", e);
      if (pedido === ultimoPedido.current) setErro(FALHA_DE_CONEXAO);
    } finally {
      setCarregandoAnteriores(false);
    }
  }

  const clicarNaSemana = useCallback((inicio: string) => {
    setSemana((atual) => (atual === inicio ? null : inicio));
  }, []);

  useEffect(() => {
    if (semana) listaRef.current?.scrollIntoView?.({ behavior: parado ? "auto" : "smooth", block: "start" });
  }, [semana, parado]);

  const todos = dados ? [...dados.grupos, ...anteriores] : [];
  const grupos = semana ? todos.filter((g) => g.inicio === semana) : todos;

  return (
    <div className="space-y-4">
      <section role="region" aria-label="Filtros das entregas" className="space-y-2">
        <GrupoDeChips rotulo="Tipo">
          {CLASSIFICACOES.map((valor) => (
            <Chip key={valor} ativo={tipo === valor} onClick={() => setTipo(tipo === valor ? null : valor)}>
              {CLASSIFICACAO_ROTULO[valor]}
            </Chip>
          ))}
        </GrupoDeChips>
        <GrupoDeChips rotulo="Origem">
          {ORIGENS.map((valor) => (
            <Chip key={valor} ativo={origem === valor} onClick={() => setOrigem(origem === valor ? null : valor)}>
              {ORIGEM_ROTULO[valor]}
            </Chip>
          ))}
        </GrupoDeChips>
        {dados && dados.responsaveis.length > 0 && (
          <GrupoDeChips rotulo="Responsável">
            {dados.responsaveis.map((r) => (
              <Chip
                key={r.valor}
                ativo={responsavel === r.valor}
                onClick={() => setResponsavel(responsavel === r.valor ? null : r.valor)}
              >
                {r.nome}
              </Chip>
            ))}
          </GrupoDeChips>
        )}
      </section>

      {dados !== null && (
        <RitmoDasEntregas
          topo={dados.topo}
          semanas={dados.semanas}
          semanaMarcada={semana}
          onClicarNaSemana={clicarNaSemana}
        />
      )}

      <section ref={listaRef} role="region" aria-label="O que foi entregue" className="space-y-3 scroll-mt-20">
        {semana && (
          <button
            type="button"
            onClick={() => setSemana(null)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-primary border border-primary/30 bg-primary/5 hover:bg-primary/10"
          >
            Semana de {diaEMes(semana)}, mostrar todas
          </button>
        )}
        {erro && (
          <p role="alert" className="px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            {erro}
          </p>
        )}
        {dados === null && !erro && (
          <p role="status" className="flex items-center gap-2 px-1 text-xs text-text-secondary">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Carregando as entregas...
          </p>
        )}
        {dados !== null && grupos.length === 0 && (
          <p className="px-1 text-sm text-text-secondary">{semana ? NENHUMA_ENTREGA_NA_SEMANA : NENHUMA_ENTREGA}</p>
        )}
        {grupos.map((grupo) => (
          <div key={grupo.inicio} className="space-y-1">
            <h3 className="px-1 text-xs font-medium text-text-secondary">{cabecalhoDaSemana(grupo)}</h3>
            <ul className="space-y-1">
              {grupo.entregas.map((entrega) => (
                <LinhaDaEntrega
                  key={entrega.id}
                  entrega={entrega}
                  aberta={aberta === entrega.id}
                  eventos={alvo(entrega.id)}
                  parado={parado}
                  onAbrirOCard={() => setNoPainel(entrega)}
                />
              ))}
            </ul>
          </div>
        ))}
        {dados !== null && !semana && corte && (
          <button
            type="button"
            onClick={carregarAnteriores}
            disabled={carregandoAnteriores}
            className={`${BOTAO_DA_LINHA} disabled:opacity-60`}
          >
            {carregandoAnteriores && <Loader2 aria-hidden="true" className="w-3 h-3 animate-spin" />}
            {VER_SEMANAS_ANTERIORES}
          </button>
        )}
      </section>

      {noPainel && <PainelDoCard demanda={noPainel} onFechar={fecharPainel} />}
    </div>
  );
}
