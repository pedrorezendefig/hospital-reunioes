"use client";

/**
 * O formulário de notificação de incidente (issue #1987, PRD #1979).
 *
 * Feito para o celular: quatro telas curtas (o que aconteceu, onde e quando,
 * o paciente foi atingido, identificação) e a confirmação. Abre por três
 * portas, e a origem vem da porta: o QR (`/notificar/qr`), o endereço
 * (`/notificar`) e o botão "Notificar incidente" do módulo
 * (`/notificar/modulo`), que já chega identificado pela sessão.
 *
 * O estado mora aqui, acima das telas, e é por isso que voltar não perde nada.
 *
 * Os anexos (issue #1988): até 3 fotos ou PDFs na primeira tela, somando menos
 * de 9 MB, com a foto grande reduzida antes do envio. Com arquivo, o envio vai
 * em multipart; sem arquivo, no JSON de sempre.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  Loader2,
  Paperclip,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import {
  PerguntasDeEsclarecimento,
  usePerguntasDeEsclarecimento,
  type ChaveDoAcompanhamento,
} from "@/components/seguranca-do-paciente/PerguntasDeEsclarecimento";
import { ACEITOS_NO_CAMPO, conferirArquivos, reduzirFoto, tamanhoLegivel } from "@/lib/seguranca-do-paciente/anexos";
import {
  AVISO_DO_PACIENTE,
  CHEGOU_AO_PACIENTE,
  ORIENTACOES,
  PERCEBIDO,
  QUEM_VE_O_NOME,
  SEM_PUNICAO,
  TITULOS_DAS_TELAS,
  TURNOS,
  montarEnvio,
  perguntaAGravidade,
  telaCompleta,
  type ChegouAoPaciente,
  type FormularioDeNotificacao as Formulario,
  type Porta,
  type SimNaoNaoSei,
  type Turno,
} from "@/lib/seguranca-do-paciente/notificacao";

interface Recibo {
  protocolo: string;
  criado_em: string | null;
  /** Só na anônima, e só nesta resposta: o banco guarda o hash. */
  codigo_acompanhamento?: string;
  /** Só quando o envio levou arquivo: `false` se a notificação ficou e os arquivos não. */
  anexos_guardados?: boolean;
}

interface Setor {
  id: string;
  nome: string;
}

const TOTAL_DE_TELAS = 4;
const LIMITE_DO_RELATO = 10000;

// Alvo de toque de 44 px em tudo que se aperta: a tela é feita para o celular.
const CAMPO =
  "w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";
const ROTULO = "block text-sm font-semibold text-slate-700";
const BOTAO_SECUNDARIO =
  "flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-border bg-white px-4 py-3 text-base font-semibold text-slate-600 hover:border-primary/40";
const BOTAO_PRINCIPAL =
  "flex flex-1 min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed";

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

function Opcional() {
  return <span className="font-normal text-slate-400">(opcional)</span>;
}

/** Um grupo de escolhas de um toque, com o rótulo lido pelo leitor de tela. */
function Escolhas<T extends string | boolean>({
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
      <p id={id} className={`etiqueta ${ROTULO}`}>
        {rotulo}
      </p>
      <div role="group" aria-labelledby={id} className={`grid ${colunas} gap-2`}>
        {opcoes.map(({ valor, rotulo: texto }) => (
          <button
            key={String(valor)}
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

function Rodape() {
  return (
    <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-emerald-700">
      <ShieldCheck className="w-4 h-4" aria-hidden />
      {SEM_PUNICAO}
    </p>
  );
}

/** O código da anônima, mostrado uma vez, com o Copiar. */
function CodigoDeAcompanhamento({ codigo }: { codigo: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Sem permissão de área de transferência: o código continua na tela.
    }
  }

  return (
    <div className="space-y-3 rounded-xl border border-border bg-slate-50 px-4 py-4">
      <div className="space-y-1">
        <p className="text-slate-600 text-sm">Seu código de acompanhamento:</p>
        <p className="text-2xl font-bold tracking-wider text-slate-900 font-mono">{codigo}</p>
      </div>
      <p className="text-sm text-slate-500">
        Anote ou copie agora: o código aparece só agora e não pode ser recuperado depois.
      </p>
      <button type="button" onClick={copiar} className={BOTAO_SECUNDARIO + " w-full"}>
        {copiado ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
        {copiado ? "Copiado" : "Copiar código"}
      </button>
    </div>
  );
}

function Confirmacao({ recibo, contato }: { recibo: Recibo; contato: string }) {
  // A chave do acompanhamento: o código na anônima, o contato na identificada.
  const chave: ChaveDoAcompanhamento | null = recibo.codigo_acompanhamento
    ? { protocolo: recibo.protocolo, codigo: recibo.codigo_acompanhamento }
    : contato
      ? { protocolo: recibo.protocolo, contato }
      : null;
  const perguntas = usePerguntasDeEsclarecimento(chave, true);

  return (
    <div className="bg-white rounded-2xl border border-emerald-200 shadow-premium px-5 py-8 text-center space-y-4">
      <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" aria-hidden />
      <h2 className="text-lg font-bold text-slate-900">Notificação registrada</h2>
      <div className="space-y-1">
        <p className="text-slate-600 text-sm">Guarde o número do protocolo:</p>
        <p className="text-3xl font-bold tracking-tight text-slate-900 tabular-nums">{recibo.protocolo}</p>
      </div>
      <p className="text-sm text-slate-500">
        O Núcleo de Segurança do Paciente vai ler o seu relato. Obrigado por notificar.
      </p>
      {recibo.anexos_guardados === false && (
        <p role="alert" className="text-sm text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
          A notificação foi registrada, mas não conseguimos guardar os arquivos. O relato já chegou ao Núcleo.
        </p>
      )}
      {recibo.codigo_acompanhamento && <CodigoDeAcompanhamento codigo={recibo.codigo_acompanhamento} />}
      {chave && <PerguntasDeEsclarecimento chave={chave} perguntas={perguntas} responderDepois />}
      <Link href="/notificar/acompanhar" className={BOTAO_SECUNDARIO + " w-full"}>
        Acompanhar a notificação
      </Link>
      <Rodape />
    </div>
  );
}

interface Props {
  porta: Porta;
  /** Na porta do módulo: quem está logado, mostrado na tela de identificação. */
  identificacao?: { nome: string; contato: string } | null;
}

// O limite sem login conta pela rede (os computadores e o Wi-Fi do hospital
// saem por uma só), e o teto estourado pode ser o da hora: a recusa não culpa
// o aparelho nem promete um minuto. O botão do módulo conta por pessoa.
const RECUSA_POR_EXCESSO_DA_REDE =
  "Recebemos muitos envios desta rede agora há pouco. Tente de novo mais tarde, o seu relato continua aqui. Se você tem login no app do hospital, pode notificar pelo botão Notificar incidente.";
const RECUSA_POR_EXCESSO_DA_PESSOA =
  "Recebemos muitos envios seus agora há pouco. Tente de novo mais tarde, o seu relato continua aqui.";
const FALHA_DOS_SETORES =
  "Não foi possível carregar a lista de setores. Verifique sua conexão e tente de novo.";
const FALHA_DO_SERVIDOR = "Não foi possível registrar a notificação agora. Tente novamente em instantes.";
const FALHA_DA_CONEXAO = "Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo.";

async function enviar(porta: Porta, corpo: Record<string, unknown>, arquivos: File[]): Promise<Response> {
  const headers: Record<string, string> = {};
  let body: BodyInit;
  if (arquivos.length > 0) {
    // O navegador põe o Content-Type com o boundary do multipart.
    const formulario = new FormData();
    formulario.append("dados", JSON.stringify(corpo));
    for (const arquivo of arquivos) formulario.append("anexos", arquivo, arquivo.name);
    body = formulario;
  } else {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(corpo);
  }
  let url = "/api/nsp/publico/notificacoes";
  if (porta === "modulo") {
    url = "/api/nsp/notificacoes";
    const {
      data: { session },
    } = await createClient().auth.getSession();
    headers.Authorization = `Bearer ${session?.access_token ?? ""}`;
  }
  return fetch(url, { method: "POST", headers, body });
}

export function FormularioDeNotificacao({ porta, identificacao = null }: Props) {
  const [tela, setTela] = useState(1);
  const [form, setForm] = useState<Formulario>({
    relato: "",
    leito: "",
    setorId: "",
    data: hoje(),
    turno: null,
    hora: "",
    chegou: null,
    grave: null,
    percebido: null,
    anonimo: false,
    nome: "",
    contato: "",
  });
  const [setores, setSetores] = useState<Setor[]>([]);
  // Sem a lista, o Setor (obrigatório) trava o Continuar: a tela tem que dizer.
  const [falhaDosSetores, setFalhaDosSetores] = useState(false);
  const [tentativaDosSetores, setTentativaDosSetores] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [recibo, setRecibo] = useState<Recibo | null>(null);
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [preparando, setPreparando] = useState(false);
  const [recusaDosArquivos, setRecusaDosArquivos] = useState<string | null>(null);

  async function aoEscolherArquivos(evento: React.ChangeEvent<HTMLInputElement>) {
    const escolhidos = Array.from(evento.target.files ?? []);
    // Limpa o campo: escolher o mesmo arquivo de novo também conta.
    evento.target.value = "";
    if (escolhidos.length === 0) return;
    setRecusaDosArquivos(null);
    setPreparando(true);
    try {
      const prontos = await Promise.all(escolhidos.map(reduzirFoto));
      const juntos = [...arquivos, ...prontos];
      const recusa = conferirArquivos(juntos);
      if (recusa) setRecusaDosArquivos(recusa);
      else setArquivos(juntos);
    } finally {
      setPreparando(false);
    }
  }

  function mudar<K extends keyof Formulario>(campo: K, valor: Formulario[K]) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  useEffect(() => {
    let vivo = true;
    fetch("/api/nsp/publico/setores")
      .then((res) => (res.ok ? res.json() : null))
      .then((corpo) => {
        if (!vivo) return;
        const lista = Array.isArray(corpo?.setores) ? corpo.setores : null;
        setSetores(lista ?? []);
        setFalhaDosSetores(lista === null);
      })
      .catch(() => {
        if (vivo) setFalhaDosSetores(true);
      });
    return () => {
      vivo = false;
    };
  }, [tentativaDosSetores]);

  // Leva o foco ao título da tela nova: quem usa leitor de tela ouve onde está.
  const titulo = useRef<HTMLHeadingElement>(null);
  const primeiraTela = useRef(true);
  useEffect(() => {
    if (primeiraTela.current) {
      primeiraTela.current = false;
      return;
    }
    titulo.current?.focus();
  }, [tela]);

  const podeSeguir = telaCompleta(tela, form, porta);

  async function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (tela !== TOTAL_DE_TELAS || !podeSeguir || enviando || preparando) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await enviar(porta, montarEnvio(form, porta), arquivos);
      if (res.status === 429) {
        setErro(porta === "modulo" ? RECUSA_POR_EXCESSO_DA_PESSOA : RECUSA_POR_EXCESSO_DA_REDE);
        return;
      }
      if (!res.ok) {
        const corpo = await res.json().catch(() => null);
        setErro(typeof corpo?.detail === "string" ? corpo.detail : FALHA_DO_SERVIDOR);
        return;
      }
      setRecibo((await res.json()) as Recibo);
    } catch {
      setErro(FALHA_DA_CONEXAO);
    } finally {
      setEnviando(false);
    }
  }

  if (recibo) {
    const contato = form.anonimo ? "" : porta === "modulo" ? (identificacao?.contato ?? "") : form.contato.trim();
    return <Confirmacao recibo={recibo} contato={contato} />;
  }

  return (
    <form
      aria-label="Notificação de incidente"
      onSubmit={aoEnviar}
      noValidate
      className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-5"
    >
      <div className="space-y-1">
        <p className="text-xs font-semibold text-slate-500">
          Tela {tela} de {TOTAL_DE_TELAS}
        </p>
        <h2 ref={titulo} tabIndex={-1} className="text-lg font-bold text-slate-900 outline-none">
          {TITULOS_DAS_TELAS[tela - 1]}
        </h2>
        <p className="text-sm text-slate-500">{ORIENTACOES[tela - 1]}</p>
      </div>

      {tela === 1 && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="nsp-relato" className={`etiqueta ${ROTULO}`}>
              O que aconteceu
            </label>
            <p id="nsp-aviso-paciente" className="text-sm text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
              {AVISO_DO_PACIENTE}
            </p>
            <textarea
              id="nsp-relato"
              aria-describedby="nsp-aviso-paciente"
              rows={6}
              maxLength={LIMITE_DO_RELATO}
              value={form.relato}
              onChange={(e) => mudar("relato", e.target.value)}
              className={CAMPO}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="nsp-leito" className={`etiqueta ${ROTULO}`}>
              Leito ou atendimento <Opcional />
            </label>
            <input
              id="nsp-leito"
              maxLength={60}
              value={form.leito}
              onChange={(e) => mudar("leito", e.target.value)}
              className={CAMPO}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="nsp-anexos" className={`etiqueta ${ROTULO}`}>
              Fotos ou PDF <Opcional />
            </label>
            <p id="nsp-anexos-ajuda" className="text-sm text-slate-500">
              Até 3 arquivos, somando menos de 9 MB. A foto grande é reduzida antes do envio.
            </p>
            <input
              id="nsp-anexos"
              type="file"
              multiple
              accept={ACEITOS_NO_CAMPO}
              aria-describedby="nsp-anexos-ajuda"
              disabled={preparando}
              onChange={aoEscolherArquivos}
              className={CAMPO}
            />
            {preparando && (
              <p className="flex items-center gap-1.5 text-sm text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                Preparando os arquivos...
              </p>
            )}
            {recusaDosArquivos && (
              <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-lg px-3 py-2">
                {recusaDosArquivos}
              </p>
            )}
            {arquivos.length > 0 && (
              <ul aria-label="Arquivos anexados" className="space-y-1.5">
                {arquivos.map((arquivo, indice) => (
                  <li
                    key={`${arquivo.name}-${indice}`}
                    className="flex items-center gap-2 rounded-xl border border-border px-3 py-1 text-sm text-slate-700"
                  >
                    <Paperclip className="w-4 h-4 shrink-0 text-slate-400" aria-hidden />
                    <span className="flex-1 truncate">
                      {arquivo.name} ({tamanhoLegivel(arquivo.size)})
                    </span>
                    <button
                      type="button"
                      aria-label={`Tirar ${arquivo.name}`}
                      onClick={() => {
                        setRecusaDosArquivos(null);
                        setArquivos((atuais) => atuais.filter((_, i) => i !== indice));
                      }}
                      className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-slate-500 hover:text-red-600"
                    >
                      <X className="w-4 h-4" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {tela === 2 && (
        <div className="space-y-4">
          {falhaDosSetores && (
            <div role="alert" className="space-y-2 rounded-xl bg-red-50 border border-red-200 px-3 py-3">
              <div className="flex gap-2 items-start">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-600" aria-hidden />
                <p className="text-sm text-red-700">{FALHA_DOS_SETORES}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setFalhaDosSetores(false);
                  setTentativaDosSetores((n) => n + 1);
                }}
                className={BOTAO_SECUNDARIO + " w-full"}
              >
                Carregar os setores de novo
              </button>
            </div>
          )}
          <div className="space-y-1.5">
            <label htmlFor="nsp-setor" className={`etiqueta ${ROTULO}`}>
              Setor
            </label>
            <select
              id="nsp-setor"
              value={form.setorId}
              onChange={(e) => mudar("setorId", e.target.value)}
              className={CAMPO}
            >
              <option value="">Escolha o setor</option>
              {setores.map((setor) => (
                <option key={setor.id} value={setor.id}>
                  {setor.nome}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="nsp-data" className={`etiqueta ${ROTULO}`}>
              Data
            </label>
            <input
              id="nsp-data"
              type="date"
              max={hoje()}
              value={form.data}
              onChange={(e) => mudar("data", e.target.value)}
              className={CAMPO}
            />
          </div>
          <Escolhas<Turno>
            id="nsp-turno"
            rotulo="Turno"
            opcoes={TURNOS}
            escolhida={form.turno}
            aoEscolher={(valor) => mudar("turno", valor)}
            colunas="grid-cols-3"
          />
          <div className="space-y-1.5">
            <label htmlFor="nsp-hora" className={`etiqueta ${ROTULO}`}>
              Hora aproximada <Opcional />
            </label>
            <input
              id="nsp-hora"
              type="time"
              value={form.hora}
              onChange={(e) => mudar("hora", e.target.value)}
              className={CAMPO}
            />
          </div>
        </div>
      )}

      {tela === 3 && (
        <div className="space-y-4">
          <Escolhas<ChegouAoPaciente>
            id="nsp-chegou"
            rotulo="O incidente chegou ao paciente?"
            opcoes={CHEGOU_AO_PACIENTE}
            escolhida={form.chegou}
            aoEscolher={(valor) => {
              mudar("chegou", valor);
              if (!perguntaAGravidade(valor)) mudar("grave", null);
            }}
          />
          {perguntaAGravidade(form.chegou) && (
            <Escolhas<"sim" | "nao">
              id="nsp-grave"
              rotulo="Foi grave ou houve morte?"
              opcoes={[
                { valor: "sim", rotulo: "Sim" },
                { valor: "nao", rotulo: "Não" },
              ]}
              escolhida={form.grave === null ? null : form.grave ? "sim" : "nao"}
              aoEscolher={(valor) => mudar("grave", valor === "sim")}
            />
          )}
          <Escolhas<SimNaoNaoSei>
            id="nsp-percebido"
            rotulo={
              <>
                A família ou o paciente percebeu, ou há risco de reclamação? <Opcional />
              </>
            }
            opcoes={PERCEBIDO}
            escolhida={form.percebido}
            aoEscolher={(valor) => mudar("percebido", valor)}
            colunas="grid-cols-3"
          />
        </div>
      )}

      {tela === 4 && (
        <div className="space-y-4">
          <Escolhas<"nome" | "anonimo">
            id="nsp-identificacao"
            rotulo="Como você quer notificar?"
            opcoes={[
              { valor: "nome", rotulo: "Com o meu nome" },
              { valor: "anonimo", rotulo: "Sem me identificar" },
            ]}
            escolhida={form.anonimo ? "anonimo" : "nome"}
            aoEscolher={(valor) => mudar("anonimo", valor === "anonimo")}
          />
          {form.anonimo ? (
            <p className="text-sm text-slate-500">
              Você recebe um código para acompanhar. Ninguém no hospital fica sabendo quem notificou.
            </p>
          ) : (
            <>
              <p className="text-sm text-slate-500">{QUEM_VE_O_NOME}</p>
              {porta === "modulo" ? (
                <p className="text-sm text-slate-700 bg-slate-50 rounded-lg px-3 py-2">
                  Você vai notificar como <strong>{identificacao?.nome ?? "a pessoa desta sessão"}</strong>
                  {identificacao?.contato ? ` (${identificacao.contato})` : ""}.
                </p>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <label htmlFor="nsp-nome" className={`etiqueta ${ROTULO}`}>
                      Nome
                    </label>
                    <input
                      id="nsp-nome"
                      autoComplete="name"
                      maxLength={200}
                      value={form.nome}
                      onChange={(e) => mudar("nome", e.target.value)}
                      className={CAMPO}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="nsp-contato" className={`etiqueta ${ROTULO}`}>
                      E-mail ou telefone
                    </label>
                    <input
                      id="nsp-contato"
                      autoComplete="email"
                      maxLength={200}
                      value={form.contato}
                      onChange={(e) => mudar("contato", e.target.value)}
                      className={CAMPO}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {erro && (
        <div role="alert" className="flex gap-2 items-start rounded-xl bg-red-50 border border-red-200 px-3 py-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-600" aria-hidden />
          <p className="text-sm text-red-700">{erro}</p>
        </div>
      )}

      <div className="flex gap-3">
        {tela > 1 && (
          <button type="button" onClick={() => setTela(tela - 1)} className={BOTAO_SECUNDARIO}>
            <ArrowLeft className="w-4 h-4" />
            Voltar
          </button>
        )}
        {tela < TOTAL_DE_TELAS ? (
          <button type="button" disabled={!podeSeguir} onClick={() => setTela(tela + 1)} className={BOTAO_PRINCIPAL}>
            Continuar
            <ArrowRight className="w-4 h-4" />
          </button>
        ) : (
          <button type="submit" disabled={!podeSeguir || enviando || preparando} className={BOTAO_PRINCIPAL}>
            {enviando ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Registrando...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                Enviar notificação
              </>
            )}
          </button>
        )}
      </div>

      <Rodape />
    </form>
  );
}
