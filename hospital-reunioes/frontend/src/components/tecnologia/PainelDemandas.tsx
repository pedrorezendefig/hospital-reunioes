"use client";

/**
 * O Painel da aba Tecnologia (issue #1059, PRD #1056), no lugar de "Minha vez"
 * e do Histórico da issue #641.
 *
 * Uma tela de leitura: no topo, quatro números (abertas, com o hospital, em
 * desenvolvimento, entregues nos últimos 30 dias); embaixo, três blocos
 * recolhíveis em linhas, não em cards:
 *
 * - **Com você**: o que espera pela pessoa LOGADA. Quem decide de quem é a vez
 *   é o backend, que lê o participante da própria sessão: o `useAuth` carrega o
 *   id do Supabase Auth, e não o `participantes.id`. A tela nem manda quem é a
 *   pessoa. Vazio aqui é BOA NOTÍCIA, e a frase diz isso;
 * - **Entregas**: as Demandas abertas com Vínculo, com a Etapa, as partes e a
 *   versão quando a Etapa é Em produção. É onde o diretor vê o que a Vitta está
 *   fazendo sem abrir card;
 * - **Histórico**: as Concluídas e Canceladas, da que fechou por último para a
 *   mais antiga, com a busca de sempre (título, descrição e texto das respostas
 *   da Conversa, varridos pelo backend). A busca espera a digitação parar
 *   (`ATRASO_DA_BUSCA`): sem isso, cada tecla seria uma ida ao servidor.
 *
 * Clicar numa linha abre o MESMO modal do Quadro: o Painel é uma vista, não uma
 * segunda tela da Demanda. Nada aqui é número por pessoa (ADR 0061): o "Com
 * você" é uma lista, sem contador.
 *
 * O Painel inteiro vem de uma rota só (`/painel`), e a busca troca a leitura.
 * As defesas da leitura (sessão carregando, falha que leva o Painel de antes,
 * corrida de duas leituras no ar) moram no `useLeituraDoPainel`.
 */

import { ReactNode, useEffect, useId, useState } from "react";
import { AlertCircle, CalendarClock, ChevronDown, Search } from "lucide-react";

import { DemandaModal } from "./DemandaModal";
import { SeloDeEtapa } from "./SeloDeEtapa";
import { TipoIcone } from "./TipoIcone";
import { useLeituraDoPainel } from "./useLeituraDoPainel";
import {
  Demanda,
  DemandaComVoce,
  DemandaDaEntrega,
  DemandaDoHistorico,
  estaAtrasado,
  EuNaAba,
  fraseDasEntregasVazias,
  fraseDoComVoceVazio,
  fraseDoHistoricoVazio,
  idadeEmDias,
  IDADE_VERMELHA_A_PARTIR_DE,
  MOTIVO_ROTULO,
  O_QUE_A_BUSCA_PROCURA,
  PainelDaAba,
  PessoaDaAba,
  PRIORIDADE_ROTULO,
  PrioridadeDemanda,
  prazoLegivel,
  ProdutoDaEscolha,
  queryDoHistorico,
  ROTULO_DOS_NUMEROS,
  textoDaIdade,
  textoDoDesfecho,
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
  /**
   * Quem está olhando, do ponto de vista do Vínculo (issue #674).
   *
   * Vem de cima, e não de uma chamada própria: as duas abas mostram o mesmo
   * modal, e duas respostas do mesmo `GET /eu` só multiplicariam a ida à rede
   * e o risco de as abas discordarem entre si.
   */
  eu: EuNaAba;
};

/** Quanto a busca espera a digitação parar, em milissegundos. */
export const ATRASO_DA_BUSCA = 300;

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
  "Não foi possível carregar o Painel: a sessão não está ativa ou o servidor não respondeu. " +
  "Tente recarregar a página.";

const NAO_DEU_PARA_CARREGAR = "Não foi possível carregar o Painel.";

export function PainelDemandas({ token, carregandoAuth, produtos, pessoas, eu }: Props) {
  /** O que está escrito na caixa agora. */
  const [termo, setTermo] = useState("");
  /** O que já foi perguntado ao servidor: o termo depois que a digitação parou. */
  const [termoBuscado, setTermoBuscado] = useState("");

  useEffect(() => {
    const espera = setTimeout(() => setTermoBuscado(termo), ATRASO_DA_BUSCA);
    return () => clearTimeout(espera);
  }, [termo]);

  const {
    dados: painel,
    carregando,
    erro,
    recarregar,
  } = useLeituraDoPainel<PainelDaAba>({
    token,
    carregandoAuth,
    caminho: `/painel${queryDoHistorico(termoBuscado)}`,
    semSessao: SEM_SESSAO,
    falhaAoCarregar: NAO_DEU_PARA_CARREGAR,
  });

  const [abertaId, setAbertaId] = useState<string | null>(null);
  // A Demanda pode estar em mais de um bloco (a minha que está em
  // desenvolvimento está no "Com você" e nas Entregas); o card é o mesmo.
  const todas: Demanda[] = painel ? [...painel.com_voce, ...painel.entregas, ...painel.historico] : [];
  const aberta = todas.find((d) => d.id === abertaId) ?? null;
  const agora = new Date();

  /** O título da linha, que é o botão que abre o card. */
  function titulo(demanda: Demanda) {
    return (
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
    );
  }

  function linhaComVoce(demanda: DemandaComVoce) {
    const dias = idadeEmDias(demanda.criado_em, agora);
    const velha = dias >= IDADE_VERMELHA_A_PARTIR_DE;
    const atrasada = estaAtrasado(demanda.prazo, agora);

    return (
      <li key={demanda.id} className="px-4 py-3 space-y-2">
        {titulo(demanda)}
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <span>{demanda.produto_nome ?? "Sem Produto"}</span>
          <span>{demanda.responsavel_nome ?? "Sem responsável"}</span>
          <span className={`px-2 py-0.5 rounded font-medium ${CLASSE_PRIORIDADE[demanda.prioridade]}`}>
            {PRIORIDADE_ROTULO[demanda.prioridade]}
          </span>
          <span className={velha ? "font-semibold text-red-600" : ""}>{textoDaIdade(dias)}</span>
          <SeloDeEtapa demanda={demanda} />
          {atrasada && demanda.prazo && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-medium bg-red-50 text-red-700">
              <CalendarClock className="w-3 h-3" />
              Atrasada desde {prazoLegivel(demanda.prazo)}
            </span>
          )}
          {/* O par na tela do carimbo do backend: o bloco traz tanto o que é
              meu quanto o que me chamaram, e sem esta marca o card de uma
              Demanda cujo responsável é outra pessoa não explicaria por que
              está aqui. */}
          {MOTIVO_ROTULO[demanda.motivo] && (
            <span className="px-2 py-0.5 rounded font-medium bg-primary/5 text-primary">
              {MOTIVO_ROTULO[demanda.motivo]}
            </span>
          )}
        </div>
      </li>
    );
  }

  function linhaDaEntrega(demanda: DemandaDaEntrega) {
    return (
      <li key={demanda.id} className="px-4 py-3 space-y-1">
        {titulo(demanda)}
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <span>{demanda.produto_nome ?? "Sem Produto"}</span>
          {/* A Etapa, as partes e, em Em produção, desde qual versão: o
              mesmo selo do Quadro (issue #1065). */}
          <SeloDeEtapa demanda={demanda} />
        </div>
      </li>
    );
  }

  function linhaDoHistorico(demanda: DemandaDoHistorico) {
    return (
      <li key={demanda.id} className="px-4 py-3 space-y-1">
        {titulo(demanda)}
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <span>{demanda.produto_nome ?? "Sem Produto"}</span>
          {/* O par na tela dos carimbos de desfecho do backend: sem esta linha,
              "quem fechou e quando" ficaria gravado no banco e invisível. */}
          <span className="font-medium text-text-secondary">{textoDoDesfecho(demanda)}</span>
          <SeloDeEtapa demanda={demanda} />
        </div>
      </li>
    );
  }

  /**
   * O conteúdo de um bloco que só depende da leitura, e não da busca.
   *
   * Sem Painel lido, o bloco não afirma nada: enquanto carrega diz que está
   * carregando, e com a leitura falhada fica calado (o alerta de cima diz o
   * que houve). A frase de vazio só sai com a leitura BOA em mãos: com ela
   * falhada o código NÃO SABE se há algo esperando, e "nada esperando por você"
   * seria afirmar um fato não verificado, ainda por cima como boa notícia.
   */
  function conteudo<T>(lista: T[] | undefined, rotulo: string, vazio: string, linha: (item: T) => ReactNode) {
    if (!lista) {
      return carregando ? <p className="px-4 py-3 text-sm text-text-secondary">Carregando...</p> : null;
    }
    if (lista.length === 0) return <p className="px-4 py-3 text-sm text-text-secondary">{vazio}</p>;
    return (
      <ul aria-label={rotulo} className="divide-y divide-border">
        {lista.map(linha)}
      </ul>
    );
  }

  const historico = painel?.historico;

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

      {painel && (
        <ul aria-label="Números do Painel" className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {ROTULO_DOS_NUMEROS.map(([chave, rotulo]) => (
            <li key={chave} className="rounded-xl border border-border bg-surface px-4 py-3">
              <span className="block text-2xl font-bold text-text">{painel.numeros[chave]}</span>
              <span className="block text-xs text-text-secondary">{rotulo}</span>
            </li>
          ))}
        </ul>
      )}

      <Bloco titulo="Com você">
        {conteudo(painel?.com_voce, "Demandas esperando por você", fraseDoComVoceVazio(), linhaComVoce)}
      </Bloco>

      <Bloco titulo="Entregas">
        {conteudo(painel?.entregas, "Demandas em desenvolvimento", fraseDasEntregasVazias(), linhaDaEntrega)}
      </Bloco>

      <Bloco titulo="Histórico">
        <div className="px-4 pt-3">
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
        </div>
        {/* O Histórico é o único bloco que a busca troca: enquanto a leitura
            nova não chega, a lista de antes não é a resposta do termo novo, e
            a espera toma o lugar dela. */}
        {carregando ? (
          <p className="px-4 py-3 text-sm text-text-secondary">Carregando o Histórico...</p>
        ) : !historico ? null : historico.length === 0 ? (
          // A frase cita o `termoBuscado`, e não o que está sendo digitado:
          // entre a tecla e o fim da espera, a lista na tela ainda é a da busca
          // anterior, e citar o termo novo daria a ele um resultado que não é
          // dele.
          <p className="px-4 py-3 text-sm text-text-secondary">{fraseDoHistoricoVazio(termoBuscado)}</p>
        ) : (
          <>
            <p className="px-4 pt-3 text-sm text-text-secondary">
              {historico.length === 1 ? "1 Demanda fechada" : `${historico.length} Demandas fechadas`}
            </p>
            <ul aria-label="Demandas concluídas e canceladas" className="divide-y divide-border">
              {historico.map(linhaDoHistorico)}
            </ul>
          </>
        )}
      </Bloco>

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

/**
 * Um bloco recolhível do Painel.
 *
 * Nasce aberto: o Painel é a primeira tela no celular, e um bloco fechado
 * esconderia justamente o que espera por quem abriu. Recolher é escolha de
 * quem lê, para dar lugar ao bloco que interessa agora.
 */
function Bloco({ titulo, children }: { titulo: string; children: ReactNode }) {
  const [aberto, setAberto] = useState(true);
  const id = useId();

  return (
    <section aria-labelledby={`${id}-titulo`} className="rounded-xl border border-border bg-surface">
      <h3 id={`${id}-titulo`} className="text-sm font-semibold text-text">
        <button
          type="button"
          aria-expanded={aberto}
          aria-controls={`${id}-conteudo`}
          onClick={() => setAberto((antes) => !antes)}
          className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-primary/5 transition-colors rounded-xl"
        >
          <span>{titulo}</span>
          <ChevronDown className={`w-4 h-4 text-text-secondary transition-transform ${aberto ? "rotate-180" : ""}`} />
        </button>
      </h3>
      {aberto && (
        <div id={`${id}-conteudo`} className="border-t border-border pb-1">
          {children}
        </div>
      )}
    </section>
  );
}
