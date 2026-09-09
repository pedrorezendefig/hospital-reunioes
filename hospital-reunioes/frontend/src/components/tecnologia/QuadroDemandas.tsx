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
import { usePolling } from "@/hooks/usePolling";

import { DemandaModal } from "./DemandaModal";
import { TipoIcone } from "./TipoIcone";
import {
  avisoPorEmail,
  BASE_TECNOLOGIA,
  COLUNAS_RECOLHIDAS,
  Demanda,
  demandaIdDaUrl,
  destinosDe,
  ESTADO_ROTULO,
  ESTADOS,
  EstadoDemanda,
  estaAtrasado,
  FALHA_DE_CONEXAO,
  FiltrosDoQuadro,
  idadeEmDias,
  IDADE_VERMELHA_A_PARTIR_DE,
  INTERVALO_DE_ATUALIZACAO_MS,
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

/**
 * As duas frases de quando o link pede uma Demanda que o Quadro não mostra
 * (issue #640, com os filtros da issue #639 no ar).
 *
 * São duas porque as causas são duas e o código as DISTINGUE. Uma frase só
 * mandaria conferir o endereço com quem enviou justamente quando o endereço
 * está certo e quem esconde a Demanda é o filtro que a própria pessoa deixou
 * ligado ontem: cobrança de uma ação que não resolve, sobre uma causa que não
 * é a verdadeira.
 *
 * A frase do filtro não AFIRMA que o filtro é a causa (a Demanda pode nem
 * existir, e o código não sabe): ela diz os dois fatos que o código tem, o
 * filtro valendo e a Demanda fora do que o Quadro mostra, e aponta a ação, que
 * está na mesma tela, no botão "Limpar filtros".
 */
const AVISO_LINK_SEM_FILTRO = "A Demanda deste link não está no Quadro. Confira o endereço com quem enviou.";
const AVISO_LINK_COM_FILTRO =
  "O Quadro está filtrado, e a Demanda deste link não está entre as que ele mostra. " +
  "Ela pode estar escondida pelo filtro: limpe os filtros abaixo e veja de novo.";

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
   * A aba do navegador está à vista? (issue #642)
   *
   * Começa em `true` porque o primeiro render acontece com a aba na frente de
   * quem abriu; o efeito abaixo corrige no mesmo commit se não for o caso.
   * Começar em `false` faria o Quadro nascer sem atualização automática toda
   * vez que o jsdom (ou um navegador que ainda não pintou) não tivesse
   * `visibilityState` pronto.
   */
  const [abaVisivel, setAbaVisivel] = useState(true);
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
  /**
   * Se o aviso na tela veio de uma ESCRITA recusada.
   *
   * A leitura que dá certo limpa o aviso, e é o que se quer quando o aviso é
   * dela. Mas trocar o filtro dispara uma leitura, e ela chegando depois de
   * uma recusa de escrita apagaria o motivo: o formulário ficaria aberto,
   * preenchido, e sem explicação nenhuma de por que a Demanda não foi criada.
   */
  const erroDeEscrita = useRef(false);
  /**
   * O id que veio no link e que ainda não foi encontrado no Quadro (issue #640).
   *
   * Ele é estado, e não uma leitura solta, porque o link chega ANTES do token:
   * quem abre pelo link cai no primeiro render, com a autenticação ainda
   * resolvendo e as Demandas ainda não pedidas. Guardado aqui, o pedido do link
   * espera as Demandas chegarem; zerado assim que a Demanda é achada, ele para
   * de ser cobrado e o aviso abaixo não reaparece depois.
   */
  const [idDoLink, setIdDoLink] = useState<string | null>(null);
  /**
   * A Demanda do link já está na lista que o Quadro carregou?
   *
   * Valor DERIVADO do estado de agora, e não uma marca que um efeito acerta um
   * render depois. O efeito que abre o card roda DEPOIS do commit: no commit em
   * que a lista chega, a Demanda já está lá e o card ainda não abriu, e um
   * aviso preso ao efeito entraria no DOM dizendo que ela não está. Para quem
   * enxerga isso é um piscar; como o aviso é `role="status"` (`aria-live`), o
   * leitor de tela ANUNCIA a acusação falsa em toda abertura por link bom. É a
   * mesma família do alarme de sessão que mordeu na fatia #637.
   */
  const achadaDoLink = idDoLink !== null && demandas.some((d) => d.id === idDoLink);

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
   *
   * `silencioso` é a leitura que a tela faz sozinha (issue #642): ela NÃO
   * acende o "Carregando Demandas...". Sem isso, o Quadro trocaria as cinco
   * colunas pela linha de espera a cada 30 segundos, e ler o quadro viraria
   * uma corrida contra o relógio, pior do que não atualizar.
   *
   * O que ela continua fazendo é APAGAR a espera quando é o pedido mais novo
   * (o `finally` não olha `silencioso`). É o que impede o Quadro de ficar
   * preso em "Carregando Demandas..." quando uma leitura da pessoa é
   * atropelada por uma automática: a leitura antiga sai pelo selo de sequência
   * sem desligar nada, e só a mais nova tem o direito de desligar.
   */
  const carregar = useCallback(async (silencioso = false) => {
    if (!token) return;
    const meuPedido = ultimoPedido.current + 1;
    ultimoPedido.current = meuPedido;
    if (!silencioso) setCarregando(true);
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}/demandas${busca}`, { headers: autorizacao() });
      // Chegou tarde: já há um pedido mais novo no ar, e o que esta resposta
      // conta não é mais o que a tela está pedindo.
      if (meuPedido !== ultimoPedido.current) return;
      if (!resposta.ok) {
        erroDeEscrita.current = false;
        setErro("Não foi possível carregar as Demandas.");
        return;
      }
      setDemandas(await resposta.json());
      // A leitura só apaga o aviso que a leitura pode ter posto.
      if (!erroDeEscrita.current) setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as Demandas", e);
      if (meuPedido !== ultimoPedido.current) return;
      erroDeEscrita.current = false;
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

  /**
   * O id da Demanda que veio no link (issue #640).
   *
   * A leitura é do `window.location`, e não do `useSearchParams`: o hook do
   * Next obriga quem o chama a ficar sob um limite de Suspense, e o limite é o
   * pedaço da tela que a renderização antecipada pode trocar pelo `fallback`.
   * Aqui o pedaço seria o Quadro inteiro, e o padrão da casa é o contrário
   * disso: o `app/login/page.tsx` mantém o limite em volta de um input
   * escondido justamente para a casca vazia não poder apagar a tela. Ler o
   * `window.location` direto também já é da casa (`RedirecionarParaLogin.tsx`).
   *
   * O parâmetro é lido uma vez, ao montar, porque o link abre o card na
   * chegada: nada nesta tela troca a query string depois.
   */
  useEffect(() => {
    setIdDoLink(demandaIdDaUrl(window.location.search));
  }, []);

  useEffect(() => {
    if (idDoLink && achadaDoLink) {
      setAbertaId(idDoLink);
      setIdDoLink(null);
    }
  }, [idDoLink, achadaDoLink]);

  /**
   * Quando o Quadro pode se recarregar sem ninguém pedir (issue #642).
   *
   * As três condições são três motivos diferentes, e nenhuma é zelo à toa:
   *
   * - **autenticação e token**: sem sessão resolvida não há o que pedir, e o
   *   `carregar` sairia na primeira linha de qualquer jeito;
   * - **modal fechado**: com o card aberto, uma leitura pode devolver uma
   *   lista em que a Demanda não está mais (outra pessoa a moveu para uma
   *   coluna que o filtro esconde), e `aberta` viraria `null`: o modal FECHA,
   *   levando junto a resposta que estava sendo digitada. O modal já recarrega
   *   sozinho o que muda dentro dele, a cada escrita;
   * - **card parado**: recarregar no meio de um arrasto pode tirar do DOM
   *   justamente o card que está na mão.
   *
   * O formulário de Nova Demanda NÃO entra na lista: o `carregar` não toca em
   * `form` nem em `abrindoForm`, e há teste provando que o que foi digitado
   * atravessa uma atualização automática. Pausar por causa dele seria congelar
   * o Quadro por um estado que a recarga não ameaça.
   */
  const podeRecarregarSozinho =
    !carregandoAuth && Boolean(token) && abertaId === null && arrastando === null;

  /**
   * Quando o RELÓGIO pode disparar.
   *
   * A aba escondida atrás de outra continua sendo aba aberta. Pedir de 30 em
   * 30 segundos para uma tela que ninguém está olhando gasta rede e CPU do
   * servidor a troco de nada, e quem volta não perde nada: o `focus` abaixo
   * recarrega na hora. Mesmo desenho do painel da Ouvidoria.
   *
   * A condição da aba fica SÓ aqui, e não no `focus`: voltar para uma aba
   * escondida dispara o `visibilitychange` antes do `focus`, mas o estado que
   * ele muda só chega ao componente no render seguinte. Um ouvinte de foco
   * preso a `abaVisivel` ainda estaria desligado no instante do `focus`, e a
   * volta que mais precisa de recarga seria justamente a que não teria.
   */
  const podeAtualizarSozinho = podeRecarregarSozinho && abaVisivel;

  usePolling(() => carregar(true), INTERVALO_DE_ATUALIZACAO_MS, podeAtualizarSozinho);

  /**
   * A volta para a janela recarrega na hora (PRD #634, história 40).
   *
   * O `usePolling` é um `setInterval` sem chamada imediata: quem volta depois
   * de meia hora fora esperaria até 30 segundos olhando a foto de antes.
   *
   * A recarga mora SÓ no `focus`, e não também no `visibilitychange`: voltar
   * para uma aba escondida devolve o foco à janela, então os dois disparariam
   * juntos e o mesmo retorno pediria o Quadro duas vezes. O
   * `visibilitychange` fica com o que é dele, que é dizer se a aba está à
   * vista.
   */
  useEffect(() => {
    if (!podeRecarregarSozinho) return;
    const aoFocar = () => carregar(true);
    window.addEventListener("focus", aoFocar);
    // Sem esta linha o ouvinte sobreviveria à saída da aba, e cada visita
    // deixaria mais um preso a um componente que já não está na tela.
    return () => window.removeEventListener("focus", aoFocar);
  }, [podeRecarregarSozinho, carregar]);

  useEffect(() => {
    const aoTrocar = () => setAbaVisivel(document.visibilityState === "visible");
    aoTrocar();
    document.addEventListener("visibilitychange", aoTrocar);
    return () => document.removeEventListener("visibilitychange", aoTrocar);
  }, []);

  async function enviar(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    let resposta: Response;
    try {
      resposta = await fetch(url, { method: metodo, headers: autorizacao(), body: JSON.stringify(corpo) });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao salvar a Demanda", e);
      erroDeEscrita.current = true;
      setErro(FALHA_DE_CONEXAO);
      return false;
    }
    if (!resposta.ok) {
      erroDeEscrita.current = true;
      setErro(await motivoDaRecusa(resposta));
      // O 409 diz que o Quadro está desatualizado e manda recarregar, e a tela
      // não tem onde: pedir uma ação que o app não oferece deixa quem levou a
      // recusa sem saída. Recarregando aqui, a frase passa a descrever o que
      // já aconteceu. O motivo continua na tela, senão o card "voltaria"
      // sozinho e ninguém saberia por quê.
      if (resposta.status === 409) await carregar();
      return false;
    }
    /**
     * A ação valeu. Falta saber se o aviso por e-mail que ela dispara saiu
     * (issue #642).
     *
     * Ele entra pelo MESMO alerta da recusa, e não por uma faixa nova: é onde
     * a pessoa acabou de olhar, e uma segunda caixa de aviso na tela seria mais
     * uma coisa a aprender por um caso raro. Entra marcado como
     * `erroDeEscrita` de propósito: sem isso, a leitura que vem logo em seguida
     * (esta linha abaixo, ou a atualização automática) apagaria o aviso antes
     * de alguém ler.
     */
    const aviso = await avisoPorEmail(resposta);
    erroDeEscrita.current = aviso !== null;
    setErro(aviso);
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

      {/* O link pediu uma Demanda que o Quadro carregado não tem (issue #640).
          A frase fica presa a `!carregando && !erro` de propósito: enquanto a
          autenticação resolve, ou quando a leitura falhou, o código NÃO SABE se
          a Demanda está no Quadro, e dizer que não está seria afirmar um fato
          não verificado. Ela também não fala em Demanda apagada (nada se apaga
          nesta aba) nem em permissão (o gate é da API, e a recusa dela vira
          erro de carregamento, não lista sem o card). E ela olha `achadaDoLink`,
          que é derivado da lista de agora: preso ao efeito que abre o card, o
          aviso apareceria no commit em que a Demanda chega, antes de o card
          abrir. A frase muda com o filtro: ver `AVISO_LINK_COM_FILTRO`. */}
      {!carregando && !erro && idDoLink && !achadaDoLink && (
        <p
          role="status"
          className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{filtrando ? AVISO_LINK_COM_FILTRO : AVISO_LINK_SEM_FILTRO}</span>
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
