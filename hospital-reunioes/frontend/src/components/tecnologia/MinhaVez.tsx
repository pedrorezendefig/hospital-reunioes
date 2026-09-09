"use client";

/**
 * A aba "Minha vez" (issue #641, PRD #634, ADR 0050).
 *
 * O que espera pela pessoa LOGADA: as Demandas abertas em que ela é a
 * responsável, mais aquelas em que a mencionaram e ela ainda não respondeu
 * depois da menção. Alta primeiro; dentro de cada prioridade, a mais velha na
 * frente.
 *
 * Quem decide de quem é a vez é o backend, e não esta tela: o `useAuth` carrega
 * o id do Supabase Auth, e não o `participantes.id` que assina responsável e
 * menção. A tela nem manda quem é a pessoa; o endpoint lê o participante da
 * própria sessão. É o mesmo motivo pelo qual o `editavel_ate` da Conversa vem
 * calculado de lá (issue #638).
 *
 * Lista vazia aqui é BOA NOTÍCIA, e a frase diz isso: "nada esperando por
 * você" não pode parecer falha de carregamento (ver `fraseDaMinhaVezVazia`).
 */

import { useState } from "react";
import { AlertCircle, CalendarClock } from "lucide-react";

import { DemandaModal } from "./DemandaModal";
import { FiltrosDeDemandas } from "./FiltrosDeDemandas";
import { TipoIcone } from "./TipoIcone";
import { useListaDeDemandas } from "./useListaDeDemandas";
import {
  DemandaDaMinhaVez,
  estaAtrasado,
  FiltrosDoQuadro,
  fraseDaMinhaVezVazia,
  idadeEmDias,
  IDADE_VERMELHA_A_PARTIR_DE,
  MOTIVO_ROTULO,
  PessoaDaAba,
  PRIORIDADE_ROTULO,
  PrioridadeDemanda,
  prazoLegivel,
  ProdutoDaEscolha,
  queryDeFiltros,
  temFiltroAtivo,
  textoDaIdade,
} from "./demandas";

type Props = {
  token: string | null;
  /**
   * Se a autenticação ainda está resolvendo.
   *
   * Sem esta prop, o token nulo do primeiro render seria lido como "não há
   * sessão" e o alerta vermelho piscaria em toda abertura da aba.
   */
  carregandoAuth: boolean;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
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
 * Ela NÃO manda entrar de novo: o hook devolve `token: null` tanto com a sessão
 * acabada quanto com o `getUser()` dele falhando por rede, e o componente não
 * distingue as duas. Recarregar é possível nos dois casos.
 */
const SEM_SESSAO =
  "Não foi possível carregar o que espera por você: a sessão não está ativa ou o servidor não respondeu. " +
  "Tente recarregar a página.";

const NAO_DEU_PARA_CARREGAR = "Não foi possível carregar o que espera por você.";

export function MinhaVez({ token, carregandoAuth, produtos, pessoas, filtros, onFiltrosChange }: Props) {
  const {
    itens: demandas,
    carregando,
    erro,
    recarregar,
  } = useListaDeDemandas<DemandaDaMinhaVez>({
    token,
    carregandoAuth,
    caminho: `/minha-vez${queryDeFiltros(filtros)}`,
    semSessao: SEM_SESSAO,
    falhaAoCarregar: NAO_DEU_PARA_CARREGAR,
  });

  const [abertaId, setAbertaId] = useState<string | null>(null);
  const aberta = demandas.find((d) => d.id === abertaId) ?? null;
  const agora = new Date();

  function linha(demanda: DemandaDaMinhaVez) {
    const dias = idadeEmDias(demanda.criado_em, agora);
    const velha = dias >= IDADE_VERMELHA_A_PARTIR_DE;
    const atrasada = estaAtrasado(demanda.prazo, agora);

    return (
      <li key={demanda.id} className="px-4 py-3 space-y-2">
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
          {/* O par na tela do carimbo do backend: a aba traz tanto o que é meu
              quanto o que me chamaram, e sem esta marca o card de uma Demanda
              cujo responsável é outra pessoa não explicaria por que está aqui. */}
          {MOTIVO_ROTULO[demanda.motivo] && (
            <span className="px-2 py-0.5 rounded font-medium bg-primary/5 text-primary">
              {MOTIVO_ROTULO[demanda.motivo]}
            </span>
          )}
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

      <FiltrosDeDemandas
        filtros={filtros}
        onFiltrosChange={onFiltrosChange}
        produtos={produtos}
        pessoas={pessoas}
        oQueEstaFiltrado="Minha vez"
      />

      {carregando ? (
        <p className="text-sm text-text-secondary">Carregando o que espera por você...</p>
      ) : demandas.length === 0 ? (
        // A frase não sai quando há erro: com a leitura falhada o código NÃO
        // SABE se há algo esperando, e dizer "nada esperando por você" seria
        // afirmar um fato não verificado, ainda por cima como boa notícia.
        !erro && <p className="text-sm text-text-secondary">{fraseDaMinhaVezVazia(temFiltroAtivo(filtros))}</p>
      ) : (
        <ul aria-label="Demandas esperando por você" className="divide-y divide-border rounded-xl border border-border bg-surface">
          {demandas.map(linha)}
        </ul>
      )}

      {aberta && (
        <DemandaModal
          demanda={aberta}
          produtos={produtos}
          pessoas={pessoas}
          token={token}
          onFechar={() => setAbertaId(null)}
          onMudou={recarregar}
        />
      )}
    </div>
  );
}
