"use client";

/**
 * A aba Assistente da Tecnologia com a lista lateral (issue #1384, PRD #1380, ADR 0077).
 *
 * Ao lado do chat, a lista das Demandas de quem está logado, com o título e a
 * Etapa, da mais recente para a mais antiga (a ordem é do servidor). Clicar
 * numa conversa sem card retoma o chat de onde parou; clicar numa que já tem
 * Vínculo mostra a conversa e O que muda. "Nova conversa" abre o chat do zero.
 *
 * No celular só um dos dois lados aparece por vez: a lista é a tela de
 * entrada, e a conversa aberta tem o caminho de volta. Na tela larga os dois
 * ficam lado a lado.
 *
 * O Desenvolvedor (issue #1531, ADR 0083) tem o filtro "Todas", com o autor
 * em cada linha. A Demanda de outro autor abre só para leitura, com a
 * entrevista inteira, os Anexos e o número e o link da issue. Quem é
 * Desenvolvedor é o servidor que diz.
 *
 * Cada linha com card mostra o Responsável, para todos, e a lista do
 * Desenvolvedor abre em "Para mim", as Demandas de que ele cuida (issue
 * #1533, ADR 0083, decisão 5).
 *
 * Toda Demanda aberta tem, embaixo, a Conversa da Demanda, numa área própria
 * (issue #1537, ADR 0083, decisão 8). O aviso do sino chega com a Demanda em
 * `demandaInicial` e a abre: o Desenvolvedor a procura em "Todas", porque a
 * menção pode ser numa Demanda de que ele não é o Responsável.
 *
 * O card que não chegou ao GitHub fica com o selo "Envio falhou" na lista, e a
 * conversa aberta traz o "Reenviar", para o autor e para o Desenvolvedor. Só o
 * Desenvolvedor lê o motivo técnico e tem o filtro "Envio falhou" (issue
 * #1535, ADR 0083, decisão 7). O card que nasceu sem o Responsável aparece
 * só para o Desenvolvedor, com o "Designar de novo" (issue #1536).
 *
 * A conversa aberta tem o "Apagar" para quem pode, com confirmação: o autor
 * na conversa Registrada, o Desenvolvedor no card até Planejada (issue
 * #1549, ADR 0084, decisão 2). Quem pode é o servidor que diz.
 *
 * A lista é larga, com a busca pelo título e os filtros em chips que quebram
 * linha (issue #1551): Tipo e Etapa para todos; o recorte (Para mim, Minhas,
 * Todas), o Responsável e o Envio falhou só para o Desenvolvedor. Tudo combina,
 * e quem filtra é o servidor. Com uma Demanda aberta a lista recolhe, e o
 * Voltar às conversas a traz de volta, na tela larga como no celular.
 *
 * Os cards que a Vitta abre pelo terminal aparecem na lista com o selo
 * "Vitta", e os do chat com "Pedido do diretor"; o chip Origem filtra (issue
 * #1554, ADR 0084, decisão 4). O card da Vitta abre o documento e a Conversa
 * da Demanda, sem conversa com o agente.
 */

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, Plus, Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";

import { ChatDaTecnologia, Fala } from "./ChatDaTecnologia";
import { ConversaDaDemanda } from "./ConversaDaDemanda";
import { DocumentoDoCard } from "./DocumentoDoCard";
import { SeloDeEtapa } from "./SeloDeEtapa";
import {
  AnexoDaDemanda,
  conversaValida,
  Desenvolvedor,
  desenvolvedoresValidos,
  FalaDoChat,
  URL_DO_CHAT_DA_ABA,
  URL_DOS_DESENVOLVEDORES,
  urlDaConversa,
  urlDoDesignarDeNovo,
  urlDoReenviar,
} from "./chat";
import {
  BASE_TECNOLOGIA,
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  Classificacao,
  Demanda,
  ETAPA_CLASSE,
  EtapaDemanda,
  ETAPA_ROTULO,
  FALHA_DE_CONEXAO,
  linkDaDemonstracao,
  motivoDaRecusa,
  Origem,
  ORIGEM_CLASSE,
  ORIGEM_ROTULO,
  TEM_DEMONSTRACAO,
  temSelo,
  textoDoSelo,
} from "./demandas";

export const NOVA_CONVERSA = "Nova conversa";
export const VOLTAR_PARA_A_LISTA = "Voltar às conversas";
export const ENVIO_FALHOU = "Envio falhou";
export const REENVIAR = "Reenviar";
export const DESIGNACAO_FALHOU = "Designação falhou";
export const DESIGNAR_DE_NOVO = "Designar de novo";
export const APAGAR = "Apagar";
const APAGAR_TITULO = "Apagar este pedido?";
const APAGAR_A_CONVERSA_EXPLICADO =
  "A conversa sai da lista com os anexos. Não dá para desfazer.";
const APAGAR_O_CARD_EXPLICADO =
  "O pedido sai da lista com a conversa e os anexos, e o card fecha como não planejado no desenvolvimento. Não dá para desfazer.";
const DESIGNACAO_FALHOU_EXPLICADO =
  "O card nasceu no GitHub sem o Responsável. Designar de novo pede só a designação, sem criar outro card.";
const ENVIO_FALHOU_EXPLICADO =
  "Este card não chegou à Vitta. O que você disse continua guardado: clique em Reenviar para tentar de novo.";
const LISTA_VAZIA = "Nenhuma conversa ainda.";
const LISTA_FALHOU = "Não foi possível carregar as suas conversas. Tente recarregar a página.";
const URL_QUEM_SOU = `${BASE_TECNOLOGIA}/eu`;

type Filtro = "para_mim" | "minhas" | "todas";
const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "para_mim", rotulo: "Para mim" },
  { valor: "minhas", rotulo: "Minhas" },
  { valor: "todas", rotulo: "Todas" },
];
const CLASSIFICACOES = Object.keys(CLASSIFICACAO_ROTULO) as Classificacao[];
const ETAPAS = Object.keys(ETAPA_ROTULO) as EtapaDemanda[];
const ORIGENS = Object.keys(ORIGEM_ROTULO) as Origem[];
/** A espera depois da última tecla, para a busca não pedir a lista a cada letra. */
const ESPERA_DA_BUSCA_MS = 300;

/** O que a lista pede ao servidor (issue #1551). */
type FiltrosDaLista = {
  recorte: Filtro;
  busca: string;
  tipo: Classificacao | null;
  etapa: EtapaDemanda | null;
  origem: Origem | null;
  responsavel: string | null;
  envioFalhou: boolean;
};

/** A URL da lista: sem nenhum filtro, a de antes (as Demandas de quem está logado). */
function urlDaLista(filtros: FiltrosDaLista): string {
  const consulta = new URLSearchParams();
  if (filtros.recorte !== "minhas") consulta.set("filtro", filtros.recorte);
  if (filtros.busca) consulta.set("busca", filtros.busca);
  if (filtros.tipo) consulta.set("tipo", filtros.tipo);
  if (filtros.etapa) consulta.set("etapa", filtros.etapa);
  if (filtros.origem) consulta.set("origem", filtros.origem);
  if (filtros.responsavel) consulta.set("responsavel", filtros.responsavel);
  if (filtros.envioFalhou) consulta.set("envio_falhou", "true");
  const texto = consulta.toString();
  return texto ? `${URL_DO_CHAT_DA_ABA}?${texto}` : URL_DO_CHAT_DA_ABA;
}

/** Um chip de filtro. Nada de `flex-1` nem `nowrap`: a linha quebra dentro da coluna. */
export function Chip({ ativo, onClick, children }: { ativo: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={`px-3 py-1 rounded-full border text-xs font-semibold ${
        ativo ? "border-primary bg-primary/5 text-primary" : "border-border text-text-secondary"
      }`}
    >
      {children}
    </button>
  );
}

export function GrupoDeChips({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={rotulo} className="flex flex-wrap gap-1">
      {children}
    </div>
  );
}

/** O item serve para a lista? O resto da Demanda é opcional para ela. */
function itemValido(item: unknown): item is Demanda {
  if (typeof item !== "object" || item === null) return false;
  const d = item as Record<string, unknown>;
  return typeof d.id === "string" && typeof d.titulo === "string";
}

/**
 * A Etapa na lista. Aqui "Registrada" aparece escrita: é a conversa sem card,
 * e a lista mostra a Etapa de toda conversa (na conversa aberta ela é a
 * ausência de selo).
 */
function EtapaNaLista({ demanda }: { demanda: Demanda }) {
  const comSelo = temSelo(demanda);
  const classe = comSelo && demanda.etapa ? ETAPA_CLASSE[demanda.etapa] : ETAPA_CLASSE.registrada;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${classe}`}>
      {comSelo ? textoDoSelo(demanda) : ETAPA_ROTULO.registrada}
    </span>
  );
}

/** Bug ou Melhoria, ao lado da Etapa (issue #1438). O pedido de antes do chat fica sem. */
function ClassificacaoNaLista({ demanda }: { demanda: Demanda }) {
  if (!demanda.classificacao) return null;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${CLASSIFICACAO_CLASSE[demanda.classificacao]}`}>
      {CLASSIFICACAO_ROTULO[demanda.classificacao]}
    </span>
  );
}

/** Pedido do diretor ou Vitta (issue #1554). Sem o campo, sem selo. */
function OrigemNaLista({ demanda }: { demanda: Demanda }) {
  if (!demanda.origem) return null;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ORIGEM_CLASSE[demanda.origem]}`}>
      {ORIGEM_ROTULO[demanda.origem]}
    </span>
  );
}

/** O pedido que tem vídeo de demonstração (issue #1559). Sem link, sem selo. */
function SeloDaDemonstracao({ demanda }: { demanda: Demanda }) {
  if (!linkDaDemonstracao(demanda)) return null;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-700">{TEM_DEMONSTRACAO}</span>;
}

/** O selo do card que não chegou ao GitHub (issue #1535). */
function SeloDoEnvioFalhou({ demanda }: { demanda: Demanda }) {
  if (!demanda.envio_falhou) return null;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700">{ENVIO_FALHOU}</span>;
}

/**
 * O aviso do Envio falhou no alto da conversa aberta, com o Reenviar (issue
 * #1535). O motivo técnico só vem do servidor para o Desenvolvedor.
 */
function AvisoDoEnvioFalhou({
  demanda,
  token,
  onReenviado,
}: {
  demanda: Demanda;
  token: string | null;
  onReenviado: (demandaId: string) => void;
}) {
  const [reenviando, setReenviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function reenviar() {
    if (!token) return;
    setReenviando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDoReenviar(demanda.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onReenviado(demanda.id);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao reenviar o card", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setReenviando(false);
    }
  }

  return (
    <section
      role="region"
      aria-label={ENVIO_FALHOU}
      className="w-full rounded-2xl border border-red-200 bg-red-50 p-4 space-y-2 text-sm text-red-800"
    >
      <p className="font-semibold">{ENVIO_FALHOU}</p>
      <p>{ENVIO_FALHOU_EXPLICADO}</p>
      {demanda.envio_motivo && <p className="normal-case font-mono text-xs">{demanda.envio_motivo}</p>}
      {erro && <p role="alert">{erro}</p>}
      <button
        type="button"
        onClick={reenviar}
        disabled={reenviando}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60"
      >
        {reenviando && <Loader2 className="w-4 h-4 animate-spin" />}
        {REENVIAR}
      </button>
    </section>
  );
}

/**
 * O aviso da designação falhada no alto da conversa aberta, com o Designar de
 * novo (issue #1536). Só o Desenvolvedor o recebe do servidor.
 */
function AvisoDaDesignacaoFalhou({
  demanda,
  token,
  onDesignado,
}: {
  demanda: Demanda;
  token: string | null;
  onDesignado: (demandaId: string) => void;
}) {
  const [designando, setDesignando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function designarDeNovo() {
    if (!token) return;
    setDesignando(true);
    setErro(null);
    try {
      const resposta = await fetch(urlDoDesignarDeNovo(demanda.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onDesignado(demanda.id);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao designar de novo", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setDesignando(false);
    }
  }

  return (
    <section
      role="region"
      aria-label={DESIGNACAO_FALHOU}
      className="w-full rounded-2xl border border-amber-200 bg-amber-50 p-4 space-y-2 text-sm text-amber-900"
    >
      <p className="font-semibold">{DESIGNACAO_FALHOU}</p>
      <p>{DESIGNACAO_FALHOU_EXPLICADO}</p>
      {demanda.envio_motivo && <p className="normal-case font-mono text-xs">{demanda.envio_motivo}</p>}
      {erro && <p role="alert">{erro}</p>}
      <button
        type="button"
        onClick={designarDeNovo}
        disabled={designando}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-60"
      >
        {designando && <Loader2 className="w-4 h-4 animate-spin" />}
        {DESIGNAR_DE_NOVO}
      </button>
    </section>
  );
}

/**
 * O "Apagar" da Demanda (issue #1549, ADR 0084, decisão 2). Só aparece com o
 * `pode_apagar` do servidor, e pede confirmação antes. A recusa do servidor
 * (o GitHub que não fechou o card, a Etapa que andou) aparece embaixo do botão.
 */
function ApagarADemanda({
  demanda,
  token,
  onApagada,
}: {
  demanda: Demanda;
  token: string | null;
  onApagada: () => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function apagar() {
    if (!token) return;
    setErro(null);
    try {
      const resposta = await fetch(urlDaConversa(demanda.id), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        setErro(await motivoDaRecusa(resposta));
        return;
      }
      onApagada();
    } catch (e) {
      console.error("[admin/tecnologia] falha ao apagar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => setConfirmando(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-red-200 text-red-700 text-xs font-semibold hover:bg-red-50"
      >
        <Trash2 className="w-3.5 h-3.5" />
        {APAGAR}
      </button>
      {erro && (
        <p role="alert" className="text-sm text-red-700">
          {erro}
        </p>
      )}
      <ConfirmDialog
        open={confirmando}
        onClose={() => setConfirmando(false)}
        onConfirm={apagar}
        title={APAGAR_TITULO}
        description={demanda.tem_vinculo ? APAGAR_O_CARD_EXPLICADO : APAGAR_A_CONVERSA_EXPLICADO}
        confirmLabel={APAGAR}
        confirmVariant="danger"
      />
    </div>
  );
}

/** Os Anexos da Demanda, que só o Desenvolvedor recebe do servidor. */
function AnexosDaDemanda({ anexos }: { anexos: AnexoDaDemanda[] }) {
  const comLink = anexos.filter((anexo) => anexo.url);
  if (comLink.length === 0) return null;
  return (
    <div className="border-t border-slate-100 pt-4 space-y-1">
      <h3 className="text-xs font-semibold text-text-secondary">Anexos</h3>
      <ul className="space-y-1 text-sm">
        {comLink.map((anexo, i) => (
          <li key={i}>
            <a
              href={anexo.url ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="normal-case text-primary underline"
            >
              {anexo.nome}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A conversa só para leitura: a que já virou card, ou a de outro autor que o
 * Desenvolvedor abriu (ADR 0083), com a Etapa e o Documento do card. O card
 * da Vitta não tem conversa com o agente (issue #1554): nem a pede.
 */
function Acompanhamento({ demanda, token }: { demanda: Demanda; token: string | null }) {
  const [falas, setFalas] = useState<FalaDoChat[]>([]);
  const [anexos, setAnexos] = useState<AnexoDaDemanda[]>([]);

  // A conversa é complemento: sem ela (a melhoria planejada, ou a rede fora),
  // o Documento do card continua à vista.
  const semChat = demanda.origem === "vitta";
  useEffect(() => {
    if (!token || semChat) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(urlDaConversa(demanda.id), { headers: { Authorization: `Bearer ${token}` } });
        if (!resposta.ok) return;
        const corpo: unknown = await resposta.json();
        if (viva && conversaValida(corpo)) {
          setFalas(corpo.mensagens);
          setAnexos(Array.isArray(corpo.anexos_da_demanda) ? corpo.anexos_da_demanda : []);
        }
      } catch (e) {
        console.error("[admin/tecnologia] falha ao abrir a conversa", e);
      }
    })();
    return () => {
      viva = false;
    };
  }, [demanda.id, token, semChat]);

  return (
    <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <h2 className="normal-case text-base font-bold text-slate-900">{demanda.titulo}</h2>
        <SeloDeEtapa demanda={demanda} />
        <OrigemNaLista demanda={demanda} />
        {demanda.autor && <span className="normal-case text-text-secondary">{demanda.autor}</span>}
      </div>
      <DocumentoDoCard demanda={demanda} />
      {falas.length > 0 && (
        <div role="log" className="space-y-3 border-t border-slate-100 pt-4">
          {falas.map((fala, i) => (
            <Fala key={i} fala={fala} />
          ))}
        </div>
      )}
      <AnexosDaDemanda anexos={anexos} />
    </section>
  );
}

export function ConversasDaTecnologia({
  token,
  demandaInicial = null,
}: {
  token: string | null;
  /** A Demanda que o aviso do sino pediu para abrir. */
  demandaInicial?: string | null;
}) {
  const [demandas, setDemandas] = useState<Demanda[] | null>(null);
  const [erroDaLista, setErroDaLista] = useState<string | null>(null);
  /** A Demanda clicada; `null` é a conversa nova. */
  const [aberta, setAberta] = useState<Demanda | null>(null);
  /** A que a lista destaca: a clicada, ou a que acabou de nascer no chat. */
  const [destacada, setDestacada] = useState<string | null>(null);
  /** Muda a cada clique, para o chat recomeçar do estado da conversa escolhida. */
  const [chave, setChave] = useState(0);
  const [naTela, setNaTela] = useState<"lista" | "conversa">("lista");
  const [desenvolvedor, setDesenvolvedor] = useState(false);
  /** Nulo até o servidor dizer quem está logado: o Desenvolvedor abre em Para mim. */
  const [filtro, setFiltro] = useState<Filtro | null>(null);
  const [textoDaBusca, setTextoDaBusca] = useState("");
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState<Classificacao | null>(null);
  const [etapa, setEtapa] = useState<EtapaDemanda | null>(null);
  const [origem, setOrigem] = useState<Origem | null>(null);
  const [responsavel, setResponsavel] = useState<string | null>(null);
  const [envioFalhou, setEnvioFalhou] = useState(false);
  const [desenvolvedores, setDesenvolvedores] = useState<Desenvolvedor[]>([]);
  /** O último pedido da lista: a resposta de um pedido mais velho não sobrescreve a do novo. */
  const ultimoPedido = useRef(0);
  /** A Demanda do sino que já foi aberta: abre uma vez, e não a cada recarga da lista. */
  const abertaPeloSino = useRef<string | null>(null);

  // Sem resposta, a tela fica como a do diretor: o filtro só aparece com o
  // sim do servidor.
  useEffect(() => {
    if (!token) return;
    let viva = true;
    (async () => {
      let sim = false;
      try {
        const resposta = await fetch(URL_QUEM_SOU, { headers: { Authorization: `Bearer ${token}` } });
        if (resposta.ok) {
          const corpo: unknown = await resposta.json();
          sim = (corpo as { desenvolvedor?: unknown })?.desenvolvedor === true;
        }
      } catch (e) {
        console.error("[admin/tecnologia] falha ao saber quem está logado", e);
      }
      if (!viva) return;
      setDesenvolvedor(sim);
      setFiltro(sim ? (demandaInicial ? "todas" : "para_mim") : "minhas");
    })();
    return () => {
      viva = false;
    };
  }, [token, demandaInicial]);

  // Os nomes do chip Responsável, só para o Desenvolvedor.
  useEffect(() => {
    if (!token || !desenvolvedor) return;
    let viva = true;
    (async () => {
      try {
        const resposta = await fetch(URL_DOS_DESENVOLVEDORES, { headers: { Authorization: `Bearer ${token}` } });
        if (!resposta.ok) return;
        const lidos = desenvolvedoresValidos(await resposta.json());
        if (viva) setDesenvolvedores(lidos);
      } catch (e) {
        console.error("[admin/tecnologia] falha ao listar quem cuida", e);
      }
    })();
    return () => {
      viva = false;
    };
  }, [token, desenvolvedor]);

  useEffect(() => {
    const espera = setTimeout(() => setBusca(textoDaBusca.trim()), ESPERA_DA_BUSCA_MS);
    return () => clearTimeout(espera);
  }, [textoDaBusca]);

  /** Relê a lista e devolve o que veio; nulo quando não deu. */
  const carregar = useCallback(async (): Promise<Demanda[] | null> => {
    if (!token || filtro === null) return null;
    const url = urlDaLista({ recorte: filtro, busca, tipo, etapa, origem, responsavel, envioFalhou });
    const pedido = ++ultimoPedido.current;
    try {
      const resposta = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (pedido !== ultimoPedido.current) return null;
      if (!resposta.ok) {
        setErroDaLista(LISTA_FALHOU);
        return null;
      }
      const corpo: unknown = await resposta.json();
      if (pedido !== ultimoPedido.current) return null;
      if (!Array.isArray(corpo)) {
        setErroDaLista(LISTA_FALHOU);
        return null;
      }
      const lidas = corpo.filter(itemValido);
      setDemandas(lidas);
      setErroDaLista(null);
      return lidas;
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as conversas", e);
      setErroDaLista(FALHA_DE_CONEXAO);
      return null;
    }
  }, [token, filtro, busca, tipo, etapa, origem, responsavel, envioFalhou]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const aoMudar = useCallback(
    (demandaId: string) => {
      setDestacada(demandaId);
      carregar();
    },
    [carregar],
  );

  const abrir = useCallback((demanda: Demanda | null) => {
    setAberta(demanda);
    setDestacada(demanda?.id ?? null);
    setChave((atual) => atual + 1);
    setNaTela("conversa");
  }, []);

  /** O card nasceu pelo Reenviar: a lista relê e a Demanda abre como está agora. */
  async function aoReenviar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, envio_falhou: false, envio_motivo: null, tem_vinculo: true } : null));
  }

  /** A Demanda foi apagada: some da lista, e a tela volta à lista com a conversa nova pronta. */
  function aoApagar() {
    setAberta(null);
    setDestacada(null);
    setChave((atual) => atual + 1);
    setNaTela("lista");
    carregar();
  }

  /** A designação pegou: a lista relê e a Demanda abre como está agora. */
  async function aoDesignar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, designacao_falhou: false, envio_motivo: null } : null));
  }

  useEffect(() => {
    if (!demandaInicial || abertaPeloSino.current === demandaInicial || !demandas) return;
    const pedida = demandas.find((d) => d.id === demandaInicial);
    if (!pedida) return;
    abertaPeloSino.current = demandaInicial;
    abrir(pedida);
  }, [demandaInicial, demandas, abrir]);

  /** Com uma Demanda aberta, a lista recolhe também na tela larga (issue #1551). */
  const recolhida = naTela === "conversa" && aberta !== null;

  return (
    <div
      className={`md:grid ${recolhida ? "md:grid-cols-1" : "md:grid-cols-[22rem_minmax(0,1fr)]"} md:gap-4 md:items-start`}
    >
      <div className={`${naTela === "lista" ? "" : "hidden"} ${recolhida ? "md:hidden" : "md:block"} space-y-3`}>
        <button
          type="button"
          onClick={() => abrir(null)}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold"
        >
          <Plus className="w-4 h-4" />
          {NOVA_CONVERSA}
        </button>
        <section role="region" aria-label="Filtros da lista" className="space-y-2">
          <input
            type="search"
            aria-label="Buscar pelo título"
            placeholder="Buscar pelo título"
            value={textoDaBusca}
            onChange={(e) => setTextoDaBusca(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-border text-sm normal-case"
          />
          {desenvolvedor && (
            <GrupoDeChips rotulo="Filtro das conversas">
              {FILTROS.map(({ valor, rotulo }) => (
                <Chip key={valor} ativo={filtro === valor} onClick={() => setFiltro(valor)}>
                  {rotulo}
                </Chip>
              ))}
            </GrupoDeChips>
          )}
          <GrupoDeChips rotulo="Tipo">
            {CLASSIFICACOES.map((valor) => (
              <Chip key={valor} ativo={tipo === valor} onClick={() => setTipo(tipo === valor ? null : valor)}>
                {CLASSIFICACAO_ROTULO[valor]}
              </Chip>
            ))}
          </GrupoDeChips>
          <GrupoDeChips rotulo="Etapa">
            {ETAPAS.map((valor) => (
              <Chip key={valor} ativo={etapa === valor} onClick={() => setEtapa(etapa === valor ? null : valor)}>
                {ETAPA_ROTULO[valor]}
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
          {desenvolvedor && desenvolvedores.length > 0 && (
            <GrupoDeChips rotulo="Responsável">
              {desenvolvedores.map((d) => (
                <Chip
                  key={d.id}
                  ativo={responsavel === d.id}
                  onClick={() => setResponsavel(responsavel === d.id ? null : d.id)}
                >
                  {d.nome}
                </Chip>
              ))}
            </GrupoDeChips>
          )}
          {desenvolvedor && (
            <GrupoDeChips rotulo="Situação">
              <Chip ativo={envioFalhou} onClick={() => setEnvioFalhou(!envioFalhou)}>
                {ENVIO_FALHOU}
              </Chip>
            </GrupoDeChips>
          )}
        </section>
        <nav aria-label="Suas conversas" className="md:max-h-[calc(100vh-20rem)] md:overflow-y-auto">
          {erroDaLista && (
            <p role="alert" className="px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              {erroDaLista}
            </p>
          )}
          {demandas === null && !erroDaLista && (
            <p role="status" className="flex items-center gap-2 px-1 text-xs text-text-secondary">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Carregando as conversas...
            </p>
          )}
          {demandas !== null && demandas.length === 0 && (
            <p className="px-1 text-sm text-text-secondary">{LISTA_VAZIA}</p>
          )}
          {demandas !== null && demandas.length > 0 && (
            <ul className="space-y-1">
              {demandas.map((demanda) => (
                <li key={demanda.id}>
                  <button
                    type="button"
                    onClick={() => abrir(demanda)}
                    aria-current={destacada === demanda.id ? "true" : undefined}
                    className={`w-full flex flex-col gap-1 px-3 py-2 rounded-xl border text-left text-sm transition-colors ${
                      destacada === demanda.id
                        ? "border-primary bg-primary/5"
                        : "border-transparent hover:border-border hover:bg-slate-50"
                    }`}
                  >
                    <span className="normal-case font-medium text-text-primary line-clamp-2">{demanda.titulo}</span>
                    {demanda.autor && (
                      <span className="normal-case text-xs text-text-secondary">{demanda.autor}</span>
                    )}
                    {demanda.responsavel && (
                      <span className="normal-case text-xs text-text-secondary">
                        Responsável: {demanda.responsavel}
                      </span>
                    )}
                    <span className="flex flex-wrap items-center gap-1.5">
                      <EtapaNaLista demanda={demanda} />
                      <ClassificacaoNaLista demanda={demanda} />
                      <OrigemNaLista demanda={demanda} />
                      <SeloDaDemonstracao demanda={demanda} />
                      <SeloDoEnvioFalhou demanda={demanda} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </div>

      <div
        role="region"
        aria-label="Conversa aberta"
        className={`${naTela === "conversa" ? "" : "hidden"} md:block min-w-0 space-y-3`}
      >
        <button
          type="button"
          onClick={() => setNaTela("lista")}
          className={`${recolhida ? "" : "md:hidden"} inline-flex items-center gap-1.5 text-sm font-semibold text-primary`}
        >
          <ArrowLeft className="w-4 h-4" />
          {VOLTAR_PARA_A_LISTA}
        </button>
        {aberta?.pode_apagar && (
          <ApagarADemanda key={`apagar-${chave}`} demanda={aberta} token={token} onApagada={aoApagar} />
        )}
        {aberta?.envio_falhou && (
          <AvisoDoEnvioFalhou key={`envio-${chave}`} demanda={aberta} token={token} onReenviado={aoReenviar} />
        )}
        {desenvolvedor && aberta?.designacao_falhou && (
          <AvisoDaDesignacaoFalhou
            key={`designacao-${chave}`}
            demanda={aberta}
            token={token}
            onDesignado={aoDesignar}
          />
        )}
        {aberta?.tem_vinculo || aberta?.minha === false ? (
          <Acompanhamento key={chave} demanda={aberta} token={token} />
        ) : (
          <ChatDaTecnologia key={chave} token={token} demandaId={aberta?.id ?? null} onMudou={aoMudar} />
        )}
        {aberta && <ConversaDaDemanda key={`conversa-${chave}`} demandaId={aberta.id} token={token} />}
      </div>
    </div>
  );
}
