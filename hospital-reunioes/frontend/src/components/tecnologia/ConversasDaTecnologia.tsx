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
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Loader2, Plus } from "lucide-react";

import { ChatDaTecnologia, Fala } from "./ChatDaTecnologia";
import { OQueMudaDaDemanda } from "./OQueMudaDaDemanda";
import { SeloDeEtapa } from "./SeloDeEtapa";
import { conversaValida, FalaDoChat, URL_DO_CHAT_DA_ABA, urlDaConversa } from "./chat";
import {
  CLASSIFICACAO_CLASSE,
  CLASSIFICACAO_ROTULO,
  Demanda,
  ETAPA_CLASSE,
  ETAPA_ROTULO,
  FALHA_DE_CONEXAO,
  temSelo,
  textoDoSelo,
} from "./demandas";

export const NOVA_CONVERSA = "Nova conversa";
export const VOLTAR_PARA_A_LISTA = "Voltar às conversas";
const LISTA_VAZIA = "Nenhuma conversa ainda.";
const LISTA_FALHOU = "Não foi possível carregar as suas conversas. Tente recarregar a página.";

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

/** A conversa que já virou card: só leitura, com a Etapa e O que muda. */
function Acompanhamento({ demanda, token }: { demanda: Demanda; token: string | null }) {
  const [falas, setFalas] = useState<FalaDoChat[]>([]);

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
        if (viva && conversaValida(corpo)) setFalas(corpo.mensagens);
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
        <h2 className="text-base font-bold text-slate-900">{demanda.titulo}</h2>
        <SeloDeEtapa demanda={demanda} />
      </div>
      <OQueMudaDaDemanda demanda={demanda} />
      {falas.length > 0 && (
        <div role="log" className="space-y-3 border-t border-slate-100 pt-4">
          {falas.map((fala, i) => (
            <Fala key={i} fala={fala} />
          ))}
        </div>
      )}
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

  const carregar = useCallback(async () => {
    if (!token) return;
    try {
      const resposta = await fetch(URL_DO_CHAT_DA_ABA, { headers: { Authorization: `Bearer ${token}` } });
      if (!resposta.ok) {
        setErroDaLista(LISTA_FALHOU);
        return;
      }
      const corpo: unknown = await resposta.json();
      if (!Array.isArray(corpo)) {
        setErroDaLista(LISTA_FALHOU);
        return;
      }
      setDemandas(corpo.filter(itemValido));
      setErroDaLista(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar as conversas", e);
      setErroDaLista(FALHA_DE_CONEXAO);
    }
  }, [token]);

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
                    <span className="font-medium text-text-primary line-clamp-2">{demanda.titulo}</span>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <EtapaNaLista demanda={demanda} />
                      <ClassificacaoNaLista demanda={demanda} />
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
        {aberta?.tem_vinculo ? (
          <Acompanhamento key={chave} demanda={aberta} token={token} />
        ) : (
          <ChatDaTecnologia key={chave} token={token} demandaId={aberta?.id ?? null} onMudou={aoMudar} />
        )}
      </div>
    </div>
  );
}
