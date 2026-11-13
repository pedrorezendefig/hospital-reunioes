"use client";

/**
 * Formulário público da Ouvidoria: a Manifestação guiada (issue #1620, ADR
 * 0086 decisão 6), que substituiu a tela única do canal aberto (issue #323).
 *
 * Sem login. Abre por duas portas: `/manifestacao`, que o site do hospital
 * linka, sem cartaz; e o endereço curto do cartaz, `/a/{código}` (issue #1617,
 * ADR 0086 decisão 5), com o código do Ponto de escuta. Feito para o celular
 * primeiro: o caso de uso principal é a pessoa apontando a câmera para o cartaz.
 *
 * Cinco passos (seção 4.2 da especificação da Diretoria): identificação, sobre
 * o quê, quando e onde, o que aconteceu e contato. O estado mora aqui, acima
 * dos passos, e é por isso que voltar não perde nada.
 */

import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, ArrowRight, CheckCircle2, Info, Loader2, Send } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  ENVIO_RECUSADO_PELA_PAGINA,
  EXPECTATIVAS,
  NATUREZAS_INFORMADAS,
  OUTRO_LUGAR,
  PERIODOS,
  RECUSA_DO_ENVIO,
  SOBRE_QUEM,
  AVISO_SO_TELEFONE,
  avisoDoPaciente,
  montarEnvio,
  passoCompleto,
  precisaDoAvisoDoEmail,
  type Expectativa,
  type FormularioPublico,
  type LocalPublico,
  type NaturezaInformada,
  type Periodo,
  type SobreQuem,
} from "@/lib/ouvidoria/publico";

interface Recibo {
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: string;
}

const LIMITE_RELATO = 10000;
const TOTAL_DE_PASSOS = 5;
const TITULOS = ["Identificação", "Sobre o quê", "Quando e onde", "O que aconteceu", "Contato"];

const FALTA_CONTATO = "Para enviar, deixe seu nome e um telefone ou e-mail.";

// As classes que se repetem. Alvo de toque de 44 px em tudo que se aperta
// (regra T4 da especificação): a tela é feita para o celular.
const CAMPO =
  "w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:bg-slate-50 disabled:text-slate-400";
const ROTULO = "block text-sm font-semibold text-slate-700";
const AJUDA = "text-xs text-slate-400";

function opcao(escolhida: boolean): string {
  return `min-h-[44px] rounded-xl border px-3 py-3 text-base font-semibold transition-colors ${
    escolhida
      ? "border-primary bg-primary/10 text-primary"
      : "border-border bg-white text-slate-600 hover:border-primary/40"
  }`;
}

/** Hoje no fuso de quem está com o celular na mão, no formato do `<input type="date">`. */
function hoje(): string {
  const d = new Date();
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}`;
}

function formatarData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function Opcional() {
  return <span className="font-normal text-slate-400">(opcional)</span>;
}

/** Um grupo de escolhas de um toque, com o rótulo lido pelo leitor de tela. */
function Escolhas<T extends string>({
  id,
  rotulo,
  opcoes,
  escolhida,
  aoEscolher,
  colunas = "grid-cols-2",
}: {
  id: string;
  rotulo: React.ReactNode;
  opcoes: { valor: T; rotulo: string }[];
  escolhida: T | null;
  aoEscolher: (valor: T) => void;
  colunas?: string;
}) {
  return (
    <div className="space-y-1.5">
      {/* `etiqueta`: o rótulo do grupo é Texto curto como o `<label>` dos
          campos ao lado (ADR 0080), e fica em caixa alta igual a eles. */}
      <p id={id} className={`etiqueta ${ROTULO}`}>
        {rotulo}
      </p>
      <div role="group" aria-labelledby={id} className={`grid ${colunas} gap-2`}>
        {opcoes.map(({ valor, rotulo: texto }) => (
          <button
            key={valor}
            type="button"
            aria-pressed={escolhida === valor}
            onClick={() => aoEscolher(valor)}
            className={opcao(escolhida === valor)}
          >
            {texto}
          </button>
        ))}
      </div>
    </div>
  );
}

function FormularioPublico({ codigoDoCartaz }: { codigoDoCartaz: string | null }) {
  const [passo, setPasso] = useState(1);

  // M1: escolhida primeiro, e por isso guardada à parte do formulário: até a
  // pessoa escolher, ela não é nem identificada nem anônima.
  const [identificacao, setIdentificacao] = useState<"identificado" | "anonimo" | null>(null);
  // M2
  const [natureza, setNatureza] = useState<NaturezaInformada | null>(null);
  const [sobre, setSobre] = useState<SobreQuem | null>(null);
  // M3
  const [dataOcorrencia, setDataOcorrencia] = useState(hoje);
  const [periodo, setPeriodo] = useState<Periodo | null>(null);
  const [horaAprox, setHoraAprox] = useState("");
  const [local, setLocal] = useState("");
  const [quarto, setQuarto] = useState("");
  // M4
  const [relato, setRelato] = useState("");
  const [profissionais, setProfissionais] = useState("");
  const [profissionaisNaoSei, setProfissionaisNaoSei] = useState(false);
  const [pacienteNome, setPacienteNome] = useState("");
  const [pacienteNascimento, setPacienteNascimento] = useState("");
  const [expectativa, setExpectativa] = useState<Expectativa | null>(null);
  // M5. O e-mail vai em `contato`, que é o que o acuse lê.
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [email, setEmail] = useState("");

  const [armadilha, setArmadilha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [recibo, setRecibo] = useState<Recibo | null>(null);

  // A lista de "Onde": o nome público de cada cartaz ativo. Falha aqui deixa
  // só o "Outro lugar do hospital", e a pessoa segue.
  const [locais, setLocais] = useState<LocalPublico[]>([]);
  // O nome público do cartaz que a pessoa leu, que já chega escolhido em
  // "Onde". A URL traz só o código (ADR 0036, decisão 10): quem diz o nome é o
  // servidor, e nunca o nome interno do setor (ADR 0086, decisão 10).
  const [localDoCartaz, setLocalDoCartaz] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    fetch("/api/ouvidoria/publico/locais")
      .then((res) => (res.ok ? res.json() : null))
      .then((corpo) => {
        if (vivo) setLocais(Array.isArray(corpo?.locais) ? corpo.locais : []);
      })
      .catch(() => {
        if (vivo) setLocais([]);
      });
    return () => {
      vivo = false;
    };
  }, []);

  useEffect(() => {
    // Sem código na URL não há o que perguntar: a maioria chega pelo site.
    if (!codigoDoCartaz) return;
    let vivo = true;
    fetch(`/api/ouvidoria/publico/pontos/${encodeURIComponent(codigoDoCartaz)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((cartaz) => {
        const nomePublico: string | null = cartaz?.nome_publico ?? null;
        if (!vivo || !nomePublico) return;
        setLocalDoCartaz(nomePublico);
        // Só preenche o que a pessoa ainda não escolheu.
        setLocal((atual) => atual || nomePublico);
      })
      // Cartaz aposentado ou falha: o lugar fica para a pessoa escolher, e o
      // formulário, que é o que ela veio fazer, continua de pé.
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [codigoDoCartaz]);

  // Leva o foco ao título do passo novo: quem usa leitor de tela ouve onde
  // está, e no celular a pessoa não fica no meio do passo anterior.
  const titulo = useRef<HTMLHeadingElement>(null);
  const primeiroPasso = useRef(true);
  useEffect(() => {
    if (primeiroPasso.current) {
      primeiroPasso.current = false;
      return;
    }
    titulo.current?.focus();
  }, [passo]);

  const anonimo = identificacao === "anonimo";
  const nomesDaLista = locais.map((l) => l.nome);
  const opcoesDeLocal = [
    ...(localDoCartaz && !nomesDaLista.includes(localDoCartaz) ? [localDoCartaz] : []),
    ...nomesDaLista,
    OUTRO_LUGAR,
  ];
  const localEhAla = locais.some((l) => l.nome === local && l.ala_internacao);

  const form: FormularioPublico = {
    relato,
    nome,
    contato: email,
    anonimo,
    p: codigoDoCartaz,
    natureza,
    sobre,
    pacienteNome,
    dataOcorrencia,
    periodo,
    horaAprox,
    local,
    localEhAla,
    quarto,
    profissionais: profissionaisNaoSei ? "" : profissionais,
    pacienteNascimento,
    expectativa,
    telefone,
  };
  const podeSeguir = passo === 1 ? identificacao !== null : passoCompleto(passo, form);

  async function handleEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    // Enter num campo dos passos de antes não envia nada: o envio é do passo 5.
    if (passo !== TOTAL_DE_PASSOS || !podeSeguir || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/publico/manifestacoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...montarEnvio(form), assunto_alternativo: armadilha }),
      });
      if (res.status === 429) {
        setErro(
          "Recebemos muitos envios deste aparelho agora há pouco. Aguarde um minuto e tente de novo."
        );
        return;
      }
      if (res.status === 400) {
        // Recusa de forma do envio (é aqui que cai o honeypot). Recusa
        // definitiva: pedir para "tentar de novo em instantes" mandaria a
        // pessoa repetir algo que nunca vai passar.
        setErro(RECUSA_DO_ENVIO);
        return;
      }
      if (res.status === 422) {
        // O servidor recusou o FORMATO do envio, e a tela não sabe por quê. A
        // causa mais provável é esta página estar velha depois de um deploy,
        // e não o texto de quem manifestou (issue #666): a mensagem pede para
        // copiar e recarregar, e nunca para reescrever.
        setErro(ENVIO_RECUSADO_PELA_PAGINA);
        return;
      }
      if (!res.ok) {
        setErro(
          "Não foi possível registrar sua manifestação agora. Tente novamente em instantes."
        );
        return;
      }
      setRecibo((await res.json()) as Recibo);
    } catch {
      setErro(
        "Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo."
      );
    } finally {
      setEnviando(false);
    }
  }

  if (recibo) {
    return (
      <div className="bg-white rounded-2xl border border-emerald-200 shadow-premium px-5 py-8 text-center space-y-4">
        <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
        <div className="space-y-1">
          <p className="text-slate-600 text-sm">
            Sua manifestação foi registrada. Guarde o número do protocolo:
          </p>
          <p className="text-3xl font-bold tracking-tight text-slate-900 tabular-nums">
            {recibo.protocolo}
          </p>
        </div>
        <p className="text-sm text-slate-500">
          Registrada em {formatarData(recibo.data_abertura)}. A Ouvidoria vai
          analisar e encaminhar ao setor responsável.
        </p>
      </div>
    );
  }

  const frases: Record<number, string> = {
    1: "Escolha se a Ouvidoria pode responder diretamente a você.",
    2: "Diga do que se trata e de quem é o relato.",
    3: "Ajude a Ouvidoria a localizar o atendimento.",
    4: "Quanto mais detalhes, mais rápido conseguimos apurar.",
    5: anonimo
      ? "Guarde o número do protocolo que vai aparecer na próxima tela."
      : "É por aqui que a Ouvidoria fala com você sobre este caso.",
  };

  return (
    <form
      onSubmit={handleEnviar}
      noValidate
      className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-5"
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-500">
          Passo {passo} de {TOTAL_DE_PASSOS}
        </p>
        <div
          role="progressbar"
          aria-label="Progresso da manifestação"
          aria-valuemin={1}
          aria-valuemax={TOTAL_DE_PASSOS}
          aria-valuenow={passo}
          className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden"
        >
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${(passo / TOTAL_DE_PASSOS) * 100}%` }}
          />
        </div>
      </div>

      <div className="space-y-1">
        <h2 ref={titulo} tabIndex={-1} className="text-lg font-bold text-slate-900 focus:outline-none">
          {TITULOS[passo - 1]}
        </h2>
        <p className="text-sm text-slate-500">{frases[passo]}</p>
      </div>

      {passo === 1 && (
        // Dois cards lado a lado, empilhados no celular (M1 da especificação).
        // O texto do card fica `normal-case`: o card é botão, e a regra de
        // caixa alta da casa (ADR 0080) pegaria a frase inteira.
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(
            [
              ["identificado", "Com identificação", "A Ouvidoria responde diretamente a você."],
              [
                "anonimo",
                "Anônimo",
                "Você recebe um número de protocolo, sem se identificar. Não conseguimos responder diretamente a você.",
              ],
            ] as const
          ).map(([valor, nomeDoCard, texto]) => (
            <button
              key={valor}
              type="button"
              aria-pressed={identificacao === valor}
              onClick={() => setIdentificacao(valor)}
              className={`${opcao(identificacao === valor)} text-left px-4 py-4`}
            >
              <span className="block">{nomeDoCard}</span>
              <span className="block mt-1 text-sm font-normal normal-case text-slate-500">
                {texto}
              </span>
            </button>
          ))}
        </div>
      )}

      {passo === 2 && (
        <div className="space-y-5">
          {/* As quatro naturezas do cartaz (RN-88, ADR 0040 decisão 3), com o
              elogio na frente. A escolha é sugestão de quem manifesta, e
              clicar de novo desmarca. */}
          <div className="space-y-1.5">
            <Escolhas
              id="rotulo-natureza"
              rotulo={
                <>
                  O que você quer registrar? <Opcional />
                </>
              }
              opcoes={NATUREZAS_INFORMADAS}
              escolhida={natureza}
              aoEscolher={(valor) => setNatureza(natureza === valor ? null : valor)}
            />
            <p className={AJUDA}>Não precisa escolher. A Ouvidoria confirma ao ler seu relato.</p>
          </div>
          {/* De quem é o relato (issue #666, ADR 0052): obrigatória, e clicar
              de novo NÃO desmarca. */}
          <Escolhas
            id="rotulo-sobre"
            rotulo="Este relato é sobre quem?"
            opcoes={SOBRE_QUEM}
            escolhida={sobre}
            aoEscolher={setSobre}
          />
        </div>
      )}

      {passo === 3 && (
        <div className="space-y-5">
          <div className="space-y-1.5">
            <label htmlFor="data-ocorrencia" className={ROTULO}>
              Em que dia foi?
            </label>
            <input
              id="data-ocorrencia"
              type="date"
              value={dataOcorrencia}
              max={hoje()}
              onChange={(e) => setDataOcorrencia(e.target.value)}
              className={CAMPO}
            />
          </div>
          <Escolhas
            id="rotulo-periodo"
            rotulo="Em que período?"
            opcoes={PERIODOS}
            escolhida={periodo}
            aoEscolher={setPeriodo}
          />
          <div className="space-y-1.5">
            <label htmlFor="hora-aprox" className={ROTULO}>
              Hora aproximada <Opcional />
            </label>
            <input
              id="hora-aprox"
              type="time"
              value={horaAprox}
              onChange={(e) => setHoraAprox(e.target.value)}
              className={CAMPO}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="local" className={ROTULO}>
              Onde foi?
            </label>
            <select
              id="local"
              value={local}
              onChange={(e) => setLocal(e.target.value)}
              className={`${CAMPO} bg-white`}
            >
              <option value="">Escolha o lugar</option>
              {opcoesDeLocal.map((nomeDoLocal) => (
                <option key={nomeDoLocal} value={nomeDoLocal}>
                  {nomeDoLocal}
                </option>
              ))}
            </select>
            <p className={AJUDA}>A Ouvidoria define o setor responsável depois de ler seu relato.</p>
          </div>
          {localEhAla && (
            <div className="space-y-1.5">
              <label htmlFor="quarto" className={ROTULO}>
                Quarto ou leito <Opcional />
              </label>
              <input
                id="quarto"
                type="text"
                value={quarto}
                onChange={(e) => setQuarto(e.target.value)}
                maxLength={40}
                className={CAMPO}
              />
            </div>
          )}
        </div>
      )}

      {passo === 4 && (
        <div className="space-y-5">
          <div className="space-y-1.5">
            <label htmlFor="relato" className={ROTULO}>
              Seu relato
            </label>
            <textarea
              id="relato"
              value={relato}
              onChange={(e) => setRelato(e.target.value)}
              maxLength={LIMITE_RELATO}
              rows={7}
              placeholder="O que aconteceu? O que você esperava? O que gostaria que fosse feito?"
              className={`${CAMPO} resize-y`}
            />
            <p className={`${AJUDA} text-right tabular-nums`}>
              {relato.length} / {LIMITE_RELATO}
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="profissionais" className={ROTULO}>
              Profissionais envolvidos <Opcional />
            </label>
            <input
              id="profissionais"
              type="text"
              value={profissionaisNaoSei ? "" : profissionais}
              disabled={profissionaisNaoSei}
              onChange={(e) => setProfissionais(e.target.value)}
              maxLength={300}
              className={CAMPO}
            />
            <p className={AJUDA}>Nome ou função, se souber.</p>
            <label className="flex min-h-[44px] items-center gap-2.5 cursor-pointer select-none normal-case text-sm text-slate-600">
              <input
                type="checkbox"
                checked={profissionaisNaoSei}
                onChange={(e) => {
                  setProfissionaisNaoSei(e.target.checked);
                  if (e.target.checked) setProfissionais("");
                }}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary/30"
              />
              Não sei
            </label>
          </div>

          {/* O paciente atendido. Sobre outra pessoa: nome e nascimento, que
              continuam aqui no anônimo (o anonimato protege quem fala, ADR
              0052 decisão 3). Quem se identifica e fala de si é o paciente, e
              só a data dele falta. O anônimo que fala de si não vê nada. */}
          {sobre === "outra_pessoa" && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="paciente-nome" className={ROTULO}>
                  Nome do paciente <Opcional />
                </label>
                <input
                  id="paciente-nome"
                  type="text"
                  value={pacienteNome}
                  onChange={(e) => setPacienteNome(e.target.value)}
                  maxLength={200}
                  className={CAMPO}
                />
                <p className={AJUDA}>{avisoDoPaciente(anonimo)}</p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="paciente-nascimento" className={ROTULO}>
                  Data de nascimento do paciente <Opcional />
                </label>
                <input
                  id="paciente-nascimento"
                  type="date"
                  value={pacienteNascimento}
                  max={hoje()}
                  onChange={(e) => setPacienteNascimento(e.target.value)}
                  className={CAMPO}
                />
              </div>
            </div>
          )}
          {sobre === "mim" && !anonimo && (
            <div className="space-y-1.5">
              <label htmlFor="paciente-nascimento" className={ROTULO}>
                Sua data de nascimento <Opcional />
              </label>
              <input
                id="paciente-nascimento"
                type="date"
                value={pacienteNascimento}
                max={hoje()}
                onChange={(e) => setPacienteNascimento(e.target.value)}
                className={CAMPO}
              />
              <p className={AJUDA}>Serve para localizar o atendimento.</p>
            </div>
          )}

          <Escolhas
            id="rotulo-expectativa"
            rotulo="O que você espera de nós?"
            opcoes={EXPECTATIVAS}
            escolhida={expectativa}
            aoEscolher={setExpectativa}
            colunas="grid-cols-1 sm:grid-cols-3"
          />
        </div>
      )}

      {passo === 5 && !anonimo && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="nome" className={ROTULO}>
              Seu nome
            </label>
            <input
              id="nome"
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={200}
              autoComplete="name"
              className={CAMPO}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="telefone" className={ROTULO}>
              Telefone
            </label>
            <input
              id="telefone"
              type="tel"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              maxLength={30}
              inputMode="tel"
              autoComplete="tel"
              className={CAMPO}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="email" className={ROTULO}>
              E-mail
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              maxLength={200}
              inputMode="email"
              autoComplete="email"
              className={CAMPO}
            />
          </div>
          {!podeSeguir && <p className="text-sm text-slate-500">{FALTA_CONTATO}</p>}
          {precisaDoAvisoDoEmail(form) && (
            <div className="flex items-start gap-2 rounded-xl bg-sky-50 border border-sky-200 px-3 py-2.5">
              <Info className="w-4 h-4 text-sky-600 mt-0.5 shrink-0" />
              <p className="text-sm text-sky-900">{AVISO_SO_TELEFONE}</p>
            </div>
          )}
        </div>
      )}

      {passo === 5 && (
        <p className="text-xs text-slate-400">
          Seus dados são usados apenas para tratar sua manifestação, conforme a LGPD.
        </p>
      )}

      {/* Armadilha para robô: pessoa nenhuma vê nem alcança este campo. */}
      <div aria-hidden="true" className="hidden">
        <label htmlFor="assunto-alternativo">Não preencha este campo</label>
        <input
          id="assunto-alternativo"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={armadilha}
          onChange={(e) => setArmadilha(e.target.value)}
        />
      </div>

      {erro && (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
          <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800">{erro}</p>
        </div>
      )}

      {/* Uma ação principal por passo (regra T2): só ela é azul preenchida. */}
      <div className="flex gap-3">
        {passo > 1 && (
          <button
            type="button"
            onClick={() => setPasso(passo - 1)}
            className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-border bg-white px-4 py-3 text-base font-semibold text-slate-600 hover:border-primary/40"
          >
            <ArrowLeft className="w-4 h-4" />
            Voltar
          </button>
        )}
        {passo < TOTAL_DE_PASSOS ? (
          <button
            type="button"
            disabled={!podeSeguir}
            onClick={() => setPasso(passo + 1)}
            className="flex flex-1 min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Continuar
            <ArrowRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!podeSeguir || enviando}
            className="flex flex-1 min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {enviando ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Registrando...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                Enviar manifestação
              </>
            )}
          </button>
        )}
      </div>
    </form>
  );
}

export function ManifestacaoPublica({ codigoDoCartaz }: { codigoDoCartaz: string | null }) {
  return (
    <main className="min-h-screen bg-bg">
      <div className="max-w-lg mx-auto px-4 py-8 space-y-5">
        <div className="flex items-center justify-center">
          <Logo variant="default" size="sm" />
        </div>
        <div className="text-center space-y-1">
          <h1 className="text-xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-sm text-slate-500">
            Reclamação, elogio ou sugestão: conte para a gente e receba seu
            protocolo na hora.
          </p>
        </div>
        <FormularioPublico codigoDoCartaz={codigoDoCartaz} />
      </div>
    </main>
  );
}
