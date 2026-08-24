"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2, Lock, ShieldAlert, UserRound } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import { LABEL_STATUS } from "@/lib/ouvidoria/fila";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";

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
