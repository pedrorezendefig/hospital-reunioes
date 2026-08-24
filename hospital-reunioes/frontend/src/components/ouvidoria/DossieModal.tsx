"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Lock, Paperclip, ShieldAlert, UserRound } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import { LABEL_STATUS } from "@/lib/ouvidoria/fila";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";

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
}

interface DossieModalProps {
  manifestacaoId: string | null;
  token: string | null;
  onClose: () => void;
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
    const aba = window.open("", "_blank", "noopener,noreferrer");
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos/${anexo.id}/url`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const { url } = await res.json();
        if (aba) aba.location.href = url;
        else window.location.href = url;
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
            <Linha rotulo="Prazo de resposta" valor={dossie.prazo_resposta} />
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

          {dossie.desfecho && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Desfecho
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
