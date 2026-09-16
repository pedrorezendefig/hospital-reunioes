"use client";

/**
 * O Assistente de Tecnologia (issue #727, PRD #726, ADR 0056).
 *
 * Molde da Ata Guiada: o Rascunho da Demanda ao vivo de um lado, o chat do
 * outro. O Rascunho vem PRIMEIRO no DOM de propósito: no celular, onde as duas
 * colunas viram uma pilha, é ele que fica no topo, recolhível, com o chat
 * embaixo (PRD #726, história 3).
 *
 * Duas coisas que este componente NÃO faz, e é o ponto:
 *
 * - não grava nada sozinho. O que sai do chat é um rascunho; a Demanda nasce
 *   no clique de "Criar Demanda", pela mesma rota do formulário de sempre;
 * - não guarda a conversa no servidor. Conversa e rascunho vivem na aba do
 *   navegador (`sessionStorage`) e somem ao criar ou descartar.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AudioLines, Bot, ChevronDown, Loader2, Mic, Paperclip, Send, Square, Trash2 } from "lucide-react";

import { Select } from "@/components/ui/Select";
import { useGravacaoVoz } from "@/hooks/useGravacaoVoz";

import {
  AUDIO_SEM_FALA,
  AUDIOS_ACEITOS,
  AVISO_DE_IA,
  avisoDoAudio,
  avisoDoDocumento,
  CONVERSA_NO_TETO,
  corpoValidado,
  CRIADA_SEM_CONFIRMACAO,
  demandaCriadaValida,
  descricaoAoCriar,
  DOCUMENTOS_ACEITOS,
  extrairODocumento,
  LIMITE_DA_DESCRICAO,
  LIMITE_DA_MENSAGEM,
  LIMITE_DE_MENSAGENS,
  LIMITE_DO_TITULO,
  mensagemComOrigem,
  MUITAS_MENSAGENS,
  gravarNaSessao,
  limparASessao,
  lerDaSessao,
  MensagemDoChat,
  PREFIXO_DE_AUDIO,
  prefixoDeDocumento,
  PRIMEIRA_MENSAGEM,
  podeCriar,
  RASCUNHO_VAZIO,
  RascunhoDaDemanda,
  RESPOSTA_ILEGIVEL,
  RespostaDoChat,
  respostaDoChatValida,
  TIPO_QUANDO_NAO_ESCOLHIDO,
  transcreverArquivoDeAudio,
  URL_DO_CHAT,
} from "./assistente";
import {
  BASE_TECNOLOGIA,
  Demanda,
  FALHA_DE_CONEXAO,
  motivoDaRecusa,
  PRIORIDADE_ROTULO,
  PRIORIDADES,
  PrioridadeDemanda,
  ProdutoDaEscolha,
  ROTA_TECNOLOGIA,
  TIPO_ROTULO,
  TIPOS,
  TipoDemanda,
} from "./demandas";

type Props = {
  token: string | null;
  produtos: ProdutoDaEscolha[];
  onCriada: (demanda: Demanda, avisoDeEmail: string | null) => void;
};

const BOAS_VINDAS: MensagemDoChat = { role: "assistant", content: PRIMEIRA_MENSAGEM };

/** O que a tela precisa guardar de um turno para saber voltar atrás dele. */
type TurnoEmVoo = {
  /** O fio como estava ANTES da fala, para o rollback. */
  anteriores: MensagemDoChat[];
  /** O fio com a fala dentro, que é o que foi para o servidor. */
  historico: MensagemDoChat[];
  /** A fala, para devolver à caixa se o turno não valer. */
  fala: string;
};

/** Como um turno termina. Só estes dois desfechos existem. */
type DesfechoDoTurno = { erro: string } | { corpo: RespostaDoChat };

/**
 * Como uma entrada de FORA termina. Só estes dois desfechos existem.
 *
 * Ou o que entrou virou uma fala pronta (com a origem na frente), ou virou um
 * aviso na conversa e nada foi mandado. Não há terceiro caminho: é o que
 * impede uma entrada nova de virar um segundo escritor do fio.
 */
type DesfechoDaEntrada = { aviso: string } | { fala: string };

export function AssistenteDeTecnologia({ token, produtos, onCriada }: Props) {
  const [messages, setMessages] = useState<MensagemDoChat[]>([BOAS_VINDAS]);
  const [rascunho, setRascunho] = useState<RascunhoDaDemanda>(RASCUNHO_VAZIO);
  const [texto, setTexto] = useState("");
  const [conversando, setConversando] = useState(false);
  const [criando, setCriando] = useState(false);
  /** A Demanda nasceu e a tela não conseguiu ler a resposta (ver `criar`). */
  const [criadaSemConfirmacao, setCriadaSemConfirmacao] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  /**
   * O aviso do que a pessoa acabou de anexar e não deu certo.
   *
   * Ele é próprio, e não o `erro` do topo, porque é uma resposta ao clique que
   * ela deu na caixa de mensagem, e é ali embaixo que ela está olhando. Ele
   * também NÃO entra em `messages`: uma linha de aviso da tela no meio do fio
   * iria junto para o prompt no turno seguinte, como se o assistente a tivesse
   * dito.
   */
  const [aviso, setAviso] = useState<string | null>(null);
  /** Um anexo está sendo lido: a caixa fica travada até virar mensagem ou aviso. */
  const [lendoOAnexo, setLendoOAnexo] = useState(false);
  const [rascunhoAberto, setRascunhoAberto] = useState(true);
  /**
   * O primeiro render já leu a sessão? Enquanto não leu, nada é gravado: o
   * efeito de gravar rodaria no estado inicial e apagaria o que estava
   * guardado antes de o efeito de ler chegar.
   */
  const leuDaSessao = useRef(false);
  /**
   * Qual conversa está valendo.
   *
   * "Descartar" começa outra, e o turno que estava no ar quando isso aconteceu
   * não pode voltar escrevendo: sem este número, a resposta chegaria quatro
   * segundos depois e traria de volta o fio e o rascunho que a pessoa acabou
   * de jogar fora.
   */
  const conversaAtual = useRef(0);
  const fimDaLista = useRef<HTMLDivElement | null>(null);
  const escolherOAudio = useRef<HTMLInputElement | null>(null);
  const escolherODocumento = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const guardado = lerDaSessao();
    if (guardado && guardado.messages.length > 0) {
      setMessages(guardado.messages);
      setRascunho(guardado.rascunho);
    }
    leuDaSessao.current = true;
  }, []);

  useEffect(() => {
    if (!leuDaSessao.current) return;
    /**
     * A tela intocada não grava, APAGA.
     *
     * É o que faz o "Descartar" valer: sem isto, ele limparia o armazenamento
     * e este mesmo efeito, disparado pela mudança de estado logo em seguida,
     * gravaria de volta a tela em branco. A comparação é por referência de
     * propósito: só o primeiro render e o "Descartar" devolvem exatamente
     * estas duas constantes, e qualquer rascunho vindo do servidor, mesmo
     * vazio, é um objeto novo, que é para ser gravado.
     */
    if (messages.length === 1 && messages[0] === BOAS_VINDAS && rascunho === RASCUNHO_VAZIO) {
      limparASessao();
      return;
    }
    gravarNaSessao({ messages, rascunho });
  }, [messages, rascunho]);

  useEffect(() => {
    fimDaLista.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, conversando]);

  const produtosAtivos = produtos.filter((p) => p.ativo);
  /** A próxima mensagem estouraria o teto do corpo, e o 422 chegaria como JSON cru. */
  const noTeto = messages.length >= LIMITE_DE_MENSAGENS;

  /**
   * O microfone, o mesmo hook da Ata Guiada e do chat de POPs.
   *
   * O que ele entrega é TEXTO, já transcrito, e o texto entra como a fala da
   * pessoa com a origem na frente. A tela não guarda o áudio em lugar nenhum, e
   * o hook também não: os bytes vivem em memória e somem (ADR 0056, decisão 4).
   */
  const { gravando, transcrevendo, iniciarGravacao, pararGravacao, abortarGravacao } = useGravacaoVoz({
    getToken: () => token,
    onTexto: (transcrito) => void receberDoMicrofone(transcrito),
  });

  /**
   * A caixa está ocupada: turno no ar, anexo sendo lido, voz sendo transcrita
   * ou microfone aberto.
   *
   * `gravando` está aqui, e não só no `disabled` dos dois botões de anexo, por
   * causa da classe inteira: **todo controle que só faz sentido fora de um
   * turno respeita o mesmo `ocupado`**. Sem isso, mandar pelo teclado no meio
   * de uma gravação começava o turno, e o botão de PARAR de gravar (que também
   * é desabilitado por `ocupado`) ficava cinza enquanto a tela mandava clicar
   * nele; se aquele turno chegasse ao teto de mensagens, o botão não reabilitava
   * nunca mais e o microfone ficava aberto até alguém descartar a conversa.
   *
   * O botão do microfone é a exceção, e é exceção por ser o caminho de VOLTA:
   * enquanto grava, ele fica vivo sempre.
   */
  const ocupado = conversando || lendoOAnexo || transcrevendo || gravando;

  function autorizacao() {
    return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  }

  /**
   * Pede o turno ao servidor e devolve o DESFECHO. Nunca levanta.
   *
   * Ela não escreve estado nenhum de propósito: é a metade que fala com a rede,
   * e a metade que escreve na tela é o `encerrarOTurno`. Todo caminho de saída
   * daqui (rede fora, recusa do servidor, corpo que não dá para ler) volta como
   * valor, e não como exceção, porque exceção escapando daqui era o que deixava
   * `conversando` preso em `true` e congelava o painel inteiro.
   */
  async function pedirOTurno(historico: MensagemDoChat[]): Promise<DesfechoDoTurno> {
    let resposta: Response;
    try {
      resposta = await fetch(URL_DO_CHAT, {
        method: "POST",
        headers: autorizacao(),
        // O rascunho que vai é o de AGORA, com as edições à mão: é ele que o
        // assistente recebe e é mandado preservar.
        body: JSON.stringify({ rascunho, messages: historico }),
      });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao falar com o assistente", e);
      return { erro: FALHA_DE_CONEXAO };
    }
    if (!resposta.ok) {
      return { erro: resposta.status === 429 ? MUITAS_MENSAGENS : await motivoDaRecusa(resposta) };
    }
    // Corpo que não dá para ler (conexão que cai depois dos cabeçalhos, proxy
    // devolvendo HTML) e corpo que dá para ler mas não é `{reply, rascunho}`
    // saem os dois por aqui, como `null`: para quem está olhando é o mesmo
    // caso. É isto que deixa `encerrarOTurno` sem leitura insegura.
    const corpo = await corpoValidado(resposta, respostaDoChatValida);
    if (corpo === null) {
      console.error("[admin/tecnologia] a resposta do assistente não deu para usar");
      return { erro: RESPOSTA_ILEGIVEL };
    }
    return { corpo };
  }

  /**
   * O ÚNICO lugar que escreve o fim de um turno.
   *
   * Três coisas passam a valer por construção, e não por lembrança:
   *
   * 1. **a tela destrava sempre.** `conversando` volta a `false` aqui, e este é
   *    o único caminho de volta do turno: não existe saída que esqueça de
   *    destravar, porque não existe outra saída. (O turno descartado sai na
   *    primeira linha, e quem descartou já destravou.)
   * 2. **a guarda da conversa vem antes de QUALQUER escrita.** Ela é a primeira
   *    linha, então nenhum ramo (nem o da rede, nem o da recusa, nem o do
   *    corpo ilegível) consegue ressuscitar o que o "Descartar" jogou fora.
   * 3. **o rollback não pisa no que a pessoa digitou.** Repor a fala só faz
   *    sentido se a caixa continuar como ela a deixou; se ela escreveu outra
   *    coisa enquanto esperava, o texto dela ganha.
   */
  function encerrarOTurno(daConversa: number, desfecho: DesfechoDoTurno, turno: TurnoEmVoo) {
    // Nenhuma linha daqui para baixo pode levantar: o corpo foi validado na
    // fronteira, então `desfecho.corpo.reply` e `.rascunho` são leitura segura.
    // Era essa a brecha que restava, e ela não se fecha por ordem de linha.
    if (conversaAtual.current !== daConversa) return;

    if ("erro" in desfecho) {
      // O turno que o servidor não aceitou VOLTA ATRÁS: deixar a fala pendurada
      // no fio diria "mande de novo" sem ter o que mandar, faria o modelo ler a
      // mesma frase duas vezes se a pessoa redigitasse, e teria queimado um dos
      // quarenta lugares do teto que o servidor nunca viu.
      setMessages(turno.anteriores);
      setTexto((atual) => (atual.trim() ? atual : turno.fala));
      setErro(desfecho.erro);
    } else {
      setMessages([...turno.historico, { role: "assistant", content: desfecho.corpo.reply }]);
      setRascunho(desfecho.corpo.rascunho);
    }
    setConversando(false);
  }

  /**
   * A ÚNICA porta de entrada de um turno.
   *
   * Digitar, falar no microfone, encaminhar um áudio e anexar um documento
   * terminam todos aqui, com uma fala pronta. As entradas de fora não ganharam
   * um segundo caminho até o servidor: elas ganharam um jeito de virar fala, e
   * o turno continua sendo montado, mandado e encerrado num lugar só.
   */
  async function mandarAFala(fala: string) {
    if (!fala || conversando || noTeto) return;
    const turno: TurnoEmVoo = {
      anteriores: messages,
      historico: [...messages, { role: "user", content: fala }],
      fala,
    };
    const daConversa = conversaAtual.current;
    setMessages(turno.historico);
    setErro(null);
    setAviso(null);
    setConversando(true);

    encerrarOTurno(daConversa, await pedirOTurno(turno.historico), turno);
  }

  async function enviar() {
    const fala = texto.trim();
    // `ocupado`, e não só `conversando`: o botão de mandar já está desabilitado
    // enquanto um anexo é lido, mas o Enter da caixa chega aqui direto. Sem
    // esta guarda, mandar pelo teclado no meio de uma leitura começava um turno,
    // e a fala do anexo voltava para uma tela que já estava conversando e era
    // engolida calada.
    if (!fala || ocupado || noTeto) return;
    setTexto("");
    await mandarAFala(fala);
  }

  /**
   * O ÚNICO lugar que escreve o fim de uma entrada de fora.
   *
   * Mesma forma do `encerrarOTurno`, e pelo mesmo motivo: a guarda da conversa
   * é a primeira linha, então um anexo que voltou depois do "Descartar" não
   * ressuscita nada; e a caixa destrava aqui, que é o único caminho de volta.
   * O que a entrada produz é uma FALA, e a fala segue pela porta de sempre.
   */
  async function encerrarAEntrada(daConversa: number, desfecho: DesfechoDaEntrada) {
    if (conversaAtual.current !== daConversa) return;
    setLendoOAnexo(false);
    if ("aviso" in desfecho) {
      setAviso(desfecho.aviso);
      return;
    }
    await mandarAFala(desfecho.fala);
  }

  /** O texto que voltou da rota de voz, do microfone ou do arquivo escolhido. */
  function falaDoAudio(transcrito: string): DesfechoDaEntrada {
    return transcrito.trim()
      ? { fala: mensagemComOrigem(PREFIXO_DE_AUDIO, transcrito) }
      : { aviso: AUDIO_SEM_FALA };
  }

  async function receberDoMicrofone(transcrito: string) {
    await encerrarAEntrada(conversaAtual.current, falaDoAudio(transcrito));
  }

  /**
   * A parte que as duas entradas por arquivo compartilham: peneira, rede, desfecho.
   *
   * A recusa local (tamanho, tipo) sai pela MESMA porta da recusa do servidor,
   * e não por um `setAviso` próprio: ela é o mesmo desfecho, e ter dois lugares
   * escrevendo o aviso era ter dois lugares para esquecer a mesma regra.
   */
  async function anexar(recusa: string | null, ler: () => Promise<DesfechoDaEntrada>): Promise<void> {
    const daConversa = conversaAtual.current;
    if (recusa) {
      // Tamanho e tipo são recusados SEM ida à rede e sem turno: a pessoa
      // escolheu o arquivo errado, e o que ela precisa é saber disso agora.
      await encerrarAEntrada(daConversa, { aviso: recusa });
      return;
    }
    setAviso(null);
    setLendoOAnexo(true);
    await encerrarAEntrada(daConversa, await ler());
  }

  function anexarOAudio(arquivo: File) {
    return anexar(avisoDoAudio(arquivo), async () => {
      const leitura = await transcreverArquivoDeAudio(arquivo, token);
      return "aviso" in leitura ? leitura : falaDoAudio(leitura.corpo.texto);
    });
  }

  function anexarODocumento(arquivo: File) {
    return anexar(avisoDoDocumento(arquivo), async () => {
      const leitura = await extrairODocumento(arquivo, token);
      if ("aviso" in leitura) return leitura;
      // O nome vem do SERVIDOR, e não do arquivo local: é lá que ele foi limpo
      // do que quebraria o prefixo de origem (colchete, quebra de linha) e com
      // ele a cerca que faz o documento entrar no prompt como texto de gente.
      return { fala: mensagemComOrigem(prefixoDeDocumento(leitura.corpo.filename), leitura.corpo.texto) };
    });
  }

  /** O input de arquivo é zerado sempre: senão escolher o MESMO arquivo de novo não dispara nada. */
  function aoEscolher(evento: React.ChangeEvent<HTMLInputElement>, usar: (arquivo: File) => Promise<void>) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = "";
    if (arquivo) void usar(arquivo);
  }

  async function criar() {
    const tipo = rascunho.tipo ?? TIPO_QUANDO_NAO_ESCOLHIDO;
    setCriando(true);
    setErro(null);
    let resposta: Response;
    try {
      resposta = await fetch(`${BASE_TECNOLOGIA}/demandas`, {
        method: "POST",
        headers: autorizacao(),
        body: JSON.stringify({
          titulo: rascunho.titulo,
          tipo,
          produto_id: rascunho.produto_id,
          prioridade: rascunho.prioridade,
          descricao: descricaoAoCriar(tipo, rascunho.descricao),
          prazo: rascunho.prazo,
        }),
      });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao criar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
      setCriando(false);
      return;
    }
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      setCriando(false);
      return;
    }
    const criada = await corpoValidado(resposta, demandaCriadaValida);
    if (criada === null) {
      /**
       * A resposta foi 201: a Demanda NASCEU, com id, no Quadro, com o dono
       * avisado. O que falhou foi ler o corpo (ou ele veio sem o `id`), então o
       * que a tela perdeu foi a confirmação, não a Demanda.
       *
       * Por isso este caminho NÃO é erro: ele fecha o botão em vez de
       * reabilitá-lo. A criação não tem chave de idempotência, e um segundo
       * clique nasceria a Demanda de novo, repetida no Quadro e com dois donos
       * notificados. A sessão é limpa como no caminho de sucesso, que é o que
       * ele é, e a saída oferecida é o Quadro.
       */
      console.error("[admin/tecnologia] a resposta da criação não deu para usar");
      limparASessao();
      setCriadaSemConfirmacao(true);
      setErro(null);
      setCriando(false);
      return;
    }
    limparASessao();
    setCriando(false);
    onCriada(criada, typeof criada.aviso_por_email === "string" ? criada.aviso_por_email : null);
  }

  function descartar() {
    // Começa outra conversa: o turno que estiver no ar deixa de ser de alguém.
    conversaAtual.current += 1;
    // E o microfone para junto, descartando o áudio: uma gravação que
    // continuasse voltaria como mensagem numa conversa que já não existe.
    abortarGravacao();
    limparASessao();
    setMessages([BOAS_VINDAS]);
    setRascunho(RASCUNHO_VAZIO);
    setTexto("");
    setErro(null);
    setAviso(null);
    setConversando(false);
    setLendoOAnexo(false);
    setCriadaSemConfirmacao(false);
  }

  function mudar(campo: Partial<RascunhoDaDemanda>) {
    setRascunho({ ...rascunho, ...campo });
  }

  return (
    <div className="grid lg:grid-cols-[1fr_minmax(360px,420px)] gap-6 items-start">
      {criadaSemConfirmacao && (
        <div
          role="alert"
          className="lg:col-span-2 flex flex-wrap items-center gap-3 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
        >
          <span>{CRIADA_SEM_CONFIRMACAO}</span>
          <Link href={ROTA_TECNOLOGIA} className="font-semibold underline">
            Ver no Quadro
          </Link>
        </div>
      )}

      {erro && (
        <p
          role="alert"
          className="lg:col-span-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm whitespace-pre-line"
        >
          {erro}
        </p>
      )}

      {/* Rascunho: primeiro no DOM, e por isso no TOPO no celular. */}
      <section className="rounded-2xl border border-border bg-surface p-4 space-y-3 w-full">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold text-text-primary">Rascunho da Demanda</h2>
          <button
            type="button"
            onClick={() => setRascunhoAberto(!rascunhoAberto)}
            aria-expanded={rascunhoAberto}
            className="lg:hidden flex items-center gap-1 px-2 py-1 rounded-lg border border-border text-xs text-text-secondary"
          >
            {rascunhoAberto ? "Recolher" : "Abrir"}
            <ChevronDown className={`w-3.5 h-3.5 ${rascunhoAberto ? "rotate-180" : ""}`} />
          </button>
        </div>

        <div className={`${rascunhoAberto ? "" : "hidden"} lg:block space-y-3`}>
          <input
            type="text"
            aria-label="Título"
            placeholder="O assistente escreve, você ajusta"
            maxLength={LIMITE_DO_TITULO}
            disabled={conversando}
            value={rascunho.titulo}
            onChange={(e) => mudar({ titulo: e.target.value })}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Select
              label="Tipo"
              value={rascunho.tipo ?? ""}
              onChange={(tipo) => mudar({ tipo: tipo as TipoDemanda })}
              options={TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] }))}
              placeholder="O assistente escolhe"
              disabled={conversando}
            />
            {rascunho.tipo === null && (
              <p className="text-xs text-text-secondary sm:col-span-2">
                Sem Tipo escolhido, a Demanda nasce como {TIPO_ROTULO[TIPO_QUANDO_NAO_ESCOLHIDO]}.
              </p>
            )}
            <Select
              label="Produto"
              value={rascunho.produto_id ?? ""}
              onChange={(produto_id) => mudar({ produto_id })}
              options={produtosAtivos.map((p) => ({ value: p.id, label: p.nome }))}
              placeholder="Escolha o Produto"
              disabled={conversando}
            />
            <Select
              label="Prioridade"
              value={rascunho.prioridade}
              onChange={(prioridade) => mudar({ prioridade: prioridade as PrioridadeDemanda })}
              options={PRIORIDADES.map((p) => ({ value: p, label: PRIORIDADE_ROTULO[p] }))}
              disabled={conversando}
            />
            <div className="flex flex-col gap-1">
              <label htmlFor="prazo-do-rascunho" className="text-xs font-medium text-text-secondary">
                Prazo
              </label>
              <input
                id="prazo-do-rascunho"
                type="date"
                disabled={conversando}
                value={rascunho.prazo ?? ""}
                onChange={(e) => mudar({ prazo: e.target.value || null })}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
          </div>
          <textarea
            aria-label="Descrição"
            rows={8}
            maxLength={LIMITE_DA_DESCRICAO}
            disabled={conversando}
            placeholder="A descrição vai tomando forma conforme vocês conversam"
            value={rascunho.descricao}
            onChange={(e) => mudar({ descricao: e.target.value })}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
          />
          {conversando && (
            <p role="status" className="text-xs text-text-secondary">
              O assistente está escrevendo aqui. Espere a resposta para ajustar à mão.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={criar}
              disabled={criando || criadaSemConfirmacao || !podeCriar(rascunho)}
              className="px-4 py-2 rounded-xl bg-primary text-white text-sm font-semibold disabled:opacity-50"
            >
              Criar Demanda
            </button>
            <button
              type="button"
              onClick={descartar}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border text-sm text-text-secondary hover:border-primary hover:text-primary transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Descartar
            </button>
          </div>
        </div>
      </section>

      {/* Chat */}
      <section className="w-full bg-white rounded-2xl border border-primary/30 shadow-premium flex flex-col h-[calc(100vh-14rem)] min-h-[420px] overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100">
          <span className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" />
          </span>
          <h2 className="text-sm font-bold text-slate-900">Assistente da aba Tecnologia</h2>
        </div>

        <div role="log" className="flex-1 overflow-y-auto px-5 py-4 space-y-3 overscroll-contain">
          {messages.map((m, i) => (
            <p
              key={i}
              className={
                m.role === "user"
                  ? "ml-auto max-w-[85%] px-3 py-2 rounded-2xl bg-primary text-white text-sm whitespace-pre-line"
                  : "mr-auto max-w-[85%] px-3 py-2 rounded-2xl bg-slate-100 text-slate-800 text-sm whitespace-pre-line"
              }
            >
              {m.content}
            </p>
          ))}
          {conversando && (
            <p role="status" className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Pensando...
            </p>
          )}
          {(lendoOAnexo || transcrevendo) && (
            <p role="status" className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Lendo o que você mandou...
            </p>
          )}
          {aviso && (
            <p
              role="status"
              className="mr-auto max-w-[85%] px-3 py-2 rounded-2xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
            >
              {aviso}
            </p>
          )}
          <div ref={fimDaLista} />
        </div>

        <div className="px-5 py-3 border-t border-slate-100 flex-shrink-0">
          {/* Escolher arquivo é o input nativo, escondido: o que a pessoa vê é o
              botão ao lado da caixa, no mesmo tamanho dos outros. */}
          <input
            ref={escolherOAudio}
            type="file"
            className="hidden"
            aria-label="Arquivo de áudio"
            accept={AUDIOS_ACEITOS.join(",")}
            onChange={(e) => aoEscolher(e, anexarOAudio)}
          />
          <input
            ref={escolherODocumento}
            type="file"
            className="hidden"
            aria-label="Arquivo de documento"
            accept={DOCUMENTOS_ACEITOS.join(",")}
            onChange={(e) => aoEscolher(e, anexarODocumento)}
          />

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => (gravando ? pararGravacao() : iniciarGravacao())}
              disabled={!gravando && (ocupado || noTeto)}
              aria-label={gravando ? "Parar de gravar" : "Gravar voz"}
              title={gravando ? "Parar de gravar" : "Gravar voz"}
              className={`px-3 py-2 rounded-xl border text-text-secondary disabled:opacity-50 ${
                gravando ? "border-red-300 bg-red-50 text-red-600" : "border-border hover:border-primary hover:text-primary"
              } transition-colors`}
            >
              {gravando ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
            <button
              type="button"
              onClick={() => escolherOAudio.current?.click()}
              disabled={ocupado || noTeto}
              aria-label="Anexar áudio"
              title="Anexar áudio"
              className="px-3 py-2 rounded-xl border border-border text-text-secondary hover:border-primary hover:text-primary transition-colors disabled:opacity-50"
            >
              <AudioLines className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => escolherODocumento.current?.click()}
              disabled={ocupado || noTeto}
              aria-label="Anexar documento"
              title="Anexar documento"
              className="px-3 py-2 rounded-xl border border-border text-text-secondary hover:border-primary hover:text-primary transition-colors disabled:opacity-50"
            >
              <Paperclip className="w-4 h-4" />
            </button>
            <textarea
              aria-label="Mensagem"
              rows={1}
              maxLength={LIMITE_DA_MENSAGEM}
              disabled={noTeto}
              placeholder={noTeto ? "Conversa no limite" : "Escreva, fale ou anexe"}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar();
                }
              }}
              className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white resize-none"
            />
            <button
              type="button"
              onClick={enviar}
              disabled={ocupado || noTeto || !texto.trim()}
              aria-label="Enviar"
              className="px-3 py-2 rounded-xl bg-primary text-white disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          {gravando && (
            <p role="status" className="mt-1.5 text-xs text-red-600">
              Gravando. Clique no quadrado para parar e mandar.
            </p>
          )}
          {noTeto && (
            <p role="status" className="mt-1.5 text-xs text-amber-700">
              {CONVERSA_NO_TETO}
            </p>
          )}
          <p className="mt-1.5 text-xs text-slate-400">{AVISO_DE_IA}</p>
        </div>
      </section>
    </div>
  );
}
