"use client";

/**
 * A Triagem de e-mail (issue #648, PRD #646, ADR 0051).
 *
 * Todo e-mail que chega em ouvidoria@ aparece aqui antes de virar caso. A
 * lista mostra o cabeçalho (remetente, assunto, chegada, anexos e as marcas
 * "interno" e "incompleto"); o painel mostra o item aberto, com o corpo em
 * texto e os anexos para baixar. Nesta fatia o ouvidor só lê: as decisões
 * (descartar, virar manifestação, juntar a um caso) chegam nas seguintes.
 *
 * O corpo de um e-mail é texto de qualquer pessoa da internet. Ele entra na
 * página como TEXTO do React, que escapa tudo, e o HTML do e-mail nem chega do
 * servidor: não existe `dangerouslySetInnerHTML` aqui, e não pode existir.
 */

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Lock, Mail, Paperclip } from "lucide-react";

import {
  formatarChegada,
  marcasDoEmail,
  nomeDoRemetente,
  rotuloDosAnexos,
  type AnexoDoEmail,
  type EmailRecebido,
  type EmailRecebidoResumo,
} from "@/lib/ouvidoria/triagem-email";

const BASE = "/api/ouvidoria/triagem-email";

type Carga = "carregando" | "pronta" | "sem_acesso" | "erro";

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

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section aria-label="E-mails recebidos" className="min-w-0">
        {emails.length === 0 ? (
          <p className="px-4 py-8 rounded-xl bg-white border border-border text-center text-sm text-slate-500">
            Nenhum e-mail recebido para triar.
          </p>
        ) : (
          <ul className="space-y-2">
            {emails.map((email) => (
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

            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Corpo</h3>
              {aberto.corpo_texto ? (
                // Texto do React: tudo o que o e-mail trouxer sai escapado.
                <p className="text-sm text-slate-700 whitespace-pre-wrap break-words">{aberto.corpo_texto}</p>
              ) : (
                <p className="text-sm text-slate-500">O corpo deste e-mail não veio do provedor.</p>
              )}
            </div>

            {aberto.anexos.length > 0 && (
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
                          <span className="text-xs shrink-0">não veio do provedor</span>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
