"use client";

/**
 * O Quadro de Demandas (issue #637, PRD #634, ADR 0050).
 *
 * Cinco colunas. Concluída e Cancelada nascem recolhidas, com o contador à
 * vista: recolher é dar espaço às colunas vivas, não esconder o que fechou.
 *
 * O card mostra o que evita abrir o modal: símbolo do tipo, título, Produto,
 * responsável, prioridade, idade em dias (vermelha a partir de 14) e a marca de
 * atrasado. Idade e atraso são coisas diferentes, e o card diz as duas: sem
 * prazo a Demanda não atrasa, só envelhece (ADR 0050, decisão 5).
 *
 * Arrastar entre colunas e a tela de filtros são da issue #639: aqui o gesto é
 * o botão "Mover", que fala com o mesmo endpoint.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CalendarClock, Plus } from "lucide-react";

import { Select } from "@/components/ui/Select";

import { DemandaModal } from "./DemandaModal";
import { TipoIcone } from "./TipoIcone";
import {
  BASE_TECNOLOGIA,
  COLUNAS_RECOLHIDAS,
  Demanda,
  destinosDe,
  ESTADO_ROTULO,
  ESTADOS,
  EstadoDemanda,
  estaAtrasado,
  FALHA_DE_CONEXAO,
  idadeEmDias,
  IDADE_VERMELHA_A_PARTIR_DE,
  motivoDaRecusa,
  PessoaDaAba,
  PRIORIDADE_ROTULO,
  PRIORIDADES,
  PrioridadeDemanda,
  prazoLegivel,
  ProdutoDaEscolha,
  textoDaIdade,
  TIPO_ROTULO,
  TIPOS,
  TipoDemanda,
} from "./demandas";

type Props = {
  token: string | null;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
};

const CLASSE_PRIORIDADE: Record<PrioridadeDemanda, string> = {
  baixa: "bg-slate-100 text-slate-500",
  normal: "bg-sky-50 text-sky-700",
  alta: "bg-amber-50 text-amber-700",
};

/**
 * A frase de quando `useAuth` não devolve token.
 *
 * Ela NÃO manda entrar de novo, pelo mesmo motivo do módulo: o hook devolve
 * `token: null` tanto com a sessão acabada quanto com o `getUser()` dele
 * falhando por rede, e o componente não distingue as duas. Recarregar é
 * possível nos dois casos.
 */
const SEM_SESSAO =
  "Não foi possível carregar as Demandas: a sessão não está ativa ou o servidor não respondeu. Tente recarregar a página.";

const FORM_VAZIO = {
  titulo: "",
  tipo: "decisao" as TipoDemanda,
  produto_id: "",
  prioridade: "normal" as PrioridadeDemanda,
  descricao: "",
};

export function QuadroDemandas({ token, produtos, pessoas }: Props) {
  const [demandas, setDemandas] = useState<Demanda[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [expandidas, setExpandidas] = useState<EstadoDemanda[]>([]);
  const [abrindoForm, setAbrindoForm] = useState(false);
  const [form, setForm] = useState(FORM_VAZIO);
  const [moverAberto, setMoverAberto] = useState<string | null>(null);
  const [abertaId, setAbertaId] = useState<string | null>(null);

  const autorizacao = useCallback(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  /**
   * Carrega o Quadro.
   *
   * A falha de rede vira AVISO, e não quadro vazio: sem o `catch`, o backend
   * fora do ar desenharia cinco colunas zeradas, que é indistinguível de "não
   * há Demanda nenhuma" e derruba o critério de aceite do Quadro.
   */
  const carregar = useCallback(async () => {
    if (!token) return;
    setCarregando(true);
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}/demandas`, { headers: autorizacao() });
      if (!resposta.ok) {
        setErro("Não foi possível carregar as Demandas.");
        return;
      }
      setDemandas(await resposta.json());
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as Demandas", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setCarregando(false);
    }
  }, [token, autorizacao]);

  useEffect(() => {
    if (!token) {
      // Sem token o Quadro desenharia cinco colunas zeradas, calado, que é
      // indistinguível de "não há Demanda nenhuma". O aviso do módulo não
      // cobre este caso: ele fala de Produtos e mora abaixo do Quadro.
      setCarregando(false);
      setErro(SEM_SESSAO);
      return;
    }
    carregar();
  }, [token, carregar]);

  async function enviar(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    let resposta: Response;
    try {
      resposta = await fetch(url, { method: metodo, headers: autorizacao(), body: JSON.stringify(corpo) });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao salvar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
      return false;
    }
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      return false;
    }
    setErro(null);
    await carregar();
    return true;
  }

  async function criarDemanda() {
    const criada = await enviar(`${BASE_TECNOLOGIA}/demandas`, "POST", {
      titulo: form.titulo,
      tipo: form.tipo,
      produto_id: form.produto_id,
      prioridade: form.prioridade,
      descricao: form.descricao,
    });
    if (criada) {
      setForm(FORM_VAZIO);
      setAbrindoForm(false);
    }
  }

  async function mover(demanda: Demanda, estado: EstadoDemanda) {
    setMoverAberto(null);
    await enviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/mover`, "POST", { estado });
  }

  const produtosAtivos = produtos.filter((p) => p.ativo);
  const aberta = demandas.find((d) => d.id === abertaId) ?? null;
  const agora = new Date();

  function coluna(estado: EstadoDemanda) {
    return demandas.filter((d) => d.estado === estado);
  }

  function cartao(demanda: Demanda) {
    const dias = idadeEmDias(demanda.criado_em, agora);
    const velha = dias >= IDADE_VERMELHA_A_PARTIR_DE;
    const atrasada = estaAtrasado(demanda.prazo, agora);

    return (
      <li key={demanda.id} className="rounded-xl border border-border bg-white p-3 space-y-2 shadow-sm">
        <button
          type="button"
          onClick={() => setAbertaId(demanda.id)}
          className="flex items-start gap-2 w-full text-left"
        >
          <span className="mt-0.5 text-primary">
            <TipoIcone tipo={demanda.tipo} />
          </span>
          <span className="text-sm font-medium text-text">{demanda.titulo}</span>
        </button>

        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <span>{demanda.produto_nome ?? "Sem Produto"}</span>
          <span>{demanda.responsavel_nome ?? "Sem responsável"}</span>
          <span className={`px-2 py-0.5 rounded font-medium ${CLASSE_PRIORIDADE[demanda.prioridade]}`}>
            {PRIORIDADE_ROTULO[demanda.prioridade]}
          </span>
          <span className={velha ? "font-semibold text-red-600" : ""}>{textoDaIdade(dias)}</span>
          {atrasada && demanda.prazo && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-medium bg-red-50 text-red-700">
              <CalendarClock className="w-3 h-3" />
              Atrasada desde {prazoLegivel(demanda.prazo)}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-label={`Mover ${demanda.titulo}`}
            onClick={() => setMoverAberto(moverAberto === demanda.id ? null : demanda.id)}
            className="px-2 py-1 rounded-lg border border-border text-xs text-text-secondary hover:border-primary hover:text-primary transition-colors"
          >
            Mover
          </button>
          {moverAberto === demanda.id &&
            destinosDe(demanda.estado).map((destino) => (
              <button
                key={destino}
                type="button"
                onClick={() => mover(demanda, destino)}
                className="px-2 py-1 rounded-lg bg-primary/5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
              >
                {ESTADO_ROTULO[destino]}
              </button>
            ))}
        </div>
      </li>
    );
  }

  return (
    <div className="space-y-4">
      {erro && (
        <p
          role="alert"
          className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erro}</span>
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-text-secondary">
          A Demanda nasce em Nova, com o dono do Produto como responsável.
        </p>
        <button
          type="button"
          onClick={() => setAbrindoForm(!abrindoForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" />
          Nova Demanda
        </button>
      </div>

      {abrindoForm && (
        <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="text"
              aria-label="Título"
              placeholder="O que precisa acontecer"
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white md:col-span-2"
            />
            <Select
              label="Tipo"
              value={form.tipo}
              onChange={(tipo) => setForm({ ...form, tipo: tipo as TipoDemanda })}
              options={TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] }))}
            />
            <Select
              label="Produto"
              value={form.produto_id}
              onChange={(produto_id) => setForm({ ...form, produto_id })}
              options={produtosAtivos.map((p) => ({ value: p.id, label: p.nome }))}
              placeholder="Escolha o Produto"
            />
            <Select
              label="Prioridade"
              value={form.prioridade}
              onChange={(prioridade) => setForm({ ...form, prioridade: prioridade as PrioridadeDemanda })}
              options={PRIORIDADES.map((p) => ({ value: p, label: PRIORIDADE_ROTULO[p] }))}
            />
            <textarea
              aria-label="Descrição"
              rows={2}
              placeholder="Contexto, se ajudar"
              value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white md:col-span-2"
            />
          </div>
          <button
            type="button"
            onClick={criarDemanda}
            disabled={!form.titulo.trim() || !form.produto_id}
            className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
          >
            Abrir Demanda
          </button>
        </div>
      )}

      {carregando ? (
        <p className="text-sm text-text-secondary">Carregando Demandas...</p>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {ESTADOS.map((estado) => {
            const cards = coluna(estado);
            const recolhivel = COLUNAS_RECOLHIDAS.includes(estado);
            const expandida = !recolhivel || expandidas.includes(estado);

            return (
              <section
                key={estado}
                aria-label={ESTADO_ROTULO[estado]}
                className={`shrink-0 rounded-xl border border-border bg-surface p-3 ${
                  expandida ? "w-[260px]" : "w-[180px]"
                }`}
              >
                {recolhivel ? (
                  <button
                    type="button"
                    aria-expanded={expandida}
                    onClick={() =>
                      setExpandidas(
                        expandida ? expandidas.filter((e) => e !== estado) : [...expandidas, estado],
                      )
                    }
                    className="w-full flex items-center justify-between gap-2 text-sm font-semibold text-text hover:text-primary transition-colors"
                  >
                    <span>{ESTADO_ROTULO[estado]}</span>
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-600">
                      {cards.length}
                    </span>
                  </button>
                ) : (
                  <h3 className="flex items-center justify-between gap-2 text-sm font-semibold text-text">
                    <span>{ESTADO_ROTULO[estado]}</span>
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-600">
                      {cards.length}
                    </span>
                  </h3>
                )}

                {expandida && (
                  <ul className="mt-3 space-y-2">
                    {cards.length === 0 ? (
                      <li className="text-xs text-text-secondary">Nenhuma Demanda aqui.</li>
                    ) : (
                      cards.map(cartao)
                    )}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}

      {aberta && (
        <DemandaModal
          demanda={aberta}
          produtos={produtos}
          pessoas={pessoas}
          token={token}
          onFechar={() => setAbertaId(null)}
          onMudou={carregar}
        />
      )}
    </div>
  );
}
