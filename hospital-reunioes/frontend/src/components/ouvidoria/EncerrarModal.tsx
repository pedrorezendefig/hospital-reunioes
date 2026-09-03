"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Mail } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import {
  DESFECHOS,
  LABEL_DESFECHO,
  descricaoDeDesfechoValida,
  type Desfecho,
} from "@/lib/ouvidoria/validacao";

interface EncerrarModalProps {
  manifestacao: { id: string; protocolo: string } | null;
  token: string | null;
  onClose: () => void;
  onEncerrada: () => void;
}

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

/**
 * Encerrar com desfecho (issue #326, ADR 0034).
 *
 * Fecha o ciclo: o ouvidor confere a resposta da área e encerra com desfecho e
 * descrição obrigatória, gravando o marco T3. Sem descrição o encerramento é
 * bloqueado, aqui e no banco (RPC da migration 064).
 *
 * O campo de descrição MUDOU DE PÚBLICO na issue #494, e a tela precisa dizer
 * isso com todas as letras. Ele sempre foi o texto que o ouvidor escreve para
 * quem manifestou (RN-64: é ele que a trilha copia como "o que foi dito à
 * pessoa"), mas até aqui nunca saía do hospital: ficava no Dossiê e na linha do
 * tempo, lido só por quem tem perfil na Ouvidoria. Desde o aviso de
 * encerramento (RN-80, ADR 0042) ele viaja por EMAIL ao manifestante.
 *
 * A escolha foi ajustar a TELA, e não criar um segundo campo só para o email.
 * Três razões: a RN-64 e o critério de aceite da #494 dizem que o texto enviado
 * é a descrição do desfecho, não um resumo dela; dois campos produziriam duas
 * versões do mesmo desfecho, e no dia em que divergissem a trilha imutável
 * guardaria uma e a pessoa teria recebido a outra; e um campo novo e opcional
 * nasceria vazio na maioria dos casos, devolvendo o paciente ao silêncio que
 * esta fatia existe para acabar.
 *
 * O preço é o bloco de aviso acima do campo, e ele não é decorativo: sem ele o
 * ouvidor escreve achando que é nota interna, e nome de colaborador ou medida
 * disciplinar sai por email assinado pelo domínio do hospital, que é
 * exatamente o que o ADR 0042 proíbe no corpo desses dois emails.
 */
export function EncerrarModal({ manifestacao, token, onClose, onEncerrada }: EncerrarModalProps) {
  const [desfecho, setDesfecho] = useState<Desfecho | "">("");
  const [descricao, setDescricao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!manifestacao) return;
    setDesfecho("");
    setDescricao("");
    setErro(null);
  }, [manifestacao]);

  const pronto = Boolean(desfecho) && descricaoDeDesfechoValida(descricao) && !salvando;

  async function encerrar() {
    if (!manifestacao || !token || !desfecho) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacao.id}/transicoes`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          estado: "encerrado",
          desfecho,
          desfecho_descricao: descricao.trim(),
        }),
      });
      if (res.ok) {
        onEncerrada();
        onClose();
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      setErro(corpo.detail || "Não foi possível encerrar o caso. Tente novamente.");
    } catch {
      setErro("Não foi possível encerrar o caso. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <AdminModal
      open={Boolean(manifestacao)}
      onClose={onClose}
      title={manifestacao ? `Encerrar ${manifestacao.protocolo}` : "Encerrar"}
      description="O caso grava o desfecho, sai da fila de tramitação e o desfecho vai por email a quem manifestou."
      icon={<CheckCircle2 className="w-5 h-5" />}
      size="md"
      scrollable
    >
      <div className="space-y-5">
        <div>
          <span className={ROTULO}>Desfecho</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {DESFECHOS.map((opcao) => (
              <button
                key={opcao}
                type="button"
                onClick={() => setDesfecho(opcao)}
                className={`text-left px-3 py-2.5 rounded-xl border transition-colors ${
                  desfecho === opcao
                    ? "bg-primary/10 border-primary/40 text-primary"
                    : "bg-white border-slate-200 hover:bg-slate-50 text-slate-700"
                }`}
              >
                <span className="block text-sm font-semibold">{LABEL_DESFECHO[opcao]}</span>
              </button>
            ))}
          </div>
          {desfecho === "sem_retorno_do_manifestante" && (
            <p className="mt-2 text-xs text-slate-500 leading-relaxed">
              Este desfecho exige duas tentativas de contato registradas no caso e cinco dias úteis de
              espera desde a primeira. Ele fica fora da conta de resolvido e não resolvido: ninguém apurou.
            </p>
          )}
        </div>

        <div>
          <label className={ROTULO} htmlFor="encerrar-descricao">
            Desfecho para o manifestante <span className="normal-case">(obrigatório)</span>
          </label>
          {/* O aviso vem ANTES do campo, e não abaixo dele: quem já escreveu o
              texto não volta para ler uma nota de rodapé. */}
          <div className="mb-2 flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs leading-relaxed">
            <Mail className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              <strong className="font-semibold">Este texto sai do hospital.</strong> Ele é enviado por
              email a quem abriu a manifestação, junto do protocolo. Escreva para a pessoa, em
              linguagem simples. Não escreva nome de colaborador, medida disciplinar nem detalhe da
              apuração interna: nada disso pode sair daqui. Caso anônimo ou sem email no contato não
              recebe o email, e o texto fica só no registro do caso.
            </span>
          </div>
          <textarea
            id="encerrar-descricao"
            className={`${CAMPO} min-h-[90px]`}
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            placeholder="O que foi apurado e como o caso terminou, dito para quem reclamou. Sem este texto o encerramento não sai."
          />
        </div>

        {erro && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{erro}</span>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide text-slate-600 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={encerrar}
            disabled={!pronto}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {salvando && <Loader2 className="w-4 h-4 animate-spin" />}
            Encerrar caso
          </button>
        </div>
      </div>
    </AdminModal>
  );
}
