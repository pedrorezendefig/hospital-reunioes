"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, Lock, Mail, Paperclip, RotateCw, ShieldAlert, UserRound } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import { LABEL_STATUS } from "@/lib/ouvidoria/fila";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import {
  LABEL_GATILHO,
  LABEL_GRAVIDADE,
  LABEL_STATUS_NOTIFICACAO,
  type Gravidade,
  type Notificacao,
} from "@/lib/ouvidoria/validacao";

interface Anexo {
  id: string;
  filename: string;
  content_type: string;
  tamanho_bytes: number;
  enviado_por_nome: string;
}

export interface Dossie {
  id: string;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusManifestacao;
  categoria: string;
  setor: string;
  resumo: string;
  relato_integral: string | null;
  manifestante_nome: string | null;
  manifestante_contato: string | null;
  manifestante_vinculo: string | null;
  anonimo: boolean;
  sigilo_reforcado: boolean;
  dados_incompletos: boolean;
  desfecho: string | null;
  desfecho_descricao: string | null;
  gravidade: string | null;
  prazo_area_em: string | null;
  validada_em: string | null;
  respondida_em: string | null;
  resposta_da_area: string | null;
  respondida_por_nome: string | null;
  encerrada_em: string | null;
}

interface DossieModalProps {
  manifestacaoId: string | null;
  token: string | null;
  onClose: () => void;
}

function formatarDataHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * O crédito da resposta da área. Nome e data entram cada um por conta própria:
 * resposta gravada por um responsável já removido do cadastro ainda mostra
 * quando chegou.
 */
function creditoDaResposta(nome: string | null, quando: string | null): string {
  const partes = [nome, quando ? formatarDataHora(quando) : null].filter(Boolean);
  return partes.length ? ` (${partes.join(", ")})` : "";
}

function formatarTamanho(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{rotulo}</dt>
      <dd className="text-sm text-slate-700 mt-0.5">{valor}</dd>
    </div>
  );
}

/**
 * Dossiê completo da manifestação (ADR 0034, decisão 1).
 *
 * Só abre para ouvidor e diretoria executiva: o gate de verdade é o backend,
 * que devolve 403 e registra o acesso no log. A tela apenas não oferece o
 * caminho a quem não pode.
 */
export function DossieModal({ manifestacaoId, token, onClose }: DossieModalProps) {
  const [dossie, setDossie] = useState<Dossie | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [abrindoAnexo, setAbrindoAnexo] = useState<string | null>(null);
  // Erro de anexo é separado do erro de carga: um link que não abriu não pode
  // apagar da tela o relato e a identificação que o ouvidor está lendo.
  const [erroAnexo, setErroAnexo] = useState<string | null>(null);
  // A trilha de cobrança do caso: o que já foi enviado, para quem e quando.
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  const [reenviando, setReenviando] = useState<string | null>(null);
  const [avisoReenvio, setAvisoReenvio] = useState<string | null>(null);

  useEffect(() => {
    if (!manifestacaoId || !token) {
      setAnexos([]);
      setErroAnexo(null);
      return;
    }
    let cancelado = false;
    fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!cancelado && res.ok) setAnexos((await res.json()).anexos);
      })
      .catch(() => {
        if (!cancelado) setAnexos([]);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacaoId, token]);

  const carregarNotificacoes = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/notificacoes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setNotificacoes((await res.json()).notificacoes);
    } catch {
      setNotificacoes([]);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setNotificacoes([]);
    setAvisoReenvio(null);
    carregarNotificacoes();
  }, [carregarNotificacoes]);

  /**
   * Reenvio manual: o ouvidor insiste quando o setor diz que não recebeu. O
   * envio original continua registrado, porque é ele que prova a data em que a
   * cobrança começou.
   */
  async function reenviar(notificacao: Notificacao) {
    if (!manifestacaoId || !token) return;
    setReenviando(notificacao.id);
    setAvisoReenvio(null);
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/notificacoes/${notificacao.id}/reenviar`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const { entregue } = await res.json();
        setAvisoReenvio(
          entregue
            ? `Reenviado para ${notificacao.destinatario_email}.`
            : "O reenvio ficou na fila: o provedor de email recusou agora e o sistema tenta de novo."
        );
        await carregarNotificacoes();
      } else {
        setAvisoReenvio("Não foi possível reenviar agora. Tente novamente.");
      }
    } catch {
      setAvisoReenvio("Não foi possível reenviar agora. Tente novamente.");
    } finally {
      setReenviando(null);
    }
  }

  /**
   * O binário vive em bucket privado: o link é assinado na hora, vale por
   * pouco tempo e por isso não pode ser um href fixo na tela.
   *
   * A aba abre ANTES do fetch, ainda dentro do clique: aberta depois do await
   * ela cai no bloqueador de pop-up do navegador e o anexo não abriria nem
   * daria erro.
   */
  async function abrirAnexo(anexo: Anexo) {
    if (!manifestacaoId || !token) return;
    setAbrindoAnexo(anexo.id);
    setErroAnexo(null);
    // Sem "noopener" na string de features: com ela o navegador devolve null e
    // a gente perderia a aba que acabou de abrir. O isolamento vem do
    // `aba.opener = null` logo abaixo, que faz o mesmo sem custo.
    const aba = window.open("", "_blank");
    if (aba) aba.opener = null;
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos/${anexo.id}/url`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const { url } = await res.json();
        // Sem aba (bloqueador agressivo), o anexo simplesmente nao abre: tirar
        // o ouvidor da tela do Dossie para mostrar um PDF seria pior.
        if (aba) aba.location.href = url;
        else setErroAnexo("Libere os pop-ups deste site para abrir o anexo.");
      } else {
        aba?.close();
        setErroAnexo("Não foi possível abrir o anexo. Tente novamente.");
      }
    } catch {
      aba?.close();
      setErroAnexo("Não foi possível abrir o anexo. Tente novamente.");
    } finally {
      setAbrindoAnexo(null);
    }
  }

  useEffect(() => {
    if (!manifestacaoId || !token) {
      setDossie(null);
      return;
    }
    let cancelado = false;
    setCarregando(true);
    setErro(null);
    fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (cancelado) return;
        if (res.status === 403) {
          setErro("Seu perfil não permite abrir esta manifestação.");
        } else if (res.ok) {
          setDossie(await res.json());
        } else {
          setErro("Não foi possível abrir a manifestação. Tente novamente.");
        }
      })
      .catch(() => {
        if (!cancelado) setErro("Não foi possível abrir a manifestação. Tente novamente.");
      })
      .finally(() => {
        if (!cancelado) setCarregando(false);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacaoId, token]);

  const identificacao = dossie?.anonimo
    ? "Manifestação anônima"
    : dossie?.manifestante_nome || "Não informado";

  return (
    <AdminModal
      open={Boolean(manifestacaoId)}
      onClose={onClose}
      title={dossie ? `Manifestação ${dossie.protocolo}` : "Manifestação"}
      description={dossie ? LABEL_STATUS[dossie.status] : undefined}
      icon={<UserRound className="w-5 h-5" />}
      size="lg"
      scrollable
    >
      {carregando ? (
        <div className="flex items-center justify-center py-12 gap-2 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
          Abrindo a manifestação...
        </div>
      ) : erro ? (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {erro}
        </div>
      ) : dossie ? (
        <div className="space-y-5">
          {dossie.sigilo_reforcado && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
              <Lock className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Sigilo reforçado. O conteúdo desta manifestação é restrito ao Ouvidor e à
                Diretoria Executiva.
              </span>
            </div>
          )}

          {dossie.dados_incompletos && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-sky-50 border border-sky-200 text-sky-800 text-sm">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Cadastro incompleto: o caso chegou resumido e precisa ser completado na
                validação.
              </span>
            </div>
          )}

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Linha rotulo="Quem manifestou" valor={identificacao} />
            <Linha rotulo="Contato" valor={dossie.manifestante_contato || "Não informado"} />
            <Linha rotulo="Vínculo" valor={dossie.manifestante_vinculo || "Não informado"} />
            <Linha rotulo="Setor" valor={dossie.setor} />
            <Linha rotulo="Categoria" valor={dossie.categoria} />
            <Linha
              rotulo="Gravidade"
              valor={
                dossie.gravidade
                  ? LABEL_GRAVIDADE[dossie.gravidade as Gravidade] ?? dossie.gravidade
                  : "Ainda não classificada"
              }
            />
            <Linha
              rotulo="Prazo da área"
              valor={
                dossie.prazo_area_em
                  ? formatarDataHora(dossie.prazo_area_em)
                  : "Definido no acionamento"
              }
            />
            <Linha
              rotulo="Validada em"
              valor={dossie.validada_em ? formatarDataHora(dossie.validada_em) : "Ainda não validada"}
            />
          </dl>

          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Resumo
            </h3>
            <p className="text-sm text-slate-700 whitespace-pre-line">{dossie.resumo}</p>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Relato integral
            </h3>
            <p className="text-sm text-slate-700 whitespace-pre-line">
              {dossie.relato_integral || "O relato integral ainda não foi registrado."}
            </p>
          </div>

          {anexos.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Anexos
              </h3>
              {erroAnexo && (
                <p className="flex items-start gap-2 mb-1.5 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  {erroAnexo}
                </p>
              )}
              <ul className="space-y-1">
                {anexos.map((anexo) => (
                  <li key={anexo.id}>
                    <button
                      onClick={() => abrirAnexo(anexo)}
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
                  </li>
                ))}
              </ul>
            </div>
          )}

          {notificacoes.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Notificações enviadas
              </h3>
              {avisoReenvio && (
                <p className="mb-1.5 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-600 text-xs">
                  {avisoReenvio}
                </p>
              )}
              <ul className="space-y-1">
                {notificacoes.map((n) => (
                  <li
                    key={n.id}
                    className="flex flex-wrap items-center gap-2 text-sm text-slate-700 px-3 py-2 rounded-lg bg-slate-50"
                  >
                    <Mail className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                    <span className="font-medium">{LABEL_GATILHO[n.gatilho] ?? n.gatilho}</span>
                    <span className="text-slate-500 truncate">{n.destinatario_email}</span>
                    <span className="text-xs text-slate-400">
                      {n.enviada_em
                        ? formatarDataHora(n.enviada_em)
                        : LABEL_STATUS_NOTIFICACAO[n.status]}
                    </span>
                    <button
                      onClick={() => reenviar(n)}
                      disabled={reenviando === n.id}
                      className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                    >
                      {reenviando === n.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <RotateCw className="w-3 h-3" />
                      )}
                      Reenviar
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {dossie.resposta_da_area && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Resposta da área
                {creditoDaResposta(dossie.respondida_por_nome, dossie.respondida_em)}
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">{dossie.resposta_da_area}</p>
            </div>
          )}

          {dossie.desfecho && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Desfecho
                {dossie.encerrada_em ? ` (encerrada em ${formatarDataHora(dossie.encerrada_em)})` : ""}
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">
                {dossie.desfecho_descricao || dossie.desfecho}
              </p>
            </div>
          )}
        </div>
      ) : null}
    </AdminModal>
  );
}

export default DossieModal;
