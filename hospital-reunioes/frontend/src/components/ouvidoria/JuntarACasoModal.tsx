"use client";

/**
 * Juntar a um caso existente, na Triagem de e-mail (issue #651, ADR 0051,
 * decisão 4).
 *
 * A resposta ao acuse e a segunda mensagem sobre o mesmo protocolo entram na
 * trilha do caso que já existe, como Movimento, sem mudar estado nem prazo. O
 * campo de protocolo abre com a sugestão do servidor (o protocolo citado no
 * assunto ou no começo do corpo), mas a escolha é do ouvidor: antes de
 * confirmar ele vê o resumo do caso (protocolo, estado e setor), e trocar o
 * protocolo pede conferir de novo, para nunca juntar ao caso que não viu.
 */

import { useEffect, useState } from "react";
import { AlertCircle, Link2, Loader2 } from "lucide-react";

import { AdminModal } from "@/components/admin/AdminModal";
import { rotuloDoStatus } from "@/lib/ouvidoria/fila";
import type { EmailRecebido, ResumoDoCaso } from "@/lib/ouvidoria/triagem-email";

const BASE = "/api/ouvidoria/triagem-email";

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";

interface JuntarACasoModalProps {
  aberto: boolean;
  token: string;
  emailId: string | null;
  onClose: () => void;
  onJuntado: (item: EmailRecebido, caso: ResumoDoCaso) => void;
}

export function JuntarACasoModal({ aberto, token, emailId, onClose, onJuntado }: JuntarACasoModalProps) {
  const [protocolo, setProtocolo] = useState("");
  const [resumo, setResumo] = useState<ResumoDoCaso | null>(null);
  const [sugerido, setSugerido] = useState(false);
  const [naoAchou, setNaoAchou] = useState(false);
  const [conferindo, setConferindo] = useState(false);
  const [juntando, setJuntando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Ao abrir, a sugestão do servidor. Sem sugestão, o campo fica vazio.
  useEffect(() => {
    if (!aberto || !emailId) return;
    let cancelado = false;
    setProtocolo("");
    setResumo(null);
    setSugerido(false);
    setNaoAchou(false);
    setErro(null);
    (async () => {
      try {
        const res = await fetch(`${BASE}/${emailId}/caso-para-juntar`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || cancelado) return;
        const { caso } = (await res.json()) as { caso: ResumoDoCaso | null };
        if (cancelado || !caso) return;
        setProtocolo(caso.protocolo);
        setResumo(caso);
        setSugerido(true);
      } catch {
        // Sem sugestão o ouvidor digita o protocolo: nada a dizer aqui.
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [aberto, emailId, token]);

  function trocarProtocolo(valor: string) {
    // O resumo é do protocolo conferido: trocou, confere de novo.
    setProtocolo(valor);
    setResumo(null);
    setSugerido(false);
    setNaoAchou(false);
    setErro(null);
  }

  async function conferir() {
    if (!emailId || protocolo.trim() === "") return;
    setConferindo(true);
    setNaoAchou(false);
    setErro(null);
    try {
      const res = await fetch(
        `${BASE}/${emailId}/caso-para-juntar?protocolo=${encodeURIComponent(protocolo.trim())}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        setErro("Não foi possível procurar o caso agora. Tente de novo em instantes.");
        return;
      }
      const { caso } = (await res.json()) as { caso: ResumoDoCaso | null };
      setResumo(caso);
      setNaoAchou(caso === null);
    } catch {
      setErro("Não foi possível procurar o caso agora. Tente de novo em instantes.");
    } finally {
      setConferindo(false);
    }
  }

  async function juntar() {
    if (!emailId || !resumo || juntando) return;
    setJuntando(true);
    setErro(null);
    try {
      const res = await fetch(`${BASE}/${emailId}/juntada`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ manifestacao_id: resumo.id }),
      });
      if (!res.ok) {
        // A recusa do servidor já vem escrita para o ouvidor (caso apagado,
        // e-mail decidido em outra aba); o resto é "tente de novo".
        const corpo = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        setErro(
          (res.status === 409 || res.status === 404) && typeof corpo?.detail === "string"
            ? corpo.detail
            : "Não foi possível juntar o e-mail agora. Tente de novo em instantes."
        );
        return;
      }
      onJuntado((await res.json()) as EmailRecebido, resumo);
    } catch {
      setErro("Não foi possível juntar o e-mail agora. Tente de novo em instantes.");
    } finally {
      setJuntando(false);
    }
  }

  return (
    <AdminModal
      open={aberto}
      onClose={onClose}
      title="Juntar a um caso"
      description="O texto e os anexos do e-mail entram na trilha do caso, sem mudar o estado nem o prazo."
      icon={<Link2 className="w-5 h-5" />}
      size="md"
      footer={
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide text-slate-600 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={juntar}
            disabled={!resumo || juntando}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {juntando && <Loader2 className="w-4 h-4 animate-spin" />}
            Juntar ao caso
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {erro && (
          <p className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {erro}
          </p>
        )}
        <div>
          <label
            className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1"
            htmlFor="protocolo-do-caso"
          >
            Protocolo do caso
          </label>
          <div className="flex gap-2">
            <input
              id="protocolo-do-caso"
              className={CAMPO}
              value={protocolo}
              onChange={(e) => trocarProtocolo(e.target.value)}
              placeholder="Ex.: 2026-0012"
              inputMode="numeric"
            />
            <button
              type="button"
              onClick={conferir}
              disabled={protocolo.trim() === "" || conferindo}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border border-border text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors"
            >
              {conferindo && <Loader2 className="w-4 h-4 animate-spin" />}
              Conferir
            </button>
          </div>
          {naoAchou && <p className="mt-1.5 text-sm text-amber-700">Nenhum caso com este protocolo.</p>}
        </div>

        {resumo && (
          <section aria-label="Caso escolhido" className="rounded-lg border border-border bg-slate-50 px-4 py-3">
            {sugerido && (
              <p className="text-xs text-slate-500 mb-2">Sugerido pelo assunto ou pelo começo do e-mail.</p>
            )}
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-500">Protocolo</dt>
              <dd className="font-mono font-semibold text-slate-900">{resumo.protocolo}</dd>
              <dt className="text-slate-500">Estado</dt>
              <dd className="text-slate-700">{rotuloDoStatus(resumo.status)}</dd>
              <dt className="text-slate-500">Setor</dt>
              <dd className="text-slate-700">{resumo.setor || "Sem setor"}</dd>
            </dl>
          </section>
        )}
      </div>
    </AdminModal>
  );
}

export default JuntarACasoModal;
