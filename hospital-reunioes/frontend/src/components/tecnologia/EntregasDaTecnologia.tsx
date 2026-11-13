"use client";

/**
 * A aba Entregas da Tecnologia (issue #1556, PRD #1548; ritmo semanal na issue
 * #1701, PRD #1689, ADR 0092).
 *
 * No topo, o ritmo: pedidos e entregas das últimas 4 semanas e o gráfico das
 * últimas 12 (`RitmoDasEntregas`). Embaixo, a lista do que já foi entregue,
 * com a data de entrega, a data em produção e o Responsável. Os filtros de
 * Tipo, Origem e Responsável valem para tudo. Quem conta, filtra e decide o
 * que entra é o servidor; a tela só desenha e monta a consulta. Nada se move
 * por aqui: não há botão que mude Etapa ou Responsável.
 *
 * O clique num card abre o mesmo Documento do card da conversa: a entrega vem
 * do servidor no formato da lista do chat, e o documento não pede outra coisa.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Chip, GrupoDeChips } from "./ConversasDaTecnologia";
import { DocumentoDoCard } from "./DocumentoDoCard";
import { RitmoDasEntregas, type SemanaDasEntregas, type TopoDasEntregas } from "./RitmoDasEntregas";
import {
  BASE_TECNOLOGIA,
  CLASSIFICACAO_ROTULO,
  Classificacao,
  Demanda,
  diaDoHospital,
  FALHA_DE_CONEXAO,
  Origem,
  ORIGEM_ROTULO,
} from "./demandas";

const URL_DAS_ENTREGAS = `${BASE_TECNOLOGIA}/entregas`;
const ENTREGAS_FALHOU = "Não foi possível carregar as entregas. Tente recarregar a página.";
const NENHUMA_ENTREGA = "Nenhuma entrega com esses filtros.";

type ResponsavelDasEntregas = { valor: string; nome: string };
type Entregas = {
  topo: TopoDasEntregas;
  semanas: SemanaDasEntregas[];
  entregas: Demanda[];
  responsaveis: ResponsavelDasEntregas[];
};

const CLASSIFICACOES = Object.keys(CLASSIFICACAO_ROTULO) as Classificacao[];
const ORIGENS = Object.keys(ORIGEM_ROTULO) as Origem[];

type Filtros = {
  tipo: Classificacao | null;
  origem: Origem | null;
  responsavel: string | null;
};

function urlDasEntregas(filtros: Filtros): string {
  const consulta = new URLSearchParams();
  if (filtros.tipo) consulta.set("tipo", filtros.tipo);
  if (filtros.origem) consulta.set("origem", filtros.origem);
  if (filtros.responsavel) consulta.set("responsavel", filtros.responsavel);
  const texto = consulta.toString();
  return texto ? `${URL_DAS_ENTREGAS}?${texto}` : URL_DAS_ENTREGAS;
}

function entregasValidas(corpo: unknown): Entregas | null {
  if (typeof corpo !== "object" || corpo === null) return null;
  const c = corpo as Partial<Entregas>;
  if (typeof c.topo !== "object" || c.topo === null || !Array.isArray(c.semanas) || !Array.isArray(c.entregas)) {
    return null;
  }
  return {
    topo: c.topo,
    semanas: c.semanas,
    entregas: c.entregas.filter((d) => typeof d?.id === "string" && typeof d?.titulo === "string"),
    responsaveis: Array.isArray(c.responsaveis) ? c.responsaveis : [],
  };
}

export function EntregasDaTecnologia({ token }: { token: string | null }) {
  const [tipo, setTipo] = useState<Classificacao | null>(null);
  const [origem, setOrigem] = useState<Origem | null>(null);
  const [responsavel, setResponsavel] = useState<string | null>(null);
  const [dados, setDados] = useState<Entregas | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<Demanda | null>(null);
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
      setErro(lidas ? null : ENTREGAS_FALHOU);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as entregas", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }, [token, tipo, origem, responsavel]);

  useEffect(() => {
    carregar();
  }, [carregar]);

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

      {dados !== null && <RitmoDasEntregas topo={dados.topo} semanas={dados.semanas} />}

      <div className="md:grid md:grid-cols-[22rem_minmax(0,1fr)] md:gap-4 md:items-start">
        <div className="space-y-3">
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
          {dados !== null && dados.entregas.length === 0 && (
            <p className="px-1 text-sm text-text-secondary">{NENHUMA_ENTREGA}</p>
          )}
          {dados !== null && dados.entregas.length > 0 && (
            <ul aria-label="Cards entregues" className="space-y-1 md:max-h-[calc(100vh-24rem)] md:overflow-y-auto">
              {dados.entregas.map((entrega) => {
                const entregueEm = diaDoHospital(entrega.fechada_em);
                const emProducaoEm = diaDoHospital(entrega.em_producao_em);
                return (
                  <li key={entrega.id}>
                    <button
                      type="button"
                      onClick={() => setAberta(entrega)}
                      aria-current={aberta?.id === entrega.id ? "true" : undefined}
                      className={`w-full flex flex-col gap-0.5 px-3 py-2 rounded-xl border text-left text-sm transition-colors ${
                        aberta?.id === entrega.id
                          ? "border-primary bg-primary/5"
                          : "border-transparent hover:border-border hover:bg-slate-50"
                      }`}
                    >
                      <span className="normal-case font-medium text-text-primary line-clamp-2">{entrega.titulo}</span>
                      {entregueEm && (
                        <span className="normal-case text-xs text-text-secondary">Entregue em {entregueEm}</span>
                      )}
                      {emProducaoEm && (
                        <span className="normal-case text-xs text-text-secondary">Em produção em {emProducaoEm}</span>
                      )}
                      {entrega.responsavel && (
                        <span className="normal-case text-xs text-text-secondary">
                          Responsável: {entrega.responsavel}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="min-w-0 mt-4 md:mt-0">{aberta && <DocumentoDoCard key={aberta.id} demanda={aberta} />}</div>
      </div>
    </div>
  );
}
