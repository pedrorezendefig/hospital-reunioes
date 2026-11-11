"use client";

/**
 * A aba Entregas da Tecnologia (issue #1556, PRD #1548, ADR 0084, decisão 8).
 *
 * O retrato do que já foi entregue: quantos cards por semana ou por mês, e a
 * lista deles com a data de entrega, a data em produção e o Responsável. Quem
 * conta, filtra e decide o que entra é o servidor; a tela só desenha e monta a
 * consulta. Nada se move por aqui: não há botão que mude Etapa ou Responsável.
 *
 * O clique num card abre o mesmo Documento do card da conversa: a entrega vem
 * do servidor no formato da lista do chat, e o documento não pede outra coisa.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Chip, GrupoDeChips } from "./ConversasDaTecnologia";
import { DocumentoDoCard } from "./DocumentoDoCard";
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

type Agrupar = "semana" | "mes";
type Periodo = { inicio: string; total: number };
type ResponsavelDasEntregas = { valor: string; nome: string };
type Entregas = { agrupar: Agrupar; periodos: Periodo[]; entregas: Demanda[]; responsaveis: ResponsavelDasEntregas[] };

const AGRUPAMENTOS: { valor: Agrupar; rotulo: string }[] = [
  { valor: "semana", rotulo: "Por semana" },
  { valor: "mes", rotulo: "Por mês" },
];
const CLASSIFICACOES = Object.keys(CLASSIFICACAO_ROTULO) as Classificacao[];
const ORIGENS = Object.keys(ORIGEM_ROTULO) as Origem[];
const MESES = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

/**
 * O período como a tela o diz. O início vem como dia do hospital (AAAA-MM-DD),
 * e é lido como texto: passar por `Date` o jogaria para o dia anterior em UTC-3.
 */
export function rotuloDoPeriodo(inicio: string, agrupar: Agrupar): string {
  const [ano, mes, dia] = inicio.split("-");
  if (agrupar === "mes") return `${MESES[Number(mes) - 1] ?? mes} de ${ano}`;
  return `Semana de ${dia}/${mes}/${ano}`;
}

type Filtros = {
  agrupar: Agrupar;
  de: string;
  ate: string;
  tipo: Classificacao | null;
  origem: Origem | null;
  responsavel: string | null;
};

function urlDasEntregas(filtros: Filtros): string {
  const consulta = new URLSearchParams({ agrupar: filtros.agrupar });
  if (filtros.de) consulta.set("de", filtros.de);
  if (filtros.ate) consulta.set("ate", filtros.ate);
  if (filtros.tipo) consulta.set("tipo", filtros.tipo);
  if (filtros.origem) consulta.set("origem", filtros.origem);
  if (filtros.responsavel) consulta.set("responsavel", filtros.responsavel);
  return `${URL_DAS_ENTREGAS}?${consulta.toString()}`;
}

function entregasValidas(corpo: unknown): Entregas | null {
  if (typeof corpo !== "object" || corpo === null) return null;
  const c = corpo as Partial<Entregas>;
  if (!Array.isArray(c.periodos) || !Array.isArray(c.entregas)) return null;
  return {
    agrupar: c.agrupar === "mes" ? "mes" : "semana",
    periodos: c.periodos,
    entregas: c.entregas.filter((d) => typeof d?.id === "string" && typeof d?.titulo === "string"),
    responsaveis: Array.isArray(c.responsaveis) ? c.responsaveis : [],
  };
}

function CampoDeData({ rotulo, valor, onChange }: { rotulo: string; valor: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs text-text-secondary">
      {rotulo}
      <input
        type="date"
        aria-label={rotulo}
        value={valor}
        onChange={(e) => onChange(e.target.value)}
        className="px-2 py-1 rounded-lg border border-border text-sm text-text"
      />
    </label>
  );
}

export function EntregasDaTecnologia({ token }: { token: string | null }) {
  const [agrupar, setAgrupar] = useState<Agrupar>("semana");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
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
      const resposta = await fetch(urlDasEntregas({ agrupar, de, ate, tipo, origem, responsavel }), {
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
  }, [token, agrupar, de, ate, tipo, origem, responsavel]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  return (
    <div className="md:grid md:grid-cols-[22rem_minmax(0,1fr)] md:gap-4 md:items-start">
      <div className="space-y-3">
        <section role="region" aria-label="Filtros das entregas" className="space-y-2">
          <GrupoDeChips rotulo="Agrupar">
            {AGRUPAMENTOS.map(({ valor, rotulo }) => (
              <Chip key={valor} ativo={agrupar === valor} onClick={() => setAgrupar(valor)}>
                {rotulo}
              </Chip>
            ))}
          </GrupoDeChips>
          <div className="flex flex-wrap gap-2">
            <CampoDeData rotulo="De" valor={de} onChange={setDe} />
            <CampoDeData rotulo="Até" valor={ate} onChange={setAte} />
          </div>
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
        {dados !== null && dados.periodos.length > 0 && (
          <ul aria-label="Entregues por período" className="space-y-1 text-sm text-text">
            {dados.periodos.map((p) => (
              <li key={p.inicio} className="flex justify-between px-3 py-1 rounded-lg bg-slate-50">
                {rotuloDoPeriodo(p.inicio, dados.agrupar)}: {p.total}
              </li>
            ))}
          </ul>
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
  );
}
