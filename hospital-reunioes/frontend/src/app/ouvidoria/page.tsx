"use client";

import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, Archive, CheckCircle2, Loader2, Lock, Megaphone, Plus } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AtalhosDaOuvidoria } from "@/components/ouvidoria/AtalhosDaOuvidoria";
import { NovaManifestacaoModal } from "@/components/ouvidoria/NovaManifestacaoModal";
import { ValidarModal } from "@/components/ouvidoria/ValidarModal";
import { ListaDaFila } from "@/components/ouvidoria/ListaDaFila";
import {
  aguardandoSeuEncerramento,
  agruparPorStatus,
  classeDoStatus,
  rotuloDoStatus,
  TITULO_AGUARDANDO_ENCERRAMENTO,
  type ManifestacaoIndice,
} from "@/lib/ouvidoria/fila";
import { avisosDeDegradacao, hojeNoHospital } from "@/lib/ouvidoria/painel";
import { type ResultadoDaCobranca } from "@/lib/ouvidoria/cobranca";
import { classificarPrazoDaManifestacao, EM_ANDAMENTO } from "@/lib/ouvidoria/prazo";
import { ALTURA_DE_TOQUE } from "@/lib/toque";
import { EncerrarModal } from "@/components/ouvidoria/EncerrarModal";
import { type Responsavel } from "@/lib/ouvidoria/validacao";

/**
 * A marca do lote na trava de "uma chamada de arquivo por vez" (issue #594).
 * Não é id de manifestação nenhuma, e não precisa ser: o que a trava guarda é
 * o que está em voo, e o lote está em voo sobre a lista inteira.
 */
const O_LOTE = "todos-os-encerrados";

export default function OuvidoriaPage() {
  const [manifestacoes, setManifestacoes] = useState<ManifestacaoIndice[]>([]);
  const [loading, setLoading] = useState(true);
  const [semAcesso, setSemAcesso] = useState(false);
  const [erroCarga, setErroCarga] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [hoje, setHoje] = useState<string | null>(null);
  const [registrando, setRegistrando] = useState(false);
  const [validando, setValidando] = useState<ManifestacaoIndice | null>(null);
  const [encerrando, setEncerrando] = useState<ManifestacaoIndice | null>(null);
  // O que o servidor não conseguiu ler nesta carga (issue #449). Chega aqui
  // pelo marcador de novidade (issue #484): trilha fora do ar desenha uma fila
  // sem ponto nenhum, que é indistinguível de uma fila sem novidade.
  const [degradado, setDegradado] = useState<string[]>([]);
  // Quem responde por cada setor, para a linha escrever um nome ao lado da
  // área (issue #495, RN-72). Cadastro pequeno e estável, lido uma vez por
  // carga da tela em vez de por caso.
  // `null` é "ainda não li", e não "não tem ninguém": quem está fora da
  // Ouvidoria nunca lê este cadastro, e afirmar ausência a partir do silêncio
  // faria toda linha da fila mentir sobre o setor (issue #449, mesma régua).
  const [responsaveis, setResponsaveis] = useState<Responsavel[] | null>(null);
  // O que cada cobrança em voo está fazendo, por manifestação. Fica na tela, e
  // não na linha, porque o clique dispara duas chamadas e a resposta precisa
  // sobreviver a um rerender da lista.
  const [cobrancas, setCobrancas] = useState<Record<string, ResultadoDaCobranca>>({});
  // O filtro do Arquivo (issue #592, ADR 0047). Desligado é a lista de
  // trabalho, e é assim que a tela nasce: o arquivo existe para desafogar a
  // fila, e abrir nele seria abrir no que já acabou.
  //
  // A lista NUNCA mistura os dois mundos, e quem separa é o servidor: a tela
  // recarrega pedindo um dos dois, em vez de peneirar em memória uma resposta
  // que traria os dois juntos.
  const [arquivados, setArquivados] = useState(false);
  // A recusa do servidor ao arquivar ou desarquivar, na frase dele. Sem isto, o
  // carimbo que o backend não gravou some em silêncio: a linha fica idêntica e
  // o ouvidor clica de novo sem saber por quê.
  const [erroDoArquivo, setErroDoArquivo] = useState<string | null>(null);
  // A manifestação com uma chamada de arquivo em voo. Trava o duplo clique, que
  // dispararia dois POST e duas recargas sobre a mesma linha.
  //
  // O lote entra na MESMA trava, com a marca abaixo no lugar de um id: os dois
  // mexem na mesma lista, e travas separadas deixariam o lote e o botão de uma
  // linha correrem juntos sobre ela (issue #594).
  const [noArquivo, setNoArquivo] = useState<string | null>(null);
  // O que o lote fez, na contagem que o SERVIDOR devolveu, e não na que a tela
  // supôs ao clicar: entre a carga e o clique, outra pessoa pode ter encerrado
  // ou arquivado um caso, e o número da tela mentiria (issue #594).
  const [resumoDoLote, setResumoDoLote] = useState<string | null>(null);
  // A carga mais recente. Ligar e desligar o filtro depressa deixa dois `fetch`
  // no ar, e sem este número quem responde por último pinta a lista, mesmo
  // sendo a resposta que o ouvidor já abandonou.
  const cargaMaisRecente = useRef(0);

  const { participante } = useCurrentParticipante();
  const podeAbrirDossie = Boolean(participante?.perfil_ouvidoria);

  // Recarrega a fila depois de registrar: o caso novo precisa aparecer sem o
  // ouvidor ter que atualizar a página na mão.
  async function recarregar(sessionToken: string, mostrarArquivados: boolean) {
    const minhaCarga = ++cargaMaisRecente.current;
    const venceu = () => minhaCarga !== cargaMaisRecente.current;
    try {
      // O parâmetro só entra quando o filtro está ligado: a lista de trabalho
      // continua sendo a mesma URL de sempre.
      const res = await fetch(
        `/api/ouvidoria/protocolos${mostrarArquivados ? "?arquivados=sim" : ""}`,
        {
          headers: { Authorization: `Bearer ${sessionToken}` },
        }
      );
      // Todos os `await` acontecem ANTES da guarda, e a guarda antes de toda
      // escrita de estado: é isso que a torna um ponto só. Resposta vencida
      // não pinta nada, nem a lista nem o erro, porque ela é a foto de um
      // filtro que o ouvidor já trocou.
      const corpo = res.ok ? await res.json() : null;
      if (venceu()) return;
      if (res.status === 403) {
        setSemAcesso(true);
      } else if (res.ok) {
        // O dia é relido a cada carga, como no painel: fila aberta na virada da
        // meia-noite continuaria chamando de "vence hoje" o que venceu ontem, e
        // deixando em âmbar o que passou a vencer hoje (issue #488).
        setHoje(hojeNoHospital());
        setManifestacoes(corpo.protocolos);
        setDegradado(corpo.degradado ?? []);
      } else {
        // Erro não pode virar "nenhuma manifestação": falso negativo num
        // painel de prazo.
        setErroCarga(true);
      }
    } catch (e) {
      console.error("Erro ao carregar manifestações:", e);
      if (venceu()) return;
      setErroCarga(true);
    }
  }

  useEffect(() => {
    // O dia civil do HOSPITAL, e não o do navegador, só após montar: evita
    // divergência de hidratação no destaque de prazo. O fuso importa desde que
    // o semáforo passou a comparar dias (issue #488): num navegador em outro
    // fuso, "vence hoje" viraria "vence amanhã" na virada da noite, e a fila
    // diria o contrário do painel sobre o mesmo caso. Quem manda no semáforo é a
    // releitura do `recarregar`: sem linha na tela não há cor para pintar, e
    // esta chamada existe para espelhar o painel, não para cobrir um caso.
    setHoje(hojeNoHospital());

    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      if (!sessionToken) {
        setLoading(false);
        return;
      }
      // A tela abre na lista de trabalho, sempre: o arquivo existe para
      // desafogar a fila, e abrir nele seria abrir no que já acabou.
      await recarregar(sessionToken, false);
      setLoading(false);
    }
    init();
  }, []);

  // O cadastro de responsáveis só é lido por quem tem o Perfil da Ouvidoria: a
  // rota o exige, e pedir sem ele renderia um 403 por carga sem nada na tela
  // para mostrar. Quem está fora da Ouvidoria também chega nesta tela (o índice
  // é da equipe de Reuniões inteira), e para ele o cadastro segue `null`: a
  // linha então não escreve nome nenhum, em vez de afirmar "Sem responsável"
  // sobre um cadastro que ela nunca leu.
  //
  // Falha de leitura não derruba a fila e também não vira afirmação: entra no
  // mesmo `degradado` do calendário e da trilha (issue #449), que já tem a
  // frase pronta para a leitura `responsaveis`.
  useEffect(() => {
    if (!token || !podeAbrirDossie) return;
    let vivo = true;
    (async () => {
      const degradar = () =>
        setDegradado((antes) => (antes.includes("responsaveis") ? antes : [...antes, "responsaveis"]));
      try {
        const res = await fetch("/api/ouvidoria/responsaveis", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          if (vivo) degradar();
          return;
        }
        const corpo = await res.json();
        if (vivo) setResponsaveis(corpo.responsaveis ?? []);
      } catch (e) {
        console.error("Erro ao carregar responsáveis:", e);
        if (vivo) degradar();
      }
    })();
    return () => {
      vivo = false;
    };
  }, [token, podeAbrirDossie]);

  /**
   * Cobrar o setor (issues #495 e #536, RN-74): o acionamento sai de novo, o
   * que antes exigia abrir o Dossiê e achar o registro certo na lista de
   * notificações.
   *
   * Uma chamada, e o destinatário é do servidor. A rota resolve quem responde
   * pelo setor HOJE (titular, senão gestor) e recusa o setor que não tem
   * ninguém: a cobrança despacha o relato integral do manifestante e um token
   * novo do portal, e escolher isso daqui deixaria a mesma regra escrita em dois
   * lugares, com o cliente dizendo para quem mandar. Antes da #536 a tela lia a
   * lista de notificações do caso só para achar o destinatário do acionamento
   * original, e travava a cobrança de todo setor que trocasse de titular.
   *
   * A fila não recarrega: cobrar não muda o estado do caso, e uma recarga aqui
   * embaralharia a lista debaixo do cursor do ouvidor.
   */
  async function cobrar(m: ManifestacaoIndice) {
    if (!token) return;
    const anotar = (resultado: ResultadoDaCobranca) =>
      setCobrancas((antes) => ({ ...antes, [m.id]: resultado }));
    anotar({ fase: "enviando" });
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${m.id}/cobrar-setor`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const corpo = await res.json().catch(() => null);
      if (!res.ok) {
        // Só os dois status com que ESTA rota explica uma recusa (setor sem
        // responsável vigente, cadastro que não pôde ser lido) chegam ao
        // ouvidor com a frase do servidor. Repassar qualquer `detail` poria um
        // "Internal Server Error" na linha da fila.
        const explicada = res.status === 409 || res.status === 503;
        anotar(
          explicada && typeof corpo?.detail === "string"
            ? { fase: "recusada", explicacao: corpo.detail }
            : { fase: "falha" }
        );
        return;
      }
      // `entregue` é o que a rota afirma sobre o provedor. Sem ele, um email
      // recusado na hora sairia da tela como cobrança feita. O `destinatario` é
      // quem o servidor escolheu, e não o nome que a linha desenhou: prometer
      // pelo nome da tela seria prometer sobre um email que não conferimos.
      anotar({
        fase: "reenviada",
        destinatario: corpo?.destinatario || "quem responde pelo setor",
        entregue: Boolean(corpo?.entregue),
      });
    } catch (e) {
      console.error("Erro ao cobrar o setor:", e);
      anotar({ fase: "falha" });
    }
  }

  /**
   * Arquivar e desarquivar pela própria lista (issue #592, ADR 0047).
   *
   * Uma chamada e uma recarga. A recarga é o que faz o caso sumir da vista (ou
   * voltar a ela) sem o ouvidor atualizar a página, e ela pede a MESMA lista
   * que está na tela: recarregar a outra trocaria o conteúdo debaixo do cursor
   * de quem só quis guardar um caso.
   *
   * Falha não some com nada e não mente: sem a recarga, a lista continua sendo
   * a de antes do clique, que é o estado verdadeiro do servidor.
   */
  async function mudarOArquivo(m: ManifestacaoIndice, metodo: "POST" | "DELETE") {
    // Uma chamada por vez: dois cliques rápidos disparariam dois POST e duas
    // recargas sobre a mesma linha.
    if (!token || noArquivo) return;
    setNoArquivo(m.id);
    setErroDoArquivo(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${m.id}/arquivo`, {
        method: metodo,
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const corpo = await res.json().catch(() => null);
        // Só os status com que ESTAS rotas explicam uma recusa chegam ao
        // ouvidor com a frase do servidor, como na cobrança ao lado. Repassar
        // qualquer `detail` poria um "Internal Server Error" na tela.
        const explicada = res.status === 403 || res.status === 409 || res.status === 503;
        setErroDoArquivo(
          explicada && typeof corpo?.detail === "string"
            ? corpo.detail
            : "Não foi possível mudar o arquivo desta manifestação. Tente de novo em instantes."
        );
        return;
      }
      await recarregar(token, arquivados);
    } catch (e) {
      console.error("Erro ao mudar o arquivo da manifestação:", e);
      setErroDoArquivo("Não foi possível falar com o servidor. Tente de novo em instantes.");
    } finally {
      setNoArquivo(null);
    }
  }

  /**
   * Arquivar todos os encerrados de uma vez (issue #594, PRD #591).
   *
   * A tela não peneira nada: ela pede o lote e adota a contagem do servidor. O
   * recorte é o mesmo dos dois lados, porque esta lista não tem filtro nenhum
   * além do próprio Arquivo, e o grupo Encerrado que oferece o botão é
   * exatamente "todo encerrado fora do arquivo".
   *
   * A confirmação é do navegador, como nas outras ações de volume da casa. Ela
   * pergunta com o número que está NA TELA, e a mensagem depois traz o número
   * que o SERVIDOR arquivou: os dois podem divergir, e quem manda é o segundo.
   *
   * `quantos` é o tamanho do grupo, e serve só à pergunta.
   */
  async function arquivarOsEncerrados(quantos: number) {
    if (!token || noArquivo) return;
    const pergunta =
      quantos === 1
        ? "Arquivar o caso encerrado? Ele sai da lista, continua contando nos relatórios e volta pelo filtro Arquivados."
        : `Arquivar os ${quantos} casos encerrados? Eles saem da lista, continuam contando nos relatórios e voltam pelo filtro Arquivados.`;
    if (!window.confirm(pergunta)) return;
    setNoArquivo(O_LOTE);
    setErroDoArquivo(null);
    setResumoDoLote(null);
    try {
      const res = await fetch("/api/ouvidoria/manifestacoes/arquivo-dos-encerrados", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const corpo = await res.json().catch(() => null);
      if (!res.ok) {
        // Os mesmos status com que ESTA rota explica uma recusa, como no ato de
        // um caso ao lado. Repassar qualquer `detail` poria um "Internal Server
        // Error" na tela do ouvidor.
        const explicada = res.status === 403 || res.status === 503;
        setErroDoArquivo(
          explicada && typeof corpo?.detail === "string"
            ? corpo.detail
            : "Não foi possível arquivar os encerrados. Tente de novo em instantes."
        );
        return;
      }
      // Contagem ausente ou de outro tipo vira zero, e o zero tem frase
      // própria: um "0 manifestações arquivadas" seco leria como defeito, e o
      // que aconteceu é que não havia o que guardar.
      const arquivadas = typeof corpo?.arquivadas === "number" ? corpo.arquivadas : 0;
      setResumoDoLote(
        arquivadas === 0
          ? "Nenhuma manifestação foi arquivada: não havia caso encerrado fora do arquivo quando o pedido chegou."
          : arquivadas === 1
            ? "1 manifestação arquivada."
            : `${arquivadas} manifestações arquivadas.`
      );
      await recarregar(token, arquivados);
    } catch (e) {
      console.error("Erro ao arquivar os encerrados:", e);
      setErroDoArquivo("Não foi possível falar com o servidor. Tente de novo em instantes.");
    } finally {
      setNoArquivo(null);
    }
  }

  /** Liga e desliga o filtro, recarregando a lista que ele passou a pedir. */
  function alternarOFiltro() {
    const proximo = !arquivados;
    setArquivados(proximo);
    // O aviso do ato anterior não sobrevive à troca de lista: ele fala de uma
    // linha que talvez nem esteja mais na tela.
    setErroDoArquivo(null);
    setResumoDoLote(null);
    if (token) recarregar(token, proximo);
  }

  const grupos = agruparPorStatus(manifestacoes).filter((g) => g.itens.length > 0);
  // O trabalho do dia do ouvidor, em cima de tudo (issue #486, RN-67): o caso
  // que a área respondeu e que ele ainda não abriu. Sai da mesma lista que os
  // grupos, sem consumi-la: o caso destacado continua no grupo de estado dele.
  const aguardandoEncerramento = aguardandoSeuEncerramento(manifestacoes);
  const emAndamento = manifestacoes.filter((m) => EM_ANDAMENTO.has(m.status)).length;
  const estourados = hoje
    ? manifestacoes.filter((m) => classificarPrazoDaManifestacao(m, hoje) === "estourado").length
    : 0;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Manifestações do hospital, na ordem do trabalho da ouvidoria
          </p>
        </div>
        {!loading && !semAcesso && !erroCarga && (
          <div className="flex flex-wrap items-center gap-2">
            {/* As portas das outras telas da Ouvidoria, com o gate de perfil de
                cada uma (issue #496, RN-77). O gate de verdade é sempre o
                backend, que recusa a tela a quem não pode; aqui só não se
                oferece o caminho que terminaria em 403. */}
            <AtalhosDaOuvidoria perfil={participante?.perfil_ouvidoria} />
            {/* O volume do dia. Ficava na mesma caixa dos atalhos e o olho o
                lia como mais uma porta, num topo que já quebrava em três
                linhas (issue #496, D-16). Informação e navegação são coisas
                diferentes, e agora moram em caixas diferentes. */}
            {/* Os contadores falam da lista de TRABALHO. Sobre o arquivo eles
                diriam "0 em andamento", que é verdade sobre o que está na tela
                e mentira sobre o hospital. */}
            {!arquivados && (
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap bg-sky-100 text-sky-700">
                  {emAndamento} em andamento
                </span>
                {estourados > 0 && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap bg-red-100 text-red-700">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {estourados} com prazo estourado
                  </span>
                )}
              </div>
            )}
            {/* O filtro do Arquivo (issue #592, ADR 0047). Só para quem tem o
                Perfil da Ouvidoria: o arquivo é ato dela, e a lista do arquivo
                é a outra metade do mesmo ato. `aria-pressed` porque isto é um
                interruptor, e não uma porta: quem usa leitor de tela precisa
                ouvir se ele está ligado. */}
            {podeAbrirDossie && (
              <button
                type="button"
                aria-pressed={arquivados}
                onClick={alternarOFiltro}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold uppercase tracking-wide whitespace-nowrap transition-colors ${ALTURA_DE_TOQUE} ${
                  arquivados
                    ? "bg-slate-700 text-white hover:bg-slate-800"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                <Archive className="w-4 h-4 shrink-0" />
                Arquivados
              </button>
            )}
            {/* Registrar é ato da Ouvidoria: o gate de verdade é o backend
                (403), a tela só não oferece o caminho a quem não pode. */}
            {podeAbrirDossie && (
              <button
                onClick={() => setRegistrando(true)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold uppercase tracking-wide whitespace-nowrap bg-primary text-white hover:bg-primary/90 transition-colors ${ALTURA_DE_TOQUE}`}
              >
                <Plus className="w-4 h-4 shrink-0" />
                Nova manifestação
              </button>
            )}
          </div>
        )}
      </div>

      {/* O que esta carga não pôde afirmar (issue #449, e agora a trilha do
          marcador de novidade, issue #484). Sinal ausente e sinal desligado
          desenham a mesma lista, então a falha precisa estar escrita. */}
      {!loading &&
        !semAcesso &&
        !erroCarga &&
        avisosDeDegradacao(degradado).map((aviso) => (
          <div
            key={aviso.leitura}
            className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{aviso.texto}</span>
          </div>
        ))}

      {/* A recusa do servidor ao arquivar ou desarquivar, na frase dele (issue
          #592). `role="status"` porque é resposta a um clique do ouvidor, e ele
          precisa ouvi-la sem procurar. Some no próximo ato e na troca de
          filtro: aviso velho sobre linha que já saiu da tela é pior que
          nenhum. */}
      {erroDoArquivo && (
        <div
          role="status"
          className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erroDoArquivo}</span>
        </div>
      )}

      {/* O que o lote fez (issue #594). `role="status"` pela mesma razão do
          aviso acima: é resposta a um clique, e o ouvidor precisa lê-la sem
          procurar. Some no próximo ato do arquivo e na troca de filtro. */}
      {resumoDoLote && (
        <div
          role="status"
          className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm"
        >
          <Archive className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{resumoDoLote}</span>
        </div>
      )}

      {!loading && !semAcesso && !erroCarga && !podeAbrirDossie && manifestacoes.length > 0 && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 text-sm">
          <Lock className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Você vê o índice das manifestações. O conteúdo completo é restrito ao Ouvidor e à
            Diretoria Executiva.
          </span>
        </div>
      )}

      {/* O bloco AGUARDANDO SEU ENCERRAMENTO (issue #486, RN-67). Fica acima
          de todos os grupos e some quando não há nenhum caso: bloco vazio
          ocupando o topo todo dia ensinaria o olho a pular a região justo
          quando ela tivesse algo. Destaque, e não filtro novo: as linhas daqui
          continuam nos seus grupos logo abaixo.

          A guarda de `erroCarga` é a mesma dos blocos irmãos daqui de cima: com
          a recarga falhada, a lista na memória é a de antes do que o ouvidor
          acabou de fazer, e o topo seguiria oferecendo o botão Encerrar sobre
          um estado que não vale mais, enquanto o card logo abaixo já diz que
          não conseguiu carregar. */}
      {/* O bloco do trabalho do dia não tem o que dizer sobre o arquivo: lá
          não há caso esperando encerramento de ninguém. */}
      {!erroCarga && !arquivados && aguardandoEncerramento.length > 0 && (
        <section
          aria-label={TITULO_AGUARDANDO_ENCERRAMENTO}
          className="bg-white rounded-2xl border border-primary/30 shadow-premium overflow-hidden mb-4"
        >
          <header className="flex items-center gap-2 px-5 py-3 bg-primary/5 border-b border-primary/20">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-primary">
              <CheckCircle2 className="w-4 h-4" />
              {TITULO_AGUARDANDO_ENCERRAMENTO}
            </span>
            <span className="text-xs text-slate-400">
              {aguardandoEncerramento.length}{" "}
              {aguardandoEncerramento.length === 1 ? "manifestação" : "manifestações"}
            </span>
          </header>
          <ListaDaFila
            itens={aguardandoEncerramento}
            hoje={hoje}
            responsaveis={responsaveis}
            podeAbrirDossie={podeAbrirDossie}
            cobrancas={cobrancas}
            onValidar={setValidando}
            onEncerrar={setEncerrando}
            onCobrar={cobrar}
            onArquivar={(m) => mudarOArquivo(m, "POST")}
            onDesarquivar={(m) => mudarOArquivo(m, "DELETE")}
          />
        </section>
      )}

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando manifestações...
          </div>
        ) : semAcesso ? (
          <div className="text-center py-16">
            <p className="text-slate-500 font-medium">Acesso restrito à equipe de Reuniões</p>
          </div>
        ) : erroCarga ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-7 h-7 text-red-400" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Não foi possível carregar as manifestações</p>
            <p className="text-slate-400 text-sm mt-1">Recarregue a página para tentar novamente.</p>
          </div>
        ) : manifestacoes.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <Megaphone className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            {arquivados ? (
              <>
                <p className="text-slate-500 font-medium">Nenhuma manifestação arquivada</p>
                <p className="text-slate-400 text-sm mt-1">
                  Os casos encerrados que a ouvidoria guardar aparecem aqui.
                </p>
              </>
            ) : (
              <>
                <p className="text-slate-500 font-medium">Nenhuma manifestação registrada</p>
                <p className="text-slate-400 text-sm mt-1">
                  As manifestações chegam pelo atendimento da Ana e pelo registro da ouvidoria.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {grupos.map((grupo) => (
              <section key={grupo.status} aria-label={rotuloDoStatus(grupo.status)}>
                {/* A faixa do grupo (issue #495, RN-70): largura total, fundo
                    na cor do estado e o contador na outra ponta. A cor de
                    estado vive só aqui (RN-71), e por isso a pílula que ficava
                    dentro do cabeçalho saiu: com ela e a faixa juntas, a mesma
                    informação era dita duas vezes e a linha ficava disputando
                    escala com a gravidade. Caixa alta é do CSS, e não do texto:
                    o leitor de tela continua ouvindo o nome do estado como ele
                    se escreve. */}
                <header
                  className={`flex items-center justify-between gap-2 px-5 py-2 ${classeDoStatus(grupo.status)}`}
                >
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {rotuloDoStatus(grupo.status)}
                  </span>
                  <div className="flex items-center gap-3">
                    {/* O lote (issue #594). Mora no cabeçalho do grupo porque
                        é sobre o grupo inteiro que ele age, e não sobre uma
                        linha. Só na lista de TRABALHO: com o filtro ligado, o
                        grupo Encerrado é o que já está guardado, e o botão ali
                        ofereceria arquivar o arquivo. O grupo vazio nem chega
                        aqui (a lista já o descarta), então o botão nunca
                        aparece prometendo um lote de zero.

                        Gate de perfil como no resto da tela: quem recusa de
                        verdade é o servidor, com 403. */}
                    {!arquivados && podeAbrirDossie && grupo.status === "encerrado" && (
                      <button
                        type="button"
                        onClick={() => arquivarOsEncerrados(grupo.itens.length)}
                        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold uppercase tracking-wide whitespace-nowrap bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 transition-colors ${ALTURA_DE_TOQUE}`}
                      >
                        <Archive className="w-3.5 h-3.5 shrink-0" />
                        Arquivar todos os encerrados
                      </button>
                    )}
                    <span className="text-xs font-semibold">
                      {grupo.itens.length}{" "}
                      {grupo.itens.length === 1 ? "manifestação" : "manifestações"}
                    </span>
                  </div>
                </header>
                <ListaDaFila
                  itens={grupo.itens}
                  hoje={hoje}
                  responsaveis={responsaveis}
                  podeAbrirDossie={podeAbrirDossie}
                  arquivados={arquivados}
                  cobrancas={cobrancas}
                  onValidar={setValidando}
                  onEncerrar={setEncerrando}
                  onCobrar={cobrar}
                  onArquivar={(m) => mudarOArquivo(m, "POST")}
                  onDesarquivar={(m) => mudarOArquivo(m, "DELETE")}
                />
              </section>
            ))}
          </div>
        )}
      </div>

      <ValidarModal
        manifestacao={validando}
        token={token}
        onClose={() => setValidando(null)}
        onAcionada={() => {
          if (token) recarregar(token, arquivados);
        }}
      />

      <EncerrarModal
        manifestacao={encerrando}
        token={token}
        onClose={() => setEncerrando(null)}
        onEncerrada={() => {
          if (token) recarregar(token, arquivados);
        }}
      />

      <NovaManifestacaoModal
        aberto={registrando}
        token={token}
        onClose={() => setRegistrando(false)}
        onRegistrada={() => {
          if (token) recarregar(token, arquivados);
        }}
      />
    </div>
  );
}
