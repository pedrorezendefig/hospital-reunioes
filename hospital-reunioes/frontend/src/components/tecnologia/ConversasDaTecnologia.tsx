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
 * O card que não chegou ao GitHub fica com o selo "Envio falhou" na lista, e a
 * conversa aberta traz o "Reenviar", para o autor e para o Desenvolvedor. Só o
 * Desenvolvedor lê o motivo técnico e tem o filtro "Envio falhou" (issue
 * #1535, ADR 0083, decisão 7).
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Loader2, Plus } from "lucide-react";

import { ChatDaTecnologia, Fala } from "./ChatDaTecnologia";
import { OQueMudaDaDemanda } from "./OQueMudaDaDemanda";
import { SeloDeEtapa } from "./SeloDeEtapa";
import {
  AnexoDaDemanda,
  conversaValida,
  FalaDoChat,
  URL_DO_CHAT_DA_ABA,
  urlDaConversa,
  urlDoReenviar,
} from "./chat";
import {
  BASE_TECNOLOGIA,
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  Demanda,
  ETAPA_CLASSE,
  ETAPA_ROTULO,
  FALHA_DE_CONEXAO,
  motivoDaRecusa,
  temSelo,
  textoDoSelo,
} from "./demandas";

export const NOVA_CONVERSA = "Nova conversa";
export const VOLTAR_PARA_A_LISTA = "Voltar às conversas";
export const ENVIO_FALHOU = "Envio falhou";
export const REENVIAR = "Reenviar";
const ENVIO_FALHOU_EXPLICADO =
  "Este card não chegou à Vitta. O que você disse continua guardado: clique em Reenviar para tentar de novo.";
const LISTA_VAZIA = "Nenhuma conversa ainda.";
const LISTA_FALHOU = "Não foi possível carregar as suas conversas. Tente recarregar a página.";
const URL_QUEM_SOU = `${BASE_TECNOLOGIA}/eu`;

type Filtro = "para_mim" | "minhas" | "todas" | "envio_falhou";
const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "para_mim", rotulo: "Para mim" },
  { valor: "minhas", rotulo: "Minhas" },
  { valor: "todas", rotulo: "Todas" },
  { valor: "envio_falhou", rotulo: ENVIO_FALHOU },
];

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

/** O link da issue, só para o Desenvolvedor e só se apontar para o GitHub. */
function LinkDaIssue({ demanda }: { demanda: Demanda }) {
  const url = demanda.issue_url;
  if (!demanda.issue_numero || !url || !url.startsWith("https://github.com/")) return null;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold text-primary underline">
      #{demanda.issue_numero}
    </a>
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
 * Desenvolvedor abriu (ADR 0083), com a Etapa e O que muda.
 */
function Acompanhamento({ demanda, token }: { demanda: Demanda; token: string | null }) {
  const [falas, setFalas] = useState<FalaDoChat[]>([]);
  const [anexos, setAnexos] = useState<AnexoDaDemanda[]>([]);

  // A conversa é complemento: sem ela (a melhoria planejada, ou a rede fora),
  // O que muda continua à vista.
  useEffect(() => {
    if (!token) return;
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
  }, [demanda.id, token]);

  return (
    <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <h2 className="normal-case text-base font-bold text-slate-900">{demanda.titulo}</h2>
        <SeloDeEtapa demanda={demanda} />
        <LinkDaIssue demanda={demanda} />
        {demanda.autor && <span className="normal-case text-text-secondary">{demanda.autor}</span>}
      </div>
      <OQueMudaDaDemanda demanda={demanda} />
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

export function ConversasDaTecnologia({ token }: { token: string | null }) {
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
      setFiltro(sim ? "para_mim" : "minhas");
    })();
    return () => {
      viva = false;
    };
  }, [token]);

  /** Relê a lista e devolve o que veio; nulo quando não deu. */
  const carregar = useCallback(async (): Promise<Demanda[] | null> => {
    if (!token || filtro === null) return null;
    const url = filtro === "minhas" ? URL_DO_CHAT_DA_ABA : `${URL_DO_CHAT_DA_ABA}?filtro=${filtro}`;
    try {
      const resposta = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!resposta.ok) {
        setErroDaLista(LISTA_FALHOU);
        return null;
      }
      const corpo: unknown = await resposta.json();
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
  }, [token, filtro]);

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

  /** O card nasceu pelo Reenviar: a lista relê e a Demanda abre como está agora. */
  async function aoReenviar(demandaId: string) {
    const lidas = await carregar();
    const atual = lidas?.find((d) => d.id === demandaId);
    abrir(atual ?? (aberta ? { ...aberta, envio_falhou: false, envio_motivo: null, tem_vinculo: true } : null));
  }

  function abrir(demanda: Demanda | null) {
    setAberta(demanda);
    setDestacada(demanda?.id ?? null);
    setChave((atual) => atual + 1);
    setNaTela("conversa");
  }

  return (
    <div className="md:grid md:grid-cols-[16rem_minmax(0,1fr)] md:gap-4 md:items-start">
      <div className={`${naTela === "lista" ? "" : "hidden"} md:block space-y-3`}>
        <button
          type="button"
          onClick={() => abrir(null)}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold"
        >
          <Plus className="w-4 h-4" />
          {NOVA_CONVERSA}
        </button>
        {desenvolvedor && (
          <div role="group" aria-label="Filtro das conversas" className="flex gap-1">
            {FILTROS.map(({ valor, rotulo }) => (
              <button
                key={valor}
                type="button"
                aria-pressed={filtro === valor}
                onClick={() => setFiltro(valor)}
                className={`flex-1 px-3 py-1.5 rounded-xl border text-xs font-semibold ${
                  filtro === valor ? "border-primary bg-primary/5 text-primary" : "border-border text-text-secondary"
                }`}
              >
                {rotulo}
              </button>
            ))}
          </div>
        )}
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
          className="md:hidden inline-flex items-center gap-1.5 text-sm font-semibold text-primary"
        >
          <ArrowLeft className="w-4 h-4" />
          {VOLTAR_PARA_A_LISTA}
        </button>
        {aberta?.envio_falhou && (
          <AvisoDoEnvioFalhou key={`envio-${chave}`} demanda={aberta} token={token} onReenviado={aoReenviar} />
        )}
        {aberta?.tem_vinculo || aberta?.minha === false ? (
          <Acompanhamento key={chave} demanda={aberta} token={token} />
        ) : (
          <ChatDaTecnologia key={chave} token={token} demandaId={aberta?.id ?? null} onMudou={aoMudar} />
        )}
      </div>
    </div>
  );
}
