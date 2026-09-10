"use client";

/**
 * A aba Histórico (issue #641, PRD #634, ADR 0050).
 *
 * As Demandas Concluídas e Canceladas, da que fechou por último para a mais
 * antiga, com busca por texto e a linha que diz quando e por quem cada uma
 * fechou. Abrir uma linha abre o MESMO modal do Quadro: o Histórico é uma
 * vista, não uma segunda tela da Demanda.
 *
 * **A busca varre título, descrição e o texto das RESPOSTAS da Conversa**, e
 * quem varre é o backend (a Conversa mora em outra tabela). A linha de
 * movimento fica de fora: o texto dela carrega o nome de quem moveu, e buscar
 * "Pedro" acharia toda Demanda que ele tocou.
 *
 * **A busca espera a digitação parar** (`ATRASO_DA_BUSCA`). Sem isso, cada
 * tecla viraria uma varredura do Histórico inteiro no servidor. O selo de
 * sequência do `useListaDeDemandas` continua valendo por cima disso: esperar a
 * digitação diminui os pedidos, mas não impede que dois voltem fora de ordem.
 *
 * **Sem paginação:** a lista vem inteira, e o contador diz quantas são. Para o
 * volume de um Quadro de cinco pessoas isso é uma leitura pequena; a paginação
 * entra quando o número na tela mostrar que precisa.
 */

import { useEffect, useState } from "react";
import { AlertCircle, Search } from "lucide-react";

import { DemandaModal } from "./DemandaModal";
import { FiltrosDeDemandas } from "./FiltrosDeDemandas";
import { SeloDeEtapa } from "./SeloDeEtapa";
import { TipoIcone } from "./TipoIcone";
import { useListaDeDemandas } from "./useListaDeDemandas";
import {
  DemandaDoHistorico,
  EuNaAba,
  FiltrosDoQuadro,
  fraseDoHistoricoVazio,
  O_QUE_A_BUSCA_PROCURA,
  PessoaDaAba,
  ProdutoDaEscolha,
  queryDoHistorico,
  temFiltroAtivo,
  textoDoDesfecho,
} from "./demandas";

type Props = {
  token: string | null;
  /** Se a autenticação ainda está resolvendo (ver `MinhaVez`). */
  carregandoAuth: boolean;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
  filtros: FiltrosDoQuadro;
  onFiltrosChange: (filtros: FiltrosDoQuadro) => void;
  /**
   * Quem está olhando, do ponto de vista do Vínculo (issue #674).
   *
   * Vem de cima, e não de uma chamada por painel: as três abas mostram o mesmo
   * modal, e três respostas do mesmo `GET /eu` só multiplicariam a ida à rede
   * e o risco de as abas discordarem entre si.
   */
  eu: EuNaAba;
};

/** Quanto a busca espera a digitação parar, em milissegundos. */
export const ATRASO_DA_BUSCA = 300;

const SEM_SESSAO =
  "Não foi possível carregar o Histórico: a sessão não está ativa ou o servidor não respondeu. " +
  "Tente recarregar a página.";

const NAO_DEU_PARA_CARREGAR = "Não foi possível carregar o Histórico.";

export function HistoricoDemandas({ token, carregandoAuth, produtos, pessoas, filtros, onFiltrosChange, eu }: Props) {
  /** O que está escrito na caixa agora. */
  const [termo, setTermo] = useState("");
  /** O que já foi perguntado ao servidor: o termo depois que a digitação parou. */
  const [termoBuscado, setTermoBuscado] = useState("");

  useEffect(() => {
    const espera = setTimeout(() => setTermoBuscado(termo), ATRASO_DA_BUSCA);
    return () => clearTimeout(espera);
  }, [termo]);

  const {
    itens: demandas,
    carregando,
    erro,
    recarregar,
  } = useListaDeDemandas<DemandaDoHistorico>({
    token,
    carregandoAuth,
    caminho: `/historico${queryDoHistorico(filtros, termoBuscado)}`,
    semSessao: SEM_SESSAO,
    falhaAoCarregar: NAO_DEU_PARA_CARREGAR,
  });

  const [abertaId, setAbertaId] = useState<string | null>(null);
  const aberta = demandas.find((d) => d.id === abertaId) ?? null;

  function linha(demanda: DemandaDoHistorico) {
    return (
      <li key={demanda.id} className="px-4 py-3 space-y-1">
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
          {/* O par na tela dos carimbos de desfecho do backend: sem esta linha,
              "quem fechou e quando" ficaria gravado no banco e invisível. */}
          <span className="font-medium text-text-secondary">{textoDoDesfecho(demanda)}</span>
          {/* O mesmo selo dos outros dois cards (issue #674): o Histórico
              também mostra em que ponto o desenvolvimento parou. */}
          <SeloDeEtapa demanda={demanda} />
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

      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          aria-label="Buscar no Histórico"
          placeholder={O_QUE_A_BUSCA_PROCURA}
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
        />
      </div>

      <FiltrosDeDemandas
        filtros={filtros}
        onFiltrosChange={onFiltrosChange}
        produtos={produtos}
        pessoas={pessoas}
        oQueEstaFiltrado="O Histórico"
      />

      {carregando ? (
        <p className="text-sm text-text-secondary">Carregando o Histórico...</p>
      ) : demandas.length === 0 ? (
        // Com a leitura falhada o código NÃO SABE se o Histórico está vazio:
        // dizer que não há nada seria afirmar um fato não verificado.
        // A frase cita o `termoBuscado`, e não o que está sendo digitado: entre
        // a tecla e o fim da espera, a lista na tela ainda é a da busca
        // anterior, e citar o termo novo daria a ele um resultado que não é
        // dele.
        !erro && (
          <p className="text-sm text-text-secondary">{fraseDoHistoricoVazio(termoBuscado, temFiltroAtivo(filtros))}</p>
        )
      ) : (
        <>
          <p className="text-sm text-text-secondary">
            {demandas.length === 1 ? "1 Demanda fechada" : `${demandas.length} Demandas fechadas`}
          </p>
          <ul
            aria-label="Demandas concluídas e canceladas"
            className="divide-y divide-border rounded-xl border border-border bg-surface"
          >
            {demandas.map(linha)}
          </ul>
        </>
      )}

      {aberta && (
        <DemandaModal
          demanda={aberta}
          produtos={produtos}
          pessoas={pessoas}
          token={token}
          eu={eu}
          onFechar={() => setAbertaId(null)}
          onMudou={recarregar}
        />
      )}
    </div>
  );
}
