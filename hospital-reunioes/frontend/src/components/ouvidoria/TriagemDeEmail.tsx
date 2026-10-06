"use client";

/**
 * A Triagem de e-mail (issue #648, PRD #646, ADR 0051).
 *
 * Todo e-mail que chega em ouvidoria@ aparece aqui antes de virar caso. A
 * lista mostra o cabeçalho (remetente, assunto, chegada, anexos e as marcas
 * "interno" e "incompleto"); o painel mostra o item aberto, com o corpo em
 * texto e os anexos para baixar. A primeira decisão é virar manifestação
 * (issue #650): abre o modal "Nova manifestação" que já existe, pré-preenchido
 * com o e-mail. A segunda é descartar (issue #649), com a confirmação do app:
 * fica só o cabeçalho e quem descartou. A terceira é juntar a um caso que já
 * existe (issue #651), com o protocolo sugerido pelo assunto.
 * A lista abre nos pendentes; o filtro "Decididos" mostra o resto, só com o
 * cabeçalho.
 *
 * O corpo de um e-mail é texto de qualquer pessoa da internet. Ele entra na
 * página como TEXTO do React, que escapa tudo, e o HTML do e-mail nem chega do
 * servidor: não existe `dangerouslySetInnerHTML` aqui, e não pode existir.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Link2, Loader2, Lock, Mail, Megaphone, Paperclip, Trash2 } from "lucide-react";

import ConfirmDialog from "@/components/ConfirmDialog";
import { JuntarACasoModal } from "@/components/ouvidoria/JuntarACasoModal";
import { NovaManifestacaoModal, type ManifestacaoRegistrada } from "@/components/ouvidoria/NovaManifestacaoModal";
import {
  avisoDosExcedentes,
  formatarChegada,
  marcasDoEmail,
  nomeDoRemetente,
  rotuloDoEstado,
  rotuloDosAnexos,
  type AnexoDoEmail,
  type EmailRecebido,
  type EmailRecebidoResumo,
  type PreCargaDoEmail,
  type ResumoDoCaso,
} from "@/lib/ouvidoria/triagem-email";

const BASE = "/api/ouvidoria/triagem-email";

type Carga = "carregando" | "pronta" | "sem_acesso" | "erro";

type Filtro = "pendentes" | "decididos";

function MarcasDoEmail({ email }: { email: Pick<EmailRecebidoResumo, "interno" | "incompleto"> }) {
  const marcas = marcasDoEmail(email);
  if (marcas.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {marcas.map((marca) => (
        <span
          key={marca}
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide ${
            marca === "Interno" ? "bg-slate-200 text-slate-700" : "bg-amber-100 text-amber-800"
          }`}
        >
          {marca}
        </span>
      ))}
    </span>
  );
}

function formatarTamanho(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function TriagemDeEmail({ token }: { token: string }) {
  const [emails, setEmails] = useState<EmailRecebidoResumo[]>([]);
  const [carga, setCarga] = useState<Carga>("carregando");
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [aberto, setAberto] = useState<EmailRecebido | null>(null);
  const [abrindo, setAbrindo] = useState(false);
  const [erroDoItem, setErroDoItem] = useState<string | null>(null);
  const [abrindoAnexo, setAbrindoAnexo] = useState<string | null>(null);
  const [erroDoAnexo, setErroDoAnexo] = useState<string | null>(null);
  const [preCarga, setPreCarga] = useState<PreCargaDoEmail | null>(null);
  const [carregandoPreCarga, setCarregandoPreCarga] = useState(false);
  const [erroDaDecisao, setErroDaDecisao] = useState<string | null>(null);
  // O caso que nasceu de cada e-mail nesta sessão da tela, para o painel
  // mostrar o protocolo com o caminho do Dossiê.
  const [casosCriados, setCasosCriados] = useState<Record<string, ManifestacaoRegistrada>>({});
  const [filtro, setFiltro] = useState<Filtro>("pendentes");
  const [confirmandoDescarte, setConfirmandoDescarte] = useState(false);
  const [juntando, setJuntando] = useState(false);
  // O caso a que cada e-mail foi juntado nesta sessão da tela, para o painel
  // mostrar o protocolo com o caminho do Dossiê.
  const [casosJuntados, setCasosJuntados] = useState<Record<string, ResumoDoCaso>>({});

  useEffect(() => {
    let cancelado = false;
    (async () => {
      try {
        const res = await fetch(BASE, { headers: { Authorization: `Bearer ${token}` } });
        if (cancelado) return;
        if (res.status === 403) {
          setCarga("sem_acesso");
          return;
        }
        if (!res.ok) {
          setCarga("erro");
          return;
        }
        const corpo = (await res.json()) as { emails: EmailRecebidoResumo[] };
        if (cancelado) return;
        setEmails(corpo.emails ?? []);
        setCarga("pronta");
      } catch {
        if (!cancelado) setCarga("erro");
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [token]);

  async function abrir(id: string) {
    setSelecionado(id);
    setAberto(null);
    setErroDoItem(null);
    setErroDoAnexo(null);
    setErroDaDecisao(null);
    setAbrindo(true);
    try {
      const res = await fetch(`${BASE}/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setAberto((await res.json()) as EmailRecebido);
      else setErroDoItem("Não foi possível abrir este e-mail. Tente novamente.");
    } catch {
      setErroDoItem("Não foi possível abrir este e-mail. Tente novamente.");
    } finally {
      setAbrindo(false);
    }
  }

  /**
   * O binário vive no bucket privado da Ouvidoria: o link é assinado na hora e
   * vale por pouco tempo. A aba abre ANTES do fetch, ainda dentro do clique,
   * senão o bloqueador de pop-up a engole (o mesmo cuidado do Dossiê).
   */
  async function abrirAnexo(emailId: string, anexo: AnexoDoEmail) {
    setAbrindoAnexo(anexo.id);
    setErroDoAnexo(null);
    const aba = window.open("", "_blank");
    if (aba) aba.opener = null;
    try {
      const res = await fetch(`${BASE}/${emailId}/anexos/${anexo.id}/url`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const { url } = (await res.json()) as { url: string };
        if (aba) aba.location.href = url;
        else setErroDoAnexo("Libere os pop-ups deste site para abrir o anexo.");
      } else {
        aba?.close();
        setErroDoAnexo("Não foi possível abrir o anexo. Tente novamente.");
      }
    } catch {
      aba?.close();
      setErroDoAnexo("Não foi possível abrir o anexo. Tente novamente.");
    } finally {
      setAbrindoAnexo(null);
    }
  }

  /** Busca a pré-carga e abre o modal "Nova manifestação" com ela. */
  async function virarManifestacao(emailId: string) {
    setCarregandoPreCarga(true);
    setErroDaDecisao(null);
    try {
      const res = await fetch(`${BASE}/${emailId}/pre-carga`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setPreCarga((await res.json()) as PreCargaDoEmail);
      else
        setErroDaDecisao(
          res.status === 409
            ? "Este e-mail já foi decidido na triagem, talvez em outra aba. Atualize a página."
            : "Não foi possível abrir o registro deste e-mail. Tente novamente."
        );
    } catch {
      setErroDaDecisao("Não foi possível abrir o registro deste e-mail. Tente novamente.");
    } finally {
      setCarregandoPreCarga(false);
    }
  }

  /**
   * Descarta o item já confirmado. Nunca levanta: com erro, o diálogo fecha e
   * o motivo aparece no painel, com o item intacto.
   */
  async function descartar(emailId: string) {
    setErroDaDecisao(null);
    try {
      const res = await fetch(`${BASE}/${emailId}/descarte`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setErroDaDecisao(
          res.status === 409
            ? "Este e-mail já virou manifestação ou foi juntado a um caso, e não pode ser descartado."
            : res.status === 503
              ? "Não foi possível terminar o descarte agora. Tente de novo em instantes."
              : "Não foi possível descartar este e-mail. Tente novamente."
        );
        return;
      }
      const decidido = (await res.json()) as EmailRecebido;
      setAberto((atual) => (atual && atual.id === emailId ? decidido : atual));
      setEmails((atuais) =>
        atuais.map((e) =>
          e.id === emailId
            ? {
                ...e,
                estado: "descartado",
                quantidade_de_anexos: 0,
                incompleto: false,
                decidido_em: decidido.decidido_em,
                decidido_por_nome: decidido.decidido_por_nome,
              }
            : e
        )
      );
    } catch {
      setErroDaDecisao("Não foi possível descartar este e-mail. Tente novamente.");
    }
  }

  /** O e-mail entrou na trilha do caso: o item sai dos pendentes. */
  function aoJuntar(item: EmailRecebido, caso: ResumoDoCaso) {
    setJuntando(false);
    setCasosJuntados((atuais) => ({ ...atuais, [item.id]: caso }));
    setAberto((atual) => (atual && atual.id === item.id ? item : atual));
    setEmails((atuais) =>
      atuais.map((e) =>
        e.id === item.id
          ? {
              ...e,
              estado: "juntado",
              quantidade_de_anexos: 0,
              decidido_em: item.decidido_em,
              decidido_por_nome: item.decidido_por_nome,
            }
          : e
      )
    );
  }

  /** O caso nasceu: o item sai dos pendentes, na lista e no painel. */
  function aoRegistrar(emailId: string, criada: ManifestacaoRegistrada) {
    setCasosCriados((atuais) => ({ ...atuais, [emailId]: criada }));
    setEmails((atuais) => atuais.map((e) => (e.id === emailId ? { ...e, estado: "virou_manifestacao" } : e)));
    setAberto((atual) => (atual && atual.id === emailId ? { ...atual, estado: "virou_manifestacao" } : atual));
  }

  if (carga === "carregando") {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center">
        <Loader2 className="w-4 h-4 animate-spin" />
        Carregando os e-mails recebidos
      </div>
    );
  }

  if (carga === "sem_acesso") {
    return (
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-slate-50 border border-border text-slate-600 text-sm">
        <Lock className="w-4 h-4 shrink-0" />
        A Triagem de e-mail é restrita à Ouvidoria.
      </div>
    );
  }

  if (carga === "erro") {
    return (
      <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
        <AlertCircle className="w-4 h-4 shrink-0" />
        Não foi possível carregar os e-mails recebidos. Atualize a página para tentar de novo.
      </div>
    );
  }

  // Os anexos além do teto de quantidade não viram anexo da lista: vêm só
  // contados, e o aviso diz quantos são e onde está o original.
  const avisoDeExcedentes = aberto ? avisoDosExcedentes(aberto) : null;
  const casoDoAberto = aberto ? casosCriados[aberto.id] : undefined;
  const casoJuntadoDoAberto = aberto ? casosJuntados[aberto.id] : undefined;
  const visiveis = emails.filter((e) => (filtro === "pendentes" ? e.estado === "pendente" : e.estado !== "pendente"));

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section aria-label="E-mails recebidos" className="min-w-0">
        <div className="flex gap-1 mb-3" role="group" aria-label="Filtro da triagem">
          {(
            [
              ["pendentes", "Pendentes"],
              ["decididos", "Decididos"],
            ] as const
          ).map(([valor, rotulo]) => (
            <button
              key={valor}
              type="button"
              aria-pressed={filtro === valor}
              onClick={() => setFiltro(valor)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filtro === valor ? "bg-primary text-white" : "bg-white border border-border text-slate-600 hover:bg-slate-50"
              }`}
            >
              {rotulo}
            </button>
          ))}
        </div>
        {visiveis.length === 0 ? (
          <p className="px-4 py-8 rounded-xl bg-white border border-border text-center text-sm text-slate-500">
            {filtro === "pendentes" ? "Nenhum e-mail recebido para triar." : "Nenhum e-mail decidido ainda."}
          </p>
        ) : (
          <ul className="space-y-2">
            {visiveis.map((email) => (
              <li key={email.id}>
                <button
                  type="button"
                  aria-pressed={selecionado === email.id}
                  onClick={() => abrir(email.id)}
                  className={`w-full text-left px-4 py-3 rounded-xl border transition-colors ${
                    selecionado === email.id
                      ? "border-primary bg-primary/5"
                      : "border-border bg-white hover:bg-slate-50"
                  }`}
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="font-medium text-slate-900 text-sm truncate">{nomeDoRemetente(email)}</span>
                    <span className="text-xs text-slate-500 shrink-0">{formatarChegada(email.recebido_em)}</span>
                  </span>
                  <span className="block text-sm text-slate-700 truncate mt-0.5">
                    {email.assunto || "Sem assunto"}
                  </span>
                  <span className="flex flex-wrap items-center gap-2 mt-1.5">
                    <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                      <Paperclip className="w-3 h-3 shrink-0" />
                      {rotuloDosAnexos(email.quantidade_de_anexos)}
                    </span>
                    <MarcasDoEmail email={email} />
                    {rotuloDoEstado(email.estado) && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700">
                        {rotuloDoEstado(email.estado)}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        aria-label="E-mail recebido"
        className="min-w-0 rounded-xl bg-white border border-border p-4 md:p-5"
      >
        {!selecionado && (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Mail className="w-4 h-4 shrink-0" />
            Escolha um e-mail da lista para ler.
          </p>
        )}
        {selecionado && abrindo && (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Abrindo o e-mail
          </p>
        )}
        {erroDoItem && (
          <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {erroDoItem}
          </p>
        )}
        {aberto && (
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 break-words">
                {aberto.assunto || "Sem assunto"}
              </h2>
              <p className="text-sm text-slate-700 mt-1 break-words">
                {aberto.remetente_nome && <span className="font-medium">{aberto.remetente_nome} </span>}
                <span>{aberto.remetente_endereco}</span>
              </p>
              <p className="text-xs text-slate-500 mt-0.5">Chegou em {formatarChegada(aberto.recebido_em)}</p>
              <div className="mt-2">
                <MarcasDoEmail email={aberto} />
              </div>
            </div>

            {aberto.estado === "pendente" && (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => virarManifestacao(aberto.id)}
                  disabled={carregandoPreCarga}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {carregandoPreCarga ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Megaphone className="w-4 h-4" />
                  )}
                  Virar manifestação
                </button>
                <button
                  type="button"
                  onClick={() => setJuntando(true)}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border border-border text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  <Link2 className="w-4 h-4" />
                  Juntar a um caso
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmandoDescarte(true)}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border border-border text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  Descartar
                </button>
              </div>
            )}
            {aberto.estado === "juntado" && (
              <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
                <Link2 className="w-4 h-4 shrink-0 mt-0.5" />
                {casoJuntadoDoAberto ? (
                  <span>
                    Juntado ao caso{" "}
                    <Link
                      href={`/ouvidoria/m/${casoJuntadoDoAberto.protocolo}`}
                      className="font-mono font-semibold underline"
                    >
                      {casoJuntadoDoAberto.protocolo}
                    </Link>
                    . O texto e os anexos entraram na trilha do caso.
                  </span>
                ) : (
                  <span>
                    Juntado a um caso por {aberto.decidido_por_nome ?? "alguém da Ouvidoria"}
                    {aberto.decidido_em ? ` em ${formatarChegada(aberto.decidido_em)}` : ""}.
                  </span>
                )}
              </p>
            )}
            {aberto.estado === "descartado" && (
              <div className="space-y-2">
                <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-slate-50 border border-border text-slate-700 text-sm">
                  <Trash2 className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>
                    Descartado por {aberto.decidido_por_nome ?? "alguém da Ouvidoria"}
                    {aberto.decidido_em ? ` em ${formatarChegada(aberto.decidido_em)}` : ""}.{" "}
                    {aberto.anexos.length > 0
                      ? "O texto foi apagado, mas algum anexo ainda não saiu do armazenamento."
                      : "O texto e os anexos foram apagados; fica só o cabeçalho."}
                  </span>
                </p>
                {/* O storage recusou algum binário num descarte anterior: o
                    descarte é idempotente, e terminar é descartar de novo. */}
                {aberto.anexos.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setConfirmandoDescarte(true)}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border border-border text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                    Terminar o descarte
                  </button>
                )}
              </div>
            )}
            {erroDaDecisao && (
              <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {erroDaDecisao}
              </p>
            )}
            {casoDoAberto && (
              <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Virou a manifestação{" "}
                  <Link href={`/ouvidoria/m/${casoDoAberto.protocolo}`} className="font-mono font-semibold underline">
                    {casoDoAberto.protocolo}
                  </Link>
                  . Quando o contato salvo tem e-mail, o acuse com o protocolo sai para ele.
                </span>
              </p>
            )}

            {aberto.estado !== "descartado" && (
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Corpo</h3>
                {aberto.corpo_texto ? (
                  // Texto do React: tudo o que o e-mail trouxer sai escapado.
                  <p className="text-sm text-slate-700 whitespace-pre-wrap break-words">{aberto.corpo_texto}</p>
                ) : (
                  <p className="text-sm text-slate-500">O corpo deste e-mail não veio do provedor.</p>
                )}
              </div>
            )}

            {(aberto.anexos.length > 0 || avisoDeExcedentes) && (
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Anexos</h3>
                {erroDoAnexo && (
                  <p className="flex items-start gap-2 mb-1.5 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    {erroDoAnexo}
                  </p>
                )}
                <ul className="space-y-1">
                  {aberto.anexos.map((anexo) => (
                    <li key={anexo.id}>
                      {anexo.disponivel ? (
                        <button
                          type="button"
                          onClick={() => abrirAnexo(aberto.id, anexo)}
                          disabled={abrindoAnexo === anexo.id}
                          className="flex items-center gap-2 w-full text-left text-sm text-slate-700 px-3 py-2 rounded-lg bg-slate-50 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                        >
                          {abrindoAnexo === anexo.id ? (
                            <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-slate-400" />
                          ) : (
                            <Paperclip className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                          )}
                          <span className="truncate flex-1">{anexo.filename}</span>
                          <span className="text-xs text-slate-400 shrink-0">
                            {formatarTamanho(anexo.tamanho_bytes)}
                          </span>
                        </button>
                      ) : (
                        <span className="flex items-center gap-2 text-sm text-slate-500 px-3 py-2 rounded-lg bg-amber-50">
                          <Paperclip className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate flex-1">{anexo.filename}</span>
                          <span className="text-xs shrink-0">
                            {anexo.motivo_indisponivel ?? "não veio do provedor"}
                          </span>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                {avisoDeExcedentes && (
                  <p className="flex items-start gap-2 mt-1 text-sm text-slate-500 px-3 py-2 rounded-lg bg-amber-50">
                    <Paperclip className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span className="min-w-0 break-words">{avisoDeExcedentes}</span>
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* A confirmação é a do app (ConfirmDialog), e não o diálogo nativo do
          navegador: é o padrão da casa para ato que apaga. */}
      <ConfirmDialog
        open={confirmandoDescarte && aberto !== null}
        onClose={() => setConfirmandoDescarte(false)}
        onConfirm={async () => {
          if (aberto) await descartar(aberto.id);
        }}
        title="Descartar este e-mail?"
        description="O texto e os anexos são apagados. Fica só o cabeçalho (remetente, assunto e data) e quem descartou. Use para spam, propaganda e o que não é manifestação."
        confirmLabel="Descartar"
        confirmVariant="danger"
      />

      <JuntarACasoModal
        aberto={juntando && aberto !== null}
        token={token}
        emailId={aberto?.id ?? null}
        onClose={() => setJuntando(false)}
        onJuntado={aoJuntar}
      />

      <NovaManifestacaoModal
        aberto={preCarga !== null}
        token={token}
        preCarga={preCarga}
        onClose={() => setPreCarga(null)}
        onRegistrada={(criada) => {
          if (preCarga) aoRegistrar(preCarga.email_recebido_id, criada);
        }}
      />
    </div>
  );
}
