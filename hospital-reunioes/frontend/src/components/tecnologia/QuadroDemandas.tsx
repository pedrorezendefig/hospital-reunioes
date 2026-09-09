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
 * Arrastar entre colunas e a barra de filtros são da issue #639. Arrastar não
 * é um caminho novo: solta o card e chama o MESMO endpoint do botão "Mover",
 * que continua ali como o caminho de quem não usa o mouse. O card só muda de
 * coluna depois que o servidor aceitou, porque a recusa (422 da transição
 * proibida, 409 do Quadro desatualizado) é dele, e não da tela.
 */

import { useCallback, useEffect, useRef, useState } from "react";
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
  FiltrosDoQuadro,
  idadeEmDias,
  IDADE_VERMELHA_A_PARTIR_DE,
  motivoDaRecusa,
  PessoaDaAba,
  PRIORIDADE_ROTULO,
  PRIORIDADES,
  PrioridadeDemanda,
  prazoLegivel,
  ProdutoDaEscolha,
  queryDeFiltros,
  SEM_FILTRO,
  temFiltroAtivo,
  textoDaIdade,
  TIPO_ROTULO,
  TIPOS,
  TipoDemanda,
} from "./demandas";

type Props = {
  token: string | null;
  /**
   * Se a autenticação ainda está resolvendo.
   *
   * O `useAuth` nasce com `{ token: null, loading: true }` e só entrega o
   * token depois de duas idas à rede. Sem esta prop, o Quadro leria o `token`
   * nulo do primeiro render como "não há sessão" e piscaria o alerta vermelho
   * em toda abertura da aba, com a sessão perfeitamente válida.
   */
  carregandoAuth: boolean;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
  /**
   * Os filtros valendo agora.
   *
   * Eles moram na aba Tecnologia, e não aqui, porque precisam sobreviver à
   * troca de aba: o painel do Quadro é desmontado quando alguém vai a "Minha
   * vez", e um estado local voltaria ao zero na volta (issue #639).
   */
  filtros: FiltrosDoQuadro;
  onFiltrosChange: (filtros: FiltrosDoQuadro) => void;
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

/** As opções que LIMPAM cada filtro: o rótulo é o mesmo do campo em branco. */
const TODOS_OS_TIPOS = "Todos os tipos";
const TODOS_OS_PRODUTOS = "Todos os Produtos";
const TODOS_OS_RESPONSAVEIS = "Todos os responsáveis";

const FORM_VAZIO = {
  titulo: "",
  tipo: "decisao" as TipoDemanda,
  produto_id: "",
  prioridade: "normal" as PrioridadeDemanda,
  descricao: "",
};

export function QuadroDemandas({
  token,
  carregandoAuth,
  produtos,
  pessoas,
  filtros,
  onFiltrosChange,
}: Props) {
  const [demandas, setDemandas] = useState<Demanda[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [expandidas, setExpandidas] = useState<EstadoDemanda[]>([]);
  const [abrindoForm, setAbrindoForm] = useState(false);
  const [form, setForm] = useState(FORM_VAZIO);
  const [moverAberto, setMoverAberto] = useState<string | null>(null);
  const [abertaId, setAbertaId] = useState<string | null>(null);
  const [arrastando, setArrastando] = useState<string | null>(null);
  /**
   * O número do pedido de leitura mais recente.
   *
   * A rede não devolve na ordem em que foi chamada: trocar o filtro duas vezes
   * rápido deixa dois GET no ar, e se o primeiro chegar por último ele pinta o
   * Quadro do filtro que ninguém está mais vendo, com os campos mostrando o
   * filtro novo. Cada leitura leva o seu número e só escreve na tela se ainda
   * for a última.
   */
  const ultimoPedido = useRef(0);

  const autorizacao = useCallback(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  // Quem peneira é a API, com os filtros que ela já aceita: peneirar aqui
  // esconderia os cards sem tirá-los da resposta, e a mesma tela mostraria
  // contas diferentes conforme o que já tivesse sido baixado.
  const busca = queryDeFiltros(filtros);

  /**
   * Carrega o Quadro.
   *
   * A falha de rede vira AVISO, e não quadro vazio: sem o `catch`, o backend
   * fora do ar desenharia cinco colunas zeradas, que é indistinguível de "não
   * há Demanda nenhuma" e derruba o critério de aceite do Quadro.
   */
  const carregar = useCallback(async () => {
    if (!token) return;
    const meuPedido = ultimoPedido.current + 1;
    ultimoPedido.current = meuPedido;
    setCarregando(true);
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}/demandas${busca}`, { headers: autorizacao() });
      // Chegou tarde: já há um pedido mais novo no ar, e o que esta resposta
      // conta não é mais o que a tela está pedindo.
      if (meuPedido !== ultimoPedido.current) return;
      if (!resposta.ok) {
        setErro("Não foi possível carregar as Demandas.");
        return;
      }
      setDemandas(await resposta.json());
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as Demandas", e);
      if (meuPedido !== ultimoPedido.current) return;
      setErro(FALHA_DE_CONEXAO);
    } finally {
      // A espera só acaba com a resposta do pedido mais novo: desligá-la na
      // resposta velha diria "pronto" com a leitura de verdade ainda vindo.
      if (meuPedido === ultimoPedido.current) setCarregando(false);
    }
  }, [token, autorizacao, busca]);

  useEffect(() => {
    // Enquanto a autenticação resolve, o token nulo não quer dizer nada ainda:
    // acusar sessão aqui pintaria o alerta vermelho em toda abertura da aba.
    // A tela segue em "Carregando Demandas...", que é o que de fato acontece.
    if (carregandoAuth) return;
    if (!token) {
      // Resolvida a autenticação, token nulo é sessão de verdade ausente. Sem
      // este aviso o Quadro desenharia cinco colunas zeradas, calado, que é
      // indistinguível de "não há Demanda nenhuma". O aviso do módulo não
      // cobre este caso: ele fala de Produtos e mora abaixo do Quadro.
      setCarregando(false);
      setErro(SEM_SESSAO);
      return;
    }
    carregar();
  }, [carregandoAuth, token, carregar]);

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

  /**
   * Solta o card na coluna.
   *
   * Nada muda de lugar antes da resposta: o servidor pode recusar a transição
   * (422) ou dizer que o Quadro está desatualizado (409), e um card já pintado
   * na coluna nova contaria uma história que não aconteceu. Soltar na coluna
   * de origem não é movimento nenhum, e a rota recusaria com um erro que quem
   * desistiu do gesto não precisa ler.
   */
  function soltarEm(estado: EstadoDemanda) {
    const demanda = demandas.find((d) => d.id === arrastando);
    setArrastando(null);
    if (!demanda || demanda.estado === estado) return;
    mover(demanda, estado);
  }

  const produtosAtivos = produtos.filter((p) => p.ativo);
  const filtrando = temFiltroAtivo(filtros);
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
      <li
        key={demanda.id}
        draggable
        onDragStart={(e) => {
          // O `setData` é para o navegador: sem carga, o Firefox nem começa o
          // arrasto. Quem o componente lê ao soltar é o estado, que o jsdom
          // também enxerga.
          e.dataTransfer?.setData("text/plain", demanda.id);
          setArrastando(demanda.id);
        }}
        onDragEnd={() => setArrastando(null)}
        className="rounded-xl border border-border bg-white p-3 space-y-2 shadow-sm cursor-grab active:cursor-grabbing"
      >
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

      <div className="rounded-xl border border-border bg-surface p-3 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Select
            label="Filtrar por tipo"
            value={filtros.tipo}
            onChange={(tipo) => onFiltrosChange({ ...filtros, tipo })}
            options={[
              { value: "", label: TODOS_OS_TIPOS },
              ...TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] })),
            ]}
            placeholder={TODOS_OS_TIPOS}
          />
          <Select
            label="Filtrar por Produto"
            value={filtros.produto_id}
            onChange={(produto_id) => onFiltrosChange({ ...filtros, produto_id })}
            // Todos os Produtos, e não só os ativos: desativar tira o Produto
            // da escolha de quem abre Demanda nova, não do histórico (ADR 0050,
            // decisão 11). As Demandas dele continuam no Quadro, e sem esta
            // opção elas ficariam fora do alcance de qualquer filtro.
            options={[
              { value: "", label: TODOS_OS_PRODUTOS },
              ...produtos.map((p) => ({ value: p.id, label: p.ativo ? p.nome : `${p.nome} (inativo)` })),
            ]}
            placeholder={TODOS_OS_PRODUTOS}
          />
          <Select
            label="Filtrar por responsável"
            value={filtros.responsavel_id}
            onChange={(responsavel_id) => onFiltrosChange({ ...filtros, responsavel_id })}
            options={[
              { value: "", label: TODOS_OS_RESPONSAVEIS },
              ...pessoas.map((p) => ({ value: p.id, label: p.nome_completo })),
            ]}
            placeholder={TODOS_OS_RESPONSAVEIS}
          />
        </div>

        {/* O Quadro filtrado e calado é indistinguível do Quadro vazio: quem
            volta à aba com o filtro de antes concluiria que as Demandas
            sumiram. O aviso diz o que está acontecendo e onde desfazer. */}
        {filtrando && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-amber-700">
              O Quadro está filtrado: as Demandas fora do filtro não aparecem em nenhuma coluna.
            </p>
            <button
              type="button"
              onClick={() => onFiltrosChange(SEM_FILTRO)}
              className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-text-secondary hover:border-primary hover:text-primary transition-colors"
            >
              Limpar filtros
            </button>
          </div>
        )}
      </div>

      {abrindoForm && (
        <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="text"
              aria-label="Título"
              placeholder="O que precisa acontecer"
              maxLength={200}
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
                onDragOver={(e) => {
                  // Sem o `preventDefault` o navegador recusa o "soltar aqui".
                  if (arrastando) e.preventDefault();
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  soltarEm(estado);
                }}
                className={`shrink-0 rounded-xl border bg-surface p-3 ${
                  expandida ? "w-[260px]" : "w-[180px]"
                } ${arrastando ? "border-dashed border-primary/50" : "border-border"}`}
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
